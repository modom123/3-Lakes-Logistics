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
italic_style = ParagraphStyle("italic", parent=styles["Normal"],
    fontSize=9, textColor=colors.HexColor("#555555"), spaceAfter=10)
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

# ── Title ──────────────────────────────────────────────────────────────────────
story.append(Spacer(1, 0.15*inch))
story.append(Paragraph("NON-DISCLOSURE AND CONFIDENTIALITY AGREEMENT", title_style))
story.append(Paragraph("IEBC Business Consultants (Parent Company)", subtitle_style))
story.append(Paragraph("3 Lakes Logistics LLC — Portfolio Company | Chief Strategy Officer Engagement", sub2_style))
story.append(hr(space_before=0, space_after=16, thick=2, color="#1a1a2e"))

# ── Preamble ───────────────────────────────────────────────────────────────────
story.append(Paragraph(
    'This Non-Disclosure and Confidentiality Agreement (this <b>"Agreement"</b>) is entered into and made '
    'effective as of the last date of signature below (the <b>"Effective Date"</b>), by and between:', body_style))
story.append(Paragraph(
    '&#8226; &nbsp;<b>IEBC BUSINESS CONSULTANTS</b>, a business consulting enterprise with its principal '
    'place of business in Detroit, Michigan, represented by its Chief Executive Officer, <b>Mark Odom</b> '
    '(hereinafter referred to as <b>"IEBC"</b> or the <b>"Company"</b>); and', bullet_style))
story.append(Paragraph(
    '&#8226; &nbsp;<b>CECILA GULLEY</b>, an individual residing in Tacoma, Washington '
    '(hereinafter referred to as the <b>"Counterparty"</b>).', bullet_style))
story.append(Spacer(1, 4))
story.append(Paragraph(
    'IEBC and the Counterparty may collectively be referred to as the <b>"Parties"</b> '
    'or individually as a <b>"Party."</b>', body_style))
story.append(hr())

# ── 1 ─────────────────────────────────────────────────────────────────────────
story.append(Paragraph("1. RECITALS &amp; PURPOSE", h1_style))
story.append(Paragraph(
    "<b>WHEREAS</b>, IEBC Business Consultants is a professional business consulting enterprise and the "
    "parent company responsible for strategic direction, governance, and oversight of its portfolio of "
    "business ventures; and", body_style))
story.append(Paragraph(
    "<b>WHEREAS</b>, <b>3 Lakes Logistics LLC</b>, a Michigan limited liability company engaged in "
    "logistics, freight dispatch, and automated operations, operates as a <b>portfolio company</b> "
    'under the ownership and strategic direction of IEBC Business Consultants '
    '(hereinafter referred to as the <b>"Portfolio Company"</b>); and', body_style))
story.append(Paragraph(
    "<b>WHEREAS</b>, IEBC Business Consultants has engaged Cecila Gulley in the executive capacity of "
    "<b>Chief Strategy Officer (\"CSO\")</b>, a senior C-suite leadership role within IEBC through which "
    "she will be granted full access to confidential, proprietary, and strategically sensitive information "
    "belonging to both IEBC Business Consultants and its portfolio company, 3 Lakes Logistics LLC; and", body_style))
story.append(Paragraph(
    "<b>WHEREAS</b>, the Parties desire to establish the terms under which all Confidential Information "
    "shall be protected, restricted in use, and safeguarded at all times.", body_style))
story.append(Paragraph(
    "<b>NOW, THEREFORE</b>, in consideration of the Counterparty's engagement as Chief Strategy Officer, "
    "the mutual covenants contained herein, and other good and valuable consideration, the receipt and "
    "sufficiency of which are hereby acknowledged, the Parties agree as follows:", body_style))

