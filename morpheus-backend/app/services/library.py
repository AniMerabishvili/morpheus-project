"""The books Morpheus holds in its RAG knowledge base, as a selectable library."""

import logging
import time

from app.database import supabase_admin_only

logger = logging.getLogger(__name__)

# Display metadata for the ingested books, keyed by knowledge_base.book_title.
# Books ingested later without an entry here still appear, with a title derived from the key.
BOOK_INFO: dict[str, dict[str, str]] = {
    "archetypes_collective_unconscious": {
        "title": "The Archetypes and the Collective Unconscious",
        "author": "C. G. Jung",
    },
    "man_and_his_symbols": {"title": "Man and His Symbols", "author": "C. G. Jung"},
    "memories_dreams_reflections": {"title": "Memories, Dreams, Reflections", "author": "C. G. Jung"},
    "interpretation_of_dreams": {"title": "The Interpretation of Dreams", "author": "Sigmund Freud"},
    "hero_thousand_faces": {"title": "The Hero with a Thousand Faces", "author": "Joseph Campbell"},
    "myths_dreams_mysteries": {"title": "Myths, Dreams and Mysteries", "author": "Mircea Eliade"},
    "dictionary_of_symbols_cirlot": {"title": "A Dictionary of Symbols", "author": "J. E. Cirlot"},
    "penguin_dictionary_symbols": {
        "title": "The Penguin Dictionary of Symbols",
        "author": "Jean Chevalier & Alain Gheerbrant",
    },
}

_CACHE_TTL_SECONDS = 3600
_cache: dict = {"at": 0.0, "books": []}


def _fallback_title(book_id: str) -> str:
    return book_id.replace("_", " ").strip().title()


def _fetch_book_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    start, page = 0, 1000
    while True:
        rows = (
            supabase_admin_only.table("knowledge_base")
            .select("book_title")
            .range(start, start + page - 1)
            .execute()
            .data
            or []
        )
        for row in rows:
            key = row.get("book_title")
            if key:
                counts[key] = counts.get(key, 0) + 1
        if len(rows) < page:
            return counts
        start += page


def get_library() -> list[dict]:
    """Books available in the knowledge base (cached for an hour)."""
    if _cache["books"] and time.time() - _cache["at"] < _CACHE_TTL_SECONDS:
        return _cache["books"]
    try:
        counts = _fetch_book_counts()
    except Exception as exc:  # fall back to the known list if the DB is unreachable
        logger.warning("Could not list knowledge_base books: %s", exc)
        counts = {key: 0 for key in BOOK_INFO}

    books = [
        {
            "id": key,
            "title": BOOK_INFO.get(key, {}).get("title") or _fallback_title(key),
            "author": BOOK_INFO.get(key, {}).get("author", ""),
            "passages": count,
        }
        for key, count in counts.items()
    ]
    books.sort(key=lambda b: (b["author"] or "~", b["title"]))
    _cache.update(at=time.time(), books=books)
    return books


def clean_book_ids(raw) -> list[str]:
    """Keep only ids that exist in the library, de-duplicated, in library order."""
    if not isinstance(raw, list):
        return []
    wanted = {item for item in raw if isinstance(item, str)}
    return [book["id"] for book in get_library() if book["id"] in wanted]


def book_label(book_id: str) -> str:
    for book in get_library():
        if book["id"] == book_id:
            return f'{book["title"]} ({book["author"]})' if book["author"] else book["title"]
    return _fallback_title(book_id)
