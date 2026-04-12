"""
merger.py — Fase 3: merge, compressao e saida de PDFs agrupados.

v1.4.0 — Smart ✔/⚠:
  ✔  se o grupo tem COMPROVANTE + pelo menos um outro tipo (BOLETO ou NOTA)
  ⚠  se falta o comprovante (suspeito) ou o grupo tem apenas 1 tipo
  Motivo: pagamentos via PIX/TED/transferencia nao tem boleto — e normal ter so C+NF.
"""

import os, re, io
from pypdf import PdfWriter, PdfReader
from .config  import ORDER_MERGE
from .models  import DocInfo
from .extractor import collect_all
from .grouper   import build_groups
from .scorer         import group_confidence, confidence_score, score_to_symbol, score_to_label, SCORE_GREEN, SCORE_YELLOW
from .feedback_store  import record_grouping
from .graph_resolver  import resolve_with_graph, find_orphan_matches


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

    # ── Score de confiança calibrado (v1.5.0) ────────────────────────────────
    extra_s = f" +{len(untyped)} sem tipo" if untyped else ""

    if errors:
        return f"\u26a0 {group_id}: erros em {'; '.join(errors)}"

    score, det = group_confidence(docs)
    sym   = score_to_symbol(score)
    label = score_to_label(score)

    # Contexto adicional: tipos presentes
    tipos_str = "+".join(t[0].upper() for t in used_types) if used_types else "?"

    # Registra grupos verdes como feedback positivo (active learning)
    if score >= SCORE_GREEN:
        try:
            record_grouping(group_id, [d.doc_type for d in docs if d.doc_type], score, det)
        except Exception:
            pass

    return f"{sym} {group_id}  [{label}] ({tipos_str}){extra_s}{size_tag}"


def scan_folder(folder, log_callback=None, cancel_flag=None):
    from .classifier import warmup as _wc; _wc()  # pre-carrega modelo ML
    if log_callback: log_callback("  -- Fase 1: lendo e extraindo dados...")
    docs = collect_all(folder, log_callback, cancel_flag)
    if cancel_flag and cancel_flag(): return {}, []
    if log_callback: log_callback(f"\n  -- Fase 2: analisando {len(docs)} doc(s)...")
    groups, conferir = build_groups(docs, log_callback)

    # Fase 2.5 — Grafo: resolve ambiguidades entre grupos e busca matches para orphans
    if len(groups) > 1:
        groups, suggestions = resolve_with_graph(
            groups, confidence_score, log_cb=log_callback
        )
        if suggestions and log_callback:
            log_callback(f"    -- {len(suggestions)} sugestao(oes) de merge disponivel(is)")

    if conferir and groups:
        orphan_matches = find_orphan_matches(
            groups, conferir, docs, confidence_score, log_cb=log_callback
        )
        # Remove do CONFERIR os orphans que encontraram match
        for fname, gid in orphan_matches.items():
            doc = next((d for d in docs if d.fname == fname), None)
            if doc:
                doc.group_id = gid
                groups[gid].append(doc)
                conferir.remove(fname)
                if log_callback:
                    log_callback(f"    -> orphan resolvido: '{fname[:40]}' -> '{gid}'")

    if log_callback: log_callback(f"\n  -- Fase 3: {len(groups)} grupo(s) prontos\n")
    return groups, conferir
