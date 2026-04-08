"""
grouper.py — Fase 2: formacao de grupos e cross-matching.

v1.4.0:
  - Detecta e registra duplicatas (SimHash) antes de agrupar
  - Fuzzy entity matching (prefixo/Jaccard + mesmo valor)
  - Doc-number cross-matching
  - Duplicatas marcadas sao excluidas do CONFERIR (nao geram ruido)
"""

import re
from collections import Counter

from .config import ORDER_MERGE
from .models import DocInfo, person_tokens, normalize, compute_batch_simhash
from .extractor import classify_segment
from .matcher import (
    detect_duplicates,
    match_by_fuzzy_entity,
    match_by_doc_number,
    match_by_secondary_value,
    match_by_nf_key,
    match_by_installment,
    expand_multi_e_values,
)


def _first_seg(gid: str) -> str:
    return gid.split(" - ")[0].strip()

def _all_val_digits(gdocs):
    return {d.value_digits for d in gdocs if d.value_digits}

def _dup_boleto_diff_values(gdocs):
    boletos = [d for d in gdocs if d.doc_type == "boleto"]
    if len(boletos) < 2: return False
    return len({d.value_digits for d in boletos if d.value_digits}) > 1

def _absorb(groups, gid_from, gid_into, log_cb, reason):
    if gid_from not in groups or gid_into not in groups:
        return   # já foi absorvido em iteração anterior
    if log_cb:
        log_cb(f"    -> merge ({reason}): '{gid_from}' -> '{gid_into}'")
    for d in groups[gid_from]:
        d.group_id = gid_into
        groups[gid_into].append(d)
    del groups[gid_from]


def _split_by_value(gid, gdocs):
    val_map: dict[str, list] = {}
    no_val: list = []
    for d in gdocs:
        if d.value_digits: val_map.setdefault(d.value_digits, []).append(d)
        else: no_val.append(d)
    if len(val_map) <= 1: return {gid: gdocs}

    # Nao divide se ha relacao de soma entre valores (ISOMAX: 8102+8102=16205)
    vals_keys = set(val_map.keys())
    for v in vals_keys:
        for other_v in vals_keys - {v}:
            for d in val_map.get(other_v, []):
                if v in d.all_value_digits: return {gid: gdocs}
            for d in val_map.get(v, []):
                if other_v in d.all_value_digits: return {gid: gdocs}

    result: dict[str, list] = {}
    for vdig, vdocs in val_map.items():
        vraw = next((d.value_raw for d in vdocs if d.value_raw), vdig)
        result[f"{gid} [{vraw}]"] = vdocs
    if no_val:
        biggest = max(result, key=lambda k: len(result[k]))
        result[biggest].extend(no_val)
    return result


def infer_types_in_group(docs, log_cb=None):
    known   = {d.doc_type for d in docs if d.doc_type}
    unknown = [d for d in docs if not d.doc_type]
    if not unknown: return
    missing = set(ORDER_MERGE) - known
    for doc in unknown:
        inferred = None
        if doc.type_segment: inferred = classify_segment(doc.type_segment)
        if not inferred and len(missing) == 1: inferred = next(iter(missing))
        if not inferred:
            if doc.pages == 1:
                inferred = "boleto" if "boleto" in missing else (next(iter(missing)) if missing else "nota")
            else:
                inferred = "nota" if "nota" in missing else (next(iter(missing)) if missing else "nota")
        if inferred:
            doc.doc_type = inferred
            if log_cb: log_cb(f"    -> inferido: {doc.fname[:50]} -> {inferred}")
            known.add(inferred); missing = set(ORDER_MERGE) - known


