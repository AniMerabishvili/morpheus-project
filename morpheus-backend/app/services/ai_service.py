import json
import logging
import os
import re
import subprocess
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

from google import genai
from google.genai import types
# from openai import OpenAI
from pydantic import BaseModel, Field
from supabase import Client
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError

from app.config import settings

# ---------------------------------------------------------------------------
# Local-only heavy imports — skipped entirely in cloud mode to save RAM.
# torch alone is 200-400 MB; omitting it keeps Railway under the free 512 MB limit.
# ---------------------------------------------------------------------------
if settings.USE_LOCAL_MODELS:
    import spacy as _spacy_mod
    import whisper as _whisper_mod
    from sentence_transformers import SentenceTransformer as _SentenceTransformer

try:
    from names_dataset import NameDataset as _NameDataset
except ImportError:  # pragma: no cover - optional fallback for constrained installs
    _NameDataset = None

# ---------------------------------------------------------------------------
# Whisper — loaded lazily. Only used when USE_LOCAL_MODELS=True.
# ---------------------------------------------------------------------------
_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = _whisper_mod.load_model(settings.WHISPER_MODEL)
    return _whisper_model

# ---------------------------------------------------------------------------
# Gemini client
# ---------------------------------------------------------------------------
_gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
_GEMINI_MODEL = "gemini-3.5-flash"
_GEMINI_EMBEDDING_MODEL = settings.GEMINI_EMBEDDING_MODEL


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
# Claude (used for extraction + analysis when AI_PROVIDER=claude / claude_cli)
# ---------------------------------------------------------------------------
_AI_PROVIDER = settings.AI_PROVIDER.strip().lower()
_USE_CLAUDE_CLI = _AI_PROVIDER == "claude_cli"
_USE_CLAUDE = _AI_PROVIDER == "claude" or _USE_CLAUDE_CLI
_claude_client = None
if _AI_PROVIDER == "claude":
    import anthropic

    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("AI_PROVIDER=claude but ANTHROPIC_API_KEY is not set.")
    _claude_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=3)
    logger.info("AI provider: Claude API (%s)", settings.CLAUDE_MODEL)
elif _USE_CLAUDE_CLI:
    logger.info("AI provider: local Claude Code CLI (%s)", settings.CLAUDE_MODEL)

# Strict JSON schema for Claude structured outputs.
_CLAUDE_ENTITY_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "symbols": {"type": "array", "items": {"type": "string"}},
        "emotions": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": ["title", "symbols", "emotions", "summary"],
    "additionalProperties": False,
}


def _resolve_claude_cli() -> str:
    """Find the Claude Code executable (avoids the Windows .cmd shim's quoting issues)."""
    import shutil

    if settings.CLAUDE_CLI_PATH:
        return settings.CLAUDE_CLI_PATH
    found = shutil.which("claude")
    if not found:
        raise RuntimeError("AI_PROVIDER=claude_cli but the `claude` CLI is not on PATH.")
    if found.lower().endswith((".cmd", ".ps1")) or not os.path.splitext(found)[1]:
        native = os.path.join(
            os.path.dirname(found), "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe"
        )
        if os.path.exists(native):
            return native
    return found


def _call_claude_cli(prompt: str, effort: str, json_schema: Optional[dict] = None) -> str:
    """Run one headless Claude Code request using the local CLI login (dev/testing only)."""
    cmd = [
        _resolve_claude_cli(), "-p",
        "--model", settings.CLAUDE_MODEL,
        "--effort", effort,
        "--output-format", "json",
        "--tools", "",
        "--no-session-persistence",
        "--system-prompt", "You are the analysis engine of the Morpheus dream journal. Follow the user prompt exactly.",
    ]
    if json_schema is not None:
        cmd += ["--json-schema", json.dumps(json_schema)]
    proc = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=300,
    )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"Claude CLI failed (exit {proc.returncode}): {(proc.stderr or proc.stdout)[:300]}")
    if data.get("is_error"):
        raise RuntimeError(f"Claude CLI error: {str(data.get('result'))[:300]}")
    if json_schema is not None and data.get("structured_output") is not None:
        return json.dumps(data["structured_output"], ensure_ascii=False)
    return (data.get("result") or "").strip()


