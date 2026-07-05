#!/usr/bin/env python3
"""
Ingest cleaned academic texts into the Supabase RAG knowledge base.

Run from the project root:
    python morpheus-backend/scripts/ingest_books.py

Or from morpheus-backend:
    python scripts/ingest_books.py
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from supabase import Client, create_client


BACKEND_DIR = Path(__file__).resolve().parents[1]
BOOKS_DIR = BACKEND_DIR / "books" / "cleaned"
ENV_FILE = BACKEND_DIR / ".env"

MAX_CHARS = 2000
OVERLAP_SENTENCES = 2
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

load_dotenv(ENV_FILE)
embedder = SentenceTransformer("all-MiniLM-L6-v2")


def get_supabase_client() -> Client:
    """Create a Supabase client using morpheus-backend/.env values."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

    if not url:
        raise RuntimeError(f"SUPABASE_URL is missing from {ENV_FILE}")
    if not key:
        raise RuntimeError(
            f"SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY is missing from {ENV_FILE}"
        )

    return create_client(url, key)


def book_title_from_path(path: Path) -> str:
    """Return filename without extension, stripping the cleaned_ prefix."""
    title = path.stem
    if title.startswith("cleaned_"):
        title = title.removeprefix("cleaned_")
    return title


def split_into_sentences(text: str) -> list[str]:
    """Split text at . ! ? followed by whitespace and a capital letter."""
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []

    return [
        sentence.strip()
        for sentence in SENTENCE_BOUNDARY.split(normalized)
        if sentence.strip()
    ]


def _overlap_that_fits(
    sentences: list[str],
    next_sentence: str,
    max_chars: int,
) -> list[str]:
    """Carry the largest possible 1-2 sentence overlap into the next chunk."""
    for count in range(min(OVERLAP_SENTENCES, len(sentences)), 0, -1):
        overlap = sentences[-count:]
        if len(" ".join([*overlap, next_sentence])) <= max_chars:
            return overlap

    return []


def chunk_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Group sentences into chunks under max_chars without splitting sentences."""
    sentences = split_into_sentences(text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        separator_len = 1 if current else 0
        sentence_len = len(sentence)

        if current and current_len + separator_len + sentence_len > max_chars:
            chunks.append(" ".join(current).strip())
            current = _overlap_that_fits(current, sentence, max_chars)
            current_len = len(" ".join(current)) if current else 0
            separator_len = 1 if current else 0

        current.append(sentence)
        current_len += separator_len + sentence_len

    if current:
        chunks.append(" ".join(current).strip())

    return chunks


def already_ingested(client: Client, book_title: str) -> bool:
    """Return True if knowledge_base already has rows for this book_title."""
    response = (
        client.table("knowledge_base")
        .select("id")
        .eq("book_title", book_title)
        .limit(1)
        .execute()
    )
    return bool(response.data)


def ingest_file(client: Client, path: Path, force: bool = False) -> int:
    """Embed and insert all chunks from one cleaned text file."""
    book_title = book_title_from_path(path)
    exists = already_ingested(client, book_title)

    if exists and not force:
        print(f"Skipping: {path.name} already exists as {book_title}")
        return 0
    if exists and force:
        print(f"Re-ingesting: {path.name} as {book_title}")
        client.table("knowledge_base").delete().eq("book_title", book_title).execute()

    text = path.read_text(encoding="utf-8")
    chunks = chunk_text(text)
    total_chunks = len(chunks)

    for index, chunk in enumerate(chunks, start=1):
        print(f"Processing: {path.name} — chunk {index}/{total_chunks}")
        embedding = embedder.encode(chunk).tolist()
        client.table("knowledge_base").insert(
            {
                "book_title": book_title,
                "content": chunk,
                "embedding": embedding,
            }
        ).execute()

    return total_chunks


def cleaned_text_files() -> list[Path]:
    """Return all .txt files from morpheus-backend/books/cleaned."""
    return sorted(BOOKS_DIR.glob("*.txt"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest cleaned academic texts into Supabase knowledge_base."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-ingest files even when book_title rows already exist.",
    )
    args = parser.parse_args()

    if not BOOKS_DIR.is_dir():
        raise RuntimeError(f"Books directory not found: {BOOKS_DIR}")

    files = cleaned_text_files()
    if not files:
        raise RuntimeError(f"No .txt files found in {BOOKS_DIR}")

    client = get_supabase_client()
    total_inserted = 0

    for path in files:
        total_inserted += ingest_file(client, path, force=args.force)

    print(f"Done. Inserted {total_inserted} chunks into knowledge_base.")


if __name__ == "__main__":
    main()
