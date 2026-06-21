from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak, Table, TableStyle
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

OUTPUT = "/home/user/3-Lakes-Logistics/IEBC_CSO_Interview_Guide.pdf"

doc = SimpleDocTemplate(OUTPUT, pagesize=letter,
    rightMargin=0.9*inch, leftMargin=0.9*inch,
    topMargin=0.9*inch, bottomMargin=0.9*inch)

styles = getSampleStyleSheet()
W = letter[0] - 1.8*inch  # usable width

# ── Styles ─────────────────────────────────────────────────────────────────────
title_s = ParagraphStyle("T", parent=styles["Title"],
    fontSize=17, textColor=colors.HexColor("#1a1a2e"),
    alignment=TA_CENTER, leading=21, spaceAfter=4)
sub_s = ParagraphStyle("Sub", parent=styles["Normal"],
    fontSize=10, alignment=TA_CENTER, textColor=colors.HexColor("#555555"),
    leading=14, spaceAfter=18)
h1_s = ParagraphStyle("H1", parent=styles["Heading1"],
    fontSize=12, textColor=colors.HexColor("#1a1a2e"),
    spaceBefore=16, spaceAfter=5, leading=15)
h2_s = ParagraphStyle("H2", parent=styles["Heading2"],
    fontSize=10.5, textColor=colors.HexColor("#1a3a6e"),
    spaceBefore=10, spaceAfter=4, leading=13)
h3_s = ParagraphStyle("H3", parent=styles["Heading3"],
    fontSize=10, textColor=colors.HexColor("#444444"),
    spaceBefore=8, spaceAfter=3, leading=13, fontName="Helvetica-BoldOblique")
body_s = ParagraphStyle("B", parent=styles["Normal"],
    fontSize=10, leading=14, spaceAfter=5, alignment=TA_JUSTIFY)
bullet_s = ParagraphStyle("BL", parent=styles["Normal"],
    fontSize=10, leading=14, spaceAfter=4, leftIndent=16)
q_s = ParagraphStyle("Q", parent=styles["Normal"],
    fontSize=10, leading=14, spaceAfter=3, leftIndent=16,
    textColor=colors.HexColor("#1a1a2e"))
note_s = ParagraphStyle("N", parent=styles["Normal"],
    fontSize=9, leading=13, spaceAfter=4, leftIndent=16,
    textColor=colors.HexColor("#666666"), fontName="Helvetica-Oblique")
tag_s = ParagraphStyle("TAG", parent=styles["Normal"],
    fontSize=8.5, textColor=colors.HexColor("#ffffff"),
    alignment=TA_CENTER, leading=11)
footer_s = ParagraphStyle("F", parent=styles["Normal"],
    fontSize=8, alignment=TA_CENTER,
    textColor=colors.HexColor("#999999"), spaceAfter=0, spaceBefore=10)

def hr(before=4, after=10, thick=0.5, col="#cccccc"):
    return HRFlowable(width="100%", thickness=thick,
        color=colors.HexColor(col), spaceBefore=before, spaceAfter=after)

def section_rule():
    return hr(before=6, after=4, thick=1.5, col="#1a1a2e")

def q_block(num, question, probe=None, look_for=None):
    out = []
    out.append(Paragraph(f"<b>Q{num}.</b> &nbsp;{question}", q_s))
    if probe:
        out.append(Paragraph(f"<i>Follow-up:</i> {probe}", note_s))
    if look_for:
        out.append(Paragraph(f"<i>Listen for:</i> {look_for}", note_s))
    out.append(Spacer(1, 0.05*inch))
    return out

def score_row(label):
    return [Paragraph(label, ParagraphStyle("sr", parent=styles["Normal"], fontSize=9, leading=12)),
            Paragraph("1 &nbsp; 2 &nbsp; 3 &nbsp; 4 &nbsp; 5",
                ParagraphStyle("sc", parent=styles["Normal"], fontSize=9, leading=12, alignment=TA_CENTER)),
            Paragraph("", styles["Normal"])]

story = []

