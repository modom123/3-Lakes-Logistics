from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

OUTPUT = "/home/user/3-Lakes-Logistics/IEBC_NDA_Gulley_Odom.pdf"

doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=letter,
    rightMargin=1*inch,
    leftMargin=1*inch,
    topMargin=1*inch,
    bottomMargin=1*inch,
)

styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    "Title", parent=styles["Title"],
    fontSize=16, spaceAfter=6, spaceBefore=0,
    textColor=colors.HexColor("#1a1a2e"), alignment=TA_CENTER, leading=20
)
subtitle_style = ParagraphStyle(
    "Subtitle", parent=styles["Normal"],
    fontSize=12, spaceAfter=18, alignment=TA_CENTER,
    textColor=colors.HexColor("#444444"), leading=16
)
h1_style = ParagraphStyle(
    "H1", parent=styles["Heading1"],
    fontSize=13, spaceBefore=18, spaceAfter=6,
    textColor=colors.HexColor("#1a1a2e"), leading=16,
    borderPad=2
)
h2_style = ParagraphStyle(
    "H2", parent=styles["Heading2"],
    fontSize=11, spaceBefore=12, spaceAfter=4,
    textColor=colors.HexColor("#333366"), leading=14
)
body_style = ParagraphStyle(
    "Body", parent=styles["Normal"],
    fontSize=10, spaceAfter=8, leading=15, alignment=TA_JUSTIFY
)
bullet_style = ParagraphStyle(
    "Bullet", parent=styles["Normal"],
    fontSize=10, spaceAfter=5, leading=14,
    leftIndent=20, bulletIndent=8, alignment=TA_JUSTIFY
)
label_style = ParagraphStyle(
    "Label", parent=styles["Normal"],
    fontSize=10, spaceAfter=5, leading=14,
    leftIndent=20, alignment=TA_JUSTIFY
)
sig_style = ParagraphStyle(
    "Sig", parent=styles["Normal"],
    fontSize=10, spaceAfter=6, leading=16
)
sig_block_style = ParagraphStyle(
    "SigBlock", parent=styles["Normal"],
    fontSize=10, spaceAfter=4, leading=16, spaceBefore=4
)
footer_style = ParagraphStyle(
    "Footer", parent=styles["Normal"],
    fontSize=8, alignment=TA_CENTER,
    textColor=colors.HexColor("#888888"), spaceAfter=0, spaceBefore=12
)

story = []

# --- Title Block ---
story.append(Spacer(1, 0.2*inch))
story.append(Paragraph("NON-DISCLOSURE AND CONFIDENTIALITY AGREEMENT", title_style))
story.append(Paragraph("Managing Partner Engagement", subtitle_style))
story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1a1a2e"), spaceAfter=16))

# --- Preamble ---
story.append(Paragraph(
    'This Non-Disclosure and Confidentiality Agreement (this <b>"Agreement"</b>) is entered into '
    'and made effective as of the last date of signature below (the <b>"Effective Date"</b>), by and between:',
    body_style
))
story.append(Spacer(1, 6))
story.append(Paragraph(
    '&#8226; &nbsp;<b>MARK ODOM</b>, principal of IEBC Business Consultants, with his principal place of '
    'business in Detroit, Michigan (hereinafter referred to as <b>"IEBC"</b> or the <b>"Company"</b>); and',
    bullet_style
))
story.append(Paragraph(
    '&#8226; &nbsp;<b>CECILA GULLEY</b>, an individual residing at [Insert Address] '
    '(hereinafter referred to as the <b>"Managing Partner"</b>).',
    bullet_style
))
story.append(Spacer(1, 4))
story.append(Paragraph(
    'IEBC and the Managing Partner may collectively be referred to as the <b>"Parties"</b> or individually as a <b>"Party."</b>',
    body_style
))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc"), spaceAfter=10, spaceBefore=10))

