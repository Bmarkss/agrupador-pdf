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
    Similaridade entre dois group_ids.
    v1.6.6 — cascata de 3 sinais:
      1. token_set_ratio (rapidfuzz) sobre nomes normalizados — lida com subconjuntos
      2. Jaccard de tokens fonéticos (doublemetaphone) — Souza/Sousa, Ferreira/Ferreir
      3. Jaccard simples de tokens — fallback

    Retorna valor em [0.0, 1.0].
    """
    # Normaliza removendo sufixos BR (normalize_company_name do validator)
    try:
        from .validator import normalize_company_name as _ncn
        na = _ncn(gid_a) or normalize(gid_a)
        nb = _ncn(gid_b) or normalize(gid_b)
    except ImportError:
        na, nb = normalize(gid_a), normalize(gid_b)

    if not na or not nb:
        return 0.0

    # Sinal 1: token_set_ratio (rapidfuzz) — robusto para substrings
    try:
        from rapidfuzz import fuzz as _fuzz
        tsr = _fuzz.token_set_ratio(na, nb) / 100.0
    except ImportError:
        tsr = 0.0

    # Sinal 2: Jaccard fonético via doublemetaphone
    try:
        from metaphone import doublemetaphone as _dm
        def _phonetic_tokens(s: str) -> set:
            codes = set()
            for tok in re.split(r'[\s\-.,;()/]+', s.lower()):
                if len(tok) >= 3:
                    primary, secondary = _dm(tok)
                    if primary: codes.add(primary)
                    if secondary: codes.add(secondary)
            return codes
        pa, pb = _phonetic_tokens(na), _phonetic_tokens(nb)
        phone_j = len(pa & pb) / len(pa | pb) if (pa and pb and pa | pb) else 0.0
    except ImportError:
        phone_j = 0.0

    # Sinal 3: Jaccard de tokens simples
    def _toks(s: str) -> set:
        return {w for w in re.split(r'[\s\-.,;()/]+', s.lower())
                if len(w) >= 3 and w not in LEGAL_SUFFIXES}
    ta, tb = _toks(na), _toks(nb)
    jaccard = len(ta & tb) / len(ta | tb) if (ta and tb and ta | tb) else 0.0

    # Combina: token_set_ratio tem mais peso, fonética corrige falsos negativos
    return max(tsr, phone_j * 0.9, jaccard)


def entity_prefix_match(gid_a: str, gid_b: str) -> bool:
    """
    True se um gid é prefixo do outro após remoção de sufixos societários puros.
    v1.6.6 — normalização suave: remove só LTDA/S.A./EIRELI, preserva descritores.

    Exemplos:
      "MINAS INDUSTRIA" vs "MINAS INDUSTRIA E COMERCIO" -> True
      "ESTADO DE MG ICMS" vs "ESTADO DE MG ICMS ST"     -> False
      "CRYOBRAS" vs "CRYOBRAS GELO SECO"                -> False
      "AMIL ASSISTENCIA MEDICA" vs "AMIL PLANO DE SAUDE" -> False
    """
    # Sufixos puramente societários (remove do final)
    _CORP = frozenset({
        "ltda","sa","s/a","me","eireli","epp","ss","slu","mei",
        "e","do","da","de","dos","das","&","cia",
    })
    # Descritores aceitos no "extra" mas não stripped do nome
    _DESC = frozenset({
        "comercio","servicos","servico","industria","industrias",
        "transportes","transportadora","logistica","express",
        "solucoes","solucao","empreendimentos","participacoes",
        "construtora","incorporadora","assessoria","consultoria",
    })
    _ABBREV = re.compile(r"^[A-Z]{2,3}$")

    def _norm_soft(gid: str) -> str:
        """Normaliza removendo só sufixos societários do final."""
        s = normalize(gid).upper()
        # Remove sufixos do final repetidamente
        changed = True
        while changed:
            changed = False
            for suf in sorted(_CORP, key=len, reverse=True):
                tail = " " + suf.upper()
                if s.endswith(tail):
                    s = s[:-(len(tail))].strip()
                    changed = True
                    break
        return s.strip()

    na, nb = _norm_soft(gid_a), _norm_soft(gid_b)
    if not na or not nb or len(min(na, nb, key=len)) < 6:
        return False

    short, long_ = (na, nb) if len(na) <= len(nb) else (nb, na)
    if not long_.startswith(short):
        return False

    extra = long_[len(short):].strip()
    if not extra:
        return True

    for w in extra.split():
        wl = w.lower()
        if _ABBREV.match(w):
            return False   # abreviação = qualificador → rejeita
        if wl not in _CORP and wl not in _DESC:
            return False   # palavra desconhecida → rejeita
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
