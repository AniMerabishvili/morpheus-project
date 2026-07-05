import os
import tempfile
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.database import supabase
from app.services.ai_service import (
    anonymize_text,
    extract_entities,
    generate_analysis,
    generate_embedding,
    get_rag_context,
    transcribe_audio,
)

router = APIRouter(prefix="/v1/dreams", tags=["dreams"])


class TextDreamRequest(BaseModel):
    dream_text: str


def save_dream(
    processed_text: str,
    entities: dict,
) -> str:
    """Persist a processed dream to Supabase and return its UUID.

    Steps:
      1. Generate 384-dim embedding from the anonymized dream text.
      2. Insert a row into `dreams` — returns the new UUID.
      3. For each symbol: upsert into `keywords`, then link via `dream_keywords`.
    """
    embedding = generate_embedding(processed_text)

    # 1. Insert the dream row.
    dream_row = (
        supabase.table("dreams")
        .insert(
            {
                "user_id": None,
                "title": entities.get("title", "Untitled Dream"),
                "raw_text": processed_text,
                "analysis": entities.get("summary", ""),
                "embedding": embedding,
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

        # Upsert: insert if the name doesn't exist yet; do nothing on conflict.
        keyword_row = (
            supabase.table("keywords")
            .upsert({"name": symbol}, on_conflict="name")
            .execute()
        )
        keyword_id: str = keyword_row.data[0]["id"]

        supabase.table("dream_keywords").upsert(
            {"dream_id": dream_id, "keyword_id": keyword_id},
            on_conflict="dream_id,keyword_id",
        ).execute()

    return dream_id


def update_dream_analysis(dream_id: str, analysis: str) -> None:
    """Persist the generated analysis on the saved dream row."""
    (
        supabase.table("dreams")
        .update({"analysis": analysis})
        .eq("id", dream_id)
        .execute()
    )


def process_text_pipeline(dream_text: str) -> dict:
    """Run the shared non-audio dream pipeline for English or Georgian text."""
    if not dream_text.strip():
        raise HTTPException(status_code=400, detail="dream_text cannot be empty.")

    # 1. Anonymize PII before sending to the external LLM
    anonymized_text = anonymize_text(dream_text.strip())

    # 2. Extract Jungian entities via Gemini
    entities = extract_entities(anonymized_text)

    # 3. Embed + save to Supabase
    dream_id = save_dream(anonymized_text, entities)

    # 4. Retrieve RAG context and generate language-matched analysis
    rag_context = get_rag_context(anonymized_text)
    analysis = generate_analysis(anonymized_text, entities, rag_context)

    # 5. Update saved dream with final analysis
    update_dream_analysis(dream_id, analysis)

    return {
        "dream_id": dream_id,
        "title": entities.get("title", ""),
        "transcription": anonymized_text,
        "symbols": entities.get("symbols", []),
        "emotions": entities.get("emotions", []),
        "analysis": analysis,
        "status": "completed",
    }


@router.post("/process")
async def process_dream(audio: UploadFile = File(...)) -> JSONResponse:
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
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        # 1. Transcribe audio → English text
        transcription_result = transcribe_audio(tmp_path)
        tmp_path = None  # ai_service cleans up the file in its finally block

        english_text = transcription_result["english_text"]

        return JSONResponse(
            status_code=200,
            content=process_text_pipeline(english_text),
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Dream processing failed: {str(exc)}",
        ) from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/process-text")
async def process_dream_text(payload: TextDreamRequest) -> JSONResponse:
    """Process an already-transcribed English or Georgian dream text."""
    try:
        return JSONResponse(
            status_code=200,
            content=process_text_pipeline(payload.dream_text),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Dream text processing failed: {str(exc)}",
        ) from exc
