from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

OUTPUT = "/home/user/3-Lakes-Logistics/3LL_IEBC_NDA_Gulley.pdf"

doc = SimpleDocTemplate(OUTPUT, pagesize=letter,
    rightMargin=1*inch, leftMargin=1*inch,
    topMargin=1*inch, bottomMargin=1*inch)

styles = getSampleStyleSheet()

title_style = ParagraphStyle("Title", parent=styles["Title"],
    fontSize=16, spaceAfter=4, textColor=colors.HexColor("#1a1a2e"),
    alignment=TA_CENTER, leading=20)
subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"],
    fontSize=11, spaceAfter=6, alignment=TA_CENTER,
    textColor=colors.HexColor("#444444"), leading=14)
sub2_style = ParagraphStyle("Sub2", parent=styles["Normal"],
    fontSize=10, spaceAfter=18, alignment=TA_CENTER,
    textColor=colors.HexColor("#666666"), leading=13)
h1_style = ParagraphStyle("H1", parent=styles["Heading1"],
    fontSize=12, spaceBefore=16, spaceAfter=5,
    textColor=colors.HexColor("#1a1a2e"), leading=15)
h2_style = ParagraphStyle("H2", parent=styles["Heading2"],
    fontSize=10.5, spaceBefore=10, spaceAfter=3,
    textColor=colors.HexColor("#333366"), leading=13)
body_style = ParagraphStyle("Body", parent=styles["Normal"],
    fontSize=10, spaceAfter=7, leading=15, alignment=TA_JUSTIFY)
bullet_style = ParagraphStyle("Bullet", parent=styles["Normal"],
    fontSize=10, spaceAfter=5, leading=14,
    leftIndent=18, bulletIndent=6, alignment=TA_JUSTIFY)
sig_style = ParagraphStyle("Sig", parent=styles["Normal"],
    fontSize=10, spaceAfter=5, leading=16, spaceBefore=4)
footer_style = ParagraphStyle("Footer", parent=styles["Normal"],
    fontSize=8, alignment=TA_CENTER,
    textColor=colors.HexColor("#888888"), spaceAfter=0, spaceBefore=12)

def hr(space_before=6, space_after=12, thick=0.5, color="#cccccc"):
    return HRFlowable(width="100%", thickness=thick,
        color=colors.HexColor(color), spaceBefore=space_before, spaceAfter=space_after)

def b(items, numbered=False):
    out = []
    for i, item in enumerate(items, 1):
        prefix = f"{i}. &nbsp;" if numbered else "&#8226; &nbsp;"
        out.append(Paragraph(f"{prefix}{item}", bullet_style))
    return out

story = []

# Title
story.append(Spacer(1, 0.15*inch))
story.append(Paragraph("NON-DISCLOSURE AND CONFIDENTIALITY AGREEMENT", title_style))
story.append(Paragraph("3 Lakes Logistics LLC", subtitle_style))
story.append(Paragraph("IEBC Business Consultants — Portfolio Company Engagement", sub2_style))
story.append(hr(space_before=0, space_after=16, thick=2, color="#1a1a2e"))

# Preamble
story.append(Paragraph(
    'This Non-Disclosure and Confidentiality Agreement (this <b>"Agreement"</b>) is entered into and made '
    'effective as of the last date of signature below (the <b>"Effective Date"</b>), by and between:', body_style))
story.append(Paragraph(
    '&#8226; &nbsp;<b>3 LAKES LOGISTICS LLC</b>, a Michigan limited liability company with its principal '
    'place of business in Detroit, Michigan, represented by its Chief Executive Officer, <b>Mark Odom</b> '
    '(hereinafter referred to as <b>"3 Lakes Logistics"</b> or the <b>"Company"</b>); and', bullet_style))
story.append(Paragraph(
    '&#8226; &nbsp;<b>CECILA GULLEY</b>, an individual residing at [Insert Address] '
    '(hereinafter referred to as the <b>"Counterparty"</b>).', bullet_style))
story.append(Spacer(1, 4))
story.append(Paragraph(
    '3 Lakes Logistics and the Counterparty may collectively be referred to as the <b>"Parties"</b> '
    'or individually as a <b>"Party."</b>', body_style))
story.append(hr())

# 1
story.append(Paragraph("1. RECITALS &amp; PURPOSE", h1_style))
story.append(Paragraph(
    "<b>WHEREAS</b>, 3 Lakes Logistics LLC is a Michigan-based enterprise engaged in logistics, freight "
    "dispatch, and investment operations, and serves as the parent and controlling entity of a portfolio of "
    'business ventures, including <b>IEBC Business Consultants</b> (the <b>"Portfolio Company"</b>); and', body_style))
story.append(Paragraph(
    "<b>WHEREAS</b>, IEBC Business Consultants is a professional business consulting firm operating as a "
    "portfolio company under the organizational umbrella and strategic direction of 3 Lakes Logistics LLC; and", body_style))
story.append(Paragraph(
    "<b>WHEREAS</b>, 3 Lakes Logistics has engaged Cecila Gulley as <b>Managing Partner of IEBC Business "
    "Consultants</b>, a senior leadership role through which she will be granted full access to confidential, "
    "proprietary, and strategically sensitive information belonging to both 3 Lakes Logistics and IEBC; and", body_style))
story.append(Paragraph(
    "<b>WHEREAS</b>, the Parties desire to establish the terms under which Confidential Information shall be "
    "protected and restricted in use at all times.", body_style))
story.append(Paragraph(
    "<b>NOW, THEREFORE</b>, in consideration of the Counterparty's engagement, the mutual covenants "
    "contained herein, and other good and valuable consideration, the Parties agree as follows:", body_style))

# 2
story.append(Paragraph("2. DEFINITION OF CONFIDENTIAL INFORMATION", h1_style))
story.append(Paragraph(
    '<b>"Confidential Information"</b> means any and all non-public, proprietary, or sensitive information, '
    'data, or material belonging to or controlled by 3 Lakes Logistics LLC or IEBC Business Consultants '
    '(collectively, the <b>"Disclosing Party"</b>) that is disclosed to, received by, developed by, or '
    'accessed by Cecila Gulley (the <b>"Receiving Party"</b>) in connection with her role as Managing Partner '
    'of IEBC Business Consultants, whether communicated orally, in writing, electronically, visually, or '
    'through direct operational participation, and whether or not specifically labeled "confidential."', body_style))
story.append(Paragraph("Without limiting the foregoing, Confidential Information specifically includes:", body_style))

story.append(Paragraph("A. 3 Lakes Logistics LLC — Corporate &amp; Operational Confidential Information", h2_style))
story.extend(b([
    "Corporate structure, ownership interests, equity arrangements, and investment portfolio composition, including the nature and terms of 3 Lakes Logistics' interest in IEBC Business Consultants and any other portfolio companies.",
    "Strategic growth roadmaps, expansion plans, capital deployment strategies, and merger/acquisition targets or negotiations.",
    "Proprietary logistics and freight dispatch systems, AI agent workforce architectures, automated workflow configurations, and technology infrastructure.",
    "Financial statements, revenue models, profit margins, investor relations data, and capitalization tables.",
    "Contracts, partnership agreements, vendor terms, and carrier or broker relationships.",
]))

story.append(Paragraph("B. IEBC Business Consultants — Portfolio Company Confidential Information", h2_style))
story.extend(b([
    "Client and prospective client identities, contact information, contractual terms, engagement histories, fees, and strategic needs.",
    "Proprietary consulting methodologies, analytical frameworks, service delivery systems, and intellectual property developed for client engagements.",
    "Business development pipelines, proposal documents, pricing structures, and competitive positioning strategies.",
    "Internal personnel information, compensation arrangements, performance data, and organizational development plans.",
]))