# ══════════════════════════════════════════════════════════════════════════════
# COVER
# ══════════════════════════════════════════════════════════════════════════════
story.append(Spacer(1, 0.2*inch))
story.append(Paragraph("IEBC BUSINESS CONSULTANTS", title_s))
story.append(Paragraph("Chief Strategy Officer (CSO) — Candidate Interview Guide", sub_s))
story.append(Paragraph("Candidate: &nbsp;<b>Cecilia Gulley</b> &nbsp;|&nbsp; Format: Zoom Panel &nbsp;|&nbsp; Panel Size: 3 Interviewers",
    ParagraphStyle("meta", parent=styles["Normal"], fontSize=10, alignment=TA_CENTER,
        textColor=colors.HexColor("#333333"), leading=14, spaceAfter=4)))
story.append(Paragraph("Prepared by: IEBC Business Consultants &nbsp;|&nbsp; Confidential — For Internal Use Only",
    ParagraphStyle("meta2", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER,
        textColor=colors.HexColor("#888888"), leading=13, spaceAfter=18)))
story.append(hr(thick=2, col="#1a1a2e", before=0, after=20))

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — PANEL OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
story.append(Paragraph("INTERVIEW PANEL", h1_s))
story.append(section_rule())
story.append(Paragraph(
    "The following three IEBC representatives will conduct this interview. Each panelist owns a "
    "specific focus area and leads their section of questioning. All panelists score independently "
    "and scores are reconciled after the interview.", body_s))
story.append(Spacer(1, 0.1*inch))

panel = [
    ["PANELIST", "TITLE", "FOCUS AREA"],
    ["Mark Odom", "CEO, IEBC Business Consultants", "Strategic Vision & Leadership"],
    ["Jordan Ellis", "Senior Managing Consultant, IEBC", "Business Consulting Expertise"],
    ["Renée Carter", "Director of Portfolio Operations, IEBC", "3 Lakes Logistics Fit & Ethics"],
]
panel_table = Table(panel, colWidths=[W*0.25, W*0.38, W*0.37])
panel_table.setStyle(TableStyle([
    ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
    ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
    ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE",      (0, 0), (-1, 0), 9),
    ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
    ("FONTSIZE",      (0, 1), (-1, -1), 9),
    ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.HexColor("#f4f6fb"), colors.white]),
    ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING",    (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ("LEFTPADDING",   (0, 0), (-1, -1), 8),
]))
story.append(panel_table)
story.append(Spacer(1, 0.15*inch))

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — ZOOM LOGISTICS
# ══════════════════════════════════════════════════════════════════════════════
story.append(Paragraph("ZOOM INTERVIEW LOGISTICS", h1_s))
story.append(section_rule())

logistics = [
    ["Item", "Detail"],
    ["Platform", "Zoom (host: Mark Odom)"],
    ["Duration", "60–75 minutes total"],
    ["Recording", "Obtain verbal consent from candidate before recording"],
    ["Candidate Location", "Tacoma, Washington (Pacific Time — confirm time zone)"],
    ["IEBC Location", "Detroit, Michigan (Eastern Time)"],
    ["Suggested Time", "10:00 AM PT / 1:00 PM ET (adjust per availability)"],
    ["Pre-Interview", "Send Zoom link 24 hrs in advance; confirm receipt"],
    ["Materials", "Candidate has executed NDA prior to interview"],
]
log_table = Table(logistics, colWidths=[W*0.30, W*0.70])
log_table.setStyle(TableStyle([
    ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#1a3a6e")),
    ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
    ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE",      (0, 0), (-1, 0), 9),
    ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
    ("FONTSIZE",      (0, 1), (-1, -1), 9),
    ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.HexColor("#f4f6fb"), colors.white]),
    ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING",    (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ("LEFTPADDING",   (0, 0), (-1, -1), 8),
]))
story.append(log_table)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — INTERVIEW STRUCTURE / RUN OF SHOW
# ══════════════════════════════════════════════════════════════════════════════
story.append(Paragraph("INTERVIEW STRUCTURE — RUN OF SHOW", h1_s))
story.append(section_rule())

