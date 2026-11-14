import json
import logging
import os
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field
from supabase import Client

from app.auth import get_current_user
from app.config import settings
from app.crypto import decrypt_dream_row, encrypt_field
from app.database import supabase_admin_only
from app.security import client_safe_error, enforce_processing_rate_limit
from app.services.library import book_label, clean_book_ids
from app.services.ai_service import (
    anonymize_text,
    extract_entities,
    generate_analysis,
    generate_embedding,
    format_passages,
    no_match_message,
    passage_sources,
    retrieve_passages,
    get_user_history,
    transcribe_audio,
    transcribe_audio_auto,
)

router = APIRouter(prefix="/dreams", tags=["dreams"])
logger = logging.getLogger(__name__)


def parse_book_ids(raw) -> list[str]:
    """Accept a JSON list (or comma list) of library book ids and keep only real ones."""
    if isinstance(raw, str):
        raw = raw.strip()
        try:
            raw = json.loads(raw) if raw.startswith("[") else [p.strip() for p in raw.split(",")]
        except json.JSONDecodeError:
            raw = []
    return clean_book_ids(raw)


class TextDreamRequest(BaseModel):
    dream_text: str = Field(min_length=1, max_length=settings.MAX_DREAM_TEXT_CHARS)
    books: list[str] = Field(default_factory=list, max_length=100)


