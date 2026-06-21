from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT

OUTPUT = "/home/user/3-Lakes-Logistics/IEBC_3LL_Revenue_Roadmap.pdf"

doc = SimpleDocTemplate(OUTPUT, pagesize=letter,
    rightMargin=0.9*inch, leftMargin=0.9*inch,
    topMargin=0.9*inch, bottomMargin=0.9*inch)

styles = getSampleStyleSheet()
W = letter[0] - 1.8*inch

title_s = ParagraphStyle("T", parent=styles["Title"], fontSize=17,
    textColor=colors.HexColor("#1a1a2e"), alignment=TA_CENTER, leading=22, spaceAfter=4)
sub_s = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=10,
    alignment=TA_CENTER, textColor=colors.HexColor("#555555"), leading=14, spaceAfter=18)
h1_s = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=12,
    textColor=colors.HexColor("#1a1a2e"), spaceBefore=16, spaceAfter=5, leading=15)
h2_s = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=10.5,
    textColor=colors.HexColor("#1a3a6e"), spaceBefore=10, spaceAfter=4, leading=13)
body_s = ParagraphStyle("B", parent=styles["Normal"], fontSize=10,
    leading=15, spaceAfter=6, alignment=TA_JUSTIFY)
bullet_s = ParagraphStyle("BL", parent=styles["Normal"], fontSize=10,
    leading=14, spaceAfter=4, leftIndent=16)
action_s = ParagraphStyle("ACT", parent=styles["Normal"], fontSize=10,
    leading=14, spaceAfter=4, leftIndent=16, textColor=colors.HexColor("#1a3a6e"))
bold_body_s = ParagraphStyle("BB", parent=styles["Normal"], fontSize=10,
    leading=15, spaceAfter=6, fontName="Helvetica-Bold")
footer_s = ParagraphStyle("F", parent=styles["Normal"], fontSize=8,
    alignment=TA_CENTER, textColor=colors.HexColor("#999999"), spaceAfter=0, spaceBefore=10)
callout_s = ParagraphStyle("CO", parent=styles["Normal"], fontSize=11,
    leading=16, spaceAfter=0, alignment=TA_CENTER, textColor=colors.white, fontName="Helvetica-Bold")

def hr(before=4, after=10, thick=0.5, col="#cccccc"):
    return HRFlowable(width="100%", thickness=thick,
        color=colors.HexColor(col), spaceBefore=before, spaceAfter=after)

def section_rule():
    return hr(before=4, after=6, thick=1.5, col="#1a1a2e")

def callout(text, bg="#1a3a6e"):
    t = Table([[Paragraph(text, callout_s)]], colWidths=[W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor(bg)),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
    ]))
    return t

story = []

# ── COVER ─────────────────────────────────────────────────────────────────────
story.append(Spacer(1, 0.2*inch))
story.append(Paragraph("IEBC BUSINESS CONSULTANTS", title_s))
story.append(Paragraph("3 Lakes Logistics LLC — Portfolio Company", sub_s))
story.append(callout("REVENUE ROADMAP: $10,000 IN 90 DAYS → $100,000 IN 12 MONTHS"))
story.append(Spacer(1, 10))
story.append(Paragraph("Prepared for: Mark Odom, CEO &nbsp;|&nbsp; Confidential Strategic Planning Document",
    ParagraphStyle("meta", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER,
        textColor=colors.HexColor("#888888"), leading=13, spaceAfter=18)))
story.append(hr(thick=2, col="#1a1a2e", before=0, after=16))

# ── THE REALITY ───────────────────────────────────────────────────────────────
story.append(Paragraph("THE HONEST STARTING POINT", h1_s))
story.append(section_rule())
story.append(Paragraph(
    "You have two revenue engines already built:", body_s))
story.append(Paragraph(
    "&#8226; &nbsp;<b>3 Lakes Logistics LLC</b> — a running AI-powered freight dispatch operation "
    "with a proven 10% service fee model, targeting cargo vans, sprinters, SUVs, and passenger cars.", bullet_s))
story.append(Paragraph(
    "&#8226; &nbsp;<b>IEBC Business Consultants</b> — a consulting firm with a CEO and incoming CSO, "
    "infrastructure (NDAs, contracts, hiring), and the strategic capability to serve small-to-mid "
    "size business clients.", bullet_s))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "The fastest path to $10K in 90 days uses BOTH engines simultaneously — not sequentially. "
    "The path to $100K in 12 months comes from systematizing what works at the 90-day mark and scaling it.",
    body_s))

