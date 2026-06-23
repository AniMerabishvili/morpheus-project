#!/usr/bin/env python3
"""
Cleans raw book .txt files for RAG ingestion into Supabase knowledge_base.

Handles all 9 source books:
  - interpretation_of_dreams       (Project Gutenberg — has wrapper markers)
  - archetypes_collective_unconscious
  - body_keeps_the_score
  - dictionary_of_symbols_cirlot   (dictionary-style A-Z entries)
  - penguin_dictionary_symbols     (dictionary-style A-Z entries, OCR page headers)
  - hero_thousand_faces
  - man_and_his_symbols
  - memories_dreams_reflections    (already fairly clean)
  - myths_dreams_mysteries         (OCR artifacts: soft hyphens, i960, etc.)

Pipeline per book
─────────────────
1.  Strip Project Gutenberg wrapper (if present)
2.  Fix OCR artifacts (soft-hyphen breaks, year typos, stray symbols)
3.  Strip leading whitespace (normalises Gutenberg-style centered text)
4.  Strip back matter  (Index, Footnotes, Bibliography, ebook footers)
5.  Strip front matter (publisher pages, copyright, blurbs)
6.  Remove TOC + illustration-list blocks (may appear after kept front sections)
7.  Normalize (whitespace, page-running headers, glued footnote digits, etc.)
"""

import re
import sys
from pathlib import Path


# ── 1. GUTENBERG WRAPPER ──────────────────────────────────────────────────────

def strip_gutenberg(text: str) -> str:
    """Remove Project Gutenberg legal header and footer."""
    start = re.search(
        r'\*{3}\s*START OF THE PROJECT GUTENBERG EBOOK[^\n]*\*{3}', text
    )
    if start:
        text = text[start.end():]

    end = re.search(
        r'\*{3}\s*END OF THE PROJECT GUTENBERG EBOOK[^\n]*\*{3}', text
    )
    if end:
        text = text[: end.start()]

    return text


# ── 2. OCR ARTIFACT FIXES ─────────────────────────────────────────────────────

_OCR_WORD_FIXES = {
    'rehgion':    'religion',
    'rehgious':   'religious',
    'rehgiously': 'religiously',
    'ofthe':      'of the',
    'inthe':      'in the',
    'andthe':     'and the',
}


def fix_ocr(text: str) -> str:
    # Soft hyphen / OCR hyphen at a line break: "addi¬\ntional" → "additional"
    text = re.sub(r'(\w+)[¬­]\n(\w+)', r'\1\2', text)

    # Standard hyphen at a line break: "con-\ncrete" → "concrete"
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)

    # OCR misreads '1' as 'i' before 3-digit years: i960 → 1960
    text = re.sub(r'\bi([89]\d{2})\b', r'1\1', text)

    # Stray decorator / bullet symbols
    text = re.sub(r'[▼►◄→←★☆■□▪▫◆◇•]', '', text)

    # Known word-level OCR errors
    for wrong, right in _OCR_WORD_FIXES.items():
        text = text.replace(wrong, right)

    return text


# ── 3. BACK MATTER ────────────────────────────────────────────────────────────

_BACK_HEADERS = re.compile(
    r'^\s*(?:INDEX|BIBLIOGRAPHY|SELECTED BIBLIOGRAPHY|REFERENCES|'
    r'NOTES AND REFERENCES|ACKNOWLEDGMENTS?|ABOUT THE AUTHOR|'
    r'PERMISSIONS|CREDITS|ILLUSTRATION CREDITS)\s*$',
    re.MULTILINE | re.IGNORECASE,
)


