from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak, Table, TableStyle
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from datetime import date

OUTPUT = "/home/user/3-Lakes-Logistics/3LL_Driver_Post_Signup_Questionnaire.pdf"
BLUE = "#1a4fa8"
NAVY = "#1e3a8a"
AMBER = "#f59e0b"

doc = SimpleDocTemplate(OUTPUT, pagesize=letter,
    rightMargin=0.9*inch, leftMargin=0.9*inch,
    topMargin=0.9*inch, bottomMargin=0.9*inch)

styles = getSampleStyleSheet()
W = letter[0] - 1.8*inch

title_s = ParagraphStyle("T", parent=styles["Title"],
    fontSize=17, textColor=colors.HexColor(NAVY),
    alignment=TA_CENTER, leading=21, spaceAfter=4)
sub_s = ParagraphStyle("Sub", parent=styles["Normal"],
    fontSize=10, alignment=TA_CENTER, textColor=colors.HexColor("#555555"),
    leading=14, spaceAfter=4)
meta_s = ParagraphStyle("meta", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER,
    textColor=colors.HexColor("#888888"), leading=13, spaceAfter=18)
h1_s = ParagraphStyle("H1", parent=styles["Heading1"],
    fontSize=12, textColor=colors.HexColor(NAVY),
    spaceBefore=16, spaceAfter=5, leading=15)
h3_s = ParagraphStyle("H3", parent=styles["Heading3"],
    fontSize=9.5, textColor=colors.HexColor("#555555"),
    spaceBefore=2, spaceAfter=6, leading=13, fontName="Helvetica-Oblique")
body_s = ParagraphStyle("B", parent=styles["Normal"],
    fontSize=10, leading=14, spaceAfter=6, alignment=TA_JUSTIFY)
q_s = ParagraphStyle("Q", parent=styles["Normal"],
    fontSize=10, leading=15, spaceAfter=2, leftIndent=14,
    textColor=colors.HexColor("#1f2937"))
sub_q_s = ParagraphStyle("SQ", parent=styles["Normal"],
    fontSize=9.5, leading=13, spaceAfter=2, leftIndent=30,
    textColor=colors.HexColor("#374151"))
note_s = ParagraphStyle("N", parent=styles["Normal"],
    fontSize=8.5, leading=12, spaceAfter=8, leftIndent=14,
    textColor=colors.HexColor("#6b7280"), fontName="Helvetica-Oblique")
footer_s = ParagraphStyle("F", parent=styles["Normal"],
    fontSize=8, alignment=TA_CENTER,
    textColor=colors.HexColor("#999999"), spaceAfter=0, spaceBefore=10)


def hr(before=4, after=10, thick=0.5, col="#cccccc"):
    return HRFlowable(width="100%", thickness=thick,
        color=colors.HexColor(col), spaceBefore=before, spaceAfter=after)


def section_rule():
    return hr(before=6, after=8, thick=1.5, col=NAVY)


def section_header(num, title):
    out = [Paragraph(f"SECTION {num} &nbsp;—&nbsp; {title.upper()}", h1_s), section_rule()]
    return out


def question(num, text, kind=None, options=None):
    out = [Paragraph(f"<b>{num}.</b> &nbsp;{text}", q_s)]
    if kind:
        out.append(Paragraph(f"[{kind}]", note_s))
    if options:
        opt_str = " &nbsp;/&nbsp; ".join(f"&#9744; {o}" for o in options)
        out.append(Paragraph(opt_str, sub_q_s))
        out.append(Spacer(1, 0.06*inch))
    return out


story = []

# ══════════════════════════════════════════════════════════════════════════
# COVER
# ══════════════════════════════════════════════════════════════════════════
story.append(Spacer(1, 0.15*inch))
story.append(Paragraph("3 LAKES LIGHT FLEET", title_s))
story.append(Paragraph("Post-Signup Driver Questionnaire", sub_s))
story.append(Paragraph(
    "Sent as a follow-up to the driver welcome email &nbsp;|&nbsp; "
    f"Prepared: {date.today().strftime('%B %d, %Y')}",
    meta_s))
story.append(hr(thick=2, col=NAVY, before=0, after=16))

story.append(Paragraph(
    "This questionnaire is delivered to a new Light Fleet driver shortly after the automated welcome "
    "email/SMS sequence (Maya workflow), and before the scheduled welcome call. It confirms driver "
    "readiness, captures service and scheduling preferences, and surfaces anything blocking a first "
    "trip — so onboarding coordinators and the welcome-call script have real signal before outreach.",
    body_s))
story.append(Spacer(1, 0.05*inch))

purpose_data = [
    ["Audience", "Newly signed-up Light Fleet drivers (NEMT, Executive, Courier, Gig)"],
    ["Trigger point", "After welcome email/SMS (Step 2) — before welcome call (Step 3)"],
    ["Format", "25 questions across 8 sections; multiple-choice + open text"],
    ["Owner", "Onboarding / Driver Success"],
]
purpose_table = Table(purpose_data, colWidths=[W*0.25, W*0.75])
purpose_table.setStyle(TableStyle([
    ("BACKGROUND",    (0, 0), (0, -1), colors.HexColor("#f4f6fb")),
    ("FONTNAME",      (0, 0), (0, -1), "Helvetica-Bold"),
    ("FONTNAME",      (1, 0), (1, -1), "Helvetica"),
    ("FONTSIZE",      (0, 0), (-1, -1), 9),
    ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING",    (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ("LEFTPADDING",   (0, 0), (-1, -1), 8),
]))
story.append(purpose_table)