@router.get("")
def list_dreams(current_user=Depends(get_current_user)) -> list[dict]:
    """Return saved dreams for the dreams list view."""
    response = (
        current_user.supabase.table("dreams")
        .select("id,title,raw_text,analysis,emotions,created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return [decrypt_dream_row(row) for row in (response.data or [])]


@router.get("/{dream_id}")
def get_dream(dream_id: str, current_user=Depends(get_current_user)) -> dict:
    """Return a single dream only if it belongs to the authenticated user."""
    response = (
        current_user.supabase.table("dreams")
        .select("id,title,raw_text,analysis,emotions,created_at,user_id")
        .eq("id", dream_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Dream not found.")
    return decrypt_dream_row(rows[0])


@router.delete("/{dream_id}")
def delete_dream(dream_id: str, current_user=Depends(get_current_user)) -> dict:
    """Delete a dream for the authenticated user.

    The `dream_keywords` rows are removed by the database foreign key cascade.
    This endpoint intentionally leaves the shared `keywords` table untouched.
    """
    response = (
        current_user.supabase.table("dreams")
        .select("id")
        .eq("id", dream_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Dream not found.")

    try:
        (
            current_user.supabase.table("dreams")
            .delete()
            .eq("id", dream_id)
            .execute()
        )
    except APIError as exc:
        error = getattr(exc, "args", [{}])[0]
        if isinstance(error, dict) and error.get("code") == "42501":
            raise client_safe_error("Unable to delete dream.") from exc
        raise

    return {"message": "Dream deleted successfully."}


def _admin_only_get_or_create_keyword_id(symbol: str) -> str:
    """Resolve the shared keyword dictionary with service-role privileges.

    `keywords` is global deduplicated taxonomy data, not a user-owned table.
    Keep this admin path tiny and never return arbitrary keyword lists through it.
    """
    existing = (
        supabase_admin_only.table("keywords")
        .select("id")
        .eq("name", symbol)
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    try:
        created = (
            supabase_admin_only.table("keywords")
            .insert({"name": symbol})
            .execute()
        )
        if created.data:
            return created.data[0]["id"]
    except APIError as exc:
        error = getattr(exc, "args", [{}])[0]
        if not isinstance(error, dict) or error.get("code") != "23505":
            raise

    retry_existing = (
        supabase_admin_only.table("keywords")
        .select("id")
        .eq("name", symbol)
        .limit(1)
        .execute()
    )
    if retry_existing.data:
        return retry_existing.data[0]["id"]

    raise RuntimeError("Keyword could not be resolved.")


def save_dream(
    db: Client,
    processed_text: str,
    entities: dict,
    user_id: str,
) -> str:
    """Persist a processed dream to Supabase and return its UUID.

    Steps:
      1. Generate 384-dim embedding from the anonymized dream text.
      2. Insert a row into `dreams` — returns the new UUID.
      3. For each symbol: upsert into `keywords`, then link via `dream_keywords`.
    """
    embedding = generate_embedding(processed_text)

    # 1. Insert the dream row — sensitive text fields are encrypted at rest.
    dream_row = (
        db.table("dreams")
        .insert(
            {
                "user_id": user_id,
                "title": encrypt_field(entities.get("title", "Untitled Dream")),
                "raw_text": encrypt_field(processed_text),
                "analysis": encrypt_field(entities.get("summary", "")),
                "embedding": embedding,
                "emotions": entities.get("emotions", []),
            }
        )
        .execute()
    )
    dream_id: str = dream_row.data[0]["id"]

    # 2. Upsert each symbol into `keywords` and link to the dream.
    for symbol in entities.get("symbols", []):
        symbol = symbol.strip()
        if not symbol:
            continue

        keyword_id = _admin_only_get_or_create_keyword_id(symbol)

        db.table("dream_keywords").upsert(
            {"dream_id": dream_id, "keyword_id": keyword_id},
            on_conflict="dream_id,keyword_id",
        ).execute()

    return dream_id


def update_dream_analysis(db: Client, dream_id: str, analysis: str) -> None:
    """Persist the generated analysis on the saved dream row (encrypted)."""
    (
        db.table("dreams")
        .update({"analysis": encrypt_field(analysis)})
        .eq("id", dream_id)
        .execute()
    )


def process_text_pipeline(dream_text: str, current_user, books: Optional[list[str]] = None) -> dict:
    """Run the shared non-audio dream pipeline for English or Georgian text."""
    if not dream_text.strip():
        raise HTTPException(status_code=400, detail="dream_text cannot be empty.")

    # 1. Anonymize PII before sending to the external LLM
    anonymized_text = anonymize_text(dream_text.strip())

    # 2. Extract Jungian entities via Gemini
    entities = extract_entities(anonymized_text)

    # 3. Embed + save to Supabase
    dream_id = save_dream(current_user.supabase, anonymized_text, entities, current_user.id)

    # 3b. Fetch user's prior dream history for personalised analysis
    user_history = get_user_history(current_user.supabase, current_user.id)

    # 4. Retrieve RAG context and generate language-matched analysis
    books = books or []
    book_labels = [book_label(b) for b in books]
    passages = retrieve_passages(current_user.supabase, anonymized_text, entities, books)
    if passages:
        analysis = generate_analysis(
            anonymized_text, entities, format_passages(passages), user_history, book_labels
        )
    else:
        # Nothing in the library clears the similarity threshold: don't interpret without a source.
        analysis = no_match_message(anonymized_text, books_chosen=bool(books))
    sources = passage_sources(passages)

    # 5. Update saved dream with final analysis
    update_dream_analysis(current_user.supabase, dream_id, analysis)

    return {
        "dream_id": dream_id,
        "title": entities.get("title", ""),
        "transcription": anonymized_text,
        "symbols": entities.get("symbols", []),
        "emotions": entities.get("emotions", []),
        "analysis": analysis,
        "books": book_labels,
        "sources": sources,
        "grounded": bool(passages),
        "status": "completed",
    }


@router.post("/process")
async def process_dream(
    audio: UploadFile = File(...),
    books: str = Form(""),
    current_user=Depends(get_current_user),
) -> JSONResponse:
    """Full dream-processing pipeline:
    upload audio → transcribe → anonymize → extract entities → RAG analysis → save to Supabase.

    Accepted audio formats: webm, mp4, wav, mp3, ogg, m4a (anything Whisper supports).

    Returns:
        dream_id      — UUID of the saved dream in Supabase
        title         — short evocative dream title (max 6 words)
        transcription — anonymized English translation from Whisper
        symbols       — list of key Jungian symbols
        emotions      — list of dominant emotions
        analysis      — RAG-grounded psychological analysis in the input text language
        status        — "completed"
    """
    suffix = os.path.splitext(audio.filename or "audio.webm")[1] or ".webm"

    tmp_path: Optional[str] = None
    try:
        enforce_processing_rate_limit(current_user.id)
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        if len(audio_bytes) > settings.MAX_AUDIO_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Uploaded file is too large.",
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        # 1. Auto-detect language and transcribe accordingly
        transcription_result = transcribe_audio_auto(tmp_path)
        tmp_path = None  # ai_service cleans up the file in its finally block

        dream_text = transcription_result["text"]

        return JSONResponse(
            status_code=200,
            content=process_text_pipeline(dream_text, current_user, parse_book_ids(books)),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Dream processing failed for user %s", current_user.id)
        raise client_safe_error("Dream processing failed.") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/process-ka")
async def process_dream_georgian(
    audio: UploadFile = File(...),
    books: str = Form(""),
    current_user=Depends(get_current_user),
) -> JSONResponse:
    """Georgian audio pipeline:
    upload Georgian audio → transcribe to Georgian text (nemo) → existing dream pipeline.

    The Georgian text is passed directly to process_text_pipeline(), identical to
    how a user would type their dream in Georgian via /dreams/process-text.
    Requires GEORGIAN_MODEL_PATH to be set in .env.
    """
    from app.services.ai_service import _transcribe_georgian_nemo

    if not settings.GEORGIAN_MODEL_PATH:
        raise HTTPException(
            status_code=503,
            detail="Georgian STT model is not configured on this server.",
        )

    suffix = os.path.splitext(audio.filename or "audio.wav")[1] or ".wav"
    tmp_path: Optional[str] = None
    try:
        enforce_processing_rate_limit(current_user.id)
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        if len(audio_bytes) > settings.MAX_AUDIO_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Uploaded file is too large.",
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        result = _transcribe_georgian_nemo(tmp_path)
        tmp_path = None  # nemo helper cleans up in its finally block

        return JSONResponse(
            status_code=200,
            content=process_text_pipeline(result["georgian_text"], current_user, parse_book_ids(books)),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Georgian dream processing failed for user %s", current_user.id)
        raise client_safe_error("Dream processing failed.") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/process-text")
async def process_dream_text(
    payload: TextDreamRequest,
    current_user=Depends(get_current_user),
) -> JSONResponse:
    """Process an already-transcribed English or Georgian dream text."""
    try:
        enforce_processing_rate_limit(current_user.id)
        return JSONResponse(
            status_code=200,
            content=process_text_pipeline(payload.dream_text, current_user, parse_book_ids(payload.books)),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Dream text processing failed for user %s", current_user.id)
        raise client_safe_error("Dream text processing failed.") from exc
