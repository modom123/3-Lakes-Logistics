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
W = letter[0] - 1.8*inch  # usable width = 6.7 inches

# ── Paragraph styles ───────────────────────────────────────────────
title_s  = ParagraphStyle("T",   parent=styles["Title"],   fontSize=17, textColor=colors.HexColor("#1a1a2e"), alignment=TA_CENTER, leading=22, spaceAfter=4)
sub_s    = ParagraphStyle("Sub", parent=styles["Normal"],  fontSize=10, alignment=TA_CENTER, textColor=colors.HexColor("#555555"), leading=14, spaceAfter=18)
h1_s     = ParagraphStyle("H1",  parent=styles["Heading1"],fontSize=12, textColor=colors.HexColor("#1a1a2e"), spaceBefore=16, spaceAfter=5, leading=15)
h2_s     = ParagraphStyle("H2",  parent=styles["Heading2"],fontSize=10.5,textColor=colors.HexColor("#1a3a6e"), spaceBefore=10, spaceAfter=4, leading=13)
body_s   = ParagraphStyle("B",   parent=styles["Normal"],  fontSize=10, leading=15, spaceAfter=6, alignment=TA_JUSTIFY)
bullet_s = ParagraphStyle("BL",  parent=styles["Normal"],  fontSize=10, leading=14, spaceAfter=4, leftIndent=16)
bold_b_s = ParagraphStyle("BB",  parent=styles["Normal"],  fontSize=10, leading=15, spaceAfter=6, fontName="Helvetica-Bold")
footer_s = ParagraphStyle("F",   parent=styles["Normal"],  fontSize=8,  alignment=TA_CENTER, textColor=colors.HexColor("#999999"), spaceAfter=0, spaceBefore=10)

# Cell styles for table content — must be Paragraph objects so text wraps
_cell  = ParagraphStyle("C",  parent=styles["Normal"], fontSize=9,  leading=13, spaceAfter=0, spaceBefore=0)
_cellC = ParagraphStyle("CC", parent=styles["Normal"], fontSize=9,  leading=13, spaceAfter=0, spaceBefore=0, alignment=TA_CENTER)
_cellB = ParagraphStyle("CB", parent=styles["Normal"], fontSize=9,  leading=13, spaceAfter=0, spaceBefore=0, fontName="Helvetica-Bold")
_hdr   = ParagraphStyle("H",  parent=styles["Normal"], fontSize=9,  leading=13, spaceAfter=0, spaceBefore=0, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_CENTER)
_hdrL  = ParagraphStyle("HL", parent=styles["Normal"], fontSize=9,  leading=13, spaceAfter=0, spaceBefore=0, textColor=colors.white, fontName="Helvetica-Bold")

def C(t, bold=False, center=False):
    """Wrap plain text in a table-cell Paragraph so it wraps properly."""
    if bold and center:
        s = ParagraphStyle("tmp", parent=_cellB, alignment=TA_CENTER)
    elif bold:
        s = _cellB
    elif center:
        s = _cellC
    else:
        s = _cell
    return Paragraph(str(t), s)

def H(t, left=False):
    return Paragraph(str(t), _hdrL if left else _hdr)

# ── Layout helpers ─────────────────────────────────────────────────
def hr(before=4, after=10, thick=0.5, col="#cccccc"):
    return HRFlowable(width="100%", thickness=thick, color=colors.HexColor(col), spaceBefore=before, spaceAfter=after)

def section_rule():
    return hr(before=4, after=6, thick=1.5, col="#1a1a2e")

def callout(text, bg="#1a3a6e"):
    cs = ParagraphStyle("co", parent=styles["Normal"], fontSize=11,
        leading=16, spaceAfter=0, alignment=TA_CENTER, textColor=colors.white, fontName="Helvetica-Bold")
    t = Table([[Paragraph(text, cs)]], colWidths=[W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor(bg)),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
        ("LEFTPADDING",   (0,0),(-1,-1), 12),
        ("RIGHTPADDING",  (0,0),(-1,-1), 12),
    ]))
    return t

TABLE_STYLE_BASE = [
    ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor("#cccccc")),
    ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ("TOPPADDING",    (0,0),(-1,-1), 6),
    ("BOTTOMPADDING", (0,0),(-1,-1), 6),
    ("LEFTPADDING",   (0,0),(-1,-1), 7),
    ("RIGHTPADDING",  (0,0),(-1,-1), 7),
]

def styled_table(rows, col_widths, header_bg="#1a1a2e", alt=True, last_bold=False):
    t = Table(rows, colWidths=col_widths)
    ts = list(TABLE_STYLE_BASE) + [
        ("BACKGROUND", (0,0),(-1,0), colors.HexColor(header_bg)),
    ]
    if alt:
        ts.append(("ROWBACKGROUNDS",(0,1),(-1,-1 if not last_bold else -2),
                   [colors.HexColor("#f4f6fb"), colors.white]))
    if last_bold:
        ts += [
            ("BACKGROUND",  (0,-1),(-1,-1), colors.HexColor("#e8f0e8")),
            ("FONTNAME",    (0,-1),(-1,-1), "Helvetica-Bold"),
        ]
    t.setStyle(TableStyle(ts))
    return t

# ══════════════════════════════════════════════════════════════════════
story = []

# ── COVER ──────────────────────────────────────────────────────────
story.append(Spacer(1, 0.2*inch))
story.append(Paragraph("IEBC BUSINESS CONSULTANTS", title_s))
story.append(Paragraph("3 Lakes Logistics LLC — Portfolio Company", sub_s))
story.append(callout("FULL REVENUE ROADMAP: $10,000 IN 90 DAYS → $100,000 IN 12 MONTHS"))
story.append(Spacer(1, 8))
story.append(Paragraph(
    "3 Revenue Streams: Light Fleet Dispatch &nbsp;|&nbsp; Heavy Fleet Dispatch &nbsp;|&nbsp; IEBC Business Consulting",
    ParagraphStyle("meta", parent=styles["Normal"], fontSize=10, alignment=TA_CENTER,
        textColor=colors.HexColor("#333333"), leading=14, spaceAfter=4)))
story.append(Paragraph("Mark Odom, CEO &nbsp;|&nbsp; Confidential Strategic Planning Document",
    ParagraphStyle("meta2", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER,
        textColor=colors.HexColor("#888888"), leading=13, spaceAfter=18)))
story.append(hr(thick=2, col="#1a1a2e", before=0, after=14))

# ── THREE ENGINES ──────────────────────────────────────────────────
story.append(Paragraph("YOUR THREE REVENUE ENGINES", h1_s))
story.append(section_rule())
story.append(Paragraph(
    "The previous roadmap only addressed one of your three revenue streams. Here is the complete picture:", body_s))

engines_rows = [
    [H("#"), H("REVENUE STREAM", left=True), H("STATUS"), H("12-MONTH POTENTIAL")],
    [C("1", center=True),
     C("3 Lakes Logistics — Light Fleet\n(cargo vans, sprinters, SUVs, passenger cars)"),
     C("Active — build pipeline", center=True),
     C("$40,000 – $55,000", center=True)],
    [C("2", center=True),
     C("3 Lakes Logistics — Heavy Fleet\n(semis, box trucks, flatbeds, reefers)"),
     C("Pipeline — not yet active", center=True),
     C("$60,000 – $100,000+", center=True)],
    [C("3", center=True),
     C("IEBC Business Consultants\n(strategy, consulting, advisory)"),
     C("Active — build pipeline", center=True),
     C("$30,000 – $50,000", center=True)],
    [C("", center=True),
     C("COMBINED 12-MONTH TARGET", bold=True),
     C(""),
     C("$100,000 – $205,000+", bold=True, center=True)],
]
story.append(styled_table(engines_rows, [W*0.06, W*0.44, W*0.22, W*0.28], last_bold=True))
story.append(Spacer(1, 8))
story.append(Paragraph(
    "<b>The heavy fleet is your single largest revenue opportunity.</b> "
    "A single semi owner-operator dispatching 8 loads/month at $3,000/load generates "
    "$2,400/month in fees for 3 Lakes Logistics. Five semis = $12,000/month from one vehicle class alone.", body_s))