# ── PHASE 1 ───────────────────────────────────────────────────────────────────
story.append(Paragraph("PHASE 1: $10,000 IN 90 DAYS", h1_s))
story.append(section_rule())
story.append(callout("Start Today — Week 1 Actions Are Listed Below", bg="#1a3a6e"))
story.append(Spacer(1, 10))

# 3LL Revenue
story.append(Paragraph("STREAM 1 — 3 Lakes Logistics: Freight Dispatch Revenue (Target: $5,000–$6,000)", h2_s))
story.append(Paragraph(
    "Your 10% dispatch fee model is your fastest cash generator. The math is simple:", body_s))

math_data = [
    ["Drivers/Carriers Active", "Avg Load Value", "Loads/Driver/Month", "Your 10% Fee", "Monthly Revenue"],
    ["3 active drivers", "$800/load", "4 loads/month", "$80/load", "$960/mo"],
    ["5 active drivers", "$800/load", "5 loads/month", "$80/load", "$2,000/mo"],
    ["8 active drivers", "$900/load", "6 loads/month", "$90/load", "$4,320/mo"],
]
math_table = Table(math_data, colWidths=[W*0.22, W*0.18, W*0.22, W*0.18, W*0.20])
math_table.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#1a1a2e")),
    ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
    ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
    ("FONTSIZE",      (0,0), (-1,-1), 8.5),
    ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.HexColor("#f4f6fb"), colors.white]),
    ("GRID",          (0,0), (-1,-1), 0.4, colors.HexColor("#cccccc")),
    ("ALIGN",         (1,0), (-1,-1), "CENTER"),
    ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ("TOPPADDING",    (0,0), (-1,-1), 6),
    ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ("LEFTPADDING",   (0,0), (-1,-1), 6),
]))
story.append(math_table)
story.append(Spacer(1, 8))
story.append(Paragraph("<b>Do this TODAY to generate 3LL revenue:</b>", bold_body_s))
for item in [
    "Post on Facebook Groups, trucking forums, and Craigslist gig sections: 'Cargo van / sprinter owners — we dispatch loads for you. You drive, we handle the booking. 10% fee.' Target your city AND Tacoma (Cecilia's market).",
    "Contact 5 independent cargo van or sprinter owners in your network this week. Offer a free first load dispatch to prove the model.",
    "Activate your 123Loadboard API integration — have your AI agents scanning and bidding on small freight loads NOW.",
    "Set up a simple one-page website or landing page for 3 Lakes Logistics with a driver sign-up form.",
    "Join DAT, Truckstop, or uShip to expand load access beyond 123Loadboard.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))

story.append(Spacer(1, 8))

# IEBC Revenue
story.append(Paragraph("STREAM 2 — IEBC Business Consultants: Consulting Revenue (Target: $4,000–$5,000)", h2_s))
story.append(Paragraph(
    "IEBC can generate revenue immediately by selling what you already know how to do. "
    "Small businesses desperately need strategy, structure, and execution help.", body_s))

iebc_data = [
    ["Service", "Price Point", "# to Sell in 90 Days", "Revenue"],
    ["Business Strategy Session (2 hrs)", "$250–$400", "5 sessions", "$1,250–$2,000"],
    ["Business Plan / Pitch Deck", "$750–$1,500", "2 plans", "$1,500–$3,000"],
    ["NDA / Contract Package", "$300–$500", "3 packages", "$900–$1,500"],
    ["Monthly Retainer (light advisory)", "$500–$800/mo", "1 client", "$500–$800"],
]
iebc_table = Table(iebc_data, colWidths=[W*0.32, W*0.22, W*0.22, W*0.24])
iebc_table.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#1a3a6e")),
    ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
    ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
    ("FONTSIZE",      (0,0), (-1,-1), 8.5),
    ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.HexColor("#f4f6fb"), colors.white]),
    ("GRID",          (0,0), (-1,-1), 0.4, colors.HexColor("#cccccc")),
    ("ALIGN",         (1,0), (-1,-1), "CENTER"),
    ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ("TOPPADDING",    (0,0), (-1,-1), 6),
    ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ("LEFTPADDING",   (0,0), (-1,-1), 6),
]))
story.append(iebc_table)
story.append(Spacer(1, 8))
story.append(Paragraph("<b>Do this TODAY to generate IEBC revenue:</b>", bold_body_s))
for item in [
    "Post on LinkedIn TODAY: 'IEBC Business Consultants is now accepting 3 new clients for Q3. We help small businesses build strategy, structure, and scalable operations. DM for a free 30-minute discovery call.'",
    "Email 10 people in your network who own or run small businesses. Offer a discounted strategy session ($150) for the first 3 who book this week.",
    "List IEBC on Google Business Profile, Alignable, and Thumbtack as a business consulting firm.",
    "Offer the NDA/contract package you already built as a product — small businesses pay $300–$500 for professional legal-grade agreements.",
    "Pitch 1-2 local small businesses on a $500/month light advisory retainer — 2 calls/month + email support.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))

story.append(Spacer(1, 8))

# 90 Day Summary
story.append(callout("90-Day Revenue Summary: 3LL ($5,500) + IEBC ($4,500) = $10,000 ✓", bg="#2d6a2d"))

# ── PHASE 2 ───────────────────────────────────────────────────────────────────
story.append(PageBreak())
story.append(Paragraph("PHASE 2: $100,000 IN 12 MONTHS", h1_s))
story.append(section_rule())
story.append(Paragraph(
    "At month 3, you know what's working. The $100K path is about doubling down on your strongest "
    "stream and systematizing the other. Here is the monthly revenue breakdown required:", body_s))

monthly_data = [
    ["Month", "3LL Target", "IEBC Target", "Monthly Total", "Running Total"],
    ["1–3",   "$1,800/mo",  "$1,500/mo",  "$3,300/mo",    "$9,900"],
    ["4–6",   "$3,500/mo",  "$3,000/mo",  "$6,500/mo",    "$29,400"],
    ["7–9",   "$5,500/mo",  "$4,500/mo",  "$10,000/mo",   "$59,400"],
    ["10–12", "$7,500/mo",  "$6,000/mo",  "$13,500/mo",   "$100,000+"],
]
monthly_table = Table(monthly_data, colWidths=[W*0.12, W*0.18, W*0.18, W*0.20, W*0.22])
monthly_table.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#1a1a2e")),
    ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
    ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
    ("FONTSIZE",      (0,0), (-1,-1), 9),
    ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.HexColor("#f4f6fb"), colors.white]),
    ("GRID",          (0,0), (-1,-1), 0.4, colors.HexColor("#cccccc")),
    ("ALIGN",         (1,0), (-1,-1), "CENTER"),
    ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ("TOPPADDING",    (0,0), (-1,-1), 7),
    ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ("LEFTPADDING",   (0,0), (-1,-1), 8),
    ("BACKGROUND",    (0,-1), (-1,-1), colors.HexColor("#e8f0e8")),
    ("FONTNAME",      (0,-1), (-1,-1), "Helvetica-Bold"),
]))
story.append(monthly_table)
story.append(Spacer(1, 10))