story.append(Paragraph("C. Cross-Entity Shared Information", h2_style))
story.extend(b([
    "Any information shared between 3 Lakes Logistics and IEBC Business Consultants in the context of portfolio management, financial reporting, or strategic alignment.",
    "Any information developed by the Counterparty in her capacity as Managing Partner that draws upon assets, clients, data, or methodologies of either entity.",
]))

# 3
story.append(Paragraph("3. EXCLUSIONS FROM CONFIDENTIALITY", h1_style))
story.append(Paragraph(
    "Confidential Information does not include information the Receiving Party can demonstrate by clear written evidence:", body_style))
story.extend(b([
    "Is or becomes publicly available through no act or omission of the Receiving Party;",
    "Was rightfully in the Receiving Party's possession prior to disclosure, without any obligation of confidentiality;",
    "Is independently developed by the Receiving Party without reference to any Confidential Information; or",
    "Is rightfully received from a third party with no confidentiality obligation to either entity.",
], numbered=True))

# 4
story.append(Paragraph("4. OBLIGATIONS &amp; USE RESTRICTIONS", h1_style))
story.append(Paragraph(
    "Cecila Gulley agrees to observe the following strict covenants at all times during and after her engagement:", body_style))
obligations = [
    ("<b>Limited Purpose Use:</b>", "Counterparty shall use Confidential Information solely for the legitimate performance of her duties as Managing Partner of IEBC Business Consultants under the direction of 3 Lakes Logistics, and for no other personal, commercial, competitive, or external purpose."),
    ("<b>Standard of Care:</b>", "Counterparty shall protect all Confidential Information with the highest degree of care — not less than the care used to protect her own most sensitive personal data — and shall implement appropriate safeguards to prevent unauthorized access, disclosure, or loss."),
    ("<b>Restricted Disclosure:</b>", "Counterparty shall not disclose, share, transfer, publish, or make available any Confidential Information to any third party — including family, associates, advisors, or prospective employers — without prior express written consent of Mark Odom on behalf of 3 Lakes Logistics."),
    ("<b>No Competitive Use:</b>", "Counterparty shall not use any Confidential Information of either entity to benefit any competing enterprise, to solicit clients or personnel, or for any purpose adverse to 3 Lakes Logistics or its portfolio companies."),
    ("<b>No Unauthorized Reproduction:</b>", "Counterparty shall not copy, photograph, extract, or summarize any Confidential Information beyond what is strictly required to fulfill her duties as Managing Partner."),
    ("<b>Portfolio Confidentiality:</b>", "Counterparty acknowledges that the existence, structure, identity, financial terms, and strategic direction of 3 Lakes Logistics' entire investment portfolio — including IEBC Business Consultants — constitutes Confidential Information and shall not be disclosed to any outside party."),
]
for label, text in obligations:
    story.append(Paragraph(f"&#8226; &nbsp;{label} {text}", bullet_style))

# 5
story.append(Paragraph("5. INTELLECTUAL PROPERTY ASSIGNMENT", h1_style))
story.append(Paragraph(
    "All inventions, works of authorship, innovations, improvements, methodologies, tools, processes, client "
    "deliverables, templates, and other intellectual property developed, authored, or conceived by Cecila Gulley "
    "during and in connection with her engagement as Managing Partner of IEBC Business Consultants — whether "
    "developed alone or jointly — shall be and remain the exclusive property of <b>3 Lakes Logistics LLC "
    "and/or IEBC Business Consultants</b>, as designated by Mark Odom. The Counterparty hereby irrevocably "
    "assigns all right, title, and interest in such works to 3 Lakes Logistics.", body_style))

# 6
story.append(Paragraph("6. NON-SOLICITATION OF CLIENTS, PARTNERS &amp; PERSONNEL", h1_style))
story.append(Paragraph(
    "During the term of this Agreement and for a period of <b>two (2) years</b> following the conclusion of "
    "Cecila Gulley's engagement — regardless of the reason — the Counterparty shall not, directly or indirectly:", body_style))
