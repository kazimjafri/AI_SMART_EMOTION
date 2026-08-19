# ===========================
# reports/pdf_generator.py
# Generate styled PDF interview report with emotion analysis
# ===========================

import io
import os
from datetime import datetime

LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "logo.png")

def generate_interview_report_pdf(
    candidate_name: str,
    job_title: str,
    company: str,
    questions: list,
    answers: dict,
    scores: dict,
    completed_at: str,
    emotion_summary: dict = None,
    overall_score: int = None,
    terminated_due_to_cheating: bool = False,
    violations_count: int = 0
) -> bytes:
    """
    Build a styled PDF report and return raw bytes.
    Includes: score summary, emotion analysis, per-question breakdown, and anti-cheat alerts.
    """
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.85 * inch,
        rightMargin=0.85 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
    )

    styles = getSampleStyleSheet()
    GREEN  = colors.HexColor("#059669")
    RED    = colors.HexColor("#dc2626")
    DARK   = colors.HexColor("#0d2218")
    MUTED  = colors.HexColor("#6b7280")
    LIGHT  = colors.HexColor("#f9fcfa")

    title_style = ParagraphStyle(
        "TitleStyle", parent=styles["Heading1"],
        fontSize=20, textColor=GREEN,
        spaceAfter=4, fontName="Helvetica-Bold",
    )
    sub_style = ParagraphStyle(
        "SubStyle", parent=styles["Normal"],
        fontSize=10, textColor=colors.HexColor("#4a7060"),
        spaceAfter=14, fontName="Helvetica",
    )
    section_style = ParagraphStyle(
        "SectionStyle", parent=styles["Heading2"],
        fontSize=12, textColor=DARK,
        spaceBefore=16, spaceAfter=6, fontName="Helvetica-Bold",
    )
    q_style = ParagraphStyle(
        "QStyle", parent=styles["Normal"],
        fontSize=10, textColor=DARK,
        fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=3,
    )
    a_style = ParagraphStyle(
        "AStyle", parent=styles["Normal"],
        fontSize=9.5, textColor=colors.HexColor("#374151"),
        fontName="Helvetica", spaceAfter=3, leftIndent=12,
    )
    fb_style = ParagraphStyle(
        "FBStyle", parent=styles["Normal"],
        fontSize=9, textColor=MUTED,
        fontName="Helvetica-Oblique", spaceAfter=6, leftIndent=12,
    )
    small_style = ParagraphStyle(
        "SmallStyle", parent=styles["Normal"],
        fontSize=8.5, textColor=colors.HexColor("#9ca3af"),
        fontName="Helvetica", spaceAfter=2,
    )
    emotion_label_style = ParagraphStyle(
        "ELabel", parent=styles["Normal"],
        fontSize=9, textColor=MUTED,
        fontName="Helvetica", spaceAfter=2,
    )

    story = []

    # ── Header ──
    date_str = completed_at[:10] if completed_at else datetime.utcnow().strftime("%Y-%m-%d")
    header_text_cell = [
        Paragraph("AI Smart Emotion Interviewer | Candidate Evaluation Report", title_style),
        Paragraph(f"{candidate_name}  ·  {job_title}{f' at {company}' if company else ''}  ·  {date_str}", sub_style),
    ]

    if os.path.exists(LOGO_PATH):
        logo_img = Image(LOGO_PATH, width=0.55 * inch, height=0.55 * inch)
        header_table = Table([[logo_img, header_text_cell]], colWidths=[0.7 * inch, 5.3 * inch])
        header_table.setStyle(TableStyle([
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",  (0, 0), (0, 0), 0),
            ("RIGHTPADDING", (0, 0), (0, 0), 10),
            ("LEFTPADDING",  (1, 0), (1, 0), 0),
            ("TOPPADDING",   (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
        ]))
        story.append(header_table)
    else:
        story.extend(header_text_cell)

    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2ede8")))
    story.append(Spacer(1, 10))

    # ── Anti-Cheating Warning Banner ──
    if terminated_due_to_cheating:
        story.append(Paragraph(
            f"<font color='#dc2626'><b>🚨 INTERVIEW TERMINATED DUE TO RULE VIOLATIONS</b></font><br/>"
            f"<font color='#374151'>Candidate switched tabs/exited fullscreen {violations_count} times during the session.</font>",
            ParagraphStyle("WarningStyle", parent=styles["Normal"], fontSize=11, spaceAfter=14)
        ))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#dc2626")))
        story.append(Spacer(1, 10))

    # ── Score summary table ──
    total_q   = len(questions)
    answered  = sum(1 for i in range(total_q) if answers.get(i, "").strip())
    correct   = sum(1 for i in range(total_q) if scores.get(i, {}).get("correct", False))
    incorrect = answered - correct
    
    if overall_score is not None:
        avg_score = overall_score
    else:
        avg_score = round(sum(scores.get(i, {}).get("score", 0) for i in range(total_q)) / total_q) if total_q else 0
        
    if terminated_due_to_cheating:
        pass_fail = "FAIL ✗ (TERMINATED)"
        pf_color = RED
    else:
        pass_fail = "PASS ✓" if avg_score >= 60 else "FAIL ✗"
        pf_color  = GREEN if avg_score >= 60 else RED

    story.append(Paragraph("Performance Summary", section_style))
    summary_data = [
        ["Metric",           "Value"],
        ["Overall Score",    f"{avg_score} / 100"],
        ["Result",           pass_fail],
        ["Total Questions",  str(total_q)],
        ["Answered",         str(answered)],
        ["Correct (≥60%)",   str(correct)],
        ["Incorrect (<60%)", str(incorrect)],
        ["Skipped",          str(total_q - answered)],
    ]
    t = Table(summary_data, colWidths=[2.6 * inch, 2.4 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), GREEN),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 9),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [LIGHT, colors.white]),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 9),
        ("TEXTCOLOR",     (0, 1), (0, -1), colors.HexColor("#374151")),
        ("TEXTCOLOR",     (1, 2), (1, 2),  pf_color),
        ("FONTNAME",      (1, 2), (1, 2),  "Helvetica-Bold"),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#e2ede8")),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("ALIGN",         (1, 0), (1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t)
    story.append(Spacer(1, 16))

    # ── Emotion Analysis section ──
    if emotion_summary and emotion_summary.get("total_samples", 0) > 0:
        story.append(Paragraph("Emotion & Behavioral Analysis", section_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2ede8")))
        story.append(Spacer(1, 6))

        avg_conf = emotion_summary.get("avg_confidence", 0)
        avg_anx  = emotion_summary.get("avg_anxiety",    0)
        avg_comp = emotion_summary.get("avg_composed",   0)
        dom_em   = emotion_summary.get("dominant_emotion","Neutral")
        assess   = emotion_summary.get("assessment",     "")
        em_score = emotion_summary.get("overall_score",  50)
        samples  = emotion_summary.get("total_samples",  0)

        emotion_data = [
            ["Metric",                  "Score",       "Assessment"],
            ["Confidence Level",        f"{avg_conf}%", _score_label(avg_conf)],
            ["Anxiety Level",           f"{avg_anx}%",  _anxiety_label(avg_anx)],
            ["Composure",               f"{avg_comp}%", _score_label(avg_comp)],
            ["Dominant Emotion",        dom_em,         ""],
            ["Behavioral Score",        f"{em_score}/100",""],
            ["Frames Analyzed",         str(samples),   ""],
        ]
        et = Table(emotion_data, colWidths=[2.2 * inch, 1.2 * inch, 2.6 * inch])
        et.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#0d2218")),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0), 8.5),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [LIGHT, colors.white]),
            ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",      (0, 1), (-1, -1), 8.5),
            ("TEXTCOLOR",     (0, 1), (0, -1), colors.HexColor("#374151")),
            ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#e2ede8")),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(et)

        if assess:
            story.append(Spacer(1, 8))
            story.append(Paragraph(f"Assessment: {assess}", emotion_label_style))

        em_dist = emotion_summary.get("emotion_distribution", {})
        if em_dist:
            story.append(Spacer(1, 6))
            dist_text = "  ·  ".join(f"{em}: {pct}%" for em, pct in em_dist.items())
            story.append(Paragraph(f"Emotion breakdown: {dist_text}", emotion_label_style))

        story.append(Spacer(1, 14))

    # ── Per-question breakdown ──
    story.append(Paragraph("Question-by-Question Breakdown", section_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2ede8")))

    for i, q_obj in enumerate(questions):
        q_text   = q_obj.get("question", "—")
        category = q_obj.get("category", "—")
        answer   = answers.get(i, "").strip() or "(No answer recorded)"
        sc       = scores.get(i, {})
        score    = sc.get("score",    0)
        feedback = sc.get("feedback", "—")
        correct  = sc.get("correct",  False)

        result_label = "✓ Correct" if correct else "✗ Needs Work"
        
        story.append(Paragraph(f"Q{i+1}. [{category}]  {q_text}", q_style))
        story.append(Paragraph(f"Answer: {answer}", a_style))
        story.append(Paragraph(
            f"<font color='{'#059669' if correct else '#dc2626'}'>"
            f"<b>Score: {score}/100 — {result_label}</b></font>",
            ParagraphStyle("SL", parent=a_style, fontSize=9, spaceAfter=2)
        ))
        story.append(Paragraph(f"Feedback: {feedback}", fb_style))
        story.append(HRFlowable(width="100%", thickness=0.3, color=colors.HexColor("#edf5f0")))

    story.append(Spacer(1, 20))
    story.append(Paragraph(f"Generated by AI Smart Emotion Interviewer  ·  {completed_at[:19] if completed_at else ''}", small_style))

    doc.build(story)
    return buf.getvalue()

def _score_label(score: int) -> str:
    if score >= 75: return "Excellent"
    if score >= 55: return "Good"
    if score >= 35: return "Moderate"
    return "Needs Work"

def _anxiety_label(score: int) -> str:
    if score <= 20: return "Very low | calm"
    if score <= 40: return "Low | composed"
    if score <= 60: return "Moderate | noticeable"
    return "High | significant stress"