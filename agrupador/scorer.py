"""
scorer.py — Sistema de scoring de confiança para agrupamento de documentos fiscais.

v1.5.0 — substitui ticks binários por scores probabilísticos calibrados.

Score final: 0.0 – 1.0
  >= 0.90  →  ✔  verde   (confiança alta — aceitar automaticamente)
  0.65–0.89 →  ⚠  amarelo  (revisar — provável mas não certo)
  < 0.65   →  ✘  vermelho (suspeito — intervenção manual)

Sinais e pesos:
  Chave NF-e compartilhada (+0.50)   — máxima especificidade
  CNPJ emitente idêntico  (+0.30)    — extraído da chave NF-e ou do conteúdo
  Valor monetário idêntico (+0.15)    — value_digits exato
  Nome fuzzy ≥ 80%        (+0.10)    — rapidfuzz token_set_ratio
  Período/data coincidente (+0.05)    — mesmo mês/ano

Cada sinal contribui apenas se ambos os documentos tiverem o campo.
O score é normalizado pela soma dos pesos aplicáveis (peso máximo possível).
"""

from __future__ import annotations
import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import DocInfo

# ── Thresholds públicos ────────────────────────────────────────────────────────
SCORE_GREEN  = 0.90   # ✔ confiança alta
SCORE_YELLOW = 0.65   # ⚠ revisar
# < SCORE_YELLOW → ✘ suspeito

# ── Pesos por sinal ───────────────────────────────────────────────────────────
_W = {
    "nf_key":   0.50,   # chave NF-e de 44 dígitos compartilhada
    "cnpj":     0.30,   # CNPJ emitente idêntico (extraído da chave ou conteúdo)
    "value":    0.15,   # valor monetário exato
    "entity":   0.10,   # nome de entidade fuzzy ≥ 80%
    "period":   0.05,   # período coincidente
}

# ── Sufixos jurídicos para normalização de nomes ─────────────────────────────
_LEGAL = frozenset({
    "ltda","sa","s/a","me","eireli","epp","ss","cia",
    "comercio","servicos","industria","transportes",
    "logistica","express","solucoes",
    "e","do","da","de","dos","das","e",
})

_RE_NONALPHA = re.compile(r"[^a-z0-9\s]")


def _normalize_name(name: str) -> str:
    """Normaliza nome de empresa para comparação fuzzy."""
    nfkd = unicodedata.normalize("NFKD", name.lower())
    s = "".join(c for c in nfkd if not unicodedata.combining(c))
    s = _RE_NONALPHA.sub(" ", s)
    tokens = [t for t in s.split() if t not in _LEGAL and len(t) >= 2]
    return " ".join(tokens)


def entity_fuzzy_score(gid_a: str, gid_b: str) -> float:
    """
    Score de similaridade entre dois group_ids usando rapidfuzz.
    Usa token_set_ratio após normalização de sufixos jurídicos.
    Retorna valor em [0.0, 1.0].

    Exemplos:
      "MINAS INDUSTRIA" vs "MINAS INDUSTRIA E COMERCIO LTDA" → 1.0
      "AMIL ASSISTENCIA MEDICA" vs "AMIL PLANO DE SAUDE"     → ~0.33
      "CRYOBRAS" vs "CRYOBRAS GELO SECO"                     → ~0.50
    """
    try:
        from rapidfuzz import fuzz
        na = _normalize_name(gid_a)
        nb = _normalize_name(gid_b)
        if not na or not nb:
            return 0.0
        return fuzz.token_set_ratio(na, nb) / 100.0
    except ImportError:
        # Fallback para Jaccard simples se rapidfuzz não estiver disponível
        ta = set(_normalize_name(gid_a).split())
        tb = set(_normalize_name(gid_b).split())
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)


def parse_nfe_key(key44: str) -> dict:
    """
    Extrai campos da chave de acesso NF-e de 44 dígitos.
    Estrutura (posições 0-indexed):
      [00:02] cUF — código IBGE da UF
      [02:06] AAMM — ano/mês de emissão
      [06:20] CNPJ do emitente (14 dígitos)
      [20:22] modelo (55=NF-e, 57=CT-e, 58=MDF-e, 65=NFC-e)
      [22:25] série
      [25:34] número da NF-e
      [34:43] código numérico aleatório
      [43:44] dígito verificador

    Retorna dict com os campos ou {} se a chave for inválida.
    """
    if not key44 or len(key44) != 44 or not key44.isdigit():
        return {}
    return {
        "uf_ibge": key44[0:2],
        "aamm":    key44[2:6],
        "cnpj":    key44[6:20],
        "modelo":  key44[20:22],
        "serie":   key44[22:25],
        "numero":  key44[25:34].lstrip("0") or "0",
        "dv":      key44[43],
    }


def cnpj_from_nfe_key(key44: str) -> str | None:
    """Extrai apenas o CNPJ do emitente da chave NF-e. Retorna 14 dígitos ou None."""
    parsed = parse_nfe_key(key44)
    cnpj = parsed.get("cnpj", "")
    return cnpj if len(cnpj) == 14 else None


def _get_cnpj(doc: "DocInfo") -> str | None:
    """
    Obtém o CNPJ mais confiável de um documento.
    Prioridade: chave NF-e > cnpj_emitter do conteúdo.
    """
    for key in doc.nf_keys:
        cnpj = cnpj_from_nfe_key(key)
        if cnpj:
            return cnpj
    return doc.cnpj_emitter


# ── Score principal ────────────────────────────────────────────────────────────