story.extend(b([
    "<b>Solicit or service</b> any client, prospective client, referral source, carrier, broker, or business partner of 3 Lakes Logistics or IEBC Business Consultants with whom she had contact or knowledge during her engagement, for the purpose of providing competing services or diverting business;",
    "<b>Recruit or solicit</b> any employee, contractor, partner, or associate of 3 Lakes Logistics or IEBC Business Consultants to leave either entity or join a competing venture;",
    "<b>Establish or assist</b> any enterprise that directly competes with the consulting services offered by IEBC Business Consultants using knowledge, relationships, or methodologies obtained through her engagement; or",
    "<b>Disparage or defame</b> the business reputation, client relationships, or professional standing of 3 Lakes Logistics LLC, IEBC Business Consultants, or Mark Odom in any public or private forum.",
], numbered=True))

# 7
story.append(Paragraph("7. COMPELLED LEGAL DISCLOSURE", h1_style))
story.append(Paragraph(
    "If the Counterparty is compelled by a valid subpoena, court order, or governmental authority to disclose "
    "any Confidential Information, she shall — to the maximum extent legally permissible — provide 3 Lakes "
    "Logistics with immediate prior written notice sufficient to allow 3 Lakes Logistics to seek a protective "
    "order or challenge the compelled disclosure. If no relief is obtained, the Counterparty shall disclose "
    "only the minimum portion of Confidential Information legally required.", body_style))

# 8
story.append(Paragraph("8. TERM &amp; SURVIVAL", h1_style))
story.append(Paragraph(
    "This Agreement shall commence on the Effective Date and shall remain in full force and effect for the "
    "entire duration of Cecila Gulley's engagement as Managing Partner of IEBC Business Consultants.", body_style))
story.extend(b([
    "Upon the conclusion of the Counterparty's engagement — for any reason — the general non-disclosure and non-use obligations herein shall <b>survive for three (3) years</b>.",
    "<b>Critical Exception:</b> With respect to 3 Lakes Logistics' proprietary technology, AI systems, portfolio investment strategy, and all core trade secrets of either entity, confidentiality and non-use obligations shall <b>survive indefinitely</b>.",
]))

# 9
story.append(Paragraph("9. RETURN OR DESTRUCTION OF MATERIALS", h1_style))
story.append(Paragraph(
    "Upon the conclusion of the Counterparty's engagement, or upon written demand by 3 Lakes Logistics at any "
    "time, Cecila Gulley shall promptly:", body_style))
story.extend(b([
    "Return all documents, records, files, devices, and materials — in physical or digital form — containing or derived from the Confidential Information of either 3 Lakes Logistics or IEBC Business Consultants;",
    "Permanently and irreversibly delete all digital copies from personal devices, personal cloud accounts, and personal email systems; and",
    "Provide written certification to 3 Lakes Logistics within <b>five (5) business days</b> confirming full compliance with this Section.",
], numbered=True))

# 10
story.append(Paragraph("10. REMEDIES FOR BREACH", h1_style))
story.append(Paragraph(
    "The Counterparty acknowledges that any unauthorized disclosure, misappropriation, or competitive use of "
    "Confidential Information belonging to 3 Lakes Logistics or IEBC Business Consultants — including client "
    "solicitation, misuse of proprietary methodologies, disclosure of portfolio structure, or personnel "
    "recruitment — will cause immediate, substantial, and irreparable harm, for which monetary damages alone "
    "are entirely inadequate.", body_style))
story.append(Paragraph("In the event of any breach or credible threat of breach, 3 Lakes Logistics shall be entitled to seek, without posting a bond:", body_style))
story.extend(b([
    "Immediate injunctive relief and a temporary restraining order in any court of competent jurisdiction;",
    "Specific performance compelling compliance with the terms of this Agreement; and",
    "All other legal and equitable remedies, including actual damages, lost profits, attorneys' fees, and costs of enforcement.",
]))

