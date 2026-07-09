import json
import logging
import os
import re
import subprocess
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

import spacy
from names_dataset import NameDataset
from google import genai
from google.genai import types
# from openai import OpenAI
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError
import whisper

from app.database import supabase
from app.config import settings

# ---------------------------------------------------------------------------
# Whisper — loaded lazily and reused after the first transcription.
# WHISPER_MODEL env var: "medium" locally, "base" on Railway (512 MB limit).
# ---------------------------------------------------------------------------
_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = whisper.load_model(settings.WHISPER_MODEL)
    return _whisper_model

# ---------------------------------------------------------------------------
# Gemini client
# ---------------------------------------------------------------------------
_gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
_GEMINI_MODEL = "gemini-3.5-flash"


class _GeminiModel:
    """Small adapter exposing generate_content for the configured Gemini model."""

    def generate_content(
        self,
        contents: str,
        config: Optional[types.GenerateContentConfig] = None,
    ):
        return _gemini_client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=contents,
            config=config,
        )


gemini_model = _GeminiModel()

# ---------------------------------------------------------------------------
# OpenAI client (disabled)
# ---------------------------------------------------------------------------
# _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
# _OPENAI_MODEL = "gpt-4o-mini"

# ---------------------------------------------------------------------------
# spaCy — for accurate PERSON entity detection (avoids mis-tagging place names).
# ---------------------------------------------------------------------------
_nlp = spacy.load("en_core_web_sm")
_name_db = NameDataset()

# ---------------------------------------------------------------------------
# Sentence-transformers — 384-dim embeddings match the Supabase schema.
# ---------------------------------------------------------------------------
_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


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
    wav_path: Optional[str] = None
    try:
        wav_path = _convert_to_wav(audio_path)
        result = _get_whisper_model().transcribe(wav_path, task="translate")
        return {"english_text": result["text"].strip()}
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)
        if wav_path and os.path.exists(wav_path):
            os.remove(wav_path)


# ---------------------------------------------------------------------------
# PII anonymization
# ---------------------------------------------------------------------------

# Compiled regex patterns for email, phone, date, and ID replacement.
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

# National/personal ID numbers: 7+ consecutive digits not already part of a
# phone number or date (handled after those are replaced).
_RE_ID = re.compile(r"\b\d{7,}\b")


def _best_rank(data: dict, key: str) -> int:
    """Return the lowest (best) rank for a name under the given key, or 99999 if absent."""
    entry = data.get(key)
    if not entry:
        return 99999
    ranks = [v for v in entry.get("rank", {}).values() if v is not None]
    return min(ranks) if ranks else 99999


def _is_surname(word: str) -> bool:
    """Return True when the word is more likely a surname than a given name.

    Uses the names_dataset rank scores: a lower rank means more common in that role.
    If the word's best rank as a last name is lower than its best rank as a first
    name, it is treated as a surname.  Unknown words (not in the dataset at all)
    default to 'first name' so they are left untouched.

    Examples:
      "John"    → first_best=1,   last_best=7   → False  (keep)
      "Smith"   → first_best=580, last_best=1   → True   (redact)
      "Beridze" → first_best=755, last_best=1   → True   (redact)
    """
    result = _name_db.search(word)
    first_best = _best_rank(result, "first_name")
    last_best = _best_rank(result, "last_name")
    return last_best < first_best


