"""EDI service — X12 parser, generator, and CLM router.

Supports:
  Inbound:  204 (Load Tender)
  Outbound: 990 (Response to Load Tender)
            214 (Shipment Status)
            210 (Freight Invoice)
"""
from .parser import parse_edi
from .generator import build_990, build_214, build_210
from .handlers import handle_inbound_edi

__all__ = ["parse_edi", "build_990", "build_214", "build_210", "handle_inbound_edi"]
