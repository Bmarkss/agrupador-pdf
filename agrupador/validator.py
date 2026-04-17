"""
validator.py — Validacao estrutural offline de documentos fiscais brasileiros.
v1.6.4 — Deterministica: DV modulo 11/10, estrutura de chaves, linha digitavel.

Filosofia: validar antes de classificar. Um documento que passa na validacao
estrutural nao precisa de ML para ser classificado — o tipo ja e certo.
"""

import re

# ── Importa brutils (MIT) para validacao CNPJ/CPF ────────────────────────────
try:
    from brutils.cnpj import is_valid as _cnpj_valid, format_cnpj
    from brutils.cpf  import is_valid as _cpf_valid
    _BRUTILS_OK = True
except ImportError:
    _BRUTILS_OK = False
    def _cnpj_valid(s): return False
    def _cpf_valid(s):  return False
    def format_cnpj(s): return s

_RE_DIGITS = re.compile(r'\D')


# ── CNPJ / CPF ─────────────────────────────────────────────────────────────────

def validate_cnpj(raw: str) -> bool:
    """Valida CNPJ (14 digitos) via DV modulo 11. Usa brutils se disponivel."""
    digits = _RE_DIGITS.sub('', raw)
    if len(digits) != 14:
        return False
    if _BRUTILS_OK:
        return _cnpj_valid(digits)
    # Fallback manual (modulo 11)
    if len(set(digits)) == 1:
        return False
    def _dv(d, weights):
        s = sum(int(d[i]) * weights[i] for i in range(len(weights)))
        r = s % 11
        return 0 if r < 2 else 11 - r
    w1 = [5,4,3,2,9,8,7,6,5,4,3,2]
    w2 = [6,5,4,3,2,9,8,7,6,5,4,3,2]
    return _dv(digits,w1) == int(digits[12]) and _dv(digits,w2) == int(digits[13])


def validate_cpf(raw: str) -> bool:
    """Valida CPF (11 digitos) via DV modulo 11."""
    digits = _RE_DIGITS.sub('', raw)
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    if _BRUTILS_OK:
        return _cpf_valid(digits)
    def _dv(d, n):
        s = sum(int(d[i]) * (n-i) for i in range(n-1))
        r = (s * 10) % 11
        return 0 if r >= 10 else r
    return _dv(digits,10) == int(digits[9]) and _dv(digits,11) == int(digits[10])


# ── Chave NF-e (44 digitos) ────────────────────────────────────────────────────

_MODELOS_NF = {'55','65'}   # NF-e, NFC-e
_MODELOS_CT = {'57','58'}   # CT-e, CT-e OS
_MODELOS_ALL = _MODELOS_NF | _MODELOS_CT | {'67'}  # MDF-e

def validate_nfe_key(key: str) -> dict | None:
    """
    Valida chave de acesso NF-e/NFC-e/CT-e (44 digitos).
    Retorna dict com campos decodificados ou None se invalida.

    Estrutura: cUF(2) AAMM(4) CNPJ(14) mod(2) serie(3) nNF(9) tpEmis(1) cNF(8) cDV(1)
    """
    digits = _RE_DIGITS.sub('', key)
    if len(digits) != 44:
        return None

    # Valida DV modulo 11 sobre os 43 primeiros digitos
    pesos = list(range(2, 10)) * 6  # [2..9, 2..9, ...]
    soma = sum(int(digits[i]) * pesos[-(i+1)] for i in range(43))
    resto = soma % 11
    dv_calc = 0 if resto < 2 else 11 - resto
    if dv_calc != int(digits[43]):
        return None

    # Decodifica campos
    modelo = digits[20:22]
    uf_cod = digits[0:2]
    cnpj   = digits[6:20]

    return {
        'key':    digits,
        'uf':     uf_cod,
        'aamm':   digits[2:6],
        'cnpj':   cnpj,
        'modelo': modelo,
        'serie':  digits[22:25],
        'nNF':    digits[25:34],
        'tpEmis': digits[34],
        'cDV':    digits[43],
        'tipo':   (
            'nfe'  if modelo in _MODELOS_NF else
            'cte'  if modelo in _MODELOS_CT else
            'mdfe' if modelo == '67' else
            'nfe'   # assume NF-e para modelos desconhecidos
        ),
        'cnpj_valido': validate_cnpj(cnpj),
    }


def classify_from_nfe_key(key: str) -> str | None:
    """Classifica doc_type diretamente da chave NF-e se valida."""
    info = validate_nfe_key(key)
    if not info:
        return None
    return info['tipo']


# ── Linha digitavel de boleto (FEBRABAN) ───────────────────────────────────────

_RE_LINHA = re.compile(
    r'(\d{5})\.(\d{5})\s+(\d{5})\.(\d{6})\s+(\d{5})\.(\d{5})\s+(\d)\s+(\d{14})'
    r'|(\d{4,5})\.(\d{5,10})\s+(\d{5,10})\s+(\d{5,10})\s+(\d)\s+(\d{14})'
)

_RE_LINHA_COMPACT = re.compile(r'\d{47}')
_RE_LINHA_ARRECAD = re.compile(r'\d{48}')


def _mod10(s: str) -> int:
    total = 0
    for i, c in enumerate(reversed(s)):
        n = int(c) * (2 if i % 2 == 0 else 1)
        total += n // 10 + n % 10
    return (10 - (total % 10)) % 10


