"""
models.py — Modelo de dados DocInfo e utilitarios de normalizacao.

Novos em v1.4.0:
  simhash      — fingerprint de 64 bits do conteudo (para deteccao de duplicatas)
  content_type — tipo de pagamento detectado no conteudo ('pix','ted','gnre',...)
  is_direct         — True se o pagamento e direto (PIX/TED/transferencia) sem boleto esperado
"""

import os, re, hashlib, unicodedata
from pathlib import Path
from .config import RE_COMP_C, FUNC_DESCRIPTORS, SIMHASH_BITS, LEGAL_SUFFIXES


def normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).upper()


def normalize_value(num_str: str) -> str:
    return re.sub(r"[^\d]", "", num_str.strip().rstrip("-").strip())


def simhash(text: str, bits: int = SIMHASH_BITS,
            exclude: set | None = None) -> int:
    """
    SimHash do conteudo textual.
    Se exclude for passado, filtra tokens estruturais antes do calculo.
    Documentos similares produzem hashes com baixa distancia de Hamming.
    """
    v = [0] * bits
    tokens = re.findall(r"[a-z0-9]{4,}", text.lower())
    if exclude:
        tokens = [t for t in tokens if t not in exclude]
    if not tokens:
        return 0
    for token in tokens:
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        for i in range(bits):
            v[i] += 1 if (h >> i) & 1 else -1
    return sum(1 << i for i in range(bits) if v[i] > 0)


def compute_batch_simhash(
    docs: list,
    bits: int = SIMHASH_BITS,
    structural_threshold: float = 0.30,
) -> set:
    """
    Calcula SimHash limpo para uma lista de DocInfo.
    Filtra tokens que aparecem em >30% dos docs (template do banco).
    Retorna o conjunto de tokens estruturais filtrados.

    Atualiza doc.simhash in-place para cada documento.
    """
    from collections import Counter
    if not docs:
        return set()

    # Tokeniza todos os docs
    per_doc = {}
    for doc in docs:
        toks = re.findall(r"[a-z0-9]{4,}", doc.content[:8000].lower())
        per_doc[doc.fname] = (doc, toks)

    # Frequencia por documento (nao total de ocorrencias)
    doc_freq: Counter = Counter()
    for _, (_, toks) in per_doc.items():
        for t in set(toks):
            doc_freq[t] += 1

    threshold = max(2, int(len(docs) * structural_threshold))
    structural: set = {tok for tok, cnt in doc_freq.items() if cnt >= threshold}

    # Recomputa simhash de cada doc excluindo tokens estruturais
    for fname, (doc, toks) in per_doc.items():
        doc.simhash = simhash(doc.content[:8000], bits=bits, exclude=structural)

    return structural


def hamming_distance(a: int, b: int) -> int:
    """Distancia de Hamming entre dois SimHashes."""
    return bin(a ^ b).count("1")


def entity_similarity(gid_a: str, gid_b: str) -> float:
    """
    Jaccard similarity entre tokens de dois group_ids normalizados.
    Ignora sufixos legais (LTDA, SA, E COMERCIO, etc.).

    Retorna valor em [0.0, 1.0].

    Exemplos:
      "MINAS INDUSTRIA" vs "MINAS INDUSTRIA E COMERCIO" -> ~0.67
      "AMIL ASSISTENCIA MEDICA" vs "AMIL PLANO DE SAUDE" -> ~0.14
      "CAIXA ECONOMICA" vs "CAIXA ECONOMICA FEDERAL" -> 0.67
    """
    def _clean_tokens(gid: str) -> set:
        s = normalize(gid).lower()
        words = re.split(r"[\s\-.,;()/]+", s)
        return {w for w in words if len(w) >= 3 and w not in LEGAL_SUFFIXES}

    ta = _clean_tokens(gid_a)
    tb = _clean_tokens(gid_b)
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    union = ta | tb
    return len(inter) / len(union)


