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

title_s  = ParagraphStyle("T",   parent=styles["Title"],   fontSize=17, textColor=colors.HexColor("#1a1a2e"), alignment=TA_CENTER, leading=22, spaceAfter=4)
sub_s    = ParagraphStyle("Sub", parent=styles["Normal"],  fontSize=10, alignment=TA_CENTER, textColor=colors.HexColor("#555555"), leading=14, spaceAfter=18)
h1_s     = ParagraphStyle("H1",  parent=styles["Heading1"],fontSize=12, textColor=colors.HexColor("#1a1a2e"), spaceBefore=16, spaceAfter=5,  leading=15)
h2_s     = ParagraphStyle("H2",  parent=styles["Heading2"],fontSize=10.5,textColor=colors.HexColor("#1a3a6e"), spaceBefore=10, spaceAfter=4,  leading=13)
body_s   = ParagraphStyle("B",   parent=styles["Normal"],  fontSize=10, leading=15, spaceAfter=6,  alignment=TA_JUSTIFY)
bullet_s = ParagraphStyle("BL",  parent=styles["Normal"],  fontSize=10, leading=14, spaceAfter=4,  leftIndent=16)
bold_b_s = ParagraphStyle("BB",  parent=styles["Normal"],  fontSize=10, leading=15, spaceAfter=6,  fontName="Helvetica-Bold")
footer_s = ParagraphStyle("F",   parent=styles["Normal"],  fontSize=8,  alignment=TA_CENTER, textColor=colors.HexColor("#999999"), spaceAfter=0, spaceBefore=10)

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
    ]))
    return t

def tbl(data, col_widths, header_bg="#1a1a2e"):
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  colors.HexColor(header_bg)),
        ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
        ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,-1), 8.5),
        ("FONTNAME",      (0,1),(-1,-1), "Helvetica"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.HexColor("#f4f6fb"), colors.white]),
        ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor("#cccccc")),
        ("ALIGN",         (1,0),(-1,-1), "CENTER"),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 7),
    ]))
    return t

story = []

# ═══════════════════════════════════════════════════════════════════
# COVER
# ═══════════════════════════════════════════════════════════════════
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

# ═══════════════════════════════════════════════════════════════════
# THE THREE ENGINES
# ═══════════════════════════════════════════════════════════════════
story.append(Paragraph("YOUR THREE REVENUE ENGINES", h1_s))
story.append(section_rule())
story.append(Paragraph(
    "The previous roadmap only addressed one of your three revenue streams. Here is the complete picture:", body_s))

engines = [
    ["#", "REVENUE STREAM", "STATUS", "12-MONTH POTENTIAL"],
    ["1", "3 Lakes Logistics — Light Fleet\n(cargo vans, sprinters, SUVs, cars)", "Active\n(build pipeline)", "$40,000–$55,000"],
    ["2", "3 Lakes Logistics — Heavy Fleet\n(semis, box trucks, flatbeds, reefers)", "Pipeline\n(not yet active)", "$60,000–$100,000+"],
    ["3", "IEBC Business Consultants\n(strategy, consulting, advisory)", "Active\n(build pipeline)", "$30,000–$50,000"],
    ["", "COMBINED 12-MONTH TARGET", "", "$100,000–$180,000"],
]
eng_table = Table(engines, colWidths=[W*0.05, W*0.38, W*0.17, W*0.25])
eng_table.setStyle(TableStyle([
    ("BACKGROUND",    (0,0),(-1,0),  colors.HexColor("#1a1a2e")),
    ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
    ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
    ("FONTSIZE",      (0,0),(-1,-1), 9),
    ("FONTNAME",      (0,1),(-1,-2), "Helvetica"),
    ("FONTNAME",      (0,-1),(-1,-1),"Helvetica-Bold"),
    ("BACKGROUND",    (0,-1),(-1,-1),colors.HexColor("#e8f0e8")),
    ("ROWBACKGROUNDS",(0,1),(-1,-2), [colors.HexColor("#f4f6fb"), colors.white, colors.HexColor("#f4f6fb")]),
    ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor("#cccccc")),
    ("ALIGN",         (0,0),(0,-1),  "CENTER"),
    ("ALIGN",         (2,0),(-1,-1), "CENTER"),
    ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ("TOPPADDING",    (0,0),(-1,-1), 8),
    ("BOTTOMPADDING", (0,0),(-1,-1), 8),
    ("LEFTPADDING",   (0,0),(-1,-1), 8),
]))
story.append(eng_table)
story.append(Spacer(1, 8))
story.append(Paragraph(
    "<b>The heavy fleet is the single largest revenue opportunity in your portfolio.</b> "
    "A single semi-truck owner-operator dispatching 8 loads/month at $3,000/load generates "
    "$2,400/month in dispatch fees for 3 Lakes Logistics at 10%. Five semis = $12,000/month "
    "from one vehicle class alone. This dwarfs the light fleet on a per-unit basis.", body_s))