def _call_claude(prompt: str, effort: str, json_schema: Optional[dict] = None) -> str:
    """Single Claude request. Returns the concatenated text output."""
    kind = "extraction" if json_schema is not None else "analysis"
    if _USE_CLAUDE_CLI:
        text = _call_claude_cli(prompt, effort, json_schema)
        logger.info("Claude %s done via local CLI (%s)", kind, settings.CLAUDE_MODEL)
        return text
    output_config: dict = {"effort": effort}
    if json_schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": json_schema}
    response = _claude_client.beta.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config=output_config,
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise ValueError("Claude declined the request.")
    logger.info("Claude %s done via API (%s)", kind, response.model)
    return "".join(b.text for b in response.content if b.type == "text").strip()

# ---------------------------------------------------------------------------
# OpenAI client (disabled)
# ---------------------------------------------------------------------------
# _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
# _OPENAI_MODEL = "gpt-4o-mini"

# ---------------------------------------------------------------------------
# spaCy — local only. Loaded at startup when USE_LOCAL_MODELS=True.
# NameDataset stays lazy and lightweight enough to use in cloud mode too.
# ---------------------------------------------------------------------------
_nlp = None
_name_db = None

if settings.USE_LOCAL_MODELS:
    _nlp = _spacy_mod.load("en_core_web_sm")


def _get_name_db():
    global _name_db
    if _name_db is None and _NameDataset is not None:
        _name_db = _NameDataset()
    return _name_db

# ---------------------------------------------------------------------------
# Sentence-transformers — 384-dim embeddings. Lazy, local only.
# In cloud mode, generate_embedding() uses the configured Gemini embedding model.
# ---------------------------------------------------------------------------
_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = _SentenceTransformer("all-MiniLM-L6-v2")
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


def _transcribe_local(audio_path: str) -> dict:
    """Transcribe using local Whisper with ffmpeg pre-processing."""
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


def _transcribe_groq(audio_path: str) -> dict:
    """Transcribe and translate to English using Groq Whisper large-v3.

    Uses the /audio/translations endpoint which always outputs English,
    matching the behaviour of Whisper's task='translate' in local mode.
    Supports Georgian, Russian, and all other Whisper languages.
    File size limit: 25 MB (Groq hard limit).
    """
    try:
        from groq import Groq  # lazy import — not needed in local mode
        client = Groq(api_key=settings.GROQ_API_KEY)
        filename = os.path.basename(audio_path)
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        result = client.audio.translations.create(
            file=(filename, audio_bytes),
            model="whisper-large-v3",
            response_format="text",
        )
        return {"english_text": str(result).strip()}
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


def _transcribe_gemini(audio_path: str) -> dict:
    """Transcribe using Gemini's audio API (fallback when no Groq key)."""
    try:
        ext = os.path.splitext(audio_path)[1].lower()
        mime_map = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".m4a": "audio/mp4",
            ".ogg": "audio/ogg",
            ".webm": "audio/webm",
            ".flac": "audio/flac",
            ".aac": "audio/aac",
        }
        mime_type = mime_map.get(ext, "audio/mpeg")
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        response = _gemini_client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=types.Content(
                parts=[
                    types.Part(inline_data=types.Blob(data=audio_bytes, mime_type=mime_type)),
                    types.Part(text=(
                        "Transcribe this audio. If the audio is not in English "
                        "(for example Georgian, Russian, or any other language), "
                        "translate the transcription to English. "
                        "Return only the plain transcript text — no labels, no explanations, no formatting."
                    )),
                ]
            ),
        )
        return {"english_text": (response.text or "").strip()}
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


