from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "pdf" / "morpheus-security-report.pdf"


class Rule(Flowable):
    def __init__(self, color=colors.HexColor("#8A7129"), width=1):
        super().__init__()
        self.color = color
        self.width = width
        self.height = 8
        self.available_width = 0

    def wrap(self, available_width, available_height):
        self.available_width = available_width
        return available_width, self.height

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.width)
        self.canv.line(0, 4, self.available_width, 4)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#6f6f6f"))
    canvas.drawString(doc.leftMargin, 1.1 * cm, "Morpheus Security Report")
    canvas.drawRightString(A4[0] - doc.rightMargin, 1.1 * cm, f"Page {doc.page}")
    canvas.restoreState()


def p(text, style):
    return Paragraph(text, style)


def bullets(items, style):
    out = []
    for item in items:
        out.append(Paragraph(f"- {item}", style))
        out.append(Spacer(1, 3))
    return out


def main():
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=29,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#111111"),
        spaceAfter=8,
    )
    subtitle = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
        spaceAfter=18,
    )
    h1 = ParagraphStyle(
        "Heading1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=colors.HexColor("#111111"),
        spaceBefore=14,
        spaceAfter=8,
    )
    h2 = ParagraphStyle(
        "Heading2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#8A7129"),
        spaceBefore=10,
        spaceAfter=5,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.4,
        leading=13.5,
        textColor=colors.HexColor("#222222"),
        spaceAfter=6,
    )
    small = ParagraphStyle(
        "Small",
        parent=body,
        fontSize=8.2,
        leading=11,
        textColor=colors.HexColor("#444444"),
    )
    risk = ParagraphStyle(
        "Risk",
        parent=body,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#8A4B00"),
    )
    code = ParagraphStyle(
        "Code",
        parent=body,
        fontName="Courier",
        fontSize=8,
        leading=10.5,
        backColor=colors.HexColor("#f3f3f3"),
        borderPadding=4,
    )

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=1.7 * cm,
        rightMargin=1.7 * cm,
        topMargin=1.7 * cm,
        bottomMargin=1.8 * cm,
        title="Morpheus Security Report",
        author="Codex / Ami",
    )

    story = []
    story.append(p("Morpheus System Security Report", title))
    story.append(p(f"Assessment date: {date(2026, 7, 13).isoformat()} | Scope: frontend, backend, Supabase database, AI data flow", subtitle))
    story.append(Rule())

    story.append(p("Executive Verdict", h1))
    story.append(p(
        "Morpheus is suitable for a controlled demo or thesis prototype, but it is not yet production-secure for real private dream journals. "
        "The system has authentication and per-user filtering, but stored dreams are visible to project administrators in Supabase and the backend relies heavily on a service-role client that bypasses row-level security.",
        body,
    ))

    score_data = [
        [p("Area", small), p("Score", small), p("Assessment", small)],
        [p("Authentication", small), p("7 / 10", small), p("Supabase bearer tokens are validated by the backend.", small)],
        [p("User-to-user isolation", small), p("6 / 10", small), p("App code filters by user_id, but live RLS must be verified.", small)],
        [p("Admin/data privacy", small), p("3 / 10", small), p("Admins can read raw dreams, analysis, emotions, titles, and embeddings.", small)],
        [p("Secrets management", small), p("5 / 10", small), p("Backend env is ignored, but frontend .env was committed and secrets have appeared locally.", small)],
        [p("AI privacy", small), p("4 / 10", small), p("Dream text is sent to Gemini; cloud-mode name anonymization is limited.", small)],
        [p("Overall", small), p("5.5 - 6 / 10", small), p("Good MVP foundation, not a strong privacy product yet.", small)],
    ]
    table = Table(score_data, colWidths=[4.0 * cm, 2.2 * cm, 9.8 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111111")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d7d7d7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fbfbfb")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#ffffff"), colors.HexColor("#f7f4e8")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)

    story.append(p("Answer To The Core Question", h1))
    story.append(p(
        "Seeing every user's raw dream text, analysis, embeddings, emotions, and titles in the Supabase dashboard is normal for a database owner, but it means Morpheus is not zero-knowledge and not private from administrators. "
        "It can still be secure against ordinary users seeing each other's data if Row Level Security is enabled and correct. It is not secure against a Supabase admin, a leaked service-role key, or a compromised project account.",
        body,
    ))
    story.append(p(
        "Privacy statement that would be accurate today: Dream content is stored on Morpheus infrastructure and may be accessible to authorized administrators for maintenance, security, or support. Dream text may also be processed by third-party AI services to generate analysis.",
        risk,
    ))

    story.append(p("Confirmed Strengths", h1))
    story.extend(bullets([
        "Backend endpoints require Supabase bearer authentication through app/auth.py.",
        "Journal and graph backend queries filter by the authenticated user's user_id.",
        "The frontend sends bearer tokens to the backend rather than user passwords.",
        "The backend .env file is ignored by git.",
        "Frontend production dependency audit returned zero current npm vulnerabilities.",
    ], body))

    story.append(PageBreak())
    story.append(p("Main Findings", h1))
    findings = [
        ["High", "Admin visibility", "Supabase project admins can read all dream data. This is expected for normal database storage, but it is not private enough for highly sensitive journals unless disclosed or encrypted."],
        ["High", "Service-role usage", "app/database.py aliases the default supabase client to supabase_admin. A service-role key bypasses RLS, so application code must be perfect to avoid cross-user access."],
        ["High", "RLS not proven from repo", "Code comments describe RLS for dreams, but live policies were not verified in this assessment. RLS should be the final guardrail for all user-owned tables."],
        ["Medium", "Token storage", "The frontend manually stores morpheus_session_token in localStorage. If XSS occurs, the bearer token is easy to steal."],
        ["Medium", "No visible rate limiting", "Authenticated users can trigger AI processing and database writes. This can cause cost abuse or denial of service."],
        ["Medium", "Raw errors", "Backend exception strings are returned to the frontend in some 500 responses, which can reveal provider or database details."],
        ["Medium", "AI provider privacy", "Dream text is sent to Gemini. Cloud mode does not run the stronger spaCy person-name redaction path."],
        ["Medium", "Embeddings sensitivity", "Embeddings are derived from private dream content and should be treated as sensitive, not anonymous."],
        ["Low", "Frontend .env committed", "The frontend .env contains public-ish Supabase URL and anon key, not a service-role key, but .env files should be replaced by .env.example."],
    ]
    finding_table = [[p("Severity", small), p("Finding", small), p("Impact", small)]]
    for sev, name, impact in findings:
        finding_table.append([p(sev, small), p(name, small), p(impact, small)])
    ft = Table(finding_table, colWidths=[2.2 * cm, 4.1 * cm, 9.7 * cm], repeatRows=1)
    ft.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111111")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d7d7d7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f4e8")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(ft)

    story.append(PageBreak())
    story.append(p("Evidence From The Codebase", h1))
    evidence = [
        ("Backend auth validation", "morpheus-backend/app/auth.py:get_current_user validates the Authorization: Bearer token through Supabase Auth."),
        ("Admin DB client", "morpheus-backend/app/database.py creates supabase_admin with SUPABASE_SERVICE_ROLE_KEY and aliases supabase to that admin client."),
        ("User filtering", "morpheus-backend/app/routers/dreams.py filters list/get/delete operations with .eq('user_id', current_user.id)."),
        ("Graph filtering", "morpheus-backend/app/services/graph_logic.py queries dreams with .eq('user_id', user_id) before loading dream_keyword links."),
        ("Token mirroring", "morpheus-frontend/src/hooks/useAuth.js writes morpheus_session_token to localStorage."),
        ("Error leakage", "morpheus-backend/app/routers/dreams.py returns exception strings in some Dream processing failures."),
        ("AI flow", "morpheus-backend/app/services/ai_service.py sends dream text to Gemini for entity extraction, embeddings, and analysis."),
    ]
    for label, text in evidence:
        story.append(p(label, h2))
        story.append(p(text, body))

    story.append(p("Recommended Supabase RLS Baseline", h1))
    story.append(p(
        "This baseline protects user-owned dream rows from other authenticated users through the database API. It does not hide data from project admins or service-role access.",
        body,
    ))
    story.append(p("""
alter table dreams enable row level security;<br/>
<br/>
create policy "Users can view own dreams"<br/>
on dreams for select to authenticated<br/>
using (auth.uid() = user_id);<br/>
<br/>
create policy "Users can insert own dreams"<br/>
on dreams for insert to authenticated<br/>
with check (auth.uid() = user_id);<br/>
<br/>
create policy "Users can update own dreams"<br/>
on dreams for update to authenticated<br/>
using (auth.uid() = user_id)<br/>
with check (auth.uid() = user_id);<br/>
<br/>
create policy "Users can delete own dreams"<br/>
on dreams for delete to authenticated<br/>
using (auth.uid() = user_id);
""", code))

    story.append(PageBreak())
    story.append(p("Priority Fix Plan", h1))
    story.append(p("Immediate fixes", h2))
    story.extend(bullets([
        "Enable MFA on Supabase, Railway, GitHub, and email accounts.",
        "Rotate service-role, Gemini, and Resend keys if any were screenshotted, pasted, or exposed.",
        "Set Railway ALLOWED_ORIGINS exactly to https://morpheus-app.up.railway.app.",
        "Verify RLS policies for dreams and user-owned relationship tables.",
        "Remove frontend .env from git and use .env.example instead.",
    ], body))
    story.append(p("Next engineering fixes", h2))
    story.extend(bullets([
        "Use a user-scoped Supabase client for user-owned reads/writes whenever possible.",
        "Keep service-role usage isolated to admin-only operations and document each use.",
        "Remove manual morpheus_session_token localStorage writes.",
        "Add rate limiting, max text length, and max upload size to AI endpoints.",
        "Replace raw exception messages with generic user-facing errors and structured server logs.",
        "Improve cloud-mode PII redaction before sending dream text to Gemini.",
    ], body))
    story.append(p("High privacy option", h2))
    story.append(p(
        "If Morpheus must promise that even the project owner cannot read dreams, implement client-side encryption before storing raw_text and analysis. This would make AI analysis, search, graphing, and support workflows more complex because the server would not be able to read encrypted content without user-held keys.",
        body,
    ))

    story.append(p("External References", h1))
    story.extend(bullets([
        "Supabase Row Level Security: https://supabase.com/docs/guides/database/postgres/row-level-security",
        "Supabase API keys and service-role/secret keys: https://supabase.com/docs/guides/getting-started/api-keys",
        "Supabase Auth security guidance: https://supabase.com/docs/guides/auth",
    ], small))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(OUT)


if __name__ == "__main__":
    main()
