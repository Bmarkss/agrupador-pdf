"""
agrupador — Pacote de agrupamento automático de PDFs fiscais.

API pública:
  scan_folder(folder, log_callback, cancel_flag) → (groups, conferir)
  merge_group(group_id, docs, output_folder)     → str
  DocInfo                                         — modelo de documento
"""

from .merger import scan_folder, merge_group
from .models import DocInfo

__version__ = "3.0.11"
__all__     = ["scan_folder", "merge_group", "DocInfo"]
