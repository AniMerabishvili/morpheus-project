"""
Clean all .txt files in morpheus-backend/books/ for RAG ingestion.

Transformations applied (in order):
  1. Strip Project Gutenberg headers/footers (skipped if markers absent)
  2. Remove ALL-CAPS-only lines
  3. Remove footnote markers like [1], [2], [3]
  4. Remove page-number-only lines (a line that is just a number)
  5. Fix broken hyphenated line splits (word-\nword → wordword)
  6. Collapse 3+ consecutive blank lines into one
  7. Strip leading/trailing whitespace from each line

Output: <original_name>_cleaned.txt in the same directory.
Original files are never modified.
"""

import re
import sys
from pathlib import Path

BOOKS_DIR = Path(__file__).resolve().parent.parent / "morpheus-backend" / "books"

GUTENBERG_START = re.compile(
    r"\*{3}\s*START OF THE PROJECT GUTENBERG EBOOK[^\n]*\n", re.IGNORECASE
)
GUTENBERG_END = re.compile(
    r"\*{3}\s*END OF THE PROJECT GUTENBERG EBOOK[^\n]*", re.IGNORECASE
)

FOOTNOTE_MARKER = re.compile(r"\[\d+\]")
PAGE_NUMBER_LINE = re.compile(r"^\d+$")


def strip_gutenberg(text: str) -> str:
    """Remove Project Gutenberg boilerplate if the standard markers are present."""
    start_match = GUTENBERG_START.search(text)
    end_match = GUTENBERG_END.search(text)

    if start_match:
        text = text[start_match.end():]
    if end_match:
        new_end = GUTENBERG_END.search(text)
        if new_end:
            text = text[: new_end.start()]

    return text


def fix_hyphenated_splits(text: str) -> str:
    """Join word-\nword into wordword (hyphen at end of line is a split artifact)."""
    return re.sub(r"-\n(\S)", r"\1", text)


def clean_text(text: str) -> str:
    # 1. Gutenberg header/footer
    text = strip_gutenberg(text)

    # 5. Fix broken hyphenated line splits before splitting into lines
    text = fix_hyphenated_splits(text)

    lines = text.splitlines()
    cleaned: list[str] = []
    blank_run = 0

    for line in lines:
        # 7. Strip leading/trailing whitespace
        line = line.strip()

        # 4. Remove page-number-only lines
        if PAGE_NUMBER_LINE.match(line):
            continue

        # 2. Remove ALL-CAPS lines (must have at least one letter, no lowercase)
        letters = [c for c in line if c.isalpha()]
        if letters and all(c.isupper() for c in letters):
            continue

        # 3. Remove footnote markers [1], [23], etc.
        line = FOOTNOTE_MARKER.sub("", line).strip()

        # 6. Collapse 3+ consecutive blank lines into one
        if line == "":
            blank_run += 1
            if blank_run <= 1:
                cleaned.append(line)
        else:
            blank_run = 0
            cleaned.append(line)

    return "\n".join(cleaned)


def process_file(src: Path) -> None:
    if src.stem.endswith("_cleaned"):
        return  # skip already-cleaned files

    dest = src.with_name(src.stem + "_cleaned.txt")
    print(f"Cleaning: {src.name} → ", end="", flush=True)

    text = src.read_text(encoding="utf-8", errors="replace")
    result = clean_text(text)
    dest.write_text(result, encoding="utf-8")

    print("done")


def main() -> None:
    txt_files = sorted(BOOKS_DIR.glob("*.txt"))

    if not txt_files:
        print(f"No .txt files found in {BOOKS_DIR}", file=sys.stderr)
        sys.exit(1)

    for path in txt_files:
        process_file(path)

    print(f"\nFinished. Cleaned files written to {BOOKS_DIR}")


if __name__ == "__main__":
    main()
