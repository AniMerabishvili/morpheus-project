import os
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.database import supabase
from app.services.ai_service import (
    anonymize_text,
    extract_entities,
    generate_embedding,
    transcribe_audio,
)

router = APIRouter(prefix="/v1/dreams", tags=["dreams"])


def save_dream(
    english_text: str,
    entities: dict,
) -> str:
    """Persist a processed dream to Supabase and return its UUID.

    Steps:
      1. Generate 384-dim embedding from the raw English transcription.
      2. Insert a row into `dreams` — returns the new UUID.
      3. For each symbol: upsert into `keywords`, then link via `dream_keywords`.
    """
    embedding = generate_embedding(english_text)

    # 1. Insert the dream row.
    dream_row = (
        supabase.table("dreams")
        .insert(
            {
                "user_id": None,
                "title": entities.get("title", "Untitled Dream"),
                "raw_text": english_text,
                "analysis": "",
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


@router.post("/process")
async def process_dream(audio: UploadFile = File(...)) -> JSONResponse:
    """Full dream-processing pipeline:
    upload audio → transcribe → anonymize → extract entities → embed → save to Supabase.

    Accepted audio formats: webm, mp4, wav, mp3, ogg, m4a (anything Whisper supports).

    Returns:
        dream_id      — UUID of the saved dream in Supabase
        title         — short evocative dream title (max 6 words)
        transcription — raw English translation from Whisper
        symbols       — list of key Jungian symbols
        emotions      — list of dominant emotions
        status        — "processing"
    """
    suffix = os.path.splitext(audio.filename or "audio.webm")[1] or ".webm"

    tmp_path: str | None = None
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

        # 2. Anonymize PII before sending to the external LLM
        anonymized = anonymize_text(english_text)

        # 3. Extract Jungian entities via Gemini (retries on 503 automatically)
        entities = extract_entities(anonymized)

        # 4. Embed + save to Supabase
        dream_id = save_dream(english_text, entities)

        return JSONResponse(
            status_code=200,
            content={
                "dream_id": dream_id,
                "title": entities.get("title", ""),
                "transcription": english_text,
                "symbols": entities.get("symbols", []),
                "emotions": entities.get("emotions", []),
                "status": "processing",
            },
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
