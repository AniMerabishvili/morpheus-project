import json
import logging
import os
import re
import subprocess
import tempfile

logger = logging.getLogger(__name__)

import spacy
from google import genai
# from openai import OpenAI
from sentence_transformers import SentenceTransformer
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError
import whisper

from app.config import settings

# ---------------------------------------------------------------------------
# Whisper — loaded once at module import to avoid per-request overhead.
# WHISPER_MODEL env var: "medium" locally, "base" on Railway (512 MB limit).
# ---------------------------------------------------------------------------
_whisper_model = whisper.load_model(settings.WHISPER_MODEL)

# ---------------------------------------------------------------------------
# Gemini client
# ---------------------------------------------------------------------------
_gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
_GEMINI_MODEL = "gemini-3.5-flash"

# ---------------------------------------------------------------------------
# OpenAI client (disabled)
# ---------------------------------------------------------------------------
# _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
# _OPENAI_MODEL = "gpt-4o-mini"

# ---------------------------------------------------------------------------
# spaCy — for accurate PERSON entity detection (avoids mis-tagging place names).
# ---------------------------------------------------------------------------
_nlp = spacy.load("en_core_web_sm")

# ---------------------------------------------------------------------------
# Sentence-transformers — 384-dim embeddings matching the Supabase schema.
# ---------------------------------------------------------------------------
_embedder = SentenceTransformer("all-MiniLM-L6-v2")


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _convert_to_wav(input_path: str) -> str:
    """Convert any audio format to 16 kHz mono WAV for Whisper.

    Returns path to a new temp WAV file — caller is responsible for deletion.
    """
    wav_fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(wav_fd)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", input_path,
            "-ar", "16000",       # 16 kHz sample rate
            "-ac", "1",           # mono
            "-c:a", "pcm_s16le",  # raw 16-bit PCM
            wav_path,
        ],
        check=True,
        capture_output=True,
    )
    return wav_path


def transcribe_audio(audio_path: str) -> dict:
    """Transcribe audio and return English text.

    Uses task="translate" so any language (Georgian, English, etc.) is
    automatically detected and translated to English. No language= lock,
    so Whisper auto-detects the source language.

    Cleans up both the original upload and the temp WAV before returning.
    Returns:
        {"english_text": str}
    """
    wav_path: str | None = None
    try:
        wav_path = _convert_to_wav(audio_path)
        result = _whisper_model.transcribe(wav_path, task="translate")
        return {"english_text": result["text"].strip()}
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)
        if wav_path and os.path.exists(wav_path):
            os.remove(wav_path)


# ---------------------------------------------------------------------------
# PII anonymization
# ---------------------------------------------------------------------------

# Compiled regex patterns for email, phone, and date replacement.
_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

_RE_PHONE = re.compile(r"\b\+?[\d][\d\s\-().]{6,}[\d]\b")

_MONTHS = (
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
)
_RE_DATE = re.compile(
    rf"\b(?:"
    rf"\d{{1,2}}[/\-\.]\d{{1,2}}[/\-\.]\d{{2,4}}"      # 12/31/2024
    rf"|\d{{4}}[/\-\.]\d{{1,2}}[/\-\.]\d{{1,2}}"        # 2024-12-31
    rf"|{_MONTHS}\s+\d{{1,2}},?\s+\d{{4}}"              # January 1, 2024
    rf"|\d{{1,2}}\s+{_MONTHS}\s+\d{{4}}"                # 1 January 2024
    rf")\b",
    re.IGNORECASE,
)


def anonymize_text(text: str) -> str:
    """Remove PII from transcribed dream text before sending to the LLM.

    Uses spaCy NER to replace only genuine PERSON entities — place names,
    organisations, and other capitalised words are left untouched.

    Replacements:
      - Person names (spaCy PERSON)  → [PERSON]
      - Email addresses               → [EMAIL]
      - Phone numbers                 → [PHONE]
      - Specific dates                → [DATE]
    """
    # spaCy PERSON replacement — iterate in reverse to preserve char offsets.
    doc = _nlp(text)
    person_spans = [
        (ent.start_char, ent.end_char)
        for ent in doc.ents
        if ent.label_ == "PERSON"
    ]
    for start, end in sorted(person_spans, reverse=True):
        text = text[:start] + "[PERSON]" + text[end:]

    # Regex-based replacements for the remaining PII types.
    text = _RE_EMAIL.sub("[EMAIL]", text)
    text = _RE_PHONE.sub("[PHONE]", text)
    text = _RE_DATE.sub("[DATE]", text)
    return text


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

def generate_embedding(text: str) -> list[float]:
    """Encode text into a 384-dimensional vector using all-MiniLM-L6-v2.

    The returned list matches the vector(384) column in the Supabase schema.
    """
    return _embedder.encode(text).tolist()


# ---------------------------------------------------------------------------
# Entity extraction — OLD: Gemini / NEW: OpenAI
# ---------------------------------------------------------------------------

_EXTRACT_PROMPT = """\
You are a Jungian dream analyst. Analyze the dream below and return ONLY valid JSON — \
no markdown, no backticks, no explanation, no extra text.

Required schema (all fields mandatory):
{{
  "title": "short evocative dream title (max 6 words)",
  "symbols": ["list", "of", "key", "symbols"],
  "emotions": ["list", "of", "dominant", "emotions"],
  "summary": "one sentence summary of the dream"
}}

Dream:
{text}"""


_SAFE_FALLBACK = {
    "title": "Untitled Dream",
    "symbols": [],
    "emotions": [],
    "summary": "",
}


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=3, max=15))
def _call_gemini(model: str, prompt: str) -> str:
    """Single Gemini API call — retried automatically on transient errors."""
    try:
        response = _gemini_client.models.generate_content(
            model=model,
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        logger.warning("_call_gemini [%s] error: %s — %s", model, type(e).__name__, e)
        raise


def _parse_gemini_json(raw: str) -> dict:
    """Try to parse raw Gemini output as JSON, stripping any markdown fences."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    return json.loads(cleaned)


# OpenAI version (disabled)
# @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=3, max=15))
# def _call_openai(prompt: str) -> str:
#     response = _openai_client.chat.completions.create(
#         model=_OPENAI_MODEL,
#         messages=[{"role": "user", "content": prompt}],
#         response_format={"type": "json_object"},
#     )
#     return response.choices[0].message.content.strip()


def extract_entities(text: str) -> dict:
    """Call Gemini to extract Jungian symbols, emotions, title, and summary.

    Strategy:
      1. Try primary model (gemini-3.5-flash) with up to 4 retries.
      2. If all fail, return a safe default so the dream is still saved to DB.
    """
    prompt = _EXTRACT_PROMPT.format(text=text)

    for model in (_GEMINI_MODEL,):
        try:
            raw = _call_gemini(model, prompt)
            return _parse_gemini_json(raw)
        except RetryError as e:
            logger.warning("Gemini model %s exhausted retries: %s", model, e)
            continue
        except json.JSONDecodeError as e:
            logger.warning("Gemini model %s returned unparseable JSON: %s", model, e)
            continue
        except Exception as e:
            logger.warning("Gemini model %s failed unexpectedly: %s", model, e)
            continue

    logger.error("All Gemini models failed — returning safe fallback.")
    return _SAFE_FALLBACK