# ── WHY HEAVY FLEET CHANGES EVERYTHING ────────────────────────────
story.append(Paragraph("WHY HEAVY FLEET CHANGES THE ENTIRE REVENUE PICTURE", h1_s))
story.append(section_rule())
story.append(Paragraph(
    "Compare the dispatch fee per unit across your fleet types at the standard 10% model:", body_s))

compare_rows = [
    [H("Vehicle Type", left=True), H("Avg Load Value"), H("10% Fee / Load"), H("Loads / Month"), H("Monthly Fee / Unit")],
    [C("Cargo Van / Sprinter"),   C("$600 – $900",   center=True), C("$60 – $90",    center=True), C("4 – 6",  center=True), C("$240 – $540",    center=True)],
    [C("Box Truck (24–26 ft)"),   C("$900 – $1,800", center=True), C("$90 – $180",   center=True), C("6 – 8",  center=True), C("$540 – $1,440",  center=True)],
    [C("Flatbed / Step-Deck"),    C("$1,500 – $3,500",center=True), C("$150 – $350", center=True), C("6 – 10", center=True), C("$900 – $3,500",  center=True)],
    [C("Reefer (Refrigerated)"),  C("$2,000 – $5,000",center=True), C("$200 – $500", center=True), C("6 – 10", center=True), C("$1,200 – $5,000",center=True)],
    [C("Semi / 18-Wheeler OTR"),  C("$2,500 – $6,000",center=True), C("$250 – $600", center=True), C("8 – 12", center=True), C("$2,000 – $7,200",center=True)],
]
story.append(styled_table(compare_rows, [W*0.24, W*0.18, W*0.18, W*0.16, W*0.24]))
story.append(Spacer(1, 8))
story.append(Paragraph(
    "One flatbed earns you more than <b>six cargo vans</b>. "
    "One reefer earns you more than <b>eight sprinters</b>. "
    "One semi earns you more than <b>ten cargo vans</b>. "
    "The heavy fleet is not a side opportunity — it is your primary path to $100K and beyond.", body_s))

# ── STREAM 1 — LIGHT FLEET ─────────────────────────────────────────
story.append(PageBreak())
story.append(Paragraph("STREAM 1 — LIGHT FLEET DISPATCH (Cargo Vans, Sprinters, SUVs)", h1_s))
story.append(section_rule())
story.append(Paragraph(
    "Light fleet is your fastest on-ramp — easier to recruit, lower barrier for drivers, "
    "and your AI agent system is already optimized for this segment. Use it to generate "
    "early cash flow while you build the heavy fleet pipeline in parallel.", body_s))