def confidence_score(
    doc_a: "DocInfo",
    doc_b: "DocInfo",
) -> tuple[float, dict]:
    """
    Calcula o score de confiança entre dois documentos do mesmo grupo.

    Retorna (score: float, detalhes: dict) onde detalhes contém cada sinal
    e sua contribuição — útil para exibir na UI o motivo do score.

    score em [0.0, 1.0]:
      >= SCORE_GREEN  →  alta confiança
      >= SCORE_YELLOW →  média confiança
      <  SCORE_YELLOW →  baixa confiança
    """
    earned = 0.0
    possible = 0.0
    details: dict[str, float | str] = {}

    # ── Sinal 1: Chave NF-e compartilhada ─────────────────────────────────
    keys_a = doc_a.nf_keys or set()
    keys_b = doc_b.nf_keys or set()
    if keys_a and keys_b:
        possible += _W["nf_key"]
        if keys_a & keys_b:
            earned += _W["nf_key"]
            details["nf_key"] = "✔ mesma chave NF-e"
        else:
            details["nf_key"] = "✘ chaves NF-e diferentes"

    # ── Sinal 2: CNPJ emitente idêntico ───────────────────────────────────
    # Nota: comprovante contém CNPJ do PAGADOR (Loglife), não do fornecedor.
    # Comparar CNPJ comprovante↔nota é sempre diferente — não penaliza.
    # Sinal válido apenas entre nota↔boleto (ambos têm CNPJ do emitente/beneficiário).
    cnpj_a = _get_cnpj(doc_a)
    cnpj_b = _get_cnpj(doc_b)
    tipos = {doc_a.doc_type, doc_b.doc_type}
    cnpj_valido = cnpj_a and cnpj_b and "comprovante" not in tipos
    if cnpj_valido:
        possible += _W["cnpj"]
        if cnpj_a == cnpj_b:
            earned += _W["cnpj"]
            details["cnpj"] = f"✔ CNPJ {cnpj_a[:4]}...{cnpj_a[-2:]}"
        else:
            details["cnpj"] = "✘ CNPJs diferentes"

    # ── Sinal 3: Valor monetário exato ────────────────────────────────────
    val_a = doc_a.value_digits
    val_b = doc_b.value_digits
    # Também considera all_value_digits (ex: soma de parcelas)
    all_a = set(doc_a.all_value_digits or [])
    all_b = set(doc_b.all_value_digits or [])
    if val_a and val_b:
        possible += _W["value"]
        if val_a == val_b or (all_a & all_b):
            earned += _W["value"]
            details["value"] = f"✔ valor R${doc_a.value_raw or val_a}"
        else:
            details["value"] = f"⚠ valores distintos ({doc_a.value_raw} vs {doc_b.value_raw})"

    # ── Sinal 4: Nome de entidade fuzzy ───────────────────────────────────
    gid_a = doc_a.group_id or ""
    gid_b = doc_b.group_id or ""
    if gid_a and gid_b:
        possible += _W["entity"]
        fscore = entity_fuzzy_score(gid_a, gid_b)
        if fscore >= 0.80:
            earned += _W["entity"]
            details["entity"] = f"✔ entidade similar ({fscore:.0%})"
        elif fscore >= 0.50:
            earned += _W["entity"] * 0.5
            details["entity"] = f"⚠ entidade parecida ({fscore:.0%})"
        else:
            details["entity"] = f"✘ entidade distinta ({fscore:.0%})"

    # ── Sinal 5: Período/data coincidente ─────────────────────────────────
    per_a = doc_a.period
    per_b = doc_b.period
    if per_a and per_b:
        possible += _W["period"]
        if per_a == per_b:
            earned += _W["period"]
            details["period"] = f"✔ período {per_a}"
        else:
            details["period"] = f"⚠ períodos distintos ({per_a} vs {per_b})"

    # ── Score normalizado ─────────────────────────────────────────────────
    if possible == 0.0:
        # Nenhum sinal disponível — score neutro
        score = 0.5
        details["fallback"] = "sinais insuficientes para scoring"
    else:
        score = earned / possible

    return round(score, 3), details


def group_confidence(docs: list["DocInfo"]) -> tuple[float, dict]:
    """
    Score de confiança de um grupo inteiro (mínimo dos pares de maior relevância).
    Para grupos de 2 documentos, calcula direto.
    Para grupos maiores, calcula o score mínimo entre comprovante e cada outro doc.
    """
    if len(docs) < 2:
        return 0.5, {"fallback": "grupo com menos de 2 documentos"}

    # Identifica o comprovante (âncora de referência)
    comprovantes = [d for d in docs if d.doc_type == "comprovante"]
    if not comprovantes:
        # Sem comprovante: calcula média dos pares
        scores = []
        for i, da in enumerate(docs):
            for db in docs[i+1:]:
                s, _ = confidence_score(da, db)
                scores.append(s)
        avg = sum(scores) / len(scores) if scores else 0.5
        return round(avg, 3), {"method": "media_sem_comprovante"}

    # Com comprovante: score mínimo entre comprovante e cada outro doc
    comp = comprovantes[0]
    min_score = 1.0
    all_details: dict = {}
    others = [d for d in docs if d is not comp]

    for other in others:
        s, det = confidence_score(comp, other)
        if s < min_score:
            min_score = s
            all_details = det
            all_details["par"] = f"{comp.doc_type}↔{other.doc_type}"

    return round(min_score, 3), all_details


def score_to_symbol(score: float) -> str:
    """Converte score em símbolo de status."""
    if score >= SCORE_GREEN:
        return "✔"
    if score >= SCORE_YELLOW:
        return "⚠"
    return "✘"


def score_to_label(score: float) -> str:
    """Rótulo legível do score."""
    if score >= SCORE_GREEN:
        return f"✔ {score:.0%}"
    if score >= SCORE_YELLOW:
        return f"⚠ {score:.0%}"
    return f"✘ {score:.0%}"