def entity_prefix_match(gid_a: str, gid_b: str) -> bool:
    """
    True se um gid e prefixo do outro considerando apenas sufixos societarios/conjuncoes.

    Regras:
      1. Normaliza removendo apenas sufixos legais puros (LTDA, SA, ME, E, DO, DA...)
         NAO remove descritores de negocio (INDUSTRIA, COMERCIO, TRANSPORTES...)
      2. O "extra" no nome mais longo so pode conter LEGAL_SUFFIXES ou descritores.
         Abreviacoes 2-3 chars (ST, AC, SP, PR) sao qualificadores — rejeitam o match.
      3. Min 6 chars no nome mais curto.

    Exemplos:
      "MINAS INDUSTRIA" vs "MINAS INDUSTRIA E COMERCIO" -> True
      "ESTADO DE MG ICMS" vs "ESTADO DE MG ICMS ST"     -> False  (ST = qualificador)
      "CRYOBRAS" vs "CRYOBRAS GELO SECO"                -> False  (GELO SECO = outro nome)
      "AMIL ASSISTENCIA MEDICA" vs "AMIL PLANO DE SAUDE"-> False  (conteudos distintos)
    """
    # Sufixos puramente societarios/conjuncoes (OK remover do final)
    _CORP = frozenset({
        "ltda","sa","s/a","me","eireli","epp","ss",
        "e","do","da","de","dos","das",
    })
    # Descritores de negocio (aceitos no "extra", mas nao stripped do nome)
    _DESC = frozenset({
        "comercio","servicos","industria","transportes",
        "logistica","express","solucoes",
    })
    _ABBREV = re.compile(r"^[A-Z]{2,3}$")   # ST, AC, SP, PR — qualificadores

    def _norm(gid: str) -> str:
        s = normalize(gid)
        for suf in sorted(_CORP, key=len, reverse=True):
            if s.endswith(" " + suf.upper()):
                s = s[:-(len(suf) + 1)].strip()
        return s

    na, nb = _norm(gid_a), _norm(gid_b)
    if not na or not nb:
        return False
    short, long_ = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(short) < 6 or not long_.startswith(short):
        return False
    extra = long_[len(short):].strip()
    if not extra:
        return True
    for w in extra.split():
        wl = w.lower()
        if wl in _CORP or wl in _DESC:
            continue
        if _ABBREV.match(w):        # abreviacao significativa -> nao e so sufixo
            return False
        return False                # palavra desconhecida -> rejeita
    return True


def person_tokens(gid: str) -> frozenset:
    tokens = set()
    for part in gid.lower().split(" - "):
        for word in re.split(r"[\s.,;()/+]+", part):
            word = word.strip()
            if len(word) >= 3 and word not in FUNC_DESCRIPTORS:
                tokens.add(normalize(word).lower())
    return frozenset(tokens)


class DocInfo:
    """
    Todos os atributos extraidos de um PDF antes de qualquer decisao
    de agrupamento.

    v1.4.0 adiciona:
      simhash       — fingerprint 64-bit do conteudo (deteccao de duplicatas)
      content_type  — 'pix'/'ted'/'transferencia'/'gnre'/'boleto_pago'/None
      is_direct     — True se o pagamento e direto (PIX/TED) sem boleto esperado
      dup_of        — fname do documento original se este for uma duplicata
    """
    __slots__ = (
        "path","fname","stem",
        "content","pages",
        "group_id","type_segment","doc_type",
        "value_raw","value_digits",
        "period","suffix_c",
        # avancados v1.2.0
        "value_sec_raw","value_sec_digits",
        "all_value_digits","installment",
        "nf_keys","cnpj_emitter","cnpj_sacado","boleto_id","pix_key","bank_code","due_dates","doc_numbers","fingerprint",
        # novos v1.4.0
        "simhash","content_type","is_direct","dup_of",
    )

    def __init__(self, path: str):
        self.path  = path
        # Normaliza #U00XX (URL-encoded unicode de filenames) → caractere real
        _bname = os.path.basename(path)
        import re as _re
        self.fname = _re.sub(r'#[Uu]([0-9a-fA-F]{4})',
                             lambda x: chr(int(x.group(1), 16)), _bname)
        raw = Path(path).stem
        # Normaliza #U00XX do stem também (mesmo fix do fname)
        raw = _re.sub(r'#[Uu]([0-9a-fA-F]{4})', lambda x: chr(int(x.group(1), 16)), raw)
        raw = re.sub(r" -([A-Za-z\xc0-\xff])", r" - \1", raw)
        raw = re.sub(r"(\s*-\s*C)\s*-\s*", r"\1 - ", raw, flags=re.IGNORECASE)
        self.stem = raw

        self.content=""; self.pages=1
        self.group_id=None; self.type_segment=None; self.doc_type=None
        self.value_raw=None; self.value_digits=None
        self.period=None; self.suffix_c=bool(RE_COMP_C.search(self.stem))

        self.value_sec_raw=None; self.value_sec_digits=None
        self.all_value_digits: list[str]=[]
        self.installment=None
        self.nf_keys: set[str]=set()
        self.cnpj_emitter=None
        self.cnpj_sacado=None
        self.boleto_id=None
        self.pix_key=None
        self.bank_code=None
        self.due_dates: list[str]=[]
        self.doc_numbers: set[str]=set()
        self.fingerprint: set[str]=set()

        # v1.4.0
        self.simhash: int  = 0
        self.content_type  = None   # 'pix','ted','transferencia','gnre',None
        self.is_direct     = False  # pagamento direto sem boleto esperado
        self.dup_of        = None   # fname do original se for duplicata

    def __repr__(self):
        return (f"DocInfo({self.fname!r}, type={self.doc_type!r}, "
                f"group={self.group_id!r}, value={self.value_raw!r})")