ros = [
    ["Time", "Segment", "Led By"],
    ["0:00 – 0:05", "Welcome, introductions, ground rules", "Mark Odom"],
    ["0:05 – 0:10", "Candidate opening — background overview (candidate-led)", "All"],
    ["0:10 – 0:25", "Section A: Strategic Vision & Leadership", "Mark Odom"],
    ["0:25 – 0:40", "Section B: Business Consulting Expertise", "Jordan Ellis"],
    ["0:40 – 0:55", "Section C: Confidentiality, Ethics & Portfolio Fit", "Renée Carter"],
    ["0:55 – 1:05", "Candidate Q&A — her questions for IEBC", "All"],
    ["1:05 – 1:10", "Closing remarks & next steps", "Mark Odom"],
]
ros_table = Table(ros, colWidths=[W*0.18, W*0.55, W*0.27])
ros_table.setStyle(TableStyle([
    ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
    ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
    ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE",      (0, 0), (-1, 0), 9),
    ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
    ("FONTSIZE",      (0, 1), (-1, -1), 9),
    ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.HexColor("#f4f6fb"), colors.white]),
    ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING",    (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ("LEFTPADDING",   (0, 0), (-1, -1), 8),
]))
story.append(ros_table)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — OPENING SCRIPT
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(Paragraph("OPENING SCRIPT — Mark Odom (CEO)", h1_s))
story.append(section_rule())
story.append(Paragraph(
    '"Cecilia, welcome and thank you for joining us today. My name is Mark Odom, I\'m the CEO of IEBC '
    'Business Consultants. With me today are Jordan Ellis, our Senior Managing Consultant, and Renée '
    'Carter, our Director of Portfolio Operations. We\'re excited to learn more about you and your '
    'vision for the Chief Strategy Officer role.',
    ParagraphStyle("script", parent=styles["Normal"], fontSize=10, leading=14,
        spaceAfter=6, leftIndent=12, textColor=colors.HexColor("#222222"),
        fontName="Helvetica-Oblique")))
story.append(Paragraph(
    'Just a few ground rules: this interview will run approximately 60 to 75 minutes. Each of us will '
    'lead a specific section of questions. We encourage you to be candid and specific — we value '
    'real-world examples. You will also have time at the end to ask us anything. '
    '[Confirm recording consent if applicable.] Let\'s begin — Cecilia, please take 3–5 minutes to '
    'walk us through your background and what drew you to this opportunity."',
    ParagraphStyle("script", parent=styles["Normal"], fontSize=10, leading=14,
        spaceAfter=6, leftIndent=12, textColor=colors.HexColor("#222222"),
        fontName="Helvetica-Oblique")))

# ══════════════════════════════════════════════════════════════════════════════
# SECTION A — MARK ODOM
# ══════════════════════════════════════════════════════════════════════════════
story.append(Paragraph("SECTION A: STRATEGIC VISION &amp; LEADERSHIP", h1_s))
story.append(Paragraph("Led by: Mark Odom, CEO — IEBC Business Consultants &nbsp;|&nbsp; (~15 minutes)", h3_s))
story.append(section_rule())
story.append(Paragraph(
    "This section assesses Cecilia's executive-level strategic thinking, her leadership philosophy, "
    "and her capacity to set and execute enterprise-wide strategy across IEBC and its portfolio companies.", body_s))
story.append(Spacer(1, 0.05*inch))

story.extend(q_block(1,
    "As Chief Strategy Officer, you would be responsible for setting strategic direction across "
    "IEBC Business Consultants and its portfolio company, 3 Lakes Logistics LLC. How do you approach "
    "building a unified strategy that serves both a parent consulting firm and an operationally "
    "distinct portfolio company?",
    probe="What frameworks or models do you use? Can you give an example from a prior role?",
    look_for="Comfort with dual-entity complexity; systems thinking; ability to align divergent business models under one strategic umbrella."))

story.extend(q_block(2,
    "Describe a time you identified a significant strategic gap in an organization and championed "
    "a change initiative to address it. What was the gap, what did you recommend, and what was the outcome?",
    probe="What resistance did you encounter and how did you handle it?",
    look_for="Evidence of proactive thinking, executive courage, measurable outcomes, and stakeholder management."))