def _transcribe_georgian_nemo(audio_path: str) -> dict:
    """Transcribe Georgian audio with transcribe-cpp + georgian-nemo-Q8_0.gguf.

    Returns {"georgian_text": str} — stays in Georgian (NOT translated).
    Requires GEORGIAN_MODEL_PATH to point to the .gguf file.
    """
    import soundfile as sf
    from transcribe_cpp import Model

    wav_path: Optional[str] = None
    try:
        wav_path = _convert_to_wav(audio_path)  # 16 kHz mono WAV
        audio_data, sr = sf.read(wav_path, dtype="float32")
        if sr != 16000:
            raise ValueError(f"Expected 16 kHz after conversion, got {sr}")
        model = Model(settings.GEORGIAN_MODEL_PATH, backend=settings.GEORGIAN_MODEL_BACKEND)
        result = model.session().run(audio_data, language="ka")
        return {"georgian_text": result.text.strip()}
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)
        if wav_path and os.path.exists(wav_path):
            os.remove(wav_path)


def transcribe_audio(audio_path: str) -> dict:
    """Transcribe audio and return English text.

    Routing priority:
      1. USE_LOCAL_MODELS=true  → local Whisper + ffmpeg (dev only, needs ~2 GB RAM)
      2. WHISPER_PROVIDER=groq  → Groq Whisper large-v3 API (recommended for production)
      3. fallback               → Gemini inline audio API

    All paths produce {"english_text": str} with any language translated to English.
    """
    if settings.USE_LOCAL_MODELS:
        return _transcribe_local(audio_path)
    if settings.WHISPER_PROVIDER == "groq" and settings.GROQ_API_KEY:
        return _transcribe_groq(audio_path)
    logger.warning(
        "WHISPER_PROVIDER=groq but GROQ_API_KEY is not set — falling back to Gemini transcription. "
        "Get a free key at console.groq.com"
    )
    return _transcribe_gemini(audio_path)


def _get_audio_mime(audio_path: str) -> str:
    """Best-effort MIME type for inline audio uploads to Gemini."""
    ext = os.path.splitext(audio_path)[1].lower()
    return {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".mp4": "audio/mp4",
        ".ogg": "audio/ogg",
        ".webm": "audio/webm",
        ".flac": "audio/flac",
        ".aac": "audio/aac",
    }.get(ext, "audio/mpeg")


def detect_audio_language(audio_path: str) -> str:
    """Return the ISO 639-1 code of the spoken language (e.g. "ka", "en").

    Does not delete the file. Returns "unknown" when detection fails.
    """
    try:
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        response = _gemini_client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=types.Content(
                parts=[
                    types.Part(inline_data=types.Blob(data=audio_bytes, mime_type=_get_audio_mime(audio_path))),
                    types.Part(text=(
                        "Identify the language spoken in this audio. "
                        "Reply with only its ISO 639-1 code, for example ka or en."
                    )),
                ]
            ),
        )
        code = (response.text or "").strip().lower()
        return code[:2] if re.fullmatch(r"[a-z]{2}\W*", code) else "unknown"
    except Exception as exc:
        logger.warning("detect_audio_language failed: %s", exc)
        return "unknown"


def transcribe_audio_auto(audio_path: str) -> dict:
    """Route audio by spoken language.

    Georgian audio → nemo model (stays Georgian), when GEORGIAN_MODEL_PATH is set.
    Anything else  → transcribe_audio() (translated to English).
    Returns {"text": str, "language": str}. The audio file is deleted afterwards.
    """
    if settings.GEORGIAN_MODEL_PATH and detect_audio_language(audio_path) == "ka":
        result = _transcribe_georgian_nemo(audio_path)
        return {"text": result["georgian_text"], "language": "ka"}
    result = transcribe_audio(audio_path)
    return {"text": result["english_text"], "language": "en"}


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
    name_db = _get_name_db()
    if name_db is None:
        return False

    result = name_db.search(word)
    first_best = _best_rank(result, "first_name")
    last_best = _best_rank(result, "last_name")
    return last_best < first_best


def _is_likely_first_name(word: str) -> bool:
    name_db = _get_name_db()
    if name_db is None:
        return False

    result = name_db.search(word)
    first_best = _best_rank(result, "first_name")
    return first_best < 99999 and first_best <= _best_rank(result, "last_name")


