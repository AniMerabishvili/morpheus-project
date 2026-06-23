"""
Convert thesis_draft.md to thesis_draft.docx with proper Word styles.
Run: python3 md_to_docx.py
"""

import sys
import re
sys.path.insert(0, ".pip_temp")

from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import xml.etree.ElementTree as ET

MD_PATH = "thesis_draft.md"
DOCX_PATH = "thesis_draft.docx"


def set_font(run, bold=False, italic=False, size=None):
    run.bold = bold
    run.italic = italic
    if size:
        run.font.size = Pt(size)


def latex_to_unicode(tex: str) -> str:
    """Convert a simple LaTeX math string to a readable Unicode representation."""
    t = tex.strip()

    # ── Step 1: expand inner commands first (so \frac sees clean braces)
    t = re.sub(r"\\text\{([^}]+)\}", r"\1", t)          # \text{x}  →  x
    t = re.sub(r"\\mathbf\{([^}]+)\}", r"\1", t)         # \mathbf{X}  →  X
    t = t.replace(r"\|", "‖")                            # \|  →  ‖
    t = t.replace(r"\cdot", "·")                         # \cdot  →  ·
    t = t.replace(r"\times", "×")                        # \times  →  ×
    t = t.replace(r"\left", "").replace(r"\right", "")   # \left / \right
    t = t.replace(r"\theta", "θ").replace(r"\alpha", "α").replace(r"\beta", "β")
    t = re.sub(r"\\(cos|sin|log|ln|exp|max|min|sum|prod)\b", r"\1", t)

    # ── Step 2: now match \frac{num}{den} (inner braces are gone)
    def replace_frac(m):
        num = m.group(1).strip()
        den = m.group(2).strip()
        return f"({num}) / ({den})"
    # Repeat up to 3 times for nested fracs
    for _ in range(3):
        t = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", replace_frac, t)

    # ── Step 3: remove any remaining backslash commands
    t = re.sub(r"\\[a-zA-Z]+", "", t)

    # ── Step 4: clean up stray braces and double spaces
    t = t.replace("{", "").replace("}", "")
    t = re.sub(r" {2,}", " ", t).strip()
    return t


def add_math_block(doc, formula_text):
    """Add a centered paragraph for a display math formula, rendered as Unicode."""
    readable = latex_to_unicode(formula_text)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(readable)
    run.italic = True
    run.font.size = Pt(12)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(6)


def apply_inline(para, line):
    """
    Parse inline markdown in a line and add runs to the paragraph.
    Handles: **bold**, *italic*, `code`, and plain text.
    """
    pattern = re.compile(r'(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\\\[.*?\\\])')
    last = 0
    for m in pattern.finditer(line):
        # plain text before this match
        if m.start() > last:
            para.add_run(line[last:m.start()])
        token = m.group(0)
        if token.startswith("**"):
            run = para.add_run(token[2:-2])
            run.bold = True
        elif token.startswith("*"):
            run = para.add_run(token[1:-1])
            run.italic = True
        elif token.startswith("`"):
            run = para.add_run(token[1:-1])
            run.font.name = "Courier New"
            run.font.size = Pt(10)
        elif token.startswith(r"\["):
            # Inline math fallback — render as italic
            inner = token[2:-2].strip()
            run = para.add_run(inner)
            run.italic = True
        last = m.end()
    if last < len(line):
        para.add_run(line[last:])


def build_docx(md_path, docx_path):
    doc = Document()

    # Global default font
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)

    # Heading styles
    for level, (name, size, bold) in enumerate([
        ("Heading 1", 16, True),
        ("Heading 2", 14, True),
        ("Heading 3", 12, True),
    ], start=1):
        h = doc.styles[f"Heading {level}"]
        h.font.name = "Times New Roman"
        h.font.size = Pt(size)
        h.font.bold = bold
        h.font.color.rgb = RGBColor(0, 0, 0)

    with open(md_path, encoding="utf-8") as f:
        lines = f.readlines()

    i = 0
    in_math_block = False
    math_lines = []

    while i < len(lines):
        raw = lines[i].rstrip("\n")
        stripped = raw.strip()

        # ── Math block \[ ... \] spanning multiple lines
        if stripped == r"\[":
            in_math_block = True
            math_lines = []
            i += 1
            continue
        if in_math_block:
            if stripped == r"\]":
                in_math_block = False
                add_math_block(doc, " ".join(math_lines).strip())
                math_lines = []
            else:
                math_lines.append(stripped)
            i += 1
            continue

        # ── Horizontal rule
        if re.match(r"^-{3,}$", stripped):
            p = doc.add_paragraph()
            pPr = p._p.get_or_add_pPr()
            pBdr = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), "6")
            bottom.set(qn("w:space"), "1")
            bottom.set(qn("w:color"), "auto")
            pBdr.append(bottom)
            pPr.append(pBdr)
            i += 1
            continue

        # ── Headings
        if stripped.startswith("### "):
            p = doc.add_heading(level=3)
            apply_inline(p, stripped[4:])
            i += 1
            continue
        if stripped.startswith("## "):
            p = doc.add_heading(level=2)
            apply_inline(p, stripped[3:])
            i += 1
            continue
        if stripped.startswith("# "):
            p = doc.add_heading(level=1)
            apply_inline(p, stripped[2:])
            i += 1
            continue

        # ── Title-block bold key:value lines (e.g. **Author:** ...)
        if stripped.startswith("**") and ":**" in stripped:
            p = doc.add_paragraph()
            apply_inline(p, stripped)
            p.paragraph_format.space_after = Pt(0)
            i += 1
            continue

        # ── Blank line
        if stripped == "":
            i += 1
            continue

        # ── Normal paragraph — collect all consecutive non-empty lines
        para_lines = []
        while i < len(lines):
            raw2 = lines[i].rstrip("\n")
            if raw2.strip() == "":
                break
            # stop if next line is a heading or rule
            if re.match(r"^#{1,3} |^-{3,}$|\\\[$", raw2.strip()):
                break
            para_lines.append(raw2.strip())
            i += 1

        if para_lines:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(6)
            apply_inline(p, " ".join(para_lines))
        continue

    doc.save(docx_path)
    print(f"Saved: {docx_path}")


if __name__ == "__main__":
    build_docx(MD_PATH, DOCX_PATH)
