"""PDF report rendering.

Renders a ``ReportRead`` into a clean, branded single-page-plus PDF using
reportlab's platypus flowables. Fonts: a Unicode TrueType font is preferred so
smart quotes and dashes survive; when none is found it falls back to the built-in
Helvetica with Latin-1 sanitization so rendering can never fail on characters.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.report import ReportRead

#: Brand colors (teal/cyan accents on white).
BRAND = colors.HexColor("#0d9488")
BRAND_SOFT = colors.HexColor("#ccfbf1")
INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#e2e8f0")

#: Known TrueType fonts, tried in order so we get a Unicode-capable font.
_FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/segoeui.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
)

_FONT = "Helvetica"


def _register_font() -> None:
    """Register a Unicode font if one is available on this machine."""
    global _FONT
    for path in _FONT_CANDIDATES:
        if not path.is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont("InterVueSans", str(path)))
            _FONT = "InterVueSans"
            return
        except Exception:  # noqa: BLE001 - try the next candidate
            continue


def _text(value: str) -> str:
    """Make a string safe for the active PDF font."""
    text = str(value or "").strip()
    if _FONT == "Helvetica":
        return text.encode("latin-1", "replace").decode("latin-1")
    return text


def _bullets(items: list[str]) -> list[Paragraph]:
    """Render a list of strings as bullet paragraphs."""
    if not items:
        return [Paragraph(_text("—"), _style("body", textColor=MUTED))]
    return [
        Paragraph(f"•&nbsp;&nbsp;{_text(item)}", _style("body"))
        for item in items
    ]


def _style(name: str, **overrides) -> ParagraphStyle:
    """Return a reportlab ParagraphStyle with the given overrides."""
    base = getSampleStyleSheet()
    defaults = {
        "fontName": _FONT,
    }
    if name == "title":
        defaults.update(
            {
                "fontName": _FONT,
                "fontSize": 22,
                "leading": 26,
                "textColor": INK,
                "alignment": TA_CENTER,
                "spaceAfter": 2 * mm,
            }
        )
    elif name == "subtitle":
        defaults.update(
            {
                "fontName": _FONT,
                "fontSize": 11,
                "leading": 15,
                "textColor": MUTED,
                "alignment": TA_CENTER,
                "spaceAfter": 6 * mm,
            }
        )
    elif name == "section":
        defaults.update(
            {
                "fontName": _FONT,
                "fontSize": 13,
                "leading": 17,
                "textColor": BRAND,
                "spaceBefore": 6 * mm,
                "spaceAfter": 3 * mm,
            }
        )
    elif name == "body":
        defaults.update(
            {
                "fontName": _FONT,
                "fontSize": 10,
                "leading": 15,
                "textColor": INK,
                "spaceAfter": 2 * mm,
            }
        )
    elif name == "small":
        defaults.update(
            {
                "fontName": _FONT,
                "fontSize": 8.5,
                "leading": 12,
                "textColor": MUTED,
            }
        )
    elif name == "score":
        defaults.update(
            {
                "fontName": _FONT,
                "fontSize": 40,
                "leading": 44,
                "textColor": BRAND,
                "alignment": TA_CENTER,
            }
        )
    else:
        defaults.update(base[name])
    defaults.update(overrides)
    return ParagraphStyle(name=name, **defaults)


def render_report_pdf(report: ReportRead) -> bytes:
    """Render a ``ReportRead`` into PDF bytes."""
    _register_font()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"InterVue AI Report — {report.candidate.name}",
        author="InterVue AI",
    )

    story: list = []

    story.append(Paragraph(_text("InterVue AI — Interview Report"), _style("title")))
    story.append(
        Paragraph(
            _text(
                f"{report.candidate.name} · {report.candidate.role or 'Technical Candidate'}"
                + (f" · {report.candidate.email}" if report.candidate.email else "")
            ),
            _style("subtitle"),
        )
    )
    story.append(HRFlowable(width="100%", thickness=1, color=LINE, spaceAfter=6 * mm))

    # --- Candidate / session facts -------------------------------------------
    facts = [
        ["Candidate", _text(report.candidate.name)],
        ["Target role", _text(report.candidate.role) or "—"],
        ["Email", _text(report.candidate.email) or "—"],
        ["Session", _text(report.session_id)],
        ["Completed", _text(report.completed_at or "—")],
    ]
    facts_table = Table(facts, colWidths=[30 * mm, 120 * mm])
    facts_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
                ("TEXTCOLOR", (1, 0), (1, -1), INK),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("BOX", (0, 0), (-1, -1), 0.75, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
            ]
        )
    )
    story.append(facts_table)

    # --- Overall score --------------------------------------------------------
    score_card = Table(
        [
            [Paragraph(_text("Overall score"), _style("small"))],
            [Paragraph(f"{report.feedback.overall_score:.1f} / 10", _style("score"))],
        ],
        colWidths=[120 * mm],
    )
    score_card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BRAND_SOFT),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(Spacer(1, 6 * mm))
    story.append(score_card)

    # --- Summary --------------------------------------------------------------
    story.append(Paragraph(_text("Summary"), _style("section")))
    story.append(Paragraph(_text(report.feedback.summary) or "—", _style("body")))

    # --- Strengths / improvements ---------------------------------------------
    story.append(Paragraph(_text("Strengths"), _style("section")))
    story.extend(_bullets(report.feedback.strengths))

    story.append(Paragraph(_text("Areas to improve"), _style("section")))
    story.extend(_bullets(report.feedback.improvements))

    # --- Topic breakdown ------------------------------------------------------
    story.append(Paragraph(_text("Topic breakdown"), _style("section")))
    if report.feedback.topics:
        rows = [[Paragraph(_text("Topic"), _style("small")), Paragraph(_text("Score"), _style("small"))]]
        for topic in report.feedback.topics:
            rows.append(
                [
                    Paragraph(_text(topic.title or topic.topic_id), _style("body")),
                    Paragraph(f"{topic.average_score:.1f} / 10", _style("body")),
                ]
            )
        topics_table = Table(rows, colWidths=[90 * mm, 30 * mm])
        topics_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), _FONT),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BACKGROUND", (0, 0), (-1, 0), BRAND_SOFT),
                    ("TEXTCOLOR", (1, 1), (1, -1), BRAND),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("BOX", (0, 0), (-1, -1), 0.75, LINE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                ]
            )
        )
        story.append(topics_table)
    else:
        story.append(Paragraph(_text("No topic scores were recorded."), _style("body")))

    # --- Transcript -----------------------------------------------------------
    story.append(Paragraph(_text("Conversation transcript"), _style("section")))
    if report.messages:
        transcript_rows = [[Paragraph(_text("Turn"), _style("small")), Paragraph(_text("Content"), _style("small"))]]
        for index, message in enumerate(report.messages, start=1):
            role = _text(message.role)
            content = _text(message.content)
            if len(content) > 400:
                content = content[:400] + "…"
            transcript_rows.append([Paragraph(f"{index}", _style("small")), Paragraph(content, _style("body"))])
        transcript_table = Table(transcript_rows, colWidths=[12 * mm, 138 * mm])
        transcript_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), BRAND_SOFT),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TEXTCOLOR", (0, 1), (0, -1), MUTED),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
                ]
            )
        )
        story.append(transcript_table)
        story.append(PageBreak())
    else:
        story.append(Paragraph(_text("No transcript recorded."), _style("body")))

    doc.build(story)
    return buffer.getvalue()