# ═══════════════════════════════════════════════════════════════════
# THE MATH — WHY HEAVY FLEET CHANGES EVERYTHING
# ═══════════════════════════════════════════════════════════════════
story.append(Paragraph("WHY HEAVY FLEET CHANGES THE ENTIRE REVENUE PICTURE", h1_s))
story.append(section_rule())
story.append(Paragraph(
    "Compare the dispatch fee per unit across your fleet types at the standard 10% model:", body_s))

compare = [
    ["Vehicle Type",          "Avg Load Value", "Your 10% Fee/Load", "Loads/Month", "Monthly Fee/Unit"],
    ["Cargo Van / Sprinter",  "$600–$900",      "$60–$90",           "4–6",         "$240–$540"],
    ["Box Truck (24–26 ft)",  "$900–$1,800",    "$90–$180",          "6–8",         "$540–$1,440"],
    ["Flatbed / Step-Deck",   "$1,500–$3,500",  "$150–$350",         "6–10",        "$900–$3,500"],
    ["Reefer (Refrigerated)", "$2,000–$5,000",  "$200–$500",         "6–10",        "$1,200–$5,000"],
    ["Semi / 18-Wheeler OTR", "$2,500–$6,000",  "$250–$600",         "8–12",        "$2,000–$7,200"],
]
story.append(tbl(compare, [W*0.22, W*0.18, W*0.18, W*0.17, W*0.25]))
story.append(Spacer(1, 8))
story.append(Paragraph(
    "One flatbed owner-operator earns you more than <b>six cargo vans</b>. "
    "One reefer truck earns you more than <b>eight sprinters</b>. "
    "One semi earns you more than <b>ten cargo vans</b>. "
    "The heavy fleet is not a side opportunity — it is your primary path to $100K.", body_s))

# ═══════════════════════════════════════════════════════════════════
# STREAM 1 — LIGHT FLEET
# ═══════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(Paragraph("STREAM 1 — LIGHT FLEET DISPATCH (Cargo Vans, Sprinters, SUVs)", h1_s))
story.append(section_rule())
story.append(Paragraph(
    "Light fleet is your fastest on-ramp — easier to recruit, lower barrier for drivers, "
    "and your AI agent system is already optimized for this segment. Use it to generate "
    "early cash flow while you build the heavy fleet pipeline.", body_s))