def _mod11_boleto(s: str) -> int:
    pesos = list(range(2, 10))
    soma = sum(int(s[-(i+1)]) * pesos[i % len(pesos)] for i in range(len(s)))
    r = soma % 11
    if r in (0, 1):
        return 1
    return 11 - r


def validate_linha_digitavel(raw: str) -> dict | None:
    """
    Valida linha digitavel bancaria FEBRABAN (47 digitos) ou arrecadacao (48).
    Retorna dict com tipo, banco, valor e flag valido, ou None se nao e linha digitavel.
    """
    digits = _RE_DIGITS.sub('', raw)

    # Boleto bancario (47 digitos)
    if len(digits) == 47:
        banco = digits[0:3]
        moeda = digits[3]           # 9 = Real
        # Campo 1: 9 digitos + DV mod10
        c1_dados = digits[0:4] + digits[19:24]
        c1_dv    = int(digits[9])
        # Campo 2
        c2_dados = digits[10:20]
        c2_dv    = int(digits[20])
        # Campo 3
        c3_dados = digits[21:31]
        c3_dv    = int(digits[31])
        # DV geral
        dv_geral = int(digits[32])
        # Fator vencimento e valor
        fator  = digits[33:37]
        valor  = digits[37:47]

        valido = (
            _mod10(c1_dados) == c1_dv and
            _mod10(c2_dados) == c2_dv and
            _mod10(c3_dados) == c3_dv
        )
        return {
            'tipo':    'boleto_bancario',
            'banco':   banco,
            'moeda':   moeda,
            'fator':   fator,
            'valor':   str(int(valor) / 100) if valor != '0' * 10 else None,
            'valido':  valido,
        }

    # Boleto arrecadacao / GNRE (48 digitos), começa com 8
    if len(digits) == 48 and digits[0] == '8':
        produto = digits[1]   # 5 = órgãos governamentais
        real    = digits[2]   # 6 = Real
        return {
            'tipo':    'boleto_arrecadacao',
            'produto': produto,
            'real':    real,
            'valido':  True,   # DV arrecadacao e complexo, aceita estruturalmente
            'gnre':    produto == '5',
        }

    return None


# ── Normalização de nome de empresa ───────────────────────────────────────────

try:
    from cleanco import basename
    _CLEANCO_OK = True
except ImportError:
    _CLEANCO_OK = False
    def basename(s): return s

_RE_SUFIXOS_BR = re.compile(
    r'(?<!\w)('
    r'LTDA\.?\s+ME|LTDA\.?\s+EPP|LTDA'
    r'|S\.?\s*A\.?(?!\s*\w)|S/A'
    r'|EIRELI|EPP|MEI'
    r'|(?<!\w)ME(?!\w)'
    r'|SLU|SS'
    r'|CIA\.?|&\s*CIA'
    r'|COMERCIO|COMERCIAL'
    r'|INDUSTRIAS|INDUSTRIA'
    r'|TRANSPORTADORA|TRANSPORTES'
    r'|DISTRIBUIDORA'
    r'|SOLUCOES|SOLUCAO'
    r'|EMPREENDIMENTOS|PARTICIPACOES'
    r'|INCORPORADORA|CONSTRUTORA'
    r'|ASSESSORIA|CONSULTORIA'
    r'|AGROPECUARIA|AGRICOLA'
    r')(?!\w)',
    re.IGNORECASE
)
_RE_MULTI_SPACE = re.compile(r'\s{2,}')


def normalize_company_name(name: str) -> str:
    """
    Normaliza razao social para matching fuzzy.
    Ordem: unidecode → uppercase → remove sufixos BR → colapsa espacos.

    cleanco nao e usado para PT-BR pois corta palavras ao remover sufixos
    compostos (ex: "Logistica" sendo removida como parte de "LTDA LOGISTICA").
    O regex BR customizado cobre todos os sufixos societarios relevantes.
    """
    if not name:
        return ''

    # Unidecode: acentos → ASCII
    try:
        from unidecode import unidecode
        s = unidecode(name).upper()
    except ImportError:
        s = name.upper().encode('ascii', 'ignore').decode()

    # Remove sufixos societarios brasileiros (regex preciso com boundaries)
    s = _RE_SUFIXOS_BR.sub(' ', s)
    s = _RE_MULTI_SPACE.sub(' ', s).strip(' -.,;/')
    return s


# ── Utilitário: extrair e validar todos os CNPJs de um texto ──────────────────

_RE_CNPJ_TEXT = re.compile(
    r'\b(\d{2})[.\s]?(\d{3})[.\s]?(\d{3})[/\s]?(\d{4})[-\s]?(\d{2})\b'
)


def extract_valid_cnpjs(text: str) -> list[str]:
    """Extrai todos os CNPJs validos (DV ok) de um texto."""
    results = []
    for m in _RE_CNPJ_TEXT.finditer(text):
        digits = ''.join(m.groups())
        if validate_cnpj(digits) and digits not in results:
            results.append(digits)
    return results


def extract_valid_nfe_keys(text: str) -> list[dict]:
    """Extrai e valida todas as chaves NF-e (44 digitos) de um texto."""
    results = []
    for m in re.finditer(r'\b(\d{44})\b', text):
        info = validate_nfe_key(m.group(1))
        if info:
            results.append(info)
    return results
