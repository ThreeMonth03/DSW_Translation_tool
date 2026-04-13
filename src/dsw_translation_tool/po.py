"""Public PO parsing and rewriting facade.

This module keeps the package-level PO API stable while the concrete
implementations live under :mod:`dsw_translation_tool.po_support`.
"""

from .po_support import PoCatalogParser, PoCatalogWriter, PoStringCodec

__all__ = [
    "PoCatalogParser",
    "PoCatalogWriter",
    "PoStringCodec",
]