# ── 2 ─────────────────────────────────────────────────────────────────────────
story.append(Paragraph("2. DEFINITION OF CONFIDENTIAL INFORMATION", h1_style))
story.append(Paragraph(
    '<b>"Confidential Information"</b> means any and all non-public, proprietary, or sensitive '
    'information, data, or material belonging to or controlled by IEBC Business Consultants or its '
    'portfolio company, 3 Lakes Logistics LLC (collectively, the <b>"Disclosing Party"</b>), that is '
    'disclosed to, received by, developed by, or accessed by Cecila Gulley (the <b>"Receiving '
    'Party"</b>) in connection with her role as Chief Strategy Officer of IEBC Business Consultants, '
    'whether communicated orally, in writing, electronically, visually, or through direct operational '
    'participation, and whether or not specifically labeled "confidential."', body_style))
story.append(Paragraph("Without limiting the foregoing, Confidential Information specifically includes:", body_style))

story.append(Paragraph("A. IEBC Business Consultants — Parent Company Confidential Information", h2_style))
story.extend(b([
    "Corporate structure, ownership interests, equity arrangements, and composition of the full investment portfolio, including the nature and terms of IEBC's controlling interest in 3 Lakes Logistics LLC and any other portfolio companies.",
    "Strategic growth roadmaps, capital deployment strategies, expansion plans, merger/acquisition targets, and board-level governance decisions.",
    "Proprietary consulting frameworks, analytical models, intellectual property, client methodologies, and service delivery systems developed by or for IEBC.",
    "Financial statements, revenue models, profit and loss data, investor relations information, and capitalization tables of IEBC and its portfolio.",
    "Client and prospective client identities, engagement terms, pricing structures, referral relationships, and business development pipelines.",
    "Internal personnel information, compensation structures, performance data, and organizational development plans.",
]))

story.append(Paragraph("B. 3 Lakes Logistics LLC — Portfolio Company Confidential Information", h2_style))
story.extend(b([
    "Proprietary logistics and freight dispatch systems, AI agent workforce architectures, automated workflow configurations, algorithmic bidding models, and technology infrastructure.",
    "Carrier rosters, driver networks, broker relationships, lane data, fleet deployment profiles, and capacity metrics.",
    "Commercial fee structures, revenue models, profit margins, operational scaling roadmaps, and strategic partnerships.",
    "API integrations, data systems, software tools, vendor agreements, and technical credentials.",
    "Any financial, operational, or strategic data relating to 3 Lakes Logistics LLC's business operations.",
]))

story.append(Paragraph("C. Cross-Entity Shared Information", h2_style))
story.extend(b([
    "Any information exchanged between IEBC Business Consultants and 3 Lakes Logistics LLC in the context of parent-portfolio governance, financial reporting, or strategic alignment.",
    "Any information developed by the Counterparty in her capacity as Chief Strategy Officer that draws upon assets, clients, data, or methodologies of either entity.",
]))

# ── 3 ─────────────────────────────────────────────────────────────────────────
story.append(Paragraph("3. EXCLUSIONS FROM CONFIDENTIALITY", h1_style))
story.append(Paragraph(
    "Confidential Information does not include information the Receiving Party can demonstrate by clear and contemporaneous written evidence:", body_style))
story.extend(b([
    "Is or becomes publicly available through no act or omission of the Receiving Party;",
    "Was rightfully in the Receiving Party's possession prior to her engagement with IEBC, without any obligation of confidentiality;",
    "Is independently developed by the Receiving Party entirely without reference to or reliance upon any Confidential Information; or",
    "Is rightfully received from a third party with no confidentiality obligation to IEBC or 3 Lakes Logistics.",
], numbered=True))

# ── 4 ─────────────────────────────────────────────────────────────────────────
story.append(Paragraph("4. OBLIGATIONS &amp; USE RESTRICTIONS", h1_style))
story.append(Paragraph(
    "Cecila Gulley, as Chief Strategy Officer of IEBC Business Consultants, agrees to observe the "
    "following strict covenants at all times during and after her engagement:", body_style))
obligations = [
    ("<b>Limited Purpose Use:</b>",
     "Counterparty shall use Confidential Information solely for the legitimate performance of her duties as "
     "Chief Strategy Officer of IEBC Business Consultants, and for no other personal, commercial, competitive, or external purpose."),
    ("<b>Standard of Care:</b>",
     "Counterparty shall protect all Confidential Information with the highest degree of care — not less than "
     "the care used to protect her own most sensitive personal data — and shall implement appropriate "
     "safeguards to prevent unauthorized access, disclosure, or loss."),
    ("<b>Restricted Disclosure:</b>",
     "Counterparty shall not disclose, share, transfer, publish, or otherwise make available any Confidential "
     "Information to any third party — including family, associates, advisors, or prospective employers — "
     "without prior express written consent of Mark Odom on behalf of IEBC Business Consultants."),
    ("<b>No Competitive Use:</b>",
     "Counterparty shall not use any Confidential Information of IEBC or 3 Lakes Logistics to benefit any "
     "competing enterprise, to solicit clients or personnel away from either entity, or for any purpose "
     "adverse to the interests of IEBC Business Consultants or its portfolio companies."),
    ("<b>No Unauthorized Reproduction:</b>",
     "Counterparty shall not copy, photograph, extract, screen-capture, or summarize any Confidential "
     "Information beyond what is strictly required to fulfill her duties as Chief Strategy Officer."),
    ("<b>Portfolio Confidentiality:</b>",
     "Counterparty acknowledges that the existence, structure, identity, financial terms, and strategic "
     "direction of IEBC's entire investment portfolio — including 3 Lakes Logistics LLC — constitutes "
     "Confidential Information and shall not be disclosed to any outside party without express written authorization."),
]
for label, text in obligations:
    story.append(Paragraph(f"&#8226; &nbsp;{label} {text}", bullet_style))

# ── 5 ─────────────────────────────────────────────────────────────────────────
story.append(Paragraph("5. INTELLECTUAL PROPERTY ASSIGNMENT", h1_style))
story.append(Paragraph(
    "All inventions, works of authorship, innovations, improvements, methodologies, tools, processes, "
    "strategic plans, client deliverables, templates, and other intellectual property developed, authored, "
    "or conceived by Cecila Gulley during and in connection with her engagement as Chief Strategy Officer "
    "of IEBC Business Consultants — whether developed alone or jointly, and whether during business hours "
    "or otherwise — shall be and remain the exclusive property of <b>IEBC Business Consultants and/or "
    "3 Lakes Logistics LLC</b>, as designated by Mark Odom. The Counterparty hereby irrevocably assigns "
    "all right, title, and interest in such works to IEBC Business Consultants.", body_style))

# ── 6 ─────────────────────────────────────────────────────────────────────────
story.append(Paragraph("6. NON-SOLICITATION OF CLIENTS, PARTNERS &amp; PERSONNEL", h1_style))
story.append(Paragraph(
    "During the term of this Agreement and for a period of <b>two (2) years</b> following the conclusion "
    "of Cecila Gulley's engagement as Chief Strategy Officer — regardless of the reason for termination — "
    "the Counterparty shall not, directly or indirectly:", body_style))
story.extend(b([
    "<b>Solicit or service</b> any client, prospective client, referral source, carrier, broker, or business "
    "partner of IEBC Business Consultants or 3 Lakes Logistics LLC with whom she had contact, knowledge of, "
    "or involvement with during her engagement, for the purpose of providing competing services or diverting "
    "business away from either entity;",
    "<b>Recruit or solicit</b> any employee, contractor, partner, or associate of IEBC Business Consultants "
    "or 3 Lakes Logistics LLC to terminate or reduce their engagement or to join a competing venture;",
    "<b>Establish or assist</b> any enterprise that directly competes with the consulting or logistics "
    "services offered by IEBC Business Consultants or 3 Lakes Logistics LLC using knowledge, relationships, "
    "or methodologies obtained through her engagement; or",
    "<b>Disparage or defame</b> the business reputation, client relationships, or professional standing of "
    "IEBC Business Consultants, 3 Lakes Logistics LLC, or Mark Odom, in any public or private forum.",
], numbered=True))