light_math = [
    ["Month",  "Active Drivers", "Avg Fee/Driver/Mo", "Light Fleet Monthly Revenue"],
    ["1–3",    "5–8 drivers",    "$320",              "$1,600–$2,560"],
    ["4–6",    "12–15 drivers",  "$380",              "$4,560–$5,700"],
    ["7–9",    "20 drivers",     "$420",              "$8,400"],
    ["10–12",  "25+ drivers",    "$450",              "$11,250+"],
]
story.append(tbl(light_math, [W*0.15, W*0.22, W*0.25, W*0.38]))
story.append(Spacer(1, 8))
story.append(Paragraph("<b>How to recruit light fleet drivers — start today:</b>", bold_b_s))
for item in [
    "Post in Facebook Groups: 'Van Life / Cargo Van Owners,' 'Amazon Flex Drivers,' local gig worker groups in Detroit AND Tacoma (Cecilia's market).",
    "Post on Craigslist gig section: 'Earn more from your cargo van or sprinter — we book the loads, you drive. 10% dispatch fee, no contracts.'",
    "Target Amazon DSP drivers and Flex drivers who want to go independent — they already know freight.",
    "Use your AI agents on 123Loadboard, uShip, and Truckstop.com to start finding and booking small loads immediately.",
    "Offer first load free — once a driver sees the system work, they stay.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))

# ═══════════════════════════════════════════════════════════════════
# STREAM 2 — HEAVY FLEET (THE BIG OPPORTUNITY)
# ═══════════════════════════════════════════════════════════════════
story.append(Paragraph("STREAM 2 — HEAVY FLEET DISPATCH (Semis, Box Trucks, Flatbeds, Reefers)", h1_s))
story.append(section_rule())
story.append(callout("⚠  This is your $100K engine. Heavy fleet is where 3 Lakes Logistics scales fast.", bg="#8b1a1a"))
story.append(Spacer(1, 10))
story.append(Paragraph(
    "Heavy fleet dispatch operates on the same 10% model but at 3–8x the load values. "
    "You are building the pipeline from zero — that means the opportunity is completely open. "
    "Here is the revenue math at scale:", body_s))

heavy_math = [
    ["Month",  "Active Heavy Units", "Avg Fee/Unit/Mo", "Heavy Fleet Monthly Revenue"],
    ["1–3",    "0–2 units",          "$1,200",           "$0–$2,400"],
    ["4–6",    "3–5 units",          "$1,800",           "$5,400–$9,000"],
    ["7–9",    "8–10 units",         "$2,200",           "$17,600–$22,000"],
    ["10–12",  "15–20 units",        "$2,500",           "$37,500–$50,000"],
]
story.append(tbl(heavy_math, [W*0.15, W*0.25, W*0.22, W*0.38], header_bg="#8b1a1a"))
story.append(Spacer(1, 8))
story.append(Paragraph(
    "At 15–20 heavy units dispatched by month 12, the heavy fleet alone covers your $100K annual target. "
    "Everything else — light fleet and IEBC — is profit on top.", body_s))

story.append(Paragraph("HEAVY FLEET: VEHICLE-BY-VEHICLE STRATEGY", h2_s))

story.append(Paragraph("<b>Box Trucks (24–26 ft) — Your First Heavy Entry Point</b>", bold_b_s))
story.append(Paragraph(
    "Box truck owner-operators are the easiest bridge from light to heavy fleet. "
    "Many already work with freight brokers and understand load boards.", body_s))
for item in [
    "Recruit on DAT One, Truckstop.com, and the Facebook group 'Box Truck Nation' and 'Box Truck Owner Operators.'",
    "Target moving companies, furniture delivery drivers, and Amazon relay drivers who own their own box trucks.",
    "Average dispatch fee: $90–$180/load. A driver doing 8 loads/month = $720–$1,440/month to 3LL.",
    "Pitch: 'We handle your load board searching, rate negotiation, and broker vetting. You drive. We take 10%.'",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))
story.append(Spacer(1, 6))

story.append(Paragraph("<b>Flatbeds / Step-Decks — High-Value, Less Competition</b>", bold_b_s))
story.append(Paragraph(
    "Flatbed loads are high-paying and many owner-operators want a reliable dispatcher "
    "because flatbed load boards are harder to navigate.", body_s))