def strip_back_matter(text: str) -> str:
    # Project Gutenberg footnote blocks (always start with "Footnote 1:")
    fn = re.search(r'\n\s*Footnote\s+1\s*:', text)
    if fn and fn.start() > len(text) * 0.4:
        text = text[: fn.start()]

    # "this page" footnote blocks (Man and His Symbols digital edition).
    # Format: "this page Bibliographic note text here."  (one per line)
    # Find the first such line in the last 30% and truncate there.
    tp_matches = list(re.finditer(r'\nthis page [A-Za-z]', text))
    if tp_matches:
        tp = tp_matches[0]
        if tp.start() > len(text) * 0.7:
            text = text[: tp.start()]

    # Ebook marketing footer (Hero with a Thousand Faces / JCF edition).
    # The phrase may also appear in the front matter, so find the LAST occurrence
    # and only strip when it is genuinely near the end (> 85 %).
    ef_matches = list(re.finditer(
        r'\n(?:Thank you for reading|If you have received this book gratis)',
        text, re.IGNORECASE,
    ))
    if ef_matches:
        last_ef = ef_matches[-1]
        if last_ef.start() > len(text) * 0.85:
            text = text[: last_ef.start()]

    # Orphan back-matter headers left when the body was already stripped
    text = re.sub(r'\n+LITERARY INDEX\s*$', '', text, flags=re.IGNORECASE)

    # Standard back-matter section headers — only strip in last 40 % of file
    cutoff = int(len(text) * 0.60)
    for m in _BACK_HEADERS.finditer(text):
        if m.start() > cutoff:
            text = text[: m.start()]
            break

    return text


# ── 4. FRONT MATTER ───────────────────────────────────────────────────────────

_METADATA_PATTERNS = [
    re.compile(r'\bISBN[-\s]?\d', re.IGNORECASE),
    re.compile(r'Copyright\s*©', re.IGNORECASE),
    re.compile(r'All rights reserved', re.IGNORECASE),
    re.compile(r'Library of Congress', re.IGNORECASE),
    re.compile(r'Printed in the United States', re.IGNORECASE),
    re.compile(r'Published by|Publishing Group|Publishers?,?\s+(?:Inc|LLC|Ltd)', re.IGNORECASE),
    re.compile(r'https?://\S+|www\.\w+\.\w+'),
    re.compile(r'\d{3,5}\s+[A-Z][a-z]+\s+(?:Street|Avenue|Boulevard|Road)\b'),
    re.compile(r'First (?:published|edition|printing)', re.IGNORECASE),
    re.compile(r'Manufactured in', re.IGNORECASE),
    re.compile(r'Bollingen Series', re.IGNORECASE),
    re.compile(r'Penguin (?:Group|Random House)', re.IGNORECASE),
    re.compile(r'Princeton University Press', re.IGNORECASE),
    re.compile(r'Catalog Card Number', re.IGNORECASE),
    re.compile(r'Random House', re.IGNORECASE),
    re.compile(r'Dell Publishing', re.IGNORECASE),
    re.compile(r'New York Review Books', re.IGNORECASE),
    re.compile(r'Harper (?:Torchbooks?|Row|Collins)', re.IGNORECASE),
    re.compile(r'This book was originally published', re.IGNORECASE),
    re.compile(r'electronic edition|eBook by', re.IGNORECASE),
    re.compile(r'version \d+\.\d+\.\d+', re.IGNORECASE),
    re.compile(r'Joseph Campbell Foundation|JCF\.org', re.IGNORECASE),
    re.compile(r'Thank you for (?:maintaining|purchasing) this ebook', re.IGNORECASE),
    re.compile(r'Internet Archive', re.IGNORECASE),
    re.compile(r'tillpoint Digital Press', re.IGNORECASE),
]

# Keyword must be preceded by start-of-text (\A) or a blank line (\n\n) so
# lowercase mid-sentence words (e.g. "introduction of Christianity" in a
# dictionary entry) are never matched after the leading-whitespace strip.
# Group 1 captures the keyword itself so callers can locate it exactly.
_CONTENT_ANCHORS = re.compile(
    r'(?:\n\n|\A)\s*('
    r'PROLOGUE|PREFACE|FOREWORD|INTRODUCTION|'
    r'EDITORIAL\s+NOTE|INTRODUCTORY\s+REMARKS|'
    r"TRANSLATOR'?S?\s+NOTE|"
    r'CHAPTER\s+(?:I|1|ONE)|PART\s+(?:I|1|ONE)'
    r')\b',
    re.IGNORECASE,
)