story.extend(q_block(3,
    "As CSO, you will be working directly with me as CEO and also interfacing with the leadership "
    "of 3 Lakes Logistics. How do you build trust and credibility quickly with operational leaders "
    "who may be skeptical of a strategy function?",
    probe="How do you balance top-down strategic mandates with bottom-up operational realities?",
    look_for="Emotional intelligence, relationship-building skills, humility paired with executive presence."))

story.extend(q_block(4,
    "Where do you see the business consulting industry heading over the next three to five years, "
    "and how would you position IEBC Business Consultants to lead — not follow — that shift?",
    probe="What would your first 90-day strategic agenda look like if you joined IEBC?",
    look_for="Market awareness, forward-thinking, concrete planning instincts, initiative."))

# ══════════════════════════════════════════════════════════════════════════════
# SECTION B — JORDAN ELLIS
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(Paragraph("SECTION B: BUSINESS CONSULTING EXPERTISE", h1_s))
story.append(Paragraph("Led by: Jordan Ellis, Senior Managing Consultant — IEBC &nbsp;|&nbsp; (~15 minutes)", h3_s))
story.append(section_rule())
story.append(Paragraph(
    "This section evaluates the depth and rigor of Cecilia's consulting background — her methodologies, "
    "client management experience, and ability to deliver measurable value to clients across industries.", body_s))
story.append(Spacer(1, 0.05*inch))

story.extend(q_block(5,
    "Walk us through a consulting engagement where you were the primary strategist. What was the "
    "client's core challenge, what methodology did you apply, and what tangible results did you deliver?",
    probe="How did you measure success? Would the client serve as a reference?",
    look_for="Structured problem-solving, clear methodology, quantified outcomes, client ownership."))

story.extend(q_block(6,
    "IEBC serves clients across multiple industries. How do you quickly build credibility and "
    "relevant expertise when entering an industry that is new to you?",
    probe="Give a specific example of a time you had to get up to speed fast in an unfamiliar sector.",
    look_for="Learning agility, intellectual curiosity, ability to translate general strategy principles to specific domains."))

story.extend(q_block(7,
    "As CSO you will also help develop and strengthen IEBC's own proprietary consulting frameworks "
    "and intellectual property. What methodologies or frameworks have you previously developed or "
    "significantly contributed to? How did those tools improve service delivery?",
    probe="Do you own any of that IP, or does it belong to a prior employer?",
    look_for="IP awareness, creative problem-solving, and understanding of who owns work product — relevant given the NDA IP assignment."))

story.extend(q_block(8,
    "Describe a situation where a client engagement was going off the rails — scope creep, "
    "misaligned expectations, or relationship friction. How did you course-correct?",
    probe="What would you do differently today?",
    look_for="Account management maturity, accountability, conflict resolution, self-awareness."))

# ══════════════════════════════════════════════════════════════════════════════
# SECTION C — RENÉE CARTER
# ══════════════════════════════════════════════════════════════════════════════
story.append(Paragraph("SECTION C: CONFIDENTIALITY, ETHICS &amp; PORTFOLIO FIT", h1_s))
story.append(Paragraph("Led by: Renée Carter, Director of Portfolio Operations — IEBC &nbsp;|&nbsp; (~15 minutes)", h3_s))
story.append(section_rule())
story.append(Paragraph(
    "This section assesses Cecilia's professional ethics, understanding of confidentiality obligations, "
    "and her fit for the unique operational dynamics of IEBC's portfolio company, 3 Lakes Logistics LLC, "
    "which operates a proprietary AI-driven logistics and freight dispatch network.", body_s))
story.append(Spacer(1, 0.05*inch))

story.extend(q_block(9,
    "You have already reviewed and executed a Non-Disclosure Agreement with IEBC Business Consultants. "
    "In your own words, what does that agreement mean to you practically, day to day, in how you "
    "handle information you learn in this role?",
    probe="Have you ever been in a situation where you were pressured to share confidential information? How did you handle it?",
    look_for="Genuine internalization of confidentiality — not just recitation. Ethical backbone. Comfort with boundaries."))