# ── 7 ─────────────────────────────────────────────────────────────────────────
story.append(Paragraph("7. COMPELLED LEGAL DISCLOSURE", h1_style))
story.append(Paragraph(
    "If the Counterparty is compelled by a valid subpoena, court order, or governmental regulatory "
    "authority to disclose any Confidential Information, she shall — to the maximum extent legally "
    "permissible — provide IEBC Business Consultants with immediate prior written notice sufficient to "
    "allow IEBC to seek a protective order or challenge the compelled disclosure. If no relief is "
    "obtained, the Counterparty shall disclose only the minimum portion of Confidential Information "
    "legally required.", body_style))

# ── 8 ─────────────────────────────────────────────────────────────────────────
story.append(Paragraph("8. TERM &amp; SURVIVAL", h1_style))
story.append(Paragraph(
    "This Agreement shall commence on the Effective Date and shall remain in full force and effect for "
    "the entire duration of Cecila Gulley's engagement as Chief Strategy Officer of IEBC Business "
    "Consultants.", body_style))
story.extend(b([
    "Upon the conclusion of the Counterparty's engagement — for any reason — the general non-disclosure "
    "and non-use obligations herein shall <b>survive for three (3) years</b>.",
    "<b>Critical Exception:</b> With respect to IEBC's proprietary consulting methodologies, portfolio "
    "investment strategy, 3 Lakes Logistics' AI systems and technology infrastructure, and all core trade "
    "secrets of either entity, confidentiality and non-use obligations shall <b>survive indefinitely</b>.",
]))

# ── 9 ─────────────────────────────────────────────────────────────────────────
story.append(Paragraph("9. RETURN OR DESTRUCTION OF MATERIALS", h1_style))
story.append(Paragraph(
    "Upon the conclusion of the Counterparty's engagement, or upon written demand by IEBC Business "
    "Consultants at any time, Cecila Gulley shall promptly:", body_style))
story.extend(b([
    "Return all documents, records, files, devices, and materials — in physical or digital form — "
    "containing or derived from the Confidential Information of IEBC Business Consultants or 3 Lakes Logistics LLC;",
    "Permanently and irreversibly delete all digital copies from personal devices, personal cloud "
    "accounts, and personal email systems; and",
    "Provide written certification to IEBC Business Consultants within <b>five (5) business days</b> "
    "confirming full compliance with this Section.",
], numbered=True))

# ── 10 ────────────────────────────────────────────────────────────────────────
story.append(Paragraph("10. REMEDIES FOR BREACH", h1_style))
story.append(Paragraph(
    "The Counterparty acknowledges that any unauthorized disclosure, misappropriation, or competitive "
    "use of Confidential Information belonging to IEBC Business Consultants or 3 Lakes Logistics LLC — "
    "including client solicitation, misuse of proprietary methodologies, disclosure of portfolio "
    "structure, or personnel recruitment — will cause immediate, substantial, and irreparable harm to "
    "IEBC and its portfolio companies, for which monetary damages alone are entirely inadequate.", body_style))
story.append(Paragraph(
    "In the event of any breach or credible threat of breach, IEBC Business Consultants shall be "
    "entitled to seek, without posting a bond or proving actual financial loss:", body_style))
story.extend(b([
    "Immediate injunctive relief and a temporary restraining order in any court of competent jurisdiction;",
    "Specific performance compelling compliance with the terms of this Agreement; and",
    "All other legal and equitable remedies, including actual damages, lost profits, attorneys' fees, "
    "and costs of enforcement.",
]))