for item in [
    "Join and recruit from Facebook group 'Flatbed Truckers' and DAT flatbed board.",
    "Target construction material haulers, steel haulers, and equipment transport drivers.",
    "Average dispatch fee: $150–$350/load. A driver doing 8 loads/month = $1,200–$2,800/month to 3LL.",
    "Extend your AI agents to monitor DAT and Truckstop flatbed boards — the automation advantage is significant here.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))
story.append(Spacer(1, 6))

story.append(Paragraph("<b>Reefer / Refrigerated Trucks — Premium Rates, Premium Revenue</b>", bold_b_s))
story.append(Paragraph(
    "Reefer loads command the highest rates in dry freight. Food, pharma, and perishables "
    "run year-round. A single reefer driver is worth more than 8 cargo vans.", body_s))
for item in [
    "Recruit on Truckstop.com reefer board, DAT reefer lanes, and Facebook groups 'Reefer Truck Drivers.'",
    "Target produce haulers, grocery distribution drivers, and pharma/cold-chain specialists.",
    "Average dispatch fee: $200–$500/load. A driver doing 8 loads/month = $1,600–$4,000/month to 3LL.",
    "Position 3LL as specialists: 'We focus on cold-chain lanes — we know the rates and the brokers in your region.'",
    "Cecilia in Tacoma is in a prime market — Pacific Northwest reefer lanes (produce, seafood) are extremely active.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))
story.append(Spacer(1, 6))

story.append(Paragraph("<b>Semi-Trucks / 18-Wheelers (OTR) — Your Biggest Revenue Unit</b>", bold_b_s))
story.append(Paragraph(
    "OTR semi owner-operators are the highest-value accounts in freight dispatch. "
    "One relationship with a reliable CDL-A owner-operator running 10 loads/month "
    "generates $2,500–$6,000/month for 3 Lakes Logistics at 10%.", body_s))
for item in [
    "Recruit on DAT One, Truckstop.com, and the #1 Facebook group for this segment: 'Truckers Justice' and 'Owner Operator Nation.'",
    "Post at truck stops in Detroit (I-75/I-94 corridor) and Tacoma (I-5 corridor) — physical flyers still work.",
    "Attend local trucking association meetings in Michigan. MMTA (Michigan Motor Truck Association) is your in.",
    "Pitch: '3 Lakes Logistics dispatches for owner-operators. We use AI to find you the best loads 24/7. You keep 90%.'",
    "Offer a rate-per-mile analysis report as a free lead magnet — show a driver they're leaving money on the table without a dispatcher.",
    "Target drivers already under a carrier who are thinking about going independent — they need a dispatcher immediately.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))

# ═══════════════════════════════════════════════════════════════════
# STREAM 3 — IEBC
# ═══════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(Paragraph("STREAM 3 — IEBC BUSINESS CONSULTANTS", h1_s))
story.append(section_rule())
story.append(Paragraph(
    "IEBC generates consulting revenue independently AND amplifies 3LL's heavy fleet growth "
    "by offering dispatch consulting as a premium service to carriers, fleet managers, and "
    "trucking companies who want to build their own dispatch infrastructure.", body_s))

iebc_svcs = [
    ["Service",                              "Price",          "Target: 90 Days",  "Revenue"],
    ["Business Strategy Session (2 hrs)",    "$300–$500",      "4 sessions",       "$1,200–$2,000"],
    ["Business Plan / Pitch Deck",           "$1,000–$2,000",  "2 plans",          "$2,000–$4,000"],
    ["NDA / Contract Package",               "$300–$500",      "3 packages",       "$900–$1,500"],
    ["Dispatch Operations Setup Consulting", "$1,500–$3,000",  "1 engagement",     "$1,500–$3,000"],
    ["Monthly Retainer (advisory)",          "$750–$1,200/mo", "2 clients",        "$1,500–$2,400"],
]
story.append(tbl(iebc_svcs, [W*0.32, W*0.18, W*0.20, W*0.30], header_bg="#1a3a6e"))
story.append(Spacer(1, 8))
story.append(Paragraph(
    "<b>The highest-value IEBC service for 12-month growth is Dispatch Operations Setup Consulting.</b> "
    "You have a working AI-dispatched fleet in 3LL. Small trucking companies will pay $1,500–$5,000 "
    "to learn how to build the same system. IEBC charges for the knowledge; 3LL is the proof of concept.", body_s))
for item in [
    "Target small trucking companies (2–10 trucks) who are dispatching manually and losing money on deadhead miles.",
    "Offer a '3LL Dispatch Blueprint' package: $2,500 flat fee. IEBC consults on their operations; 3LL's system is the model.",
    "Upsell: after the consulting engagement, offer to put their drivers on the 3LL dispatch platform permanently at 10%.",
    "Cecilia (CSO, Tacoma) runs the Pacific Northwest IEBC client pipeline. Pacific Northwest has a huge independent trucking community.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))

# ═══════════════════════════════════════════════════════════════════
# COMBINED 12-MONTH PROJECTION
# ═══════════════════════════════════════════════════════════════════
story.append(Paragraph("COMBINED 12-MONTH REVENUE PROJECTION — ALL THREE STREAMS", h1_s))
story.append(section_rule())

projection = [
    ["Quarter", "Light Fleet",  "Heavy Fleet",  "IEBC Consulting", "QUARTERLY TOTAL", "RUNNING TOTAL"],
    ["Q1 (Mo 1–3)",  "$4,800",  "$1,200",       "$4,000",          "$10,000",          "$10,000"],
    ["Q2 (Mo 4–6)",  "$8,400",  "$18,000",      "$8,500",          "$34,900",          "$44,900"],
    ["Q3 (Mo 7–9)",  "$12,000", "$55,000",      "$12,000",         "$79,000",          "$123,900"],
    ["Q4 (Mo 10–12)","$15,000", "$112,500",     "$18,000",         "$145,500",         "$269,400"],
    ["12-MO TOTAL",  "$40,200", "$186,700",     "$42,500",         "", "$269,400"],
]
proj_table = Table(projection, colWidths=[W*0.16, W*0.13, W*0.14, W*0.17, W*0.19, W*0.21])
proj_table.setStyle(TableStyle([
    ("BACKGROUND",    (0,0),(-1,0),  colors.HexColor("#1a1a2e")),
    ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
    ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
    ("FONTSIZE",      (0,0),(-1,-1), 8.5),
    ("FONTNAME",      (0,1),(-1,-2), "Helvetica"),
    ("FONTNAME",      (0,-1),(-1,-1),"Helvetica-Bold"),
    ("BACKGROUND",    (0,-1),(-1,-1),colors.HexColor("#e8f0e8")),
    ("BACKGROUND",    (2,1),(2,-1),  colors.HexColor("#fff8f0")),
    ("ROWBACKGROUNDS",(0,1),(-1,-2), [colors.HexColor("#f4f6fb"), colors.white,
                                       colors.HexColor("#f4f6fb"), colors.white]),
    ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor("#cccccc")),
    ("ALIGN",         (1,0),(-1,-1), "CENTER"),
    ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ("TOPPADDING",    (0,0),(-1,-1), 7),
    ("BOTTOMPADDING", (0,0),(-1,-1), 7),
    ("LEFTPADDING",   (0,0),(-1,-1), 7),
]))
story.append(proj_table)
story.append(Spacer(1, 8))
story.append(Paragraph(
    "Note: Heavy fleet projections assume active recruiting begins in Month 1 with first units "
    "dispatched by Month 2–3. Q2 and beyond reflect the compounding effect of signed owner-operators "
    "running consistent monthly load volume. These are conservative mid-range estimates based on "
    "industry-standard owner-operator activity levels.", body_s))
story.append(Spacer(1, 6))
story.append(callout("$100,000 is achievable by Month 7–8 with heavy fleet active. $250,000+ is the 12-month ceiling.", bg="#2d6a2d"))

# ═══════════════════════════════════════════════════════════════════
# 7-DAY ACTION PLAN
# ═══════════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(Paragraph("START TODAY — 7-DAY ACTION PLAN (ALL THREE STREAMS)", h1_s))
story.append(section_rule())

week = [
    ["DAY",     "ACTION",                                                                    "STREAM",       "RESULT"],
    ["Today",   "Post driver recruitment ad for cargo van + sprinter owners on Facebook, Craigslist, LinkedIn.", "Light Fleet", "First inquiries"],
    ["Today",   "Post driver recruitment ad for semi and box truck owner-operators on DAT and Facebook 'Owner Operator Nation.'", "Heavy Fleet", "Heavy pipeline opens"],
    ["Today",   "Post IEBC consulting offer on LinkedIn. Email 10 business owner contacts.", "IEBC",         "Discovery calls booked"],
    ["Day 2",   "Activate AI agents on 123Loadboard + DAT to scan light AND heavy freight boards simultaneously.", "3LL Both",    "Loads identified"],
    ["Day 2",   "Call 3 independent CDL-A drivers in your network — pitch the 10% dispatch model.", "Heavy Fleet", "First semi interest"],
    ["Day 3",   "Onboard first light fleet driver. Send dispatch agreement (NDA already built).", "Light Fleet", "First driver signed"],
    ["Day 4",   "Brief Cecilia Gulley (CSO, Tacoma) on the heavy fleet pipeline. Assign her Pacific Northwest semi and reefer recruitment.", "Heavy Fleet", "West Coast pipeline"],
    ["Day 5",   "Run first IEBC discovery call. Pitch strategy session or dispatch consulting package.", "IEBC",         "First paid client"],
    ["Day 6",   "Sign first heavy fleet owner-operator (box truck or semi). Dispatch first heavy load.", "Heavy Fleet", "First heavy revenue"],
    ["Day 7",   "Review all three pipeline statuses. Set 30-day targets for each stream.", "All",          "Week 1 complete"],
]
wk_table = Table(week, colWidths=[W*0.08, W*0.46, W*0.18, W*0.28])
wk_table.setStyle(TableStyle([
    ("BACKGROUND",    (0,0),(-1,0),  colors.HexColor("#1a1a2e")),
    ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
    ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
    ("FONTSIZE",      (0,0),(-1,-1), 8.5),
    ("FONTNAME",      (0,1),(-1,-1), "Helvetica"),
    ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.HexColor("#f4f6fb"), colors.white]),
    ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor("#cccccc")),
    ("VALIGN",        (0,0),(-1,-1), "TOP"),
    ("TOPPADDING",    (0,0),(-1,-1), 6),
    ("BOTTOMPADDING", (0,0),(-1,-1), 6),
    ("LEFTPADDING",   (0,0),(-1,-1), 7),
]))
story.append(wk_table)
story.append(Spacer(1, 12))