story.extend(q_block(10,
    "As CSO, you will have full visibility into IEBC's investment portfolio, including the structure "
    "and financials of 3 Lakes Logistics. How do you personally manage the firewall between what "
    "you know confidentially and your external professional relationships?",
    probe="Do you have any current clients, advisors, or affiliations that might create a conflict of interest?",
    look_for="Proactive conflict-of-interest awareness, professional maturity, willingness to be transparent."))

story.extend(q_block(11,
    "3 Lakes Logistics operates a proprietary AI agent workforce for freight dispatch — a highly "
    "automated system with significant competitive value. How would you approach learning and "
    "contributing to the strategy of a technology-forward portfolio company when your background "
    "is primarily in consulting?",
    probe="How comfortable are you with AI-driven operations? Have you worked alongside automation or AI tools in a strategic capacity?",
    look_for="Intellectual openness, technology curiosity, humility about learning curves, strategic — not just operational — thinking about AI."))

story.extend(q_block(12,
    "The CSO role will require you to operate effectively from Tacoma, Washington while the IEBC "
    "leadership team and 3 Lakes Logistics are based in Detroit, Michigan. How have you successfully "
    "led or contributed to geographically distributed teams, and what systems do you use to stay "
    "aligned across time zones and locations?",
    probe="What's your preference for communication cadence with a CEO when working remotely?",
    look_for="Remote work maturity, communication discipline, proactive alignment habits, trust-building."))

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — CANDIDATE Q&A
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(Paragraph("CANDIDATE Q&amp;A — Her Questions for IEBC", h1_s))
story.append(section_rule())
story.append(Paragraph(
    "Reserve 10 minutes for Cecilia to ask the panel questions. This is an important signal — "
    "strong candidates ask substantive, forward-looking questions. Note what she asks and what she "
    "does not ask. Suggested facilitator: Mark Odom.", body_s))
story.append(Spacer(1, 0.06*inch))
for item in [
    "What does success look like for the CSO in the first 6 months?",
    "How does IEBC currently make strategic decisions across its portfolio — is it centralized or does each company operate independently?",
    "What are the biggest strategic challenges facing IEBC right now that you're hoping the CSO will help solve?",
    "How does the IEBC leadership team prefer to communicate and how often would I be expected to travel to Detroit?",
    "What is the current relationship dynamic between IEBC and 3 Lakes Logistics at the leadership level?",
]:
    story.append(Paragraph(f"&#8226; &nbsp;<i>Watch for:</i> {item}", bullet_s))

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — SCORING RUBRIC
# ══════════════════════════════════════════════════════════════════════════════
story.append(Paragraph("PANELIST SCORING RUBRIC", h1_s))
story.append(section_rule())
story.append(Paragraph(
    "Each panelist completes this rubric independently immediately after the interview. "
    "Scores are on a scale of <b>1–5</b> (1 = Does not meet expectations, 3 = Meets expectations, "
    "5 = Exceeds expectations). Total max score: <b>50 points per panelist / 150 points combined.</b>", body_s))
story.append(Spacer(1, 0.08*inch))

rubric_data = [
    ["COMPETENCY", "SCORE (1–5)", "NOTES / EVIDENCE"],
    ["Strategic Vision & Long-Term Thinking", "", ""],
    ["Executive Leadership & Presence", "", ""],
    ["Business Consulting Depth & Methodology", "", ""],
    ["Client Management & Relationship Skills", "", ""],
    ["IP & Confidentiality Awareness", "", ""],
    ["Ethics & Professional Integrity", "", ""],
    ["3 Lakes Logistics / Logistics Sector Fit", "", ""],
    ["Technology & AI Openness", "", ""],
    ["Remote Work & Communication Discipline", "", ""],
    ["Overall Cultural Fit with IEBC", "", ""],
    ["TOTAL SCORE (out of 50)", "", ""],
]
rub_table = Table(rubric_data, colWidths=[W*0.42, W*0.15, W*0.43])
rub_table.setStyle(TableStyle([
    ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
    ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
    ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE",      (0, 0), (-1, 0), 9),
    ("FONTNAME",      (0, 1), (-1, -2), "Helvetica"),
    ("FONTSIZE",      (0, 1), (-1, -2), 9),
    ("FONTNAME",      (0, -1), (-1, -1), "Helvetica-Bold"),
    ("FONTSIZE",      (0, -1), (-1, -1), 9),
    ("BACKGROUND",    (0, -1), (-1, -1), colors.HexColor("#e8eaf0")),
    ("ROWBACKGROUNDS",(0, 1), (-1, -2), [colors.HexColor("#f4f6fb"), colors.white]),
    ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING",    (0, 0), (-1, -1), 7),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ("LEFTPADDING",   (0, 0), (-1, -1), 8),
    ("ALIGN",         (1, 0), (1, -1), "CENTER"),
]))
story.append(rub_table)

