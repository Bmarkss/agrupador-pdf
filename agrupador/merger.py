"""
merger.py — Fase 3: merge, compressao e saida de PDFs agrupados.

v1.4.0 — Smart ✔/⚠:
  ✔  se o grupo tem COMPROVANTE + pelo menos um outro tipo (BOLETO ou NOTA)
  ⚠  se falta o comprovante (suspeito) ou o grupo tem apenas 1 tipo
  Motivo: pagamentos via PIX/TED/transferencia nao tem boleto — e normal ter so C+NF.
"""

import os, re, io
from pypdf import PdfWriter, PdfReader
from .config import ORDER_MERGE
from .models import DocInfo
from .extractor import collect_all
from .grouper  import build_groups


def _build_output_name(group_id, docs):
    value  = next((d.value_raw  for d in docs if d.value_raw),  "")
    period = next((d.period     for d in docs if d.period),     "")
    clean  = re.sub(r"\s*\[.*?\]\s*$", "", group_id).strip()
    parts  = [clean]
    if value:  parts.append(value)
    if period: parts.append(period.upper())
    name = " - ".join(parts).replace("/", ".")
    return re.sub(r"[<>:\"\\|?*]", "", name)


def build_output_name(group_id, docs):
    return _build_output_name(group_id, docs)


def _unique_path(folder, base_name):
    path = os.path.join(folder, f"{base_name}_AGRUPADO.pdf")
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{base_name}_AGRUPADO ({n}).pdf"); n += 1
    return path


def _compress_writer(writer):
    for page in writer.pages:
        try: page.compress_content_streams()
        except Exception: pass
    try: writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    except Exception: pass


def _size_kb(path):
    try: return os.path.getsize(path) // 1024
    except Exception: return 0


def merge_group(group_id: str, docs: list[DocInfo], output_folder: str) -> str:
    """
    Merge na ordem: comprovante -> boleto -> nota.

    v1.4.0 — Smart ✔/⚠:
      ✔  grupo tem comprovante E pelo menos boleto ou nota
      ⚠  suspeito: falta comprovante, ou so tem 1 tipo, ou erros
    """
    writer = PdfWriter()
    errors: list[str] = []
    used_types: list[str] = []
    size_orig = 0

    for tipo in ORDER_MERGE:
        for doc in (d for d in docs if d.doc_type == tipo):
            try:
                reader = PdfReader(doc.path)
                for page in reader.pages: writer.add_page(page)
                used_types.append(tipo)
                size_orig += _size_kb(doc.path)
            except Exception as e:
                errors.append(f"{doc.fname}: {e}")

    untyped = [d for d in docs if not d.doc_type]
    for doc in untyped:
        try:
            reader = PdfReader(doc.path)
            for page in reader.pages: writer.add_page(page)
            size_orig += _size_kb(doc.path)
        except Exception as e:
            errors.append(f"{doc.fname}: {e}")

    if not writer.pages:
        return f"\u2718 {group_id}: nenhuma pagina gerada"

    agrupados = os.path.join(output_folder, "AGRUPADOS")
    os.makedirs(agrupados, exist_ok=True)
    out_name = _build_output_name(group_id, docs)
    out_path = _unique_path(agrupados, out_name)

    try:
        with open(out_path, "wb") as f: writer.write(f)
    except Exception as e:
        return f"\u2718 {group_id}: erro ao salvar — {e}"

    size_out = _size_kb(out_path)

    try:
        writer_c = PdfWriter()
        for page in PdfReader(out_path).pages: writer_c.add_page(page)
        _compress_writer(writer_c)
        buf = io.BytesIO(); writer_c.write(buf)
        size_c = len(buf.getvalue()) // 1024
        if size_c < size_out:
            with open(out_path, "wb") as f: f.write(buf.getvalue())
            size_out = size_c
    except Exception: pass

    if size_orig > 0 and size_out > 0:
        pct = int((1 - size_out / size_orig) * 100)
        size_tag = f" ({size_orig}KB->{size_out}KB, -{pct}%)" if pct > 0 else f" ({size_out}KB)"
    else:
        size_tag = ""

    # ── Smart ✔/⚠ ────────────────────────────────────────────────────────────
    has_comp = "comprovante" in used_types
    has_nota = "nota"        in used_types
    has_bole = "boleto"      in used_types
    extra_s  = f" +{len(untyped)} sem tipo" if untyped else ""

    if errors:
        return f"\u26a0 {group_id}: erros em {'; '.join(errors)}"

    # ✔ completo: comprovante + pelo menos outro tipo
    if has_comp and (has_nota or has_bole):
        return f"\u2714 {group_id}{extra_s}{size_tag}"

    # ⚠ falta comprovante — suspeito (boleto/NF sem evidencia de pagamento)
    if not has_comp:
        missing = [t.upper() for t in ORDER_MERGE if t not in used_types]
        return f"\u26a0 {group_id}: faltou {', '.join(missing)}{extra_s}{size_tag}"

    # ⚠ so tem comprovante (nenhum doc fiscal)
    return f"\u26a0 {group_id}: so comprovante, faltou BOLETO ou NOTA{extra_s}{size_tag}"


def scan_folder(folder, log_callback=None, cancel_flag=None):
    if log_callback: log_callback("  -- Fase 1: lendo e extraindo dados...")
    docs = collect_all(folder, log_callback, cancel_flag)
    if cancel_flag and cancel_flag(): return {}, []
    if log_callback: log_callback(f"\n  -- Fase 2: analisando {len(docs)} doc(s)...")
    groups, conferir = build_groups(docs, log_callback)
    if log_callback: log_callback(f"\n  -- Fase 3: {len(groups)} grupo(s) prontos\n")
    return groups, conferir