def _has_prose(text_after: str, min_endings: int = 2) -> bool:
    """
    True if any paragraph within the next 600 chars looks like real prose.

    Two tiers:
    - Long paragraph (≥ 200 chars) with ≥ 1 sentence ending → prose.
    - Medium paragraph (≥ 80 chars) with ≥ min_endings endings → prose.

    Hard stop after 6 non-empty paragraphs: prevents a TOC entry from
    borrowing its prose score from the real section ~200 chars further on.
    """
    sample = text_after[:600]
    seen = 0
    for para in re.split(r'\n{2,}', sample):
        para = para.strip()
        if not para:
            continue
        seen += 1
        ends = len(re.findall(r'[.!?](?:\s|$)', para))
        if len(para) >= 200 and ends >= 1:
            return True
        if len(para) >= 80 and ends >= min_endings:
            return True
        if seen >= 6:
            return False
    return False


def _is_metadata_para(para: str) -> bool:
    """True if a paragraph looks like publisher/copyright boilerplate."""
    for pat in _METADATA_PATTERNS:
        if pat.search(para):
            return True

    lines = [ln.strip() for ln in para.split('\n') if ln.strip()]
    if not lines:
        return True

    # Title-page style: majority of short ALL-CAPS lines
    caps_short = sum(1 for ln in lines if ln.isupper() and len(ln) < 70)
    if caps_short >= max(3, len(lines) * 0.7) and len(lines) < 10:
        return True

    # Endorsement attribution: ends with an em-dash line
    if lines[-1].startswith(('—', '–', '-')):
        return True

    # Endorsement quote: entire paragraph wrapped in double quotes
    flat = para.strip()
    if flat.startswith('"') and flat.endswith('"'):
        return True

    return False


def strip_front_matter(text: str) -> str:
    """
    Strip front matter (publisher pages, copyright, blurbs).

    Strategy 2 (first): dictionary A-Z entry blocks.
    Strategy 1:         known content-section anchors.
    Strategy 3:         paragraph-by-paragraph scan (generic fallback).
    """

    # Strategy 2: dictionary A-Z entry blocks (checked before generic anchors).
    # Looks for standalone "A" followed by a lowercase entry word — the
    # fingerprint of an alphabetical reference dictionary.
    # Limited to the first 50 k chars to avoid mid-text "A" sections.
    dict_start = re.search(r'\n\s*A\s*\n\s*\n\s*[a-z]', text[:50_000])
    if dict_start:
        return text[dict_start.start() + 1:]

    # Strategy 1: content anchors
    for m in _CONTENT_ANCHORS.finditer(text):
        pos = m.start(1)   # position of the keyword (group 1), not of \n\n

        if pos < 30:
            # File starts almost immediately with content
            return text

        after = text[m.end(): m.end() + 600]
        if _has_prose(after):
            line_start = text.rfind('\n', 0, pos) + 1
            return text[line_start:]

    # Strategy 3: paragraph-by-paragraph scan (generic fallback)
    paragraphs = re.split(r'\n{2,}', text)
    for i, para in enumerate(paragraphs):
        if i < 5:
            continue
        if not _is_metadata_para(para) and _has_prose(para, min_endings=2):
            return '\n\n'.join(paragraphs[i:])

    return text


# ── 5. TOC + ILLUSTRATION-LIST REMOVAL (post front-matter) ────────────────────

_NOISE_BLOCK_HEADERS = re.compile(
    r'\n\n((?:TABLE\s+OF\s+)?CONTENTS|LIST\s+OF\s+(?:ILLUSTRATIONS?|FIGURES?|PLATES?))\s*\n',
    re.IGNORECASE,
)


def _is_prose_para(para: str) -> bool:
    """True if a paragraph looks like real prose (not a TOC/list entry)."""
    lines = [l.strip() for l in para.split('\n') if l.strip()]
    if not lines:
        return False
    avg_len = sum(len(l) for l in lines) / len(lines)
    has_sentence = bool(re.search(r'[.!?]\s+[A-Za-z]', para))
    return avg_len >= 60 and has_sentence


def remove_toc_and_list_blocks(text: str) -> str:
    """
    Remove TABLE OF CONTENTS and LIST OF ILLUSTRATIONS blocks that appear
    after the content anchor has already been found (e.g. archetypes has
    EDITORIAL NOTE → … → TABLE OF CONTENTS → LIST OF ILLUSTRATIONS → essays).

    Only processes blocks in the first 40 % of the (already front-stripped) file.
    Recurses once to handle the case where TABLE OF CONTENTS is immediately
    followed by LIST OF ILLUSTRATIONS before the first prose paragraph.
    """
    m = _NOISE_BLOCK_HEADERS.search(text)
    if not m or m.start() > len(text) * 0.40:
        return text

    block_start = m.start()
    after = text[m.end():]

    for para in re.split(r'\n{2,}', after):
        if _is_prose_para(para.strip()):
            prose_pos = text.find(para, m.end())
            if prose_pos > m.end():
                # Recurse to catch a second noise block (e.g. LIST OF ILLUSTRATIONS
                # that immediately follows the TABLE OF CONTENTS)
                tail = remove_toc_and_list_blocks(text[prose_pos:])
                return text[:block_start] + '\n\n' + tail
            break

    return text


# ── 6. GENERAL NORMALIZATION ──────────────────────────────────────────────────

def normalize(text: str) -> str:
    # ── Whitespace first (normalises \n{3,} → \n\n so later patterns are consistent)

    text = re.sub(r'\t', ' ', text)
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # ── Footnote anchors and reference codes ──────────────────────────────────

    # Symbol anchors (†, ‡)
    text = re.sub(r'[†‡]', '', text)

    # Bracketed reference numbers: [1], [22]
    text = re.sub(r'\[\d{1,3}\]', '', text)

    # Letter-coded Gutenberg footnote references: [GC], [CR], [LH] etc.
    text = re.sub(r'\[[A-Z]{1,4}\]', '', text)

    # Glued naked footnote superscripts left after [n] removal.
    # Pattern: lowercase/quote/closing-paren → period/!/?  → digit(s) → space/newline.
    # Example: "beaten or hit.1\n"  →  "beaten or hit.\n"
    # Avoids breaking decimal numbers (2.1) by requiring the char before . to be
    # a word character that is NOT a digit.
    text = re.sub(r'([a-z\'"])([.!?])\d{1,3}(?=[\s\n])', r'\1\2', text)

    # ── Page-running headers (OCR artefacts in Penguin-style dictionaries) ─────
    # Pattern: a standalone ALL-CAPS line (2–50 chars, no digits) between two
    # paragraphs where the first ends WITHOUT sentence-closing punctuation
    # (meaning the page-header split a sentence in two) and the second starts
    # with a lowercase letter (confirming the continuation).
    # Replace the orphaned header + surrounding blank lines with a single space
    # so the two fragments rejoin into one readable sentence.
    text = re.sub(
        r'(?<![.!?])\n\n([A-Z][A-Z \'-]{0,48}[A-Z])\n\n(?=[a-z])',
        ' ',
        text,
    )

    # ── Structural noise ──────────────────────────────────────────────────────

    # Isolated page numbers on their own lines
    text = re.sub(r'^\s*\d{1,4}\s*$', '', text, flags=re.MULTILINE)

    # Isolated roman numerals on their own lines (chapter / page markers)
    text = re.sub(r'^\s*[IVXLCDMivxlcdm]{1,8}\s*$', '', text, flags=re.MULTILINE)

    # TOC leader dots and long separator bars
    text = re.sub(r'\.{4,}', '', text)
    text = re.sub(r'-{4,}', '', text)
    text = re.sub(r'_{3,}', '', text)

    # Lines containing only stray punctuation / decoration
    text = re.sub(r'^\s*[=~*]{3,}\s*$', '', text, flags=re.MULTILINE)

    # Collapse any blank-line runs introduced by the passes above
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