_RE_HONORIFIC_NAME = re.compile(
    r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+[A-Z][a-zA-Z'\-]{1,}\b"
)
_RE_LATIN_FULL_NAME = re.compile(
    r"\b([A-Z][a-zA-Z'\-]{1,})\s+([A-Z][a-zA-Z'\-]{1,})(?:\s+[A-Z][a-zA-Z'\-]{1,})?\b"
)


def _redact_obvious_person_names(text: str) -> str:
    """Redact obvious Latin-script personal names without sending text to a model."""

    text = _RE_HONORIFIC_NAME.sub("[PERSON]", text)

    def replace_full_name(match: re.Match) -> str:
        first = match.group(1)
        last = match.group(2)
        if _is_likely_first_name(first) and _is_surname(last):
            return f"{first} [SURNAME]"
        return match.group(0)

    return _RE_LATIN_FULL_NAME.sub(replace_full_name, text)


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
    if settings.USE_LOCAL_MODELS and _nlp is not None:
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

    # Runs in both cloud and local modes before third-party AI calls.
    text = _redact_obvious_person_names(text)

    # Regex-based replacements always run regardless of mode.
    text = _RE_EMAIL.sub("[EMAIL]", text)
    text = _RE_PHONE.sub("[PHONE]", text)
    text = _RE_DATE.sub("[DATE]", text)
    text = _RE_ID.sub("[ID]", text)
    return text


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

def generate_embedding(text: str) -> list[float]:
    """Encode text into a 384-dimensional all-MiniLM-L6-v2 vector.

    Same model locally and on Render (fastembed/ONNX, no API calls), matching the
    model the book library was embedded with, so similarity scores are meaningful.
    """
    from app.services.embeddings import embed_text

    return embed_text(text)


def _rag_query_text(dream_text: str, entities: Optional[dict]) -> str:
    """Text to embed for retrieval. MiniLM is English-only, so Georgian dreams are
    searched with their English symbols/emotions; English dreams get them appended."""
    extras = []
    if entities:
        if entities.get("symbols"):
            extras.append("Symbols: " + ", ".join(entities["symbols"]))
        if entities.get("emotions"):
            extras.append("Emotions: " + ", ".join(entities["emotions"]))
    is_georgian = bool(re.search(r"[\u10A0-\u10FF]", dream_text))
    if is_georgian and extras:
        return ". ".join(extras)
    return "\n".join([dream_text, *extras])


def _round_robin(rows: list[dict], books: list[str], limit: int) -> list[dict]:
    """Spread picks across the chosen books, best passages first within each book."""
    per_book: dict[str, list[dict]] = {}
    for row in rows:  # rows arrive sorted by similarity
        per_book.setdefault(row.get("book_title"), []).append(row)
    picked: list[dict] = []
    while len(picked) < limit and any(per_book.get(b) for b in books):
        for title in books:
            if per_book.get(title) and len(picked) < limit:
                picked.append(per_book[title].pop(0))
    return picked


def retrieve_passages(
    db: Client,
    dream_text: str,
    entities: Optional[dict] = None,
    books: Optional[list[str]] = None,
) -> list[dict]:
    """Library passages at least RAG_MIN_SIMILARITY similar to the dream.

    Returns [] when nothing in the library (or in the chosen books) is close enough.
    """
    threshold = settings.RAG_MIN_SIMILARITY
    limit = settings.RAG_MAX_PASSAGES
    query_embedding = generate_embedding(_rag_query_text(dream_text, entities))

    if not books:
        return (
            db.rpc(
                "match_documents",
                {"query_embedding": query_embedding, "match_threshold": threshold, "match_count": limit},
            )
            .execute()
            .data
            or []
        )

    try:
        rows = (
            db.rpc(
                "match_documents_in_books",
                {
                    "query_embedding": query_embedding,
                    "match_threshold": threshold,
                    "match_count": 60,
                    "book_titles": books,
                },
            )
            .execute()
            .data
            or []
        )
    except Exception as exc:
        # Migration not applied yet: fetch from the unfiltered function and filter here.
        logger.warning("match_documents_in_books unavailable (%s); filtering in Python.", exc)
        rows = (
            db.rpc(
                "match_documents",
                {"query_embedding": query_embedding, "match_threshold": threshold, "match_count": 1000},
            )
            .execute()
            .data
            or []
        )
        rows = [r for r in rows if r.get("book_title") in books]
    return _round_robin(rows, books, limit)


def format_passages(passages: list[dict]) -> str:
    from app.services.library import book_label

    parts: list[str] = []
    for index, match in enumerate(passages, start=1):
        source = book_label(match["book_title"]) if match.get("book_title") else "Unknown source"
        content = " ".join(str(match.get("content") or "").split())
        parts.append(f"[{index}] Source: {source}\n{content}")
    return "\n\n".join(parts)


def passage_sources(passages: list[dict]) -> list[str]:
    """Distinct book labels used, in order of first appearance."""
    from app.services.library import book_label

    seen: list[str] = []
    for match in passages:
        label = book_label(match["book_title"]) if match.get("book_title") else None
        if label and label not in seen:
            seen.append(label)
    return seen


def no_match_message(dream_text: str, books_chosen: bool) -> str:
    """Honest reply when no passage clears the similarity threshold. No LLM call,
    so nothing is interpreted without a source."""
    if re.search(r"[\u10A0-\u10FF]", dream_text):
        scope = "შენ მიერ არჩეულ წიგნებში" if books_chosen else "Morpheus-ის ბიბლიოთეკაში"
        return (
            f"{scope} ვერ ვიპოვე ფრაგმენტი, რომელიც საკმარისად ახლოსაა შენს სიზმართან, "
            "ამიტომ ინტერპრეტაციას არ გთავაზობ, რომ წყაროს გარეშე არაფერი მოვიგონო. "
            "სიზმარი შენახულია. სცადე მეტი დეტალის დამატება ან სხვა წიგნების არჩევა."
        )
    scope = "the books you chose" if books_chosen else "the Morpheus library"
    return (
        f"I could not find a passage in {scope} that is close enough to this dream, "
        "so I am not offering an interpretation rather than inventing one without a source. "
        "Your dream is saved. Try adding more detail, or choose different books."
    )


def get_user_history(db: Client, user_id: str, limit: int = 5) -> str:
    """Return a short digest of the user's most recent dream analyses for personalisation.

    Fetches the last `limit` dreams (excluding the one just saved, because this is called
    after the insert but before the final analysis is written back). Returns an empty string
    when the user has no prior history so the caller can skip the personalisation block.
    """
    response = (
        db.table("dreams")
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
    symbols: list[str] = Field(description="Key Jungian symbols from the dream, translated to English.")
    emotions: list[str] = Field(description="Dominant emotions in the dream, translated to English.")
    summary: str = Field(description="One sentence summary of the dream.")


_ENTITY_JSON_SCHEMA = DreamEntities.model_json_schema()


_EXTRACT_PROMPT = """\
You are a Jungian dream analyst. Analyze the dream below and return ONLY valid JSON — \
no markdown, no backticks, no explanation, no extra text.

Required schema (all fields mandatory):
{{
  "title": "short evocative dream title (max 6 words, written in the SAME language as the Dream text — Georgian if the dream is in Georgian, English if the dream is in English)",
  "symbols": ["list", "of", "key", "symbols", "always", "in", "English"],
  "emotions": ["list", "of", "dominant", "emotions", "always", "in", "English"],
  "summary": "one sentence summary of the dream"
}}

Rules:
- Always return symbols and emotions in English, even when the Dream is written in Georgian or another language.
- Use short lowercase noun phrases for symbols, e.g. "full moon", "twin sister", "black dog".
- Do not mix languages inside the symbols or emotions arrays.

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

    if not symbols and settings.USE_LOCAL_MODELS and _nlp is not None:
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

    if _USE_CLAUDE:
        try:
            raw = _call_claude(prompt, effort="low", json_schema=_CLAUDE_ENTITY_SCHEMA)
            return _normalize_entities(_parse_gemini_json(raw), text)
        except Exception as e:
            logger.error("Claude extraction failed (%s: %s) — returning local fallback.", type(e).__name__, e)
            return _local_entity_fallback(text)

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


def _books_section(book_labels: Optional[list[str]]) -> str:
    """Prompt block for when the dreamer chose specific books from the Morpheus library."""
    if not book_labels:
        return ""
    listed = "\n".join(f"- {label}" for label in book_labels)
    return f"""
The dreamer chose to have this dream read through these books from the Morpheus library:
{listed}
The library passages above were retrieved only from these books. Name the books (and
their authors) you draw on. Never invent quotes or attribute ideas a book does not
contain. If a chosen book has no passage that fits this dream, rely on the others.
"""


def generate_analysis(
    dream_text: str,
    entities: dict,
    rag_context: str,
    user_history: str = "",
    book_labels: Optional[list[str]] = None,
) -> str:
    """Generate a language-matched dream analysis grounded only in library passages.

    `rag_context` holds the retrieved passages (the only allowed sources).
    `user_history` may only be used to notice recurring symbols or feelings.
    """
    symbols = entities.get("symbols", [])
    emotions = entities.get("emotions", [])
    summary = entities.get("summary", "")
    user_history_section = (
        "\nUser's personal dream history (only for noticing recurring symbols or feelings, "
        "not as a source of meaning):"
        f"\n{user_history}\n"
    ) if user_history else ""
    prompt = f"""\
You are the dream analyst of Morpheus. Your ONLY sources of interpretation are the
passages from the Morpheus library given below under "Library passages".

GROUNDING RULES (most important):
- Every interpretive idea must come from the library passages. Name the book you
  draw on (for example "In Man and His Symbols, Jung..."), but do not mention
  passage numbers like [1].
- Do not use outside knowledge, other authors, popular dream dictionaries, or ideas
  the passages do not contain. Do not invent quotes.
- If the passages fit only part of the dream, interpret only that part and say
  plainly that the library does not speak to the rest. Saying less is better than
  adding unsupported meaning.
- The personal dream history (if present) may only be used to notice recurring
  symbols or feelings, never as a source of meaning.

First detect whether the Dream text is written in English or Georgian.
Write the analysis in the exact same language as the Dream text:
- If the Dream text is Georgian, write in Georgian (ქართული).
- If the Dream text is English, write in English.

CRITICAL LANGUAGE RULE:
You must write the entire analysis in Georgian using the INFORMAL singular
address form (შენ-form). Never use the formal plural/polite form (თქვენ-form).

Correct:   შენი სიზმარი, შენ გრძნობ, გაქვს, გიდგას, შეგიძლია
Incorrect: თქვენი სიზმარი, თქვენ გრძნობთ, გაქვთ, გიდგათ, შეგიძლიათ

The tone must feel like a warm, personal conversation with one person you know
well. Not clinical, not distant, not formal.

The analysis must be 120-200 words in either language (shorter is fine when the
passages support less). Use warm, non-diagnostic, empathetic language. Never
diagnose, never make clinical claims, and never imply that the dream proves a
mental health condition.

Do not use long dashes (---, --, em dash, en dash) or any other special
punctuation characters. Use only standard commas, periods, and question marks.

Dream:
{dream_text}

Extracted entities:
{json.dumps({"symbols": symbols, "emotions": emotions, "summary": summary}, ensure_ascii=False)}

Library passages (the only allowed sources):
{rag_context}
{user_history_section}{_books_section(book_labels)}
Return only the analysis text in the same language as the Dream text. Do not
use markdown.
"""
    if _USE_CLAUDE:
        analysis = _call_claude(prompt, effort="medium")
        if not analysis:
            raise ValueError("Claude returned an empty analysis.")
        return analysis

    try:
        analysis = _call_gemini_analysis(prompt)
    except RetryError as e:
        logger.error("Gemini analysis exhausted retries: %s", e)
        raise

    if not analysis:
        raise ValueError("Gemini returned an empty analysis.")

    return analysis
