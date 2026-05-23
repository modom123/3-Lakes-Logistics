"""X12 EDI generator — builds 990, 214, and 210 outbound transactions.

Output is standard X12 with * element delimiter and ~ segment terminator.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..models.broker import EDI210Invoice, EDI214StatusUpdate, EDI990Response


_CARRIER_ID   = "3LAKESLOGIST"   # 3LL's EDI sender ID (ISA06)
_CARRIER_QUAL = "02"             # ISA05 qualifier — SCAC


def _now() -> tuple[str, str]:
    """Return (YYMMDD, HHMM) for EDI timestamps."""
    now = datetime.now(timezone.utc)
    return now.strftime("%y%m%d"), now.strftime("%H%M")


def _isa_header(partner_id: str, qualifier: str, ctrl: str) -> str:
    date, time = _now()
    return (
        f"ISA*00*          *00*          "
        f"*{_CARRIER_QUAL}*{_CARRIER_ID:<15}"
        f"*{qualifier}*{partner_id:<15}"
        f"*{date}*{time}*^*00501*{ctrl.zfill(9)}*0*P*:~"
    )


def _gs_header(func_id: str, partner_id: str, ctrl: str) -> str:
    date, time = _now()
    return f"GS*{func_id}*{_CARRIER_ID}*{partner_id}*{date}*{time}*{ctrl}*X*005010~"


def _trailer(ts_id: str, seg_count: int, ctrl: str, gs_ctrl: str, isa_ctrl: str) -> str:
    return (
        f"SE*{seg_count}*{ctrl}~"
        f"GE*1*{gs_ctrl}~"
        f"IEA*1*{isa_ctrl.zfill(9)}~"
    )


def build_990(resp: EDI990Response, partner_id: str = "BROKER", qualifier: str = "02") -> str:
    """Build EDI 990 Response to Load Tender.

    response_code: "A" = Accept, "D" = Decline, "C" = Conditional
    """
    ctrl = "000001"
    lines = [
        _isa_header(partner_id, qualifier, ctrl),
        _gs_header("QO", partner_id, ctrl),
        f"ST*990*{ctrl}~",
        f"B1*{_CARRIER_ID}*{resp.load_number}*{resp.response_code}~",
        f"SE*2*{ctrl}~",
        f"GE*1*{ctrl}~",
        f"IEA*1*{ctrl.zfill(9)}~",
    ]
    return "".join(lines)


def build_214(status: EDI214StatusUpdate, partner_id: str = "BROKER", qualifier: str = "02") -> str:
    """Build EDI 214 Shipment Status Message.

    Common status codes:
      X3 = Picked up
      D1 = Delivered
      AB = Driver assigned
      I1 = In transit
    """
    ctrl = "000002"
    date, time = _now()
    city  = (status.city  or "").upper()
    state = (status.state or "").upper()

    segments = [
        _isa_header(partner_id, qualifier, ctrl),
        _gs_header("QM", partner_id, ctrl),
        f"ST*214*{ctrl}~",
        f"B10**{status.load_number}*{_CARRIER_ID}~",
        f"L11*{status.load_number}*BM~",
        f"AT7*{status.status_code}*NS**{status.status_datetime or date}*{time}*LT~",
        f"MS1*{city}*{state}~",
    ]
    if status.driver_name:
        segments.append(f"NM1*QD*1*{status.driver_name}****~")

    seg_count = len(segments) - 3  # exclude ISA, GS, and trailers from count
    segments.append(f"SE*{seg_count + 1}*{ctrl}~")
    segments.append(f"GE*1*{ctrl}~")
    segments.append(f"IEA*1*{ctrl.zfill(9)}~")

    return "".join(segments)


def build_210(invoice: EDI210Invoice, partner_id: str = "BROKER", qualifier: str = "02") -> str:
    """Build EDI 210 Motor Carrier Freight Details and Invoice."""
    ctrl = "000003"
    date, time = _now()

    segments = [
        _isa_header(partner_id, qualifier, ctrl),
        _gs_header("IM", partner_id, ctrl),
        f"ST*210*{ctrl}~",
        (
            f"B3**{invoice.invoice_number}*{invoice.invoice_date.replace('-','')}*"
            f"*{invoice.payment_terms or 'Net30'}*"
            f"{date}*{invoice.total_amount:.2f}**{invoice.load_number}~"
        ),
        f"N1*BT*BROKER~",
        f"N1*SF*3 LAKES LOGISTICS~",
    ]

    # Line items
    lx = 1
    segments.append(f"LX*{lx}~")
    segments.append(f"L0*1***{invoice.linehaul_amount:.2f}***L~")
    segments.append(f"L1*1*{invoice.linehaul_amount:.2f}***FR~")

    if invoice.fuel_surcharge:
        lx += 1
        segments.append(f"LX*{lx}~")
        segments.append(f"L0*{lx}***{invoice.fuel_surcharge:.2f}***L~")
        segments.append(f"L1*{lx}*{invoice.fuel_surcharge:.2f}***FSC~")

    if invoice.detention_amount:
        lx += 1
        segments.append(f"LX*{lx}~")
        segments.append(f"L0*{lx}***{invoice.detention_amount:.2f}***L~")
        segments.append(f"L1*{lx}*{invoice.detention_amount:.2f}***DET~")

    seg_count = len(segments) - 3
    segments.append(f"SE*{seg_count + 1}*{ctrl}~")
    segments.append(f"GE*1*{ctrl}~")
    segments.append(f"IEA*1*{ctrl.zfill(9)}~")

    return "".join(segments)