# --- Section 1 ---
story.append(Paragraph("1. RECITALS &amp; PURPOSE", h1_style))
story.append(Paragraph(
    "<b>WHEREAS</b>, IEBC Business Consultants is a professional business consulting enterprise engaged in providing "
    "strategic advisory, operational consulting, client development, and business management services to a diverse "
    "portfolio of clients and partners; and",
    body_style
))
story.append(Paragraph(
    "<b>WHEREAS</b>, Mark Odom, as principal of IEBC Business Consultants, desires to engage Cecila Gulley in the "
    "capacity of <b>Managing Partner</b>, a senior leadership role that requires full access to the Company's "
    "confidential client relationships, strategic plans, proprietary methodologies, financial structures, and "
    "internal operational data; and",
    body_style
))
story.append(Paragraph(
    "<b>WHEREAS</b>, in connection with her engagement as Managing Partner, the Managing Partner will necessarily "
    "receive, develop, and be entrusted with information that is highly sensitive, proprietary, and critical to "
    "IEBC's competitive standing and client relationships; and",
    body_style
))
story.append(Paragraph(
    "<b>WHEREAS</b>, the Parties desire to define the terms and conditions governing the protection of such "
    "confidential information to preserve the value and integrity of IEBC Business Consultants.",
    body_style
))
story.append(Paragraph(
    "<b>NOW, THEREFORE</b>, in consideration of the Managing Partner's engagement with IEBC Business Consultants, "
    "the mutual covenants contained herein, and other good and valuable consideration, the receipt and sufficiency "
    "of which are hereby acknowledged, the Parties agree as follows:",
    body_style
))

# --- Section 2 ---
story.append(Paragraph("2. DEFINITION OF CONFIDENTIAL INFORMATION", h1_style))
story.append(Paragraph(
    '<b>"Confidential Information"</b> means any and all non-public, proprietary information, data, or material '
    'disclosed by IEBC Business Consultants (the <b>"Disclosing Party"</b>) to Cecila Gulley (the <b>"Receiving '
    'Party"</b>), or developed, discovered, or accessed by the Receiving Party in the course of her engagement '
    'as Managing Partner, whether disclosed orally, visually, in writing, electronically, or through direct '
    'participation in business operations, that is designated as confidential or that reasonably should be '
    'understood to be confidential given its nature and circumstances.',
    body_style
))
story.append(Paragraph("Without limiting the generality of the foregoing, Confidential Information specifically includes:", body_style))

