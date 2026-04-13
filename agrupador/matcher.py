"""
matcher.py — Estrategias de cross-matching avancado.

v1.4.0 adiciona:
  detect_duplicates      — SimHash: dois docs com conteudo identico/quase-identico
  match_by_fuzzy_entity  — entidade similar (prefixo ou Jaccard alto) + mesmo valor
  match_by_doc_number    — numero de NF/boleto em comum entre grupos distintos
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import DocInfo

from .config import SIMHASH_NEAR_THRESHOLD
from .models import hamming_distance, entity_similarity, entity_prefix_match


def _first_seg(gid: str) -> str:
    return gid.split(" - ")[0].strip()

def _all_sec_digits(gdocs):
    return {d.value_sec_digits for d in gdocs if d.value_sec_digits}

def _all_val_digits(gdocs):
    return {d.value_digits for d in gdocs if d.value_digits}

def _absorb(groups, gid_from, gid_into, log_cb, reason):
    if log_cb:
        log_cb(f"    -> merge ({reason}): '{gid_from}' -> '{gid_into}'")
    for d in groups[gid_from]:
        d.group_id = gid_into
        groups[gid_into].append(d)
    del groups[gid_from]


# ── Deteccao de duplicatas via SimHash ────────────────────────────────────────

def detect_duplicates(
    docs: list["DocInfo"],
    log_cb=None,
) -> list[tuple["DocInfo", "DocInfo", int]]:
    """
    Detecta duplicatas usando SimHash limpo (tokens estruturais ja filtrados).

    Regras (conservadoras para evitar falsos positivos):
      1. hamming == 0  (conteudo identico apos filtro)  -> duplicata certa
      2. hamming 1-3 + mesmo group_id + mesmo value_digits -> muito provavel

    Casos cobertos:
      - GNREs com timestamp name mas conteudo identico
      - Mesmo comprovante baixado duas vezes
      - NF reenviada com versao diferente

    NAO detecta como duplicata:
      - Dois comprovantes Itau de fornecedores diferentes (tokens de banco compartilhados)
      - Documentos similares mas de pagamentos distintos
    """
    pairs: list[tuple["DocInfo","DocInfo",int]] = []
    docs_validos = [d for d in docs if d.simhash and d.simhash != 0]

    for i, da in enumerate(docs_validos):
        for db in docs_validos[i+1:]:
            if da.fname == db.fname:
                continue
            dist = hamming_distance(da.simhash, db.simhash)

            # Criterio 1: identicos apos filtro estrutural
            is_dup = (dist == 0)

            # Criterio 2: muito similar + mesmo grupo + mesmo valor
            if not is_dup and dist <= SIMHASH_NEAR_THRESHOLD:
                same_group = (da.group_id and db.group_id
                              and da.group_id == db.group_id)
                same_value = (da.value_digits and db.value_digits
                              and da.value_digits == db.value_digits)
                is_dup = same_group and same_value

            if is_dup:
                original  = da if len(da.fname) >= len(db.fname) else db
                duplicata = db if original is da else da
                if duplicata.dup_of is None:
                    duplicata.dup_of = original.fname
                pairs.append((original, duplicata, dist))
                if log_cb:
                    log_cb(
                        f"    -> DUPLICATA (hamming={dist}): "
                        f"'{duplicata.fname[:45]}' ~ '{original.fname[:45]}'"
                    )
    return pairs


# ── Fuzzy entity matching ─────────────────────────────────────────────────────

def match_by_fuzzy_entity(
    groups: dict,
    log_cb=None,
) -> None:
    """
    Funde grupos cujos group_ids sao entidades MUITO similares + mesmo valor.

    Dois criterios alternativos (ambos exigem mesmo value_digits):
      A. Prefixo: um nome e prefixo do outro apos remover sufixos legais
         Ex: "MINAS INDUSTRIA" <-> "MINAS INDUSTRIA E COMERCIO"
      B. Jaccard >= 0.80: 80% dos tokens em comum (threshold alto para evitar FP)
         Ex: "CRYOBRAS GELO SECO" <-> "CRYOBRAS" (se mesmo valor)

    NAO funde:
      - "AMIL ASSISTENCIA MEDICA" <-> "AMIL PLANO DE SAUDE" (Jaccard ~0.20)
      - "ESTADO DE MG ICMS" <-> "ESTADO DE MG ICMS ST" (tokens diferentes)
      - Qualquer par sem valor em comum
    """
    gids = list(groups.keys())
    merged: set[str] = set()

    for i, ga in enumerate(gids):
        if ga in merged or ga not in groups:
            continue
        # Não funde grupos que são todos GNRE — cada GNRE é de um estado distinto
        # e GNREs diferentes nunca devem ser agrupados entre si
        if all(d.doc_type == "gnre" for d in groups[ga]):
            continue
        va = _all_val_digits(groups[ga])
        if not va:
            continue

        for gb in gids[i+1:]:
            if gb in merged or gb not in groups:
                continue
            vb = _all_val_digits(groups[gb])
            if not (va & vb):
                continue  # valores diferentes -> nunca funde

            # Criterio A: prefixo apos normalizacao
            prefix_ok = entity_prefix_match(ga, gb)

            # Criterio B: Jaccard alto (threshold conservador)
            jaccard   = entity_similarity(ga, gb)
            jaccard_ok = jaccard >= 0.80

            if prefix_ok or jaccard_ok:
                reason = f"fuzzy-{'prefixo' if prefix_ok else f'jaccard={jaccard:.2f}'}"
                if len(groups[ga]) >= len(groups[gb]):
                    _absorb(groups, gb, ga, log_cb, reason)
                    merged.add(gb)
                else:
                    _absorb(groups, ga, gb, log_cb, reason)
                    merged.add(ga)
                    break


# ── Doc-number cross-matching ─────────────────────────────────────────────────

def match_by_doc_number(
    groups: dict,
    log_cb=None,
) -> None:
    """
    Funde grupos que compartilham o mesmo numero de NF/boleto no nome ou conteudo.
    Ex: "NF 20468" em dois arquivos diferentes -> mesmo pagamento.

    Confianca alta: numeros de NF sao unicos por emitente.
    Nao funde se os numeros sao muito curtos (<= 3 digitos) — muito genericos.
    """
    gids = list(groups.keys())
    merged: set[str] = set()

    # Coleta todos os doc_numbers por grupo (apenas numeros com 4+ digitos)
    group_nums: dict[str, set[str]] = {}
    for gid, gdocs in groups.items():
        nums = set()
        for d in gdocs:
            nums.update(n for n in d.doc_numbers if len(n) >= 4)
        if nums:
            group_nums[gid] = nums

    for i, ga in enumerate(gids):
        if ga in merged or ga not in groups or ga not in group_nums:
            continue
        nums_a = group_nums[ga]

        for gb in gids[i+1:]:
            if gb in merged or gb not in groups or gb not in group_nums:
                continue
            nums_b = group_nums[gb]

            if nums_a & nums_b:
                if len(groups[ga]) >= len(groups[gb]):
                    _absorb(groups, gb, ga, log_cb, "num-nf")
                    merged.add(gb)
                    if gb in group_nums:
                        group_nums[ga] = group_nums[ga] | group_nums[gb]
                else:
                    _absorb(groups, ga, gb, log_cb, "num-nf")
                    merged.add(ga)
                    if ga in group_nums:
                        group_nums[gb] = group_nums[gb] | group_nums[ga]
                    break


# ── Estrategias existentes (v1.2.0+) ─────────────────────────────────────────

def match_by_secondary_value(groups, log_cb=None):
    gids = list(groups.keys()); merged: set[str] = set()
    for i, ga in enumerate(gids):
        if ga in merged or ga not in groups: continue
        sec_a = _all_sec_digits(groups[ga])
        vals_a = _all_val_digits(groups[ga])
        if not sec_a and not vals_a: continue
        seg_a = _first_seg(ga)
        for gb in gids[i+1:]:
            if gb in merged or gb not in groups: continue
            if _first_seg(gb) != seg_a: continue
            vals_b = _all_val_digits(groups[gb])
            sec_b  = _all_sec_digits(groups[gb])
            if (sec_a & vals_b) or (sec_b & vals_a):
                if len(groups[ga]) >= len(groups[gb]):
                    _absorb(groups, gb, ga, log_cb, "valor-parentetico"); merged.add(gb)
                else:
                    _absorb(groups, ga, gb, log_cb, "valor-parentetico"); merged.add(ga); break


def match_by_nf_key(groups, log_cb=None):
    gids = list(groups.keys()); merged: set[str] = set()
    for i, ga in enumerate(gids):
        if ga in merged or ga not in groups: continue
        keys_a = set().union(*(d.nf_keys for d in groups[ga]))
        if not keys_a: continue
        for gb in gids[i+1:]:
            if gb in merged or gb not in groups: continue
            keys_b = set().union(*(d.nf_keys for d in groups[gb]))
            if keys_a & keys_b:
                if len(groups[ga]) >= len(groups[gb]):
                    _absorb(groups, gb, ga, log_cb, "chave-NF-e"); merged.add(gb)
                else:
                    _absorb(groups, ga, gb, log_cb, "chave-NF-e"); merged.add(ga); break


def match_by_installment(groups, log_cb=None):
    gids = list(groups.keys()); merged: set[str] = set()
    for i, ga in enumerate(gids):
        if ga in merged or ga not in groups: continue
        parc_docs = [d for d in groups[ga] if d.installment]
        if not parc_docs: continue
        parc_vals = {d.value_digits for d in parc_docs if d.value_digits}
        seg_a = _first_seg(ga)
        for gb in gids[i+1:]:
            if gb in merged or gb not in groups: continue
            if _first_seg(gb) != seg_a: continue
            sec_b = _all_sec_digits(groups[gb])
            if parc_vals & sec_b:
                if len(groups[ga]) >= len(groups[gb]):
                    _absorb(groups, gb, ga, log_cb, "parcela+NF"); merged.add(gb)
                else:
                    _absorb(groups, ga, gb, log_cb, "parcela+NF"); merged.add(ga); break


def expand_multi_e_values(groups, docs_all, log_cb=None):
    for doc in docs_all:
        if len(doc.all_value_digits) < 2: continue
        if doc.group_id not in groups: continue
        seg = _first_seg(doc.group_id)
        for val in doc.all_value_digits[1:]:
            for gid, gdocs in groups.items():
                if gid == doc.group_id: continue
                if _first_seg(gid) != seg: continue
                if any(d.value_digits == val for d in gdocs):
                    doc.fingerprint.add(f"multival:{val}")
                    break