# ═══════════════════════════════════════════════════════════════════
# THE LEVERAGE POINT + KEY AVOIDS
# ═══════════════════════════════════════════════════════════════════
story.append(Paragraph("THE ADVANTAGE YOU HAVE THAT COMPETITORS DON'T", h1_s))
story.append(section_rule())
for item in [
    "<b>AI-powered dispatch across ALL fleet types.</b> Most dispatchers are one person with a phone and a load board account. Your AI agents run 24/7 across multiple boards simultaneously — this is a real competitive moat. Lead with it when recruiting heavy fleet drivers.",
    "<b>Cecilia Gulley as CSO in Tacoma.</b> The Pacific Northwest is one of the most active reefer and flatbed markets in the country (produce, seafood, lumber, manufacturing). She is physically in that market. Put her on heavy fleet recruitment from day one.",
    "<b>IEBC as the consulting arm that sells 3LL's model.</b> Carrier companies will pay IEBC $2,500+ to learn how to build an AI-dispatched fleet — and then 3LL dispatches their drivers. One client relationship generates revenue from two streams.",
    "<b>You already have the legal infrastructure.</b> NDAs, contracts, and agreements are done. You can onboard a new owner-operator today — there is no legal barrier to first revenue.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))

story.append(Spacer(1, 8))
story.append(Paragraph("WHAT TO AVOID", h1_s))
story.append(section_rule())
for item in [
    "<b>Don't wait to build the heavy fleet pipeline.</b> Every week you delay is a week without your highest-earning asset. Start recruiting CDL-A owner-operators today even if you have no loads confirmed — sign them and then find the freight.",
    "<b>Don't underestimate the reefer and flatbed market.</b> These drivers are often underserved by dispatchers who focus only on dry van. That gap is your entry point.",
    "<b>Don't let Cecilia sit idle while you're setting up.</b> Her first job as CSO is pipeline development — Pacific Northwest heavy fleet recruitment and IEBC client acquisition in Washington State.",
    "<b>Don't ignore fleet accounts.</b> One company with 5 box trucks on your dispatch platform = 5 units overnight. Target small trucking companies, not just individual owner-operators.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_s))

story.append(Spacer(1, 14))
story.append(hr(before=8, after=6, thick=1, col="#1a1a2e"))
story.append(Paragraph(
    "IEBC Business Consultants | 3 Lakes Logistics LLC — Confidential Revenue Strategy | Mark Odom, CEO",
    footer_s))

doc.build(story)
print(f"PDF generated: {OUTPUT}")