# 3LL Scale
story.append(Paragraph("HOW 3 LAKES LOGISTICS GETS TO $7,500/MONTH", h2_s))
for item in [
    "<b>Months 1–3:</b> Sign 5–8 drivers. Focus on cargo vans and sprinters. Use AI agents to dispatch 3–5 loads per driver per month.",
    "<b>Months 4–6:</b> Target 15 active drivers. Introduce a driver referral bonus ($50 per driver they bring). Expand to Tacoma/Pacific Northwest market through Cecilia Gulley (CSO) who is already on the ground there.",
    "<b>Months 7–9:</b> Aim for 25+ drivers. Add a dedicated account rep to handle driver relationships. Begin targeting small courier and last-mile delivery companies as fleet clients (dispatch 10+ vehicles under one contract).",
    "<b>Months 10–12:</b> Lock in 2–3 fleet accounts (companies with 5–10 vans). These are $1,500–$3,000/month contracts each. One fleet account alone can hit your monthly target.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))

story.append(Spacer(1, 8))

# IEBC Scale
story.append(Paragraph("HOW IEBC BUSINESS CONSULTANTS GETS TO $6,000/MONTH", h2_s))
for item in [
    "<b>Months 1–3:</b> Land 3–5 one-time consulting projects. Build your case studies and testimonials from these.",
    "<b>Months 4–6:</b> Convert 2–3 one-time clients into monthly retainers at $750–$1,000/month. Add Cecilia as CSO — she begins managing client delivery while you focus on business development.",
    "<b>Months 7–9:</b> Introduce a flagship consulting package: 90-Day Business Transformation ($3,500 flat fee). Target small businesses doing $250K–$1M/year. Sell 1–2 per month.",
    "<b>Months 10–12:</b> Stack retainers + project work. Goal: 4 retainer clients at $800/mo ($3,200) + 2 project engagements at $1,500 each ($3,000) = $6,200/month.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))

story.append(Spacer(1, 8))

# Leverage point
story.append(Paragraph("THE LEVERAGE POINT: HOW IEBC AND 3LL MAKE EACH OTHER MORE VALUABLE", h2_s))
story.append(Paragraph(
    "This is what most people miss. You don't have two separate businesses — you have a consulting firm "
    "that ALSO runs a logistics company. That combination is your competitive advantage:", body_s))
for item in [
    "<b>IEBC can sell logistics consulting</b> to small trucking companies, independent dispatchers, and freight brokers — using 3LL as the proof of concept. 'We built and operate our own AI-dispatched fleet. Now we'll help you build yours.'",
    "<b>3LL can be the case study</b> that lands IEBC consulting clients. Show the AI automation, the 10% fee model, the scale. Clients will pay to replicate it.",
    "<b>Cecilia Gulley (CSO, Tacoma)</b> opens the Pacific Northwest market for BOTH businesses simultaneously — 3LL drivers in Tacoma/Seattle AND IEBC consulting clients in Washington State.",
    "<b>Bundle the offer:</b> Offer small logistics businesses a package — 'IEBC will consult on your operations AND put your drivers on the 3LL dispatch platform.' Charge $2,000 upfront + 10% ongoing.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))

# ── START TODAY ───────────────────────────────────────────────────────────────
story.append(PageBreak())
story.append(Paragraph("START MAKING MONEY TODAY — YOUR NEXT 7 DAYS", h1_s))
story.append(section_rule())

week_data = [
    ["DAY", "ACTION", "EXPECTED RESULT"],
    ["Today",   "Post driver recruitment ad on Facebook, LinkedIn, Craigslist.\nText/call 5 van/sprinter owners you know personally.",
                "1–3 driver inquiries"],
    ["Today",   "Post IEBC consulting offer on LinkedIn.\nEmail 10 business owner contacts — offer free 30-min call.",
                "2–4 discovery calls booked"],
    ["Day 2",   "Activate 3LL AI agents on 123Loadboard — begin scanning and bidding on small loads.",
                "First load dispatched"],
    ["Day 3",   "Set up IEBC Google Business Profile.\nList on Alignable and Thumbtack.",
                "Online visibility live"],
    ["Day 4",   "Follow up on all driver inquiries — onboard your first driver.\nSend dispatch agreement.",
                "First driver signed"],
    ["Day 5",   "Run first IEBC discovery call.\nPitch strategy session or business plan package.",
                "First paid client"],
    ["Day 6–7", "Brief Cecilia Gulley on the 90-day revenue plan.\nAssign her Tacoma market outreach for both 3LL drivers and IEBC clients.",
                "West Coast pipeline opens"],
]
week_table = Table(week_data, colWidths=[W*0.10, W*0.55, W*0.35])
week_table.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#1a1a2e")),
    ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
    ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
    ("FONTSIZE",      (0,0), (-1,-1), 8.5),
    ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.HexColor("#f4f6fb"), colors.white]),
    ("GRID",          (0,0), (-1,-1), 0.4, colors.HexColor("#cccccc")),
    ("VALIGN",        (0,0), (-1,-1), "TOP"),
    ("TOPPADDING",    (0,0), (-1,-1), 7),
    ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ("LEFTPADDING",   (0,0), (-1,-1), 7),
]))
story.append(week_table)
story.append(Spacer(1, 12))