story.append(Spacer(1, 0.15*inch))
story.append(Paragraph("Panelist Name: ______________________________ &nbsp;&nbsp; Date: ___________________", body_s))
story.append(Paragraph("Overall Recommendation:", body_s))
rec_data = [["Strongly Recommend", "Recommend", "Recommend with Reservations", "Do Not Recommend"]]
rec_table = Table(rec_data, colWidths=[W*0.25]*4)
rec_table.setStyle(TableStyle([
    ("BOX",         (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
    ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
    ("FONTNAME",    (0, 0), (-1, -1), "Helvetica"),
    ("FONTSIZE",    (0, 0), (-1, -1), 9),
    ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
    ("TOPPADDING",  (0, 0), (-1, -1), 8),
    ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
    ("ROWBACKGROUNDS",(0, 0), (-1, -1), [colors.HexColor("#f9f9f9")]),
]))
story.append(rec_table)
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("Comments / Key Observations:", body_s))
story.append(Paragraph("_" * 90, ParagraphStyle("line", parent=styles["Normal"], fontSize=10, spaceAfter=6, leading=18)))
story.append(Paragraph("_" * 90, ParagraphStyle("line", parent=styles["Normal"], fontSize=10, spaceAfter=6, leading=18)))
story.append(Paragraph("_" * 90, ParagraphStyle("line", parent=styles["Normal"], fontSize=10, spaceAfter=6, leading=18)))

# ══════════════════════════════════════════════════════════════════════════════
# CLOSING
# ══════════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(Paragraph("CLOSING SCRIPT — Mark Odom (CEO)", h1_s))
story.append(section_rule())
story.append(Paragraph(
    '"Cecilia, thank you so much for your time today — this has been a genuinely impressive conversation. '
    'We have a few more steps in our process before we make a decision. You can expect to hear from us '
    'within [X business days]. Please don\'t hesitate to reach out if you have any additional questions '
    'in the meantime. We appreciate your interest in IEBC Business Consultants and look forward to '
    'staying in touch."',
    ParagraphStyle("script2", parent=styles["Normal"], fontSize=10, leading=14,
        spaceAfter=6, leftIndent=12, textColor=colors.HexColor("#222222"),
        fontName="Helvetica-Oblique")))
story.append(Spacer(1, 0.15*inch))
story.append(Paragraph("POST-INTERVIEW DEBRIEF CHECKLIST", h2_s))
for item in [
    "Each panelist completes scoring rubric within 30 minutes of call end.",
    "Panelists share scores privately with Mark Odom (do not discuss before scoring independently).",
    "Mark Odom convenes 15-minute debrief call to reconcile scores and align on recommendation.",
    "Candidate is notified of next steps within the committed timeframe.",
    "All interview notes and scorecards are retained in IEBC's confidential hiring file.",
]:
    story.append(Paragraph(f"&#9744; &nbsp;{item}", bullet_s))

story.append(hr(before=20, after=6, thick=1, col="#1a1a2e"))
story.append(Paragraph(
    "IEBC Business Consultants — Confidential Internal Document — CSO Candidate: Cecilia Gulley",
    footer_s))

doc.build(story)
print(f"PDF generated: {OUTPUT}")