def anonymize_text(text: str) -> str:
    """Remove only strongly identifying PII from dream text before sending to the LLM.

    Rules (no hardcoding):
      - Relationship words (sister, mother, boyfriend, etc.) are kept — spaCy
        does not tag common nouns as PERSON.
      - "John"        (single-word, dataset says first name)  → kept
      - "Smith"       (single-word, dataset says surname)      → [SURNAME]
      - "John Smith"  (multi-word PERSON entity)                  → "John [SURNAME]"
      - Email addresses               → [EMAIL]
      - Phone numbers                 → [PHONE]
      - Specific dates                → [DATE]
      - Personal/national ID numbers  → [ID]
    """
    doc = _nlp(text)
    replacements: list[tuple[int, int, str]] = []

    for ent in doc.ents:
        if ent.label_ != "PERSON":
            continue
        tokens = [t for t in ent]

        if len(tokens) == 1:
            # Single-word entity: redact only if the dataset says it is a surname.
            token = tokens[0]
            if _is_surname(token.text):
                replacements.append((token.idx, token.idx + len(token.text), "[SURNAME]"))
        else:
            # Multi-word entity (e.g. "John Smith"): redact only the last token.
            surname_token = tokens[-1]
            replacements.append(
                (surname_token.idx, surname_token.idx + len(surname_token.text), "[SURNAME]")
            )

    for start, end, placeholder in sorted(replacements, reverse=True):
        text = text[:start] + placeholder + text[end:]

    # Regex-based replacements for the remaining PII types.
    text = _RE_EMAIL.sub("[EMAIL]", text)
    text = _RE_PHONE.sub("[PHONE]", text)
    text = _RE_DATE.sub("[DATE]", text)
    text = _RE_ID.sub("[ID]", text)
    return text


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

def generate_embedding(text: str) -> list[float]:
    """Encode text into a 384-dimensional vector using all-MiniLM-L6-v2.

    The returned list matches the vector(384) column in the Supabase schema.
    """
    return _get_embedder().encode(text).tolist()


def get_rag_context(dream_text: str) -> str:
    """Retrieve the most relevant knowledge_base chunks for a dream.

    Uses the same all-MiniLM-L6-v2 384-dimensional embedding model as
    book ingestion, which keeps pgvector cosine similarity meaningful.
    """
    query_embedding = generate_embedding(dream_text)
    response = (
        supabase.rpc(
            "match_documents",
            {
                "query_embedding": query_embedding,
                "match_threshold": 0.75,
                "match_count": 5,
            },
        )
        .execute()
    )

    matches = response.data or []
    if not matches:
        return "No sufficiently similar academic context was retrieved."

    context_parts: list[str] = []
    for index, match in enumerate(matches, start=1):
        book_title = match.get("book_title") or "Unknown source"
        content = " ".join(str(match.get("content") or "").split())
        similarity = match.get("similarity")

        if similarity is None:
            heading = f"[{index}] Source: {book_title}"
        else:
            heading = (
                f"[{index}] Source: {book_title} "
                f"(similarity: {float(similarity):.3f})"
            )

        context_parts.append(f"{heading}\n{content}")

    return "\n\n".join(context_parts)