story.append(Paragraph("A. Client &amp; Business Development Information", h2_style))
for item in [
    "Names, contact information, contractual terms, project histories, and strategic needs of all IEBC clients, prospective clients, and referral sources.",
    "Client engagement letters, scope-of-work documents, proposals, pricing models, and service agreements.",
    "Client financial data, internal assessments, vulnerabilities, and confidential communications shared with IEBC in the course of consulting engagements.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_style))

story.append(Paragraph("B. Proprietary Business Methodologies &amp; Strategies", h2_style))
for item in [
    "IEBC's proprietary consulting frameworks, analytical models, service delivery systems, and best-practice methodologies developed for client use.",
    "Strategic business plans, growth roadmaps, market expansion strategies, and competitive positioning analyses.",
    "Internal training materials, onboarding processes, and standard operating procedures.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_style))

story.append(Paragraph("C. Financial &amp; Operational Data", h2_style))
for item in [
    "IEBC's revenue figures, fee structures, profit margins, compensation arrangements, and financial projections.",
    "Vendor agreements, partner contracts, subcontractor arrangements, and pricing terms.",
    "Internal budgets, cost structures, and resource allocation plans.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_style))

story.append(Paragraph("D. Personnel &amp; Partner Information", h2_style))
for item in [
    "Information regarding IEBC employees, contractors, partners, and associates, including compensation, performance evaluations, and roles.",
    "Recruiting strategies, talent pipelines, and organizational development plans.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_style))

story.append(Paragraph("E. Intellectual Property", h2_style))
story.append(Paragraph(
    "Any and all original works of authorship, inventions, discoveries, innovations, software, tools, scripts, "
    "templates, or processes conceived, developed, or reduced to practice by the Managing Partner in connection "
    "with her engagement with IEBC, whether alone or jointly, shall be considered the exclusive property of "
    "IEBC Business Consultants.",
    label_style
))

# --- Section 3 ---
story.append(Paragraph("3. EXCLUSIONS FROM CONFIDENTIALITY", h1_style))
story.append(Paragraph(
    "Confidential Information does not include information that the Managing Partner can demonstrate by clear and convincing written evidence:",
    body_style
))
for i, item in enumerate([
    "Is or becomes generally known to the public through no act or omission of the Managing Partner;",
    "Was rightfully in the Managing Partner's possession prior to her engagement with IEBC, without any accompanying obligation of confidentiality;",
    "Is independently developed by the Managing Partner entirely without reference to or use of IEBC's Confidential Information; or",
    "Is rightfully received from a third party who owes no obligation of confidentiality to IEBC with respect to such information.",
], 1):
    story.append(Paragraph(f"{i}. &nbsp;{item}", bullet_style))

# --- Section 4 ---
story.append(Paragraph("4. OBLIGATIONS &amp; USE RESTRICTIONS OF THE MANAGING PARTNER", h1_style))
story.append(Paragraph(
    "Cecila Gulley, as Managing Partner, shall strictly observe the following covenants throughout the term of her engagement and following its conclusion:",
    body_style
))
obligations = [
    ("<b>Limited Purpose Use:</b>", "The Managing Partner shall use Confidential Information solely for the legitimate performance of her duties as Managing Partner of IEBC Business Consultants, and for no other personal, commercial, or competitive purpose."),
    ("<b>Standard of Care:</b>", "The Managing Partner shall safeguard all Confidential Information using at least the same degree of care she uses to protect her own most sensitive personal data, but in no event less than a reasonable, professional standard of care appropriate to the sensitivity of the information."),
    ("<b>Restricted Disclosure:</b>", "The Managing Partner shall not disclose, share, transmit, publish, or otherwise make available any Confidential Information to any third party — including family members, associates, or prospective employers — without the prior express written consent of Mark Odom."),
    ("<b>No Competitive Use:</b>", "The Managing Partner shall not use any Confidential Information to compete with IEBC Business Consultants, to solicit IEBC clients or prospects, or to benefit any person or entity other than IEBC."),
    ("<b>No Unauthorized Copying:</b>", "The Managing Partner shall not copy, reproduce, extract, or summarize any Confidential Information except as strictly necessary to perform her duties on behalf of IEBC."),
]
for label, text in obligations:
    story.append(Paragraph(f"&#8226; &nbsp;{label} {text}", bullet_style))

# --- Section 5 ---
story.append(Paragraph("5. NON-SOLICITATION OF CLIENTS &amp; PERSONNEL", h1_style))
story.append(Paragraph(
    "During the term of this Agreement and for a period of <b>two (2) years</b> following the conclusion of "
    "Cecila Gulley's engagement as Managing Partner, regardless of the reason for such conclusion, the Managing "
    "Partner agrees that she shall not, directly or indirectly:",
    body_style
))
for i, item in enumerate([
    "<b>Solicit, contact, or pursue</b> any client, prospective client, or referral source of IEBC Business Consultants with whom she had contact, knowledge, or involvement during her engagement, for the purpose of providing competing consulting services or redirecting business away from IEBC;",
    "<b>Recruit, solicit, or induce</b> any employee, contractor, partner, or associate of IEBC Business Consultants to leave their engagement with IEBC or to work with a competing enterprise; or",
    "<b>Disparage, defame, or undermine</b> the professional reputation, client relationships, or business standing of IEBC Business Consultants or Mark Odom in any forum, whether public or private.",
], 1):
    story.append(Paragraph(f"{i}. &nbsp;{item}", bullet_style))

# --- Section 6 ---
story.append(Paragraph("6. COMPELLED LEGAL DISCLOSURE", h1_style))
story.append(Paragraph(
    "If the Managing Partner is compelled by a valid subpoena, court order, or governmental regulatory authority "
    "to disclose any portion of IEBC's Confidential Information, she shall, to the extent legally permissible, "
    "provide IEBC with immediate written notice. Such notice must be issued sufficiently in advance of any required "
    "disclosure to enable IEBC to seek a protective order or otherwise contest the mandate. If no protective order "
    "is secured, the Managing Partner shall disclose only that specific portion of the Confidential Information "
    "that she is legally required to produce.",
    body_style
))

# --- Section 7 ---
story.append(Paragraph("7. TERM &amp; SURVIVAL", h1_style))
story.append(Paragraph(
    "This Agreement shall commence on the Effective Date and shall remain in full force and effect throughout "
    "the entirety of Cecila Gulley's engagement as Managing Partner with IEBC Business Consultants.",
    body_style
))
story.append(Paragraph(
    "&#8226; &nbsp;Upon conclusion of the Managing Partner's engagement — for any reason — the general non-use "
    "and non-disclosure obligations set forth herein shall <b>survive for a period of three (3) years</b>.",
    bullet_style
))
story.append(Paragraph(
    "&#8226; &nbsp;<b>Critical Exception:</b> With respect to IEBC's client identities and relationships, "
    "proprietary consulting methodologies, and core trade secrets, the obligations of confidentiality and "
    "non-use shall <b>survive indefinitely</b>.",
    bullet_style
))

# --- Section 8 ---
story.append(Paragraph("8. RETURN OR DESTRUCTION OF PROPRIETARY MATERIALS", h1_style))
story.append(Paragraph(
    "Upon the conclusion of Cecila Gulley's engagement as Managing Partner, or upon written demand by Mark Odom "
    "at any time, the Managing Partner shall promptly:",
    body_style
))
for i, item in enumerate([
    "Return to IEBC all documents, files, records, materials, devices, and copies — whether in physical or digital form — containing or derived from IEBC's Confidential Information;",
    "Permanently delete all digital copies of Confidential Information from personal devices, cloud storage accounts, and email systems; and",
    "Certify in writing, within <b>five (5) business days</b>, that all such materials have been returned or destroyed in full compliance with this Section.",
], 1):
    story.append(Paragraph(f"{i}. &nbsp;{item}", bullet_style))

# --- Section 9 ---
story.append(Paragraph("9. REMEDIES FOR BREACH", h1_style))
story.append(Paragraph(
    "Cecila Gulley acknowledges that any unauthorized disclosure, misappropriation, or competitive use of IEBC's "
    "Confidential Information — including but not limited to the solicitation of IEBC clients, the use of "
    "proprietary methodologies for personal gain, or the recruitment of IEBC personnel — will cause immediate, "
    "substantial, and irreparable harm to IEBC Business Consultants, for which monetary damages alone will be "
    "entirely inadequate.",
    body_style
))
story.append(Paragraph(
    "Accordingly, in the event of a breach or the credible threat of an imminent breach of this Agreement, "
    "IEBC and Mark Odom shall be entitled to seek, without the necessity of posting a bond or proving actual "
    "financial loss:",
    body_style
))
for item in [
    "Immediate injunctive relief and a temporary restraining order from any court of competent jurisdiction;",
    "Specific performance compelling compliance with the terms of this Agreement; and",
    "All other legal and equitable remedies available, including recovery of actual damages, attorneys' fees, and costs of litigation.",
]:
    story.append(Paragraph(f"&#8226; &nbsp;{item}", bullet_style))

# --- Section 10 ---
story.append(Paragraph("10. GOVERNING LAW AND JURISDICTION", h1_style))
story.append(Paragraph(
    "This Agreement shall be governed by, construed, and enforced in accordance with the laws of the "
    "<b>State of Michigan</b>, without regard to any conflict-of-law principles. The Parties hereby "
    "irrevocably consent to the exclusive personal jurisdiction of the state and federal courts located "
    "within <b>Wayne County, Michigan</b>, for any dispute arising out of or related to this Agreement.",
    body_style
))

# --- Section 11 ---
story.append(Paragraph("11. MISCELLANEOUS", h1_style))
misc = [
    ("<b>Entire Agreement:</b>", "This Agreement constitutes the entire understanding between the Parties with respect to the subject matter hereof and supersedes all prior negotiations, representations, warranties, or agreements, whether oral or written, relating to the confidentiality of IEBC's information."),
    ("<b>Amendments:</b>", "No modification or amendment to this Agreement shall be valid or binding unless made in writing and signed by both Parties."),
    ("<b>No Assignment:</b>", "Neither Party may assign its rights or obligations under this Agreement without the prior written consent of the other Party."),
    ("<b>Severability:</b>", "If any provision of this Agreement is found to be invalid, illegal, or unenforceable by a court of competent jurisdiction, the remaining provisions shall continue in full force and effect."),
    ("<b>No Waiver:</b>", "The failure of either Party to enforce any provision of this Agreement shall not constitute a waiver of that Party's right to enforce such provision in the future."),
    ("<b>Counterparts &amp; Electronic Execution:</b>", "This Agreement may be executed in one or more counterparts, each of which shall constitute an original. Signatures delivered via digital signature platforms (e.g., DocuSign), certified electronic mail, or PDF facsimile shall be fully binding and legally enforceable."),
    ("<b>Independent Legal Advice:</b>", "Each Party acknowledges that they have had a full and fair opportunity to consult with legal counsel of their own choosing prior to executing this Agreement, and that they enter into this Agreement freely, voluntarily, and with full understanding of its terms."),
]
for label, text in misc:
    story.append(Paragraph(f"&#8226; &nbsp;{label} {text}", bullet_style))

# --- Signature Page ---
story.append(PageBreak())
story.append(Paragraph("IN WITNESS WHEREOF", h1_style))
story.append(Paragraph(
    "The Parties have executed this Non-Disclosure and Confidentiality Agreement as of the Effective Date written below.",
    body_style
))
story.append(Spacer(1, 0.3*inch))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc"), spaceAfter=20))

# Sig block 1
story.append(Paragraph("<b>IEBC BUSINESS CONSULTANTS</b>", sig_style))
story.append(Spacer(1, 0.05*inch))
story.append(Paragraph("Signature: &nbsp;___________________________________________", sig_block_style))
story.append(Paragraph("By: &nbsp;<b>Mark Odom</b>", sig_block_style))
story.append(Paragraph("Title: &nbsp;<b>Principal / Chief Executive Officer, IEBC Business Consultants</b>", sig_block_style))
story.append(Paragraph("Date: &nbsp;___________________________________________", sig_block_style))
story.append(Spacer(1, 0.35*inch))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc"), spaceAfter=20))

# Sig block 2
story.append(Paragraph("<b>MANAGING PARTNER</b>", sig_style))
story.append(Spacer(1, 0.05*inch))
story.append(Paragraph("Signature: &nbsp;___________________________________________", sig_block_style))
story.append(Paragraph("By: &nbsp;<b>Cecila Gulley</b>", sig_block_style))
story.append(Paragraph("Title: &nbsp;<b>Managing Partner, IEBC Business Consultants</b>", sig_block_style))
story.append(Paragraph("Date: &nbsp;___________________________________________", sig_block_style))
story.append(Spacer(1, 0.4*inch))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc"), spaceAfter=10))

story.append(Paragraph(
    "This Agreement is intended for informational and operational use. "
    "IEBC Business Consultants recommends review by a licensed Michigan attorney prior to execution.",
    footer_style
))

doc.build(story)
print(f"PDF generated: {OUTPUT}")