# ── 11 ────────────────────────────────────────────────────────────────────────
story.append(Paragraph("11. GOVERNING LAW AND JURISDICTION", h1_style))
story.append(Paragraph(
    "This Agreement shall be governed by and construed in accordance with the laws of the "
    "<b>State of Michigan</b>, without regard to conflict-of-law principles. The Parties irrevocably "
    "consent to the exclusive jurisdiction of the state and federal courts of <b>Wayne County, "
    "Michigan</b> for any dispute arising from this Agreement.", body_style))

# ── 12 ────────────────────────────────────────────────────────────────────────
story.append(Paragraph("12. MISCELLANEOUS", h1_style))
misc = [
    ("<b>Entire Agreement:</b>",
     "This Agreement constitutes the complete and exclusive understanding between the Parties regarding "
     "confidentiality and supersedes all prior oral or written representations on the subject."),
    ("<b>Amendments:</b>",
     "No amendment shall be valid unless in writing and signed by authorized representatives of both Parties."),
    ("<b>No Assignment:</b>",
     "Neither Party may assign rights or obligations under this Agreement without prior written consent of the other Party."),
    ("<b>Severability:</b>",
     "If any provision is found unenforceable, the remaining provisions shall remain in full force and effect."),
    ("<b>No Waiver:</b>",
     "Failure to enforce any provision shall not constitute a waiver of the right to enforce it in the future."),
    ("<b>Counterparts &amp; Electronic Execution:</b>",
     "This Agreement may be signed in counterparts. Electronic, DocuSign, and PDF signatures are fully binding and legally enforceable."),
    ("<b>Independent Legal Advice:</b>",
     "Each Party acknowledges the opportunity to review this Agreement with independent counsel of their "
     "own choosing and enters into it voluntarily and with full understanding of its terms."),
]
for label, text in misc:
    story.append(Paragraph(f"&#8226; &nbsp;{label} {text}", bullet_style))

# ── Signature Page ─────────────────────────────────────────────────────────────
story.append(PageBreak())
story.append(Paragraph("IN WITNESS WHEREOF", h1_style))
story.append(Paragraph(
    "The Parties have executed this Non-Disclosure and Confidentiality Agreement as of the Effective Date set forth below.",
    body_style))
story.append(Spacer(1, 0.25*inch))
story.append(hr(thick=0.5))

# Sig 1 — IEBC (Parent)
story.append(Paragraph("<b>IEBC BUSINESS CONSULTANTS</b>", sig_style))
story.append(Paragraph("<i>(Parent Company — Portfolio Owner of 3 Lakes Logistics LLC)</i>", italic_style))
story.append(Paragraph("Signature: &nbsp;___________________________________________", sig_style))
story.append(Paragraph("By: &nbsp;<b>Mark Odom</b>", sig_style))
story.append(Paragraph("Title: &nbsp;<b>Chief Executive Officer, IEBC Business Consultants</b>", sig_style))
story.append(Paragraph("Date: &nbsp;___________________________________________", sig_style))
story.append(Spacer(1, 0.3*inch))
story.append(hr(thick=0.5))

# Sig 2 — Cecila Gulley
story.append(Paragraph("<b>COUNTERPARTY</b>", sig_style))
story.append(Paragraph("Signature: &nbsp;___________________________________________", sig_style))
story.append(Paragraph("By: &nbsp;<b>Cecila Gulley</b>", sig_style))
story.append(Paragraph("Title: &nbsp;<b>Chief Strategy Officer (CSO), IEBC Business Consultants</b>", sig_style))
story.append(Paragraph("<i>Oversight extends to 3 Lakes Logistics LLC (Portfolio Company of IEBC Business Consultants)</i>", italic_style))
story.append(Paragraph("Date: &nbsp;___________________________________________", sig_style))
story.append(Spacer(1, 0.3*inch))
story.append(hr(thick=0.5))

story.append(Paragraph(
    "This Agreement is intended for operational use. IEBC Business Consultants recommends review "
    "by a licensed Michigan attorney prior to execution.",
    footer_style))

doc.build(story)
print(f"PDF generated: {OUTPUT}")