story.append(callout("The only thing standing between you and $10,000 is execution. You already have the infrastructure.", bg="#1a3a6e"))
story.append(Spacer(1, 10))

# ── WHAT YOU NEED TO NOT DO ────────────────────────────────────────────────────
story.append(Paragraph("WHAT TO AVOID — COMMON TRAPS", h1_s))
story.append(section_rule())
for item in [
    "<b>Don't wait until everything is 'perfect.'</b> The NDA is done. The contracts are done. Start selling today with what you have.",
    "<b>Don't try to build the technology before you have revenue.</b> The AI dispatch system is an asset — use it to generate cash, don't keep building it without clients.",
    "<b>Don't undercharge.</b> IEBC consulting is worth $300–$1,500+ per engagement. Don't discount below your value to chase easy sales.",
    "<b>Don't ignore the Tacoma market.</b> Cecilia on the ground in the Pacific Northwest is a free business development asset. Put her to work on revenue from day one.",
    "<b>Don't try to do everything alone.</b> That's why you hired a CSO. Delegate client delivery and driver onboarding to Cecilia so you can focus on closing new business.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))

story.append(Spacer(1, 12))
story.append(hr(before=10, after=6, thick=1, col="#1a1a2e"))
story.append(Paragraph(
    "IEBC Business Consultants | 3 Lakes Logistics LLC — Confidential Revenue Strategy Document | Mark Odom, CEO",
    footer_s))

doc.build(story)
print(f"PDF generated: {OUTPUT}")