# 11
story.append(Paragraph("11. GOVERNING LAW AND JURISDICTION", h1_style))
story.append(Paragraph(
    "This Agreement shall be governed by and construed in accordance with the laws of the <b>State of Michigan</b>, "
    "without regard to conflict-of-law principles. The Parties irrevocably consent to the exclusive jurisdiction "
    "of the state and federal courts of <b>Wayne County, Michigan</b> for any dispute arising from this Agreement.", body_style))

# 12
story.append(Paragraph("12. MISCELLANEOUS", h1_style))
misc = [
    ("<b>Entire Agreement:</b>", "This Agreement constitutes the complete and exclusive understanding between the Parties regarding confidentiality and supersedes all prior oral or written representations on the subject."),
    ("<b>Amendments:</b>", "No amendment shall be valid unless in writing and signed by authorized representatives of both Parties."),
    ("<b>No Assignment:</b>", "Neither Party may assign rights or obligations under this Agreement without prior written consent of the other Party."),
    ("<b>Severability:</b>", "If any provision is found unenforceable, the remaining provisions shall remain in full force and effect."),
    ("<b>No Waiver:</b>", "Failure to enforce any provision shall not constitute a waiver of the right to enforce it in the future."),
    ("<b>Counterparts &amp; Electronic Execution:</b>", "This Agreement may be signed in counterparts. Electronic, DocuSign, and PDF signatures are fully binding and legally enforceable."),
    ("<b>Independent Legal Advice:</b>", "Each Party acknowledges the opportunity to review this Agreement with independent counsel and enters into it voluntarily and with full understanding of its terms."),
]
for label, text in misc:
    story.append(Paragraph(f"&#8226; &nbsp;{label} {text}", bullet_style))

# Signature page
story.append(PageBreak())
story.append(Paragraph("IN WITNESS WHEREOF", h1_style))
story.append(Paragraph(
    "The Parties have executed this Non-Disclosure and Confidentiality Agreement as of the Effective Date set forth below.",
    body_style))
story.append(Spacer(1, 0.25*inch))
story.append(hr(thick=0.5))

# Sig 1
story.append(Paragraph("<b>3 LAKES LOGISTICS LLC</b>", sig_style))
story.append(Paragraph("<i>(Parent Entity &amp; Portfolio Manager — IEBC Business Consultants)</i>",
    ParagraphStyle("italic", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#555555"), spaceAfter=10)))
story.append(Paragraph("Signature: &nbsp;___________________________________________", sig_style))
story.append(Paragraph("By: &nbsp;<b>Mark Odom</b>", sig_style))
story.append(Paragraph("Title: &nbsp;<b>Chief Executive Officer, 3 Lakes Logistics LLC</b>", sig_style))
story.append(Paragraph("Date: &nbsp;___________________________________________", sig_style))
story.append(Spacer(1, 0.3*inch))
story.append(hr(thick=0.5))

# Sig 2
story.append(Paragraph("<b>COUNTERPARTY</b>", sig_style))
story.append(Paragraph("Signature: &nbsp;___________________________________________", sig_style))
story.append(Paragraph("By: &nbsp;<b>Cecila Gulley</b>", sig_style))
story.append(Paragraph("Title: &nbsp;<b>Managing Partner, IEBC Business Consultants</b>", sig_style))
story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<i>(Portfolio Company of 3 Lakes Logistics LLC)</i>",
    ParagraphStyle("italic2", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#555555"), spaceAfter=6)))
story.append(Paragraph("Date: &nbsp;___________________________________________", sig_style))
story.append(Spacer(1, 0.3*inch))
story.append(hr(thick=0.5))

story.append(Paragraph(
    "This Agreement is intended for operational use. 3 Lakes Logistics LLC recommends review by a licensed Michigan attorney prior to execution.",
    footer_style))

doc.build(story)
print(f"PDF generated: {OUTPUT}")