def get_user_history(user_id: str, limit: int = 5) -> str:
    """Return a short digest of the user's most recent dream analyses for personalisation.

    Fetches the last `limit` dreams (excluding the one just saved, because this is called
    after the insert but before the final analysis is written back). Returns an empty string
    when the user has no prior history so the caller can skip the personalisation block.
    """
    response = (
        supabase.table("dreams")
        .select("title,analysis,created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = response.data or []
    if not rows:
        return ""

    parts: list[str] = []
    for index, row in enumerate(rows, start=1):
        title = (row.get("title") or "Untitled").strip()
        analysis = (row.get("analysis") or "").strip()
        if not analysis:
            continue
        # Keep only the first ~60 words to stay within prompt budget.
        short = " ".join(analysis.split()[:60])
        parts.append(f"[{index}] {title}: {short}…")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Entity extraction — Gemini JSON mode
# ---------------------------------------------------------------------------

class DreamEntities(BaseModel):
    title: str = Field(description="Short evocative dream title, max 6 words, in the same language as the dream text.")
    symbols: list[str] = Field(description="Key Jungian symbols from the dream.")
    emotions: list[str] = Field(description="Dominant emotions in the dream.")
    summary: str = Field(description="One sentence summary of the dream.")


_ENTITY_JSON_SCHEMA = DreamEntities.model_json_schema()


_EXTRACT_PROMPT = """\
You are a Jungian dream analyst. Analyze the dream below and return ONLY valid JSON — \
no markdown, no backticks, no explanation, no extra text.

Required schema (all fields mandatory):
{{
  "title": "short evocative dream title (max 6 words, written in the SAME language as the Dream text — Georgian if the dream is in Georgian, English if the dream is in English)",
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

_SYMBOL_PATTERNS = (
    (re.compile(r"\b(away|travel\w*|journey|road|world|around the world)\b", re.I), "journey"),
    (re.compile(r"\b(city|town|village|new york|street|building|house|home)\b", re.I), "place"),
    (re.compile(r"\b(people|everyone|crowd|family|friend|stranger|societ\w*)\b", re.I), "community"),
    (re.compile(r"\b(water|sea|ocean|river|lake|rain)\b", re.I), "water"),
    (re.compile(r"\b(fly|flying|sky|air|bird)\b", re.I), "flight"),
    (re.compile(r"\b(dark|night|shadow)\b", re.I), "shadow"),
    (re.compile(r"\b(door|gate|window|threshold)\b", re.I), "threshold"),
)

_EMOTION_PATTERNS = (
    (re.compile(r"\b(sociable|connect\w*|know everyone|together|friend\w*)\b", re.I), "connection"),
    (re.compile(r"\b(want\w*|curious|search\w*|look\w*)\b", re.I), "longing"),
    (re.compile(r"\b(afraid|fear|scared|terrified|anxious|worr\w*)\b", re.I), "fear"),
    (re.compile(r"\b(happy|joy|excited|delight\w*)\b", re.I), "joy"),
    (re.compile(r"\b(sad|grief|cry\w*|lonely|alone)\b", re.I), "sadness"),
    (re.compile(r"\b(angry|rage|furious|annoyed)\b", re.I), "anger"),
    (re.compile(r"\b(calm|peaceful|safe|relieved)\b", re.I), "calm"),
)


def _clean_string_list(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        item = str(item).strip()
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    return cleaned


def _local_entity_fallback(text: str) -> dict:
    """Small deterministic fallback for when LLM output is missing fields."""
    symbols = [
        label
        for pattern, label in _SYMBOL_PATTERNS
        if pattern.search(text)
    ]
    emotions = [
        label
        for pattern, label in _EMOTION_PATTERNS
        if pattern.search(text)
    ]

    if not symbols:
        doc = _nlp(text)
        symbols = [
            chunk.text.strip()
            for chunk in doc.noun_chunks
            if chunk.text.strip()
            and "[PERSON]" not in chunk.text
            and chunk.root.pos_ in {"NOUN", "PROPN"}
        ][:5]

    symbols = _clean_string_list(symbols) or ["dream narrative"]
    emotions = _clean_string_list(emotions) or ["uncertainty"]

    title_words = " ".join(symbols[:2]).title()
    title = title_words if title_words else "Untitled Dream"

    return {
        "title": title,
        "symbols": symbols,
        "emotions": emotions,
        "summary": text[:220].strip(),
    }


def _normalize_entities(data: dict, text: str) -> dict:
    fallback = _local_entity_fallback(text)
    data = {**_SAFE_FALLBACK, **(data or {})}
    data["symbols"] = _clean_string_list(data.get("symbols"))
    data["emotions"] = _clean_string_list(data.get("emotions"))
    data["title"] = str(data.get("title") or "").strip()
    data["summary"] = str(data.get("summary") or "").strip()

    entities = DreamEntities.model_validate(data).model_dump()
    if not entities["symbols"]:
        entities["symbols"] = fallback["symbols"]
    if not entities["emotions"]:
        entities["emotions"] = fallback["emotions"]
    if not entities["title"] or entities["title"] == _SAFE_FALLBACK["title"]:
        entities["title"] = fallback["title"]
    if not entities["summary"]:
        entities["summary"] = fallback["summary"]

    return entities


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=3, max=15))
def _call_gemini(model: str, prompt: str) -> str:
    """Single Gemini API call — retried automatically on transient errors."""
    try:
        response = _gemini_client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=_ENTITY_JSON_SCHEMA,
                temperature=0.2,
            ),
        )
        return response.text.strip()
    except Exception as e:
        logger.warning("_call_gemini [%s] error: %s — %s", model, type(e).__name__, e)
        raise


def _parse_gemini_json(raw: str) -> dict:
    """Try to parse raw Gemini output as JSON, stripping any markdown fences."""
    raw = (raw or "").strip()
    if not raw:
        raise json.JSONDecodeError("Empty Gemini response", raw, 0)
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
      1. Try the configured Gemini model with up to 4 retries.
      2. Normalize missing fields and fill them with local extraction.
      3. If Gemini fails, return the local extraction so arrays are not empty.
    """
    prompt = _EXTRACT_PROMPT.format(text=text)

    for model in (_GEMINI_MODEL,):
        try:
            raw = _call_gemini(model, prompt)
            return _normalize_entities(_parse_gemini_json(raw), text)
        except RetryError as e:
            logger.warning("Gemini model %s exhausted retries: %s", model, e)
            continue
        except json.JSONDecodeError as e:
            logger.warning("Gemini model %s returned unparseable JSON: %s", model, e)
            continue
        except Exception as e:
            logger.warning("Gemini model %s failed unexpectedly: %s", model, e)
            continue

    logger.error("All Gemini models failed — returning local fallback.")
    return _local_entity_fallback(text)


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=3, max=15))
def _call_gemini_analysis(prompt: str) -> str:
    """Call Gemini for warm language-matched analysis text."""
    try:
        response = gemini_model.generate_content(
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.45,
            ),
        )
        return (response.text or "").strip()
    except Exception as e:
        logger.warning(
            "_call_gemini_analysis [%s] error: %s — %s",
            _GEMINI_MODEL,
            type(e).__name__,
            e,
        )
        raise