light_rows = [
    [H("Period"), H("Active Drivers"), H("Avg Fee / Driver / Mo"), H("Light Fleet Monthly Revenue")],
    [C("Months 1–3",  center=True), C("5–8 drivers",   center=True), C("$320", center=True), C("$1,600 – $2,560",  center=True)],
    [C("Months 4–6",  center=True), C("12–15 drivers", center=True), C("$380", center=True), C("$4,560 – $5,700",  center=True)],
    [C("Months 7–9",  center=True), C("20 drivers",    center=True), C("$420", center=True), C("$8,400",           center=True)],
    [C("Months 10–12",center=True), C("25+ drivers",   center=True), C("$450", center=True), C("$11,250+",         center=True)],
]
story.append(styled_table(light_rows, [W*0.18, W*0.22, W*0.28, W*0.32]))
story.append(Spacer(1, 8))
story.append(Paragraph("<b>How to recruit light fleet drivers — start today:</b>", bold_b_s))
for item in [
    "Post in Facebook Groups: 'Van Life / Cargo Van Owners,' 'Amazon Flex Drivers,' and local gig worker groups in Detroit AND Tacoma (Cecilia's market).",
    "Post on Craigslist gig section: 'Earn more from your cargo van or sprinter — we book the loads, you drive. 10% dispatch fee, no contracts.'",
    "Target Amazon DSP drivers and Flex drivers who want to go independent — they already know freight.",
    "Activate AI agents on 123Loadboard, uShip, and Truckstop.com to find and book small loads immediately.",
    "Offer first load free — once a driver sees the system work, they stay.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))

# ── STREAM 2 — HEAVY FLEET ─────────────────────────────────────────
story.append(Paragraph("STREAM 2 — HEAVY FLEET DISPATCH (Semis, Box Trucks, Flatbeds, Reefers)", h1_s))
story.append(section_rule())
story.append(callout("This is your $100K engine. Heavy fleet is where 3 Lakes Logistics scales fast.", bg="#8b1a1a"))
story.append(Spacer(1, 10))
story.append(Paragraph(
    "Heavy fleet dispatch runs the same 10% model but at 3–8x the load values of light fleet. "
    "You are building this pipeline from zero — the opportunity is completely open. "
    "Here is the revenue math at scale:", body_s))

heavy_rows = [
    [H("Period"), H("Active Heavy Units"), H("Avg Fee / Unit / Mo"), H("Heavy Fleet Monthly Revenue")],
    [C("Months 1–3",  center=True), C("0–2 units",    center=True), C("$1,200", center=True), C("$0 – $2,400",       center=True)],
    [C("Months 4–6",  center=True), C("3–5 units",    center=True), C("$1,800", center=True), C("$5,400 – $9,000",   center=True)],
    [C("Months 7–9",  center=True), C("8–10 units",   center=True), C("$2,200", center=True), C("$17,600 – $22,000", center=True)],
    [C("Months 10–12",center=True), C("15–20 units",  center=True), C("$2,500", center=True), C("$37,500 – $50,000", center=True)],
]
story.append(styled_table(heavy_rows, [W*0.18, W*0.22, W*0.28, W*0.32], header_bg="#8b1a1a"))
story.append(Spacer(1, 8))
story.append(Paragraph(
    "At 15–20 heavy units by month 12, the heavy fleet alone clears your $100K annual target. "
    "Light fleet and IEBC revenue on top of that puts you at $200K+.", body_s))

story.append(Paragraph("HEAVY FLEET: VEHICLE-BY-VEHICLE STRATEGY", h2_s))

for vehicle, intro, items in [
    ("Box Trucks (24–26 ft) — Your First Heavy Entry Point",
     "Box truck owner-operators are the easiest bridge from light to heavy fleet. Many already work with freight brokers and understand load boards.",
     [
         "Recruit on DAT One, Truckstop.com, and Facebook groups 'Box Truck Nation' and 'Box Truck Owner Operators.'",
         "Target moving companies, furniture delivery drivers, and Amazon relay drivers who own their own box trucks.",
         "Average dispatch fee: $90–$180 per load. A driver doing 8 loads/month = $720–$1,440/month to 3LL.",
         "Pitch: 'We handle your load board searching, rate negotiation, and broker vetting. You drive. We take 10%.'",
     ]),
    ("Flatbeds / Step-Decks — High-Value, Less Competition",
     "Flatbed loads are high-paying and many owner-operators want a reliable dispatcher because flatbed load boards are harder to navigate.",
     [
         "Recruit from Facebook group 'Flatbed Truckers' and the DAT flatbed board.",
         "Target construction material haulers, steel haulers, and equipment transport drivers.",
         "Average dispatch fee: $150–$350 per load. A driver doing 8 loads/month = $1,200–$2,800/month to 3LL.",
         "Extend AI agents to monitor DAT and Truckstop flatbed boards — automation is a major advantage in this segment.",
     ]),
    ("Reefer / Refrigerated Trucks — Premium Rates, Premium Revenue",
     "Reefer loads command the highest rates in freight. Food, pharma, and perishables run year-round. One reefer driver is worth more than 8 cargo vans.",
     [
         "Recruit on Truckstop.com reefer board, DAT reefer lanes, and Facebook groups 'Reefer Truck Drivers.'",
         "Target produce haulers, grocery distribution drivers, and pharma/cold-chain specialists.",
         "Average dispatch fee: $200–$500 per load. A driver doing 8 loads/month = $1,600–$4,000/month to 3LL.",
         "Cecilia in Tacoma is in a prime market — Pacific Northwest reefer lanes (produce, seafood) are extremely active year-round.",
     ]),
    ("Semi-Trucks / 18-Wheelers (OTR) — Your Biggest Revenue Unit",
     "OTR semi owner-operators are the highest-value accounts in freight dispatch. One CDL-A driver running 10 loads/month generates $2,500–$6,000/month for 3LL.",
     [
         "Recruit on DAT One, Truckstop.com, and Facebook groups 'Owner Operator Nation' and 'Truckers Justice.'",
         "Post physical flyers at truck stops on I-75/I-94 in Detroit and I-5 in Tacoma — this still works.",
         "Attend MMTA (Michigan Motor Truck Association) events — direct access to owner-operators.",
         "Pitch: '3 Lakes Logistics dispatches for owner-operators. AI finds your loads 24/7. You keep 90%.'",
         "Offer a free rate-per-mile analysis report as a lead magnet — show drivers they are leaving money on the table.",
         "Target drivers under carriers who are considering going independent — they need a dispatcher immediately.",
     ]),
]:
    story.append(Paragraph(f"<b>{vehicle}</b>", bold_b_s))
    story.append(Paragraph(intro, body_s))
    for item in items:
        story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))
    story.append(Spacer(1, 8))

# ── STREAM 3 — IEBC ────────────────────────────────────────────────
story.append(PageBreak())
story.append(Paragraph("STREAM 3 — IEBC BUSINESS CONSULTANTS", h1_s))
story.append(section_rule())
story.append(Paragraph(
    "IEBC generates consulting revenue independently AND amplifies 3LL's heavy fleet growth "
    "by offering dispatch operations consulting to carriers, fleet managers, and trucking companies "
    "who want to build their own AI-dispatched infrastructure.", body_s))

iebc_rows = [
    [H("Service", left=True), H("Price"), H("Target: 90 Days"), H("Projected Revenue")],
    [C("Business Strategy Session (2 hrs)"),     C("$300 – $500",      center=True), C("4 sessions",   center=True), C("$1,200 – $2,000", center=True)],
    [C("Business Plan / Pitch Deck"),             C("$1,000 – $2,000",  center=True), C("2 plans",      center=True), C("$2,000 – $4,000", center=True)],
    [C("NDA / Contract Package"),                 C("$300 – $500",      center=True), C("3 packages",   center=True), C("$900 – $1,500",   center=True)],
    [C("Dispatch Operations Setup Consulting"),   C("$1,500 – $3,000",  center=True), C("1 engagement", center=True), C("$1,500 – $3,000", center=True)],
    [C("Monthly Advisory Retainer"),              C("$750 – $1,200/mo", center=True), C("2 clients",    center=True), C("$1,500 – $2,400", center=True)],
]
story.append(styled_table(iebc_rows, [W*0.36, W*0.20, W*0.20, W*0.24], header_bg="#1a3a6e"))
story.append(Spacer(1, 8))
story.append(Paragraph(
    "<b>The highest-value IEBC service for 12-month growth is Dispatch Operations Setup Consulting.</b> "
    "You have a working AI-dispatched fleet in 3LL. Small trucking companies will pay $1,500–$5,000 "
    "to learn how to replicate it. IEBC charges for the knowledge; 3LL is the proof of concept.", body_s))
for item in [
    "Target small trucking companies (2–10 trucks) dispatching manually and losing money on deadhead miles.",
    "Offer a '3LL Dispatch Blueprint' package at $2,500 flat fee — IEBC consults on operations, 3LL's system is the model.",
    "Upsell: after the consulting engagement, offer to put their drivers on the 3LL dispatch platform permanently at 10%.",
    "Cecilia (CSO, Tacoma) manages the Pacific Northwest IEBC client pipeline — huge independent trucking community there.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))

# ── COMBINED PROJECTION ────────────────────────────────────────────
story.append(Paragraph("COMBINED 12-MONTH REVENUE PROJECTION — ALL THREE STREAMS", h1_s))
story.append(section_rule())
story.append(Paragraph(
    "Quarterly breakdown across all three revenue streams with running total:", body_s))

# Split into two tables for readability
proj_rows = [
    [H("Period"), H("Light Fleet"), H("Heavy Fleet"), H("IEBC Consulting"), H("Quarter Total"), H("Running Total")],
    [C("Q1  Mo 1–3",  center=True), C("$4,800",   center=True), C("$1,200",    center=True), C("$4,000",  center=True), C("$10,000",   center=True), C("$10,000",   center=True)],
    [C("Q2  Mo 4–6",  center=True), C("$8,400",   center=True), C("$18,000",   center=True), C("$8,500",  center=True), C("$34,900",   center=True), C("$44,900",   center=True)],
    [C("Q3  Mo 7–9",  center=True), C("$12,000",  center=True), C("$55,000",   center=True), C("$12,000", center=True), C("$79,000",   center=True), C("$123,900",  center=True)],
    [C("Q4  Mo 10–12",center=True), C("$15,000",  center=True), C("$112,500",  center=True), C("$18,000", center=True), C("$145,500",  center=True), C("$269,400",  center=True)],
    [C("12-MO TOTAL", bold=True, center=True),
     C("$40,200",  bold=True, center=True),
     C("$186,700", bold=True, center=True),
     C("$42,500",  bold=True, center=True),
     C("",         center=True),
     C("$269,400", bold=True, center=True)],
]
proj_table = Table(proj_rows, colWidths=[W*0.18, W*0.13, W*0.14, W*0.17, W*0.17, W*0.21])
proj_table.setStyle(TableStyle([
    ("BACKGROUND",    (0,0),(-1,0),  colors.HexColor("#1a1a2e")),
    ("BACKGROUND",    (0,-1),(-1,-1),colors.HexColor("#e8f0e8")),
    ("BACKGROUND",    (2,1),(2,-1),  colors.HexColor("#fff8f0")),
    ("ROWBACKGROUNDS",(0,1),(-1,-2), [colors.HexColor("#f4f6fb"), colors.white,
                                       colors.HexColor("#f4f6fb"), colors.white]),
    ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor("#cccccc")),
    ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ("TOPPADDING",    (0,0),(-1,-1), 6),
    ("BOTTOMPADDING", (0,0),(-1,-1), 6),
    ("LEFTPADDING",   (0,0),(-1,-1), 5),
    ("RIGHTPADDING",  (0,0),(-1,-1), 5),
]))
story.append(proj_table)
story.append(Spacer(1, 8))
story.append(Paragraph(
    "Note: Heavy fleet projections assume active owner-operator recruitment begins in Month 1 with "
    "first units dispatched by Month 2–3. Figures are conservative mid-range estimates based on "
    "industry-standard owner-operator load activity. Light fleet highlighted in orange column "
    "shows its smaller but consistent contribution as the early cash foundation.", body_s))
story.append(Spacer(1, 6))
story.append(callout("$100,000 is achievable by Month 7–8 with heavy fleet active. $269,000+ is the realistic 12-month ceiling.", bg="#2d6a2d"))

# ── 7-DAY ACTION PLAN ─────────────────────────────────────────────
story.append(PageBreak())
story.append(Paragraph("START TODAY — 7-DAY ACTION PLAN", h1_s))
story.append(section_rule())

week_rows = [
    [H("Day"), H("Action", left=True), H("Stream"), H("Expected Result")],
    [C("Today", center=True),
     C("Post cargo van/sprinter driver recruitment on Facebook, Craigslist, and LinkedIn."),
     C("Light Fleet", center=True),
     C("First driver inquiries", center=True)],
    [C("Today", center=True),
     C("Post semi and box truck owner-operator recruitment on DAT and Facebook 'Owner Operator Nation.'"),
     C("Heavy Fleet", center=True),
     C("Heavy pipeline opens", center=True)],
    [C("Today", center=True),
     C("Post IEBC consulting offer on LinkedIn. Email 10 business owner contacts for discovery calls."),
     C("IEBC", center=True),
     C("Discovery calls booked", center=True)],
    [C("Day 2", center=True),
     C("Activate AI agents on 123Loadboard and DAT to scan light AND heavy freight boards simultaneously."),
     C("3LL Both", center=True),
     C("Loads identified", center=True)],
    [C("Day 2", center=True),
     C("Call 3 independent CDL-A drivers in your network personally — pitch the 10% dispatch model."),
     C("Heavy Fleet", center=True),
     C("First semi interest", center=True)],
    [C("Day 3", center=True),
     C("Onboard first light fleet driver. Send dispatch agreement (NDA already built and ready)."),
     C("Light Fleet", center=True),
     C("First driver signed", center=True)],
    [C("Day 4", center=True),
     C("Brief Cecilia Gulley (CSO, Tacoma) on heavy fleet pipeline. Assign Pacific Northwest semi and reefer recruitment."),
     C("Heavy Fleet", center=True),
     C("West Coast pipeline opens", center=True)],
    [C("Day 5", center=True),
     C("Run first IEBC discovery call. Pitch strategy session or dispatch consulting package."),
     C("IEBC", center=True),
     C("First paid client", center=True)],
    [C("Day 6", center=True),
     C("Sign first heavy fleet owner-operator (box truck or semi). Dispatch first heavy freight load."),
     C("Heavy Fleet", center=True),
     C("First heavy revenue", center=True)],
    [C("Day 7", center=True),
     C("Review all three pipeline statuses. Set 30-day targets for drivers, loads, and consulting clients."),
     C("All Streams", center=True),
     C("Week 1 complete", center=True)],
]
story.append(styled_table(week_rows, [W*0.09, W*0.47, W*0.18, W*0.26]))

# ── ADVANTAGES + AVOIDS ────────────────────────────────────────────
story.append(Spacer(1, 10))
story.append(Paragraph("THE ADVANTAGES YOU HAVE THAT COMPETITORS DON'T", h1_s))
story.append(section_rule())
for item in [
    "<b>AI-powered dispatch across ALL fleet types.</b> Most dispatchers are one person with a phone and a single load board. Your AI agents run 24/7 across multiple boards simultaneously — lead with this when recruiting heavy fleet drivers.",
    "<b>Cecilia Gulley as CSO in Tacoma.</b> The Pacific Northwest is one of the most active reefer and flatbed markets in the country (produce, seafood, lumber, manufacturing). She is physically in that market from day one.",
    "<b>IEBC as the consulting arm that monetizes 3LL's model.</b> Carrier companies will pay IEBC $2,500+ to learn how to build an AI-dispatched fleet — then 3LL dispatches their drivers. One relationship generates revenue from two streams.",
    "<b>Legal infrastructure already built.</b> NDAs, dispatch agreements, and contracts are done. You can legally onboard a new owner-operator today — there is no administrative barrier to first revenue.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))

story.append(Spacer(1, 8))
story.append(Paragraph("WHAT TO AVOID", h1_s))
story.append(section_rule())
for item in [
    "<b>Don't delay heavy fleet recruitment.</b> Every week without a heavy fleet pipeline is your highest-earning asset sitting idle. Start recruiting CDL-A owner-operators today in parallel with light fleet.",
    "<b>Don't underestimate reefer and flatbed markets.</b> These drivers are often underserved by dispatchers who focus only on dry van. That gap is your entry point and your competitive advantage.",
    "<b>Don't let Cecilia sit idle during setup.</b> Her first priority as CSO is pipeline development — Pacific Northwest heavy fleet recruitment and IEBC client acquisition in Washington State should begin immediately upon signing.",
    "<b>Don't ignore fleet accounts.</b> One company with 5 box trucks on your dispatch platform equals 5 heavy units overnight. Target small trucking companies alongside individual owner-operators.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))

story.append(Spacer(1, 16))
story.append(hr(before=8, after=6, thick=1, col="#1a1a2e"))
story.append(Paragraph(
    "IEBC Business Consultants | 3 Lakes Logistics LLC — Confidential Revenue Strategy | Mark Odom, CEO",
    footer_s))

doc.build(story)
print(f"PDF generated: {OUTPUT}")