def build_groups(
    docs: list[DocInfo],
    log_cb=None,
) -> tuple[dict[str, list[DocInfo]], list[str]]:
    """FASE 2 — Analisa relacoes e forma grupos de pagamento."""

    # ── Pre: calcula SimHash limpo (filtra tokens estruturais do lote) ─────────
    if log_cb: log_cb("    -- calculando SimHash (filtrando template do banco)...")
    structural = compute_batch_simhash(docs)
    if log_cb and structural:
        log_cb(f"    -- {len(structural)} tokens estruturais filtrados do SimHash")

    # Detecta duplicatas com SimHash limpo
    if log_cb: log_cb("    -- detectando duplicatas...")
    dup_pairs = detect_duplicates(docs, log_cb)
    dup_fnames: set[str] = {db.fname for _, db, _ in dup_pairs}

    # ── Pre: filtro de tokens estruturais do fingerprint ─────────────────────
    if docs:
        tok_freq  = Counter(tok for d in docs for tok in d.fingerprint)
        threshold = max(3, len(docs) // 5)
        structural = {tok for tok, cnt in tok_freq.items() if cnt >= threshold}
        if structural and log_cb:
            log_cb(f"    -- {len(structural)} tokens estruturais filtrados")
        for d in docs:
            d.fingerprint -= structural

    # ── 2a. group_id identico ────────────────────────────────────────────────
    groups: dict[str, list[DocInfo]] = {}
    orphans: list[DocInfo] = []
    for doc in docs:
        if doc.dup_of: continue   # duplicatas nao participam do agrupamento
        if doc.group_id: groups.setdefault(doc.group_id, []).append(doc)
        else: orphans.append(doc)

    # ── 2b. Orfaos por valor + periodo ────────────────────────────────────────
    still_orphan: list[DocInfo] = []
    for doc in orphans:
        matched = None
        if doc.value_digits:
            for gid, gdocs in groups.items():
                if any(gd.value_digits == doc.value_digits
                       and gd.period == doc.period for gd in gdocs):
                    matched = gid; break
        if matched:
            if log_cb: log_cb(f"    -> casado (valor+periodo) -> '{matched}'")
            doc.group_id = matched; groups[matched].append(doc)
        else:
            still_orphan.append(doc)

    # ── 2c. Fingerprint fuzzy ─────────────────────────────────────────────────
    conferir: list[str] = []
    group_fp = {gid: set().union(*(d.fingerprint for d in gdocs))
                for gid, gdocs in groups.items()}
    for doc in still_orphan:
        if not doc.fingerprint: conferir.append(doc.fname); continue
        best_gid, best_score = None, 0
        for gid, gfp in group_fp.items():
            score = len(doc.fingerprint & gfp)
            if score > best_score: best_score, best_gid = score, gid
        if best_gid and best_score >= 3:
            if log_cb: log_cb(f"    -> casado (fingerprint {best_score}) -> '{best_gid}'")
            doc.group_id = best_gid; groups[best_gid].append(doc)
            group_fp[best_gid].update(doc.fingerprint)
        else:
            conferir.append(doc.fname)

    # ── 2c2. Mesmo segmento + mesmo valor (exclui prefixos genericos) ─────────
    _GENERIC = frozenset({
        "FUNCIONARIOS","ESTADO","MINISTERIO",
        "SECRETARIA","MUNICIPIO","PREFEITURA","GOVERNO",
        "CAIXA ECONOMICA","BANCO",
    })
    gids = list(groups.keys()); to_del: set[str] = set()
    for i, ga in enumerate(gids):
        if ga in to_del or ga not in groups: continue
        fs_a = _first_seg(ga)
        if normalize(fs_a) in _GENERIC: continue
        va = _all_val_digits(groups[ga])
        for gb in gids[i+1:]:
            if gb in to_del or gb not in groups: continue
            if _first_seg(gb) != fs_a: continue
            if va & _all_val_digits(groups[gb]):
                _absorb(groups, gb, ga, log_cb, "seg+valor"); to_del.add(gb)

    # ── 2c3. Tokens de pessoa + mesmo valor ───────────────────────────────────
    gids = list(groups.keys()); to_del3: set[str] = set()
    for i, ga in enumerate(gids):
        if ga in to_del3 or ga not in groups: continue
        ta = person_tokens(ga)
        if len(ta) < 2: continue
        va = _all_val_digits(groups[ga])
        for gb in gids[i+1:]:
            if gb in to_del3 or gb not in groups: continue
            tb = person_tokens(gb)
            if len(tb) < 2 or len(ta & tb) < 2: continue
            vb = _all_val_digits(groups[gb])
            if not (va & vb): continue
            winner = ga if len(ga) <= len(gb) else gb
            loser  = gb if winner == ga else ga
            _absorb(groups, loser, winner, log_cb, "pessoa+valor")
            to_del3.add(loser)
            if winner != ga: ta, va = tb, vb
    for gid in to_del3:
        if gid in groups: del groups[gid]

    # ── 2d. Valor parentetico ────────────────────────────────────────────────
    if log_cb: log_cb("    -- matching por valor parentetico...")
    match_by_secondary_value(groups, log_cb)

    # ── 2e. Chave NF-e ───────────────────────────────────────────────────────
    if log_cb: log_cb("    -- matching por chave NF-e...")
    match_by_nf_key(groups, log_cb)

    # ── 2f. Parcelas ─────────────────────────────────────────────────────────
    if log_cb: log_cb("    -- matching por parcelas...")
    match_by_installment(groups, log_cb)

    # ── 2g. [NOVO v1.4.0] Fuzzy entity ───────────────────────────────────────
    if log_cb: log_cb("    -- matching fuzzy de entidade...")
    match_by_fuzzy_entity(groups, log_cb)

    # ── 2h. [NOVO v1.4.0] Numero de NF/boleto ────────────────────────────────
    if log_cb: log_cb("    -- matching por numero NF/boleto...")
    match_by_doc_number(groups, log_cb)

    # ── 2i. Inferencia de tipo ────────────────────────────────────────────────
    for gid, gdocs in groups.items():
        if len(gdocs) >= 6 and log_cb:
            log_cb(f"    ⚠ '{gid}' tem {len(gdocs)} docs — verifique duplicatas")
        infer_types_in_group(gdocs, log_cb)

    # ── 2j. Sub-agrupamento por valor + descarte de invalidos ─────────────────
    for gid in list(groups.keys()):
        gdocs = groups[gid]
        vals  = {d.value_digits for d in gdocs if d.value_digits}
        if len(vals) <= 1: continue
        sub = _split_by_value(gid, gdocs)
        if len(sub) > 1:
            del groups[gid]
            for sk, sdocs in sub.items():
                groups[sk] = sdocs
                if log_cb: log_cb(f"    -> sub-grupo: '{sk}' [{len(sdocs)} docs]")

    for gid in list(groups.keys()):
        gdocs = groups[gid]
        if len(gdocs) == 1:           reason = "sem par"
        elif _dup_boleto_diff_values(gdocs): reason = "boletos com valores diferentes"
        else: continue
        if log_cb: log_cb(f"    -> '{gid}' ({reason}) -> CONFERIR")
        for doc in gdocs: conferir.append(doc.fname)
        del groups[gid]

    # Adiciona duplicatas ao log (mas nao ao CONFERIR — sao automaticamente ignoradas)
    if dup_fnames and log_cb:
        log_cb(f"    -- {len(dup_fnames)} duplicata(s) ignorada(s): "
               + ", ".join(sorted(dup_fnames)[:3])
               + ("..." if len(dup_fnames) > 3 else ""))

    return groups, conferir