# ── MAIN PIPELINE ─────────────────────────────────────────────────────────────

def clean_book(text: str) -> str:
    text = strip_gutenberg(text)
    text = fix_ocr(text)
    # Strip leading whitespace so content anchors match Gutenberg centered text
    text = re.sub(r'^ +', '', text, flags=re.MULTILINE)
    text = strip_back_matter(text)
    text = strip_front_matter(text)
    # Remove TOC / illustration-list blocks that survived front-matter stripping
    text = remove_toc_and_list_blocks(text)
    text = normalize(text)
    # Extra pass for dictionary-format books (Penguin-style):
    # Remove ALL standalone ALL-CAPS page-running headers and single-letter
    # section dividers. Safe only in dictionaries where entries start lowercase
    # or mixed-case — the ALL-CAPS lines are always OCR page-header artefacts.
    if _is_dictionary_book(text):
        # Single-letter section dividers (A, B, C …)
        text = re.sub(r'\n\n[A-Z]\n\n', '\n\n', text)
        # Multi-word ALL-CAPS page headers (ABSTINENCE, ADAM, AIRCRAFT …)
        text = re.sub(r'\n\n([A-Z][A-Z \'-]{1,48}[A-Z])\n\n', '\n\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def _is_dictionary_book(text: str) -> bool:
    """
    True when the book uses lowercase-word entry format (Penguin-style).
    Detection: cleaned content starts with the letter 'A' on its own line,
    immediately followed by a lowercase entry word — the exact fingerprint of
    an A-Z reference dictionary whose front matter has already been stripped.
    """
    return bool(re.match(r'A\s*\n\s*\n[a-z]', text.lstrip()[:20]))


def process_books(books_dir: str, output_dir=None) -> None:
    books_path = Path(books_dir)
    if not books_path.is_dir():
        print(f"Error: '{books_dir}' is not a directory.")
        return

    out_path = Path(output_dir) if output_dir else books_path / "cleaned"
    out_path.mkdir(parents=True, exist_ok=True)

    files = sorted(
        f for f in books_path.glob('*.txt')
        if not f.name.startswith('.')
        and 'cleaned' not in str(f.parent)
    )

    if not files:
        print(f"No .txt files found in '{books_dir}'.")
        return

    print(f"Found {len(files)} book(s). Cleaning for RAG...\n" + '─' * 64)

    total_original = total_cleaned = 0

    for fpath in files:
        out_file = out_path / f'cleaned_{fpath.name}'
        try:
            raw = fpath.read_text(encoding='utf-8', errors='replace')
            orig = len(raw)

            cleaned = clean_book(raw)
            clen = len(cleaned)

            out_file.write_text(cleaned, encoding='utf-8')

            reduction = (1 - clen / orig) * 100
            total_original += orig
            total_cleaned += clen

            print(f'  ✓  {fpath.name}')
            print(f'     {orig:>10,} chars  →  {clen:>10,} chars  ({reduction:.1f}% removed)\n')

        except Exception as exc:
            print(f'  ✗  {fpath.name}: {exc}\n')

    if total_original:
        overall = (1 - total_cleaned / total_original) * 100
        print('─' * 64)
        print(f'Total: {total_original:,} → {total_cleaned:,} chars  ({overall:.1f}% removed)')
        print(f'Output: {out_path}')


if __name__ == '__main__':
    _dir = sys.argv[1] if len(sys.argv) > 1 else 'morpheus-backend/books'
    _out = sys.argv[2] if len(sys.argv) > 2 else None
    process_books(_dir, _out)