# ══════════════════════════════════════════════════════════════════════════
# SECTION 1 — Confirm details
# ══════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.extend(section_header(1, "Confirm Your Details"))
story.extend(question(1, "Is the name and phone number on file correct?", options=["Yes", "No — please provide correction"]))
story.extend(question(2, "What's the best email address to reach you at?", kind="open text"))
story.extend(question(3, "What city/area will you primarily be operating in?", kind="open text"))

# ══════════════════════════════════════════════════════════════════════════
# SECTION 2 — Vehicle & Equipment
# ══════════════════════════════════════════════════════════════════════════
story.extend(section_header(2, "Vehicle &amp; Equipment Readiness"))
story.extend(question(4, "What vehicle will you be using? (Year / Make / Model)", kind="open text"))
story.extend(question(5, "Is your vehicle currently insured, registered, and under 10 years old?", options=["Yes", "No"]))
story.extend(question(6, "Do you have a smartphone with data service to run the driver app and partner platform apps?", options=["Yes", "No"]))
story.extend(question(7, "Any known vehicle issues we should be aware of before your first trip?", kind="open text"))

# ══════════════════════════════════════════════════════════════════════════
# SECTION 3 — Approved services
# ══════════════════════════════════════════════════════════════════════════
story.extend(section_header(3, "Approved Services — Confirm &amp; Prioritize"))
story.extend(question(8, "You were approved for the services listed in your welcome email. Does this match what you signed up for?", options=["Yes", "No"]))
story.extend(question(9, "If approved for more than one service, which would you like to receive trips for first?",
    options=["Medical Transport (NEMT)", "Executive Transfers", "Same-Day Courier", "Gig / On-Demand"]))
story.extend(question(10, "Do you have prior experience in any of these service types? (e.g. rideshare, courier, NEMT, chauffeur)", kind="open text"))

# ══════════════════════════════════════════════════════════════════════════
# SECTION 4 — Platform & app setup
# ══════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.extend(section_header(4, "Platform &amp; App Setup"))
story.extend(question(11, "Have you downloaded the app(s) for your approved service(s) — Curri, Roadie, Modivcare, MTM, Uber/Lyft Business, 3 Lakes Driver Portal?",
    options=["Yes, all", "Some", "Not yet"]))
story.extend(question(12, "If “Some” or “Not yet” — which app(s) do you still need help setting up?", kind="checklist"))
story.extend(question(13, "Have you set up direct deposit / your payout method in the Driver Portal?", options=["Yes", "No", "Need help"]))

# ══════════════════════════════════════════════════════════════════════════
# SECTION 5 — Availability
# ══════════════════════════════════════════════════════════════════════════
story.extend(section_header(5, "Availability &amp; Scheduling"))
story.extend(question(14, "What days are you generally available?", options=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]))
story.extend(question(15, "What time blocks work best for you?", options=["Early AM", "Daytime", "Evening", "Overnight", "Flexible"]))
story.extend(question(16, "Roughly how many trips per week are you hoping to run?", kind="open text"))
story.extend(question(17, "Is this full-time, part-time, or occasional/gig work for you?", options=["Full-time", "Part-time", "Occasional/gig"]))

# ══════════════════════════════════════════════════════════════════════════
# SECTION 6 — Support & training
# ══════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.extend(section_header(6, "Support &amp; Training Needs"))
story.extend(question(18, "Do you have questions about how dispatch, trip acceptance, or pay works?", options=["Yes — see notes below", "No"]))
story.extend(question(19, "Would you like a live walkthrough call with your onboarding coordinator before your first trip?", options=["Yes", "No"]))
story.extend(question(20, "Is there anything blocking you from accepting your first trip right now?", kind="open text"))

# ══════════════════════════════════════════════════════════════════════════
# SECTION 7 — Communication preferences
# ══════════════════════════════════════════════════════════════════════════
story.extend(section_header(7, "Communication Preferences"))
story.extend(question(21, "How do you prefer to be contacted for dispatch and updates?", options=["Text", "Call", "Email", "App notification"]))
story.extend(question(22, "Are you okay receiving occasional promotional or bonus-tier updates via SMS?", options=["Yes", "No"]))

# ══════════════════════════════════════════════════════════════════════════
# SECTION 8 — Feedback
# ══════════════════════════════════════════════════════════════════════════
story.extend(section_header(8, "Feedback"))
story.extend(question(23, "How did you hear about 3 Lakes Light Fleet?", kind="open text / referral name"))
story.extend(question(24, "On a scale of 1–5, how clear was the sign-up and welcome process so far?", options=["1", "2", "3", "4", "5"]))
story.extend(question(25, "Anything else we should know before your first assignment?", kind="open text"))

# ══════════════════════════════════════════════════════════════════════════
# IMPLEMENTATION NOTES
# ══════════════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(Paragraph("IMPLEMENTATION NOTES", h1_s))
story.append(section_rule())
for item in [
    "Natural insertion point: a new scheduled step between the welcome email (Step 2) and the "
    "welcome call (Step 3) in the Maya welcome workflow, so answers — especially availability, "
    "training needs, and blockers — can feed the welcome-call script.",
    "Responses can be stored in a new driver_intake_responses table keyed by driver_id, mirroring "
    "how insurance_compliance / banking_accounts are keyed off carrier_id elsewhere in the system.",
    "Recommended delivery channel: emailed link to a short hosted form (mobile-friendly), with an "
    "SMS nudge if not completed within 24 hours.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", body_s))

story.append(hr(before=20, after=6, thick=1, col=NAVY))
story.append(Paragraph(
    "3 Lakes Logistics — Light Fleet Onboarding — Internal Use",
    footer_s))

doc.build(story)
print(f"PDF generated: {OUTPUT}")