def generate_analysis(dream_text: str, entities: dict, rag_context: str, user_history: str = "") -> str:
    """Generate a language-matched Jungian dream analysis grounded in RAG context.

    When `user_history` is provided the prompt instructs the model to use it as a
    secondary personalisation layer on top of the RAG foundation — noting recurring
    symbols, emotions, and growth across sessions — without letting personal history
    override the academic psychological grounding.
    """
    symbols = entities.get("symbols", [])
    emotions = entities.get("emotions", [])
    summary = entities.get("summary", "")
    user_history_section = (
        "\nUser's personal dream history (secondary layer, use this to personalise the response;"
        "\nnote recurring symbols, themes, and emotional patterns across sessions; reference growth"
        "\nor continuity when meaningful, but keep the academic RAG above as the primary foundation):"
        f"\n{user_history}\n"
    ) if user_history else ""
    prompt = f"""\
You are a compassionate Jungian dream analyst.

First detect whether the Dream text is written in English or Georgian.
Write the analysis in the exact same language as the Dream text:
- If the Dream text is Georgian, write in Georgian (ქართული).
- If the Dream text is English, write in English.

CRITICAL LANGUAGE RULE:
You must write the entire analysis in Georgian using the INFORMAL singular
address form (შენ-form). Never use the formal plural/polite form (თქვენ-form).

Correct:   შენი სიზმარი, შენ გრძნობ, გაქვს, გიდგას, შეგიძლია
Incorrect: თქვენი სიზმარი, თქვენ გრძნობთ, გაქვთ, გიდგათ, შეგიძლიათ

The tone must feel like a warm, personal conversation, like a trusted friend
who also happens to understand Jungian psychology. Not clinical, not distant,
not formal. Write as if speaking directly to one person you know well.

The analysis must be 150-200 words in either language. Use warm,
non-diagnostic, empathetic language. Never diagnose, never make clinical
claims, and never imply that the dream proves a mental health condition.

Do not use long dashes (---, --, em dash, en dash) or any other special
punctuation characters. Use only standard commas, periods, and question marks.

Reference specific symbols from the dream. Connect those symbols to Jungian
concepts found in the academic context, such as archetype, shadow, anima,
animus, self, individuation, myth, transformation, projection, or the
unconscious, but only when the retrieved context supports the connection.

Dream:
{dream_text}

Extracted entities:
{json.dumps({"symbols": symbols, "emotions": emotions, "summary": summary}, ensure_ascii=False)}

Academic RAG context (primary foundation, always use this as the psychological basis):
{rag_context}
{user_history_section}
Return only the analysis text in the same language as the Dream text. Do not
use markdown.
"""
    try:
        analysis = _call_gemini_analysis(prompt)
    except RetryError as e:
        logger.error("Gemini analysis exhausted retries: %s", e)
        raise

    if not analysis:
        raise ValueError("Gemini returned an empty analysis.")

    return analysis
