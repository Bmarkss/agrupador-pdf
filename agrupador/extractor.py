"""
extractor.py — Fase 1: leitura, extracao e classificacao de PDFs.

v1.4.0:
  - compute_simhash() para deteccao de duplicatas
  - detect_content_type() — 'pix','ted','transferencia','gnre'
  - extract_period() tambem detecta datas VENCIMENTO DD-MM-YYYY do nome
  - extract_group_id() remove tokens de VENCIMENTO do gid
"""

import os, re, warnings
from .config import (
    OCR_AVAILABLE, _POPPLER, pytesseract, convert_from_path,
    MIN_TEXT_CHARS, SEG_MAP, ENTITY_STOP,
    RE_VALUE, RE_VALUE_SEC, RE_PERIOD, RE_VENCIMENTO, RE_DIGITS_ONLY,
    RE_STRIP_C, RE_INSTALLMENT, RE_NF_KEY, RE_CNPJ, RE_DUE_DATE,
    RE_DOC_NUMBER,
)
from .models import DocInfo, normalize, normalize_value, simhash
from .scorer     import cnpj_from_nfe_key
from .classifier import classify, warmup as _warmup_classifier
try:
    from .cnpj_cache import lookup_cnpj_async as _lookup_cnpj_async
    _CNPJ_CACHE_OK = True
except ImportError:
    _CNPJ_CACHE_OK = False

try:
    import pdfplumber as _pdfplumber
    _PLUMBER_OK = True
except ImportError:
    _PLUMBER_OK = False

try:
    from pypdf import PdfReader as _PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader as _PdfReader
    except ImportError:
        _PdfReader = None


# ── Extracao de texto ─────────────────────────────────────────────────────────

def extract_text(path: str) -> tuple[str, int]:
    """
    Extrai texto de um PDF.
    Estratégia otimizada para performance:
    - pypdf como extrator principal (rápido, ~10ms/pág)
    - pdfplumber como fallback quando pypdf retorna pouco texto
    - OCR como último recurso
    pdfplumber é chamado separadamente em extract_boleto_fields apenas para
    documentos classificados como boleto, onde as tabelas estruturadas importam.
    """
    text = ""; pages = 1

    # Tentativa 1: pypdf — skip em PDFs > 3MB (contratos/relatórios pesados)
    # Para docs fiscais, o GID vem do nome do arquivo; o conteúdo é complementar.
    _fsize_kb = os.path.getsize(path) // 1024 if os.path.exists(path) else 0
    if _PdfReader and _fsize_kb <= 3000:
        try:
            reader = _PdfReader(path)
            pages  = len(reader.pages)
            # Lê no máximo 8 páginas para documentos multi-página
            pages_to_read = reader.pages[:8] if pages > 8 else reader.pages
            text   = " ".join(p.extract_text() or "" for p in pages_to_read).strip()
        except Exception:
            pass

    # Tentativa 2: pdfplumber como fallback se pypdf extraiu pouco
    # Limita a 5MB para evitar timeout em PDFs grandes (ex: relatórios com imagens)
    _fsize = os.path.getsize(path) if os.path.exists(path) else 0
    if len(text) < MIN_TEXT_CHARS and _PLUMBER_OK and _fsize < 5_000_000:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
            with _pdfplumber.open(path) as pdf:
                pages = len(pdf.pages)
                parts = [p.extract_text(x_tolerance=3, y_tolerance=3) or ""
                         for p in pdf.pages]
                text = " ".join(parts).strip()
        except Exception:
            pass

    if len(text) >= MIN_TEXT_CHARS:
        return text.lower(), pages

    # Tentativa 3: OCR
    if OCR_AVAILABLE:
        try:
            kw = {"poppler_path": _POPPLER} if os.path.isdir(_POPPLER) else {}
            imgs  = convert_from_path(path, dpi=200, **kw)
            pages = len(imgs)
            text  = " ".join(pytesseract.image_to_string(i, lang="por") for i in imgs).strip()
        except Exception:
            pass
    return text.lower(), pages


# ── Extração estruturada de boleto (pdfplumber) ───────────────────────────────

_RE_NOSSO_NUM = re.compile(
    r'nosso\s+n[uú]mero[\s\S]{0,40}?(\d[\d\/\-\.]{4,20}\d)', re.I
)


# ── Dicionário estático de bancos brasileiros (top 60 por uso) ────────────────
# Fonte: Bacen / BrasilAPI /banks/v1 — atualizado periodicamente
_BANKS: dict[str, str] = {
    "001": "Banco do Brasil", "033": "Santander", "041": "Banrisul",
    "070": "BRB", "077": "Inter", "084": "CC Uniprime", "085": "Ailos",
    "097": "Crehnor", "099": "Uniprime Central", "104": "Caixa Econômica",
    "133": "Cresol", "136": "Unicred", "197": "Stone", "208": "BTG Pactual",
    "212": "Banco Original", "218": "BS2", "237": "Bradesco",
    "260": "Nubank", "290": "PagSeguro", "301": "BPP",
    "318": "BMG", "336": "C6 Bank", "341": "Itaú", "348": "XP",
    "364": "Gerencianet/Efí", "380": "PicPay", "389": "Mercantil",
    "394": "Banco Finaxis", "403": "Cora", "422": "Safra",
    "461": "Asaas", "477": "Citibank", "505": "Credit Suisse",
    "637": "Sofisa", "655": "Votorantim", "707": "Daycoval",
    "735": "Neon", "739": "BCN", "741": "Ribeirão Preto",
    "745": "Citibank N.A.", "748": "Sicredi", "752": "BNB",
    "756": "Sicoob", "757": "BSES", "77":  "Inter",
}

_RE_PIX_KEY  = re.compile(
    r'chave(?:\s+pix)?[\s:]+([\w@.+\-]{5,77})', re.I
)
_RE_PIX_CNPJ = re.compile(r'\d{2}[.\s]?\d{3}[.\s]?\d{3}[/\s]?\d{4}[-\s]?\d{2}')
_RE_PIX_CPF  = re.compile(r'(?<!\d)\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}(?!\d)')
_RE_LINHA_DIG = re.compile(r'(\d{3})(\d)(\d{5})\.\d{5}\s+(\d{5})\.\d{6}\s+(\d{5})')


def extract_pix_key(content: str) -> str | None:
    """
    Extrai a chave PIX do recebedor de um comprovante.
    Retorna CNPJ/CPF limpo (só dígitos) se a chave for CNPJ ou CPF,
    ou a chave bruta (UUID, email, telefone) nos demais casos.
    """
    if not content: return None
    m = _RE_PIX_KEY.search(content)
    if not m: return None
    raw = m.group(1).strip()
    # Se for CNPJ (14 dígitos)
    cnpj = _RE_PIX_CNPJ.search(raw)
    if cnpj:
        return re.sub(r'\D', '', cnpj.group())[:14]
    # Se for CPF (11 dígitos)
    cpf = _RE_PIX_CPF.search(raw)
    if cpf:
        return re.sub(r'\D', '', cpf.group())[:11]
    # UUID, e-mail, telefone — retorna bruto truncado
    return raw[:50]


def extract_bank_code(content: str) -> str | None:
    """
    Extrai o código do banco (3 dígitos) da linha digitável de um boleto.
    Os primeiros 3 dígitos da linha digitável são o código do banco emissor.
    """
    m = _RE_LINHA_DIG.search(content)
    if m:
        return m.group(1)   # primeiros 3 dígitos
    return None


def bank_name(code: str | None) -> str | None:
    """Retorna o nome do banco pelo código de 3 dígitos."""
    if not code: return None
    return _BANKS.get(code.lstrip("0").zfill(3)) or _BANKS.get(code.lstrip("0"))

def extract_boleto_fields(path: str) -> dict:
    """
    Usa pdfplumber para extrair campos estruturados de boletos bancários.
    Retorna dict com: cedente, sacado, cnpj_sacado, nosso_numero, vencimento, valor_doc.
    Retorna {} se pdfplumber não disponível ou PDF não é boleto.
    """
    if not _PLUMBER_OK:
        return {}
    result = {}
    # Boletos legítimos são < 2MB — ignora PDFs muito grandes
    if os.path.getsize(path) > 2_000_000:
        return {}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
        with _pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                for table in (page.extract_tables() or []):
                    for row in table:
                        cells = [str(c or "").strip() for c in row]
                        row_text = " | ".join(cells).lower()

                        for cell in cells:
                            cell_l = cell.lower()
                            # Cedente (quem emite o boleto)
                            if "cedente" in cell_l and len(cells) > 1:
                                idx = next((i for i,c in enumerate(cells) if "cedente" in c.lower()), -1)
                                if idx >= 0 and idx+1 < len(cells) and cells[idx+1]:
                                    result['cedente'] = cells[idx+1].split('\n')[0].strip()
                            # Sacado (quem paga — normalmente LOGLIFE)
                            if "sacado" in cell_l:
                                # Extrai CNPJ do sacado
                                cnpjs = RE_CNPJ.findall(cell)
                                if cnpjs:
                                    result['cnpj_sacado'] = re.sub(r'\D','', cnpjs[0])
                            # Nosso Número
                            if "nosso" in cell_l and "n" in cell_l:
                                m = _RE_NOSSO_NUM.search(cell)
                                if m:
                                    result['nosso_numero'] = re.sub(r'[\s\-]','', m.group(1))
                            # Vencimento
                            if "vencimento" in cell_l:
                                dates = RE_DUE_DATE.findall(cell)
                                if dates:
                                    d = dates[0]
                                    # RE_DUE_DATE retorna tuple de grupos — converte para string DD/MM/YYYY
                                    if isinstance(d, tuple):
                                        parts = [p for p in d if p]
                                        if len(parts) >= 3:
                                            d = f"{parts[0]}/{parts[1]}/{parts[2]}"
                                        else:
                                            d = "/".join(parts)
                                    result['vencimento'] = d
                            # Valor do documento
                            if "valor" in cell_l and "documento" in cell_l:
                                idx = next((i for i,c in enumerate(cells)
                                           if "valor" in c.lower() and "doc" in c.lower()), -1)
                                if idx >= 0 and idx+1 < len(cells):
                                    val_cell = cells[idx+1]
                                    _, val_d = extract_value(val_cell)
                                    if val_d:
                                        result['valor_doc'] = val_d
    except Exception:
        pass
    return result


# ── Deteccao de tipo de pagamento pelo conteudo ───────────────────────────────

_CONTENT_TYPE_KW: dict[str, list[str]] = {
    "pix":           ["pagamento via pix", "pix efetuado", "transferencia pix",
                      "chave pix", "qr code pix", "tipo de pagamento: pix"],
    "ted":           ["ted realizada", "ted efetuada", "transferencia ted",
                      "tipo ted", "transferencia entre bancos"],
    "transferencia": ["comprovante de transferencia", "transferencia realizada",
                      "transferencia entre contas", "dados da conta debitada"],
    # Nota: keywords de gnre precisam ser específicos o suficiente para não capturar
    # comprovantes bancários que apenas citam "GNRE ONLINE" na descrição do pagamento.
    # "guia nacional de recolhimento" e "uf favorecida" são exclusivos do doc original.
    "gnre":          ["guia nacional de recolhimento", "uf favorecida",
                      "codigo de receita gnre", "receita estadual gnre"],
    "boleto_pago":   ["comprovante de pagamento de boleto", "boleto pago",
                      "codigo de barras", "nosso numero", "linha digitavel"],
}

def detect_content_type(text: str) -> str | None:
    """
    Detecta o tipo especifico de pagamento pelo conteudo do PDF.
    Retorna: 'pix', 'ted', 'transferencia', 'gnre', 'boleto_pago', ou None.
    Prioridade: gnre antes de pix (GNRE menciona QR Code PIX mas nao é comprovante PIX).
    """
    if not text:
        return None
    tl = text.lower()
    for ctype in ("gnre", "pix", "ted", "boleto_pago", "transferencia"):
        if any(kw in tl for kw in _CONTENT_TYPE_KW[ctype]):
            return ctype
    return None


# ── Extracao de valores ───────────────────────────────────────────────────────

def extract_value(text: str) -> tuple[str | None, str | None]:
    m = RE_VALUE.search(text)
    if not m:
        return None, None
    num    = m.group(1).strip().rstrip("-")
    prefix = "R$ " if m.start() < len(text) and text[m.start()] == "R" else "$ "
    return prefix + num, normalize_value(num)


def extract_value_secondary(text: str) -> tuple[str | None, str | None]:
    m = RE_VALUE_SEC.search(text)
    if not m:
        return None, None
    num = m.group(1).strip()
    return "$ " + num, normalize_value(num)


def extract_gnre_total(text: str) -> tuple[str | None, str | None]:
    """
    Extrai o 'Total a Recolher' da GNRE.

    O layout da GNRE separa rótulos e valores em colunas distintas, então
    "Total a Recolher" nunca fica adjacente ao seu valor no texto extraído.
    Como o Total = Principal + Juros + Multa + Atualização, ele é sempre o
    maior valor monetário do documento — estratégia usada aqui.

    Fallback: regex adjacente para layouts onde o texto sai concatenado.
    """
    import re as _re
    # Fallback: regex adjacente (layouts onde o valor fica junto do rótulo)
    m = _re.search(
        r"total\s+a\s+recolher\s*[:\-]?\s*R?\$\s*([\d.,]+)",
        text, _re.IGNORECASE
    )
    if m:
        num = m.group(1).strip()
        return "R$ " + num, normalize_value(num)

    # Estratégia principal: maior R$ do documento = Total a Recolher
    vals = [(normalize_value(mv.group(1)), mv.group(1).strip())
            for mv in RE_VALUE.finditer(text)
            if mv.group(1).strip()]
    vals = [(d, r) for d, r in vals if d]
    if not vals:
        return None, None
    digits, raw = max(vals, key=lambda x: int(x[0]))
    return "R$ " + raw, digits


def extract_all_values(text: str) -> list[str]:
    """
    Todos os valores monetarios + soma de pares consecutivos.
    Ex: "R$8102,66 ... R$8102,65" -> ['810266','810265','1620531']
    """
    vals = [normalize_value(m.group(1))
            for m in RE_VALUE.finditer(text)
            if m.group(1).strip().rstrip("-")]
    extras = []
    for i in range(len(vals) - 1):
        try:
            s = str(int(vals[i]) + int(vals[i+1]))
            if s not in vals:
                extras.append(s)
        except (ValueError, TypeError):
            pass
    return vals + extras


# ── Extracao de metadados ─────────────────────────────────────────────────────

def extract_period(stem: str, content: str = "") -> str | None:
    """
    Extrai periodo de referencia. Prioridade:
    1. Data VENCIMENTO no nome (VENCIMENTO DD-MM-YYYY)
    2. Mes/ano no nome (JANEIRO.2026, 01/2026)
    3. Conteudo do PDF
    """
    # 1. VENCIMENTO no nome do arquivo
    m = RE_VENCIMENTO.search(stem)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{mm}.{yyyy[-2:]}"  # ex: "04.26"

    # 2. Mes/ano no nome
    m = RE_PERIOD.search(stem)
    if m:
        return m.group(0).strip().upper()

    # 3. Conteudo
    if content:
        m = RE_PERIOD.search(content)
        if m:
            return m.group(0).strip().upper()
    return None


def extract_installment(text: str) -> tuple[int, int] | None:
    m = RE_INSTALLMENT.search(text.lower())
    if not m:
        return None
    groups = [g for g in m.groups() if g is not None]
    if len(groups) >= 2:
        try:
            return (int(groups[0]), int(groups[1]))
        except (ValueError, IndexError):
            pass
    return None


def extract_nf_keys(content: str) -> set[str]:
    return set(RE_NF_KEY.findall(content))


def extract_cnpj(content: str) -> str | None:
    m = RE_CNPJ.search(content)
    return "".join(m.groups()) if m else None


def extract_due_dates(content: str) -> list[str]:
    dates = set()
    for m in RE_DUE_DATE.finditer(content):
        groups = [g for g in m.groups() if g is not None]
        if len(groups) >= 3:
            try:
                dates.add(f"{groups[0]}{groups[1]}{groups[2]}")
            except IndexError:
                pass
    return sorted(dates)


def extract_doc_numbers(stem: str, content: str) -> set[str]:
    numbers = set()
    for src in [stem, content[:3000]]:
        for m in RE_DOC_NUMBER.finditer(src.lower()):
            numbers.add(m.group(1).lstrip("0") or "0")
    return numbers


def extract_type_segment(stem: str) -> str | None:
    stem_norm = re.sub(r"(?<=[A-Za-z0-9])-(?=[A-Za-z])", " - ", stem)
    # Remove VENCIMENTO do stem antes de extrair segmento
    stem_norm = RE_VENCIMENTO.sub("", stem_norm).strip()
    s     = RE_STRIP_C.sub("", stem_norm).strip()
    parts = re.split(r"\s+-\s+", s)
    for i, p in enumerate(parts):
        if RE_VALUE.search(p):
            if i > 0:
                candidate = parts[i-1].strip()
                if RE_PERIOD.match(candidate):
                    return None
                if len(candidate.split()) > 4:
                    return None
                return candidate
            break
    return None



def _fix_url_unicode(s: str) -> str:
    """Converte #U00XX (URL-encoded unicode em filenames) para caractere real.
    Ex: FUNCION#U00c1RIOS → FUNCIONÁRIOS"""
    return re.sub(
        r'#[Uu]([0-9a-fA-F]{4})',
        lambda m: chr(int(m.group(1), 16)),
        s
    )

def extract_group_id(stem: str) -> str | None:
    """
    Extrai a ENTIDADE do nome do arquivo.
    v1.4.0: remove tokens VENCIMENTO antes de processar.
    """
    # Normaliza unicode URL-encoded que pode vir do filesystem
    stem = _fix_url_unicode(stem)
    # Remove VENCIMENTO DD-MM-YYYY do stem (nao e parte da entidade)
    stem = RE_VENCIMENTO.sub("", stem).strip()
    # Normaliza espaços inconsistentes ao redor do separador " - "
    # Ex: "LACRES GOLD LTDA  - C" → "LACRES GOLD LTDA - C"  (não "LACRES GOLD LTDA - - C")
    # Ex: "AQUA  PURA - BOLETO"   → "AQUA PURA - BOLETO"    (não "AQUA - PURA - BOLETO")
    stem = re.sub(r'\s{2,}-\s*|\s*-\s{2,}', ' - ', stem)   # espaços em torno do traço
    stem = re.sub(r' {2,}', ' ', stem)                       # espaços duplos internos
    s    = RE_STRIP_C.sub("", stem).strip()
    s    = re.sub(r"(\w)-\s+(?=R?\$|\d)", r"\1 - ", s)
    parts = re.split(r"\s+-\s+", s)

    id_parts = []
    for p in parts:
        p = p.strip()
        if RE_VALUE.search(p): break
        if RE_PERIOD.match(p): break

        words = re.split(r"[\s.,;()+]+", p.lower())
        stop_idx = None
        for i, w in enumerate(words):
            if len(w) >= 2 and w in ENTITY_STOP:
                stop_idx = i
                break

        if stop_idx is not None:
            before = " ".join(w for w in words[:stop_idx] if w).strip()
            if before:
                id_parts.append(before.upper())
            break
        else:
            id_parts.append(p)

    raw  = " - ".join(id_parts).strip()
    segs = [s.strip() for s in raw.split(" - ")]
    segs = [s for s in segs if s and s != "-"]
    raw  = " - ".join(segs)
    result = normalize(raw)
    return result if result else normalize(parts[0].strip())


def extract_fingerprint(stem: str, content: str) -> set[str]:
    """
    Tokens de identidade para fuzzy match.
    v1.4.0: exclui tokens de data e valor (muito genericos).
    Foca em CNPJ, CPF, numeros de NF/boleto (8+ digitos), chaves NF-e.
    """
    tokens: set[str] = set()
    for src in [stem.lower(), content[:6000]]:
        for m in re.findall(r"\d{3}[.\s]?\d{3}[.\s]?\d{3}[-.\s]?\d{2}", src):
            d = RE_DIGITS_ONLY.sub("", m)
            if len(d) == 11: tokens.add("cpf:" + d)
        for m in re.findall(r"\d{2}[.\s]?\d{3}[.\s]?\d{3}[/\s]?\d{4}[-.\s]?\d{2}", src):
            d = RE_DIGITS_ONLY.sub("", m)
            if len(d) == 14: tokens.add("cnpj:" + d)
        for m in re.findall(r"\b\d{8,43}\b", src):
            tokens.add("num:" + m)
    for key in extract_nf_keys(content):
        tokens.add("nfkey:" + key)
    return tokens


# ── Classificacao de tipo ─────────────────────────────────────────────────────

_CONTENT_KW: dict[str, list[str]] = {
    "comprovante": [
        "comprovante de pagamento", "pagamento via pix", "pagamento efetuado",
        "transferencia realizada", "ted realizada", "doc realizado",
        "autenticacao bancaria", "recibo de pagamento", "pix efetuado",
        "dados da conta debitada",
    ],
    "boleto": [
        "boleto bancario", "nosso numero", "linha digitavel",
        "codigo de barras", "beneficiario", "titulo bancario",
    ],
    "nota": [
        "dacte", "documento auxiliar do ct-e", "conhecimento de transporte",
        "nfse", "nota fiscal de servicos", "danfe",
        "documento auxiliar da nota fiscal", "nota fiscal eletronica",
        "chave de acesso", "cfop", "cst", "nota fiscal", "ct-e",
        "fatura de servicos", "fatura",
    ],
}


def classify_by_content(text: str) -> str | None:
    if not text:
        return None
    for doc_type, keywords in _CONTENT_KW.items():
        if any(kw in text for kw in keywords):
            return doc_type
    return None


def classify_segment(segment: str | None) -> str | None:
    if not segment:
        return None
    s = segment.lower().strip()
    if s in SEG_MAP:
        return SEG_MAP[s]
    for word, tipo in SEG_MAP.items():
        # Usa word boundary flexivel: aceita separadores nao-alfanumericos
        # Ex: "gnre_-_167" nao casa com \bgnre\b (underscore eh word char)
        if re.search(r"(?<![a-zA-Z0-9])" + re.escape(word) + r"(?![a-zA-Z0-9])", s):
            return tipo
    return None  # Nenhum keyword reconhecido — deixa pipeline tentar ML/content


# ── Fase 1: coleta principal ──────────────────────────────────────────────────

def collect_all(
    folder: str,
    log_callback=None,
    cancel_flag=None,
) -> list[DocInfo]:
    files = sorted([
        f for f in os.listdir(folder)
        if f.lower().endswith(".pdf")
        and not f.upper().endswith("_AGRUPADO.PDF")
    ])
    total = len(files)
    docs: list[DocInfo] = []

    for idx, (raw_fname, fname) in enumerate(
        [(f, _fix_url_unicode(f)) for f in files], 1
    ):
        if cancel_flag and cancel_flag():
            return []
        path = os.path.join(folder, raw_fname)
        if log_callback:
            log_callback(f"  [{idx}/{total}] Lendo: {fname[:60]}")

        doc = DocInfo(path)
        doc.content, doc.pages = extract_text(path)

        stem_clean       = RE_STRIP_C.sub("", doc.stem).strip()
        doc.type_segment = extract_type_segment(doc.stem)
        doc.group_id     = extract_group_id(doc.stem)

        doc.value_raw, doc.value_digits = extract_value(stem_clean)
        if not doc.value_digits:
            doc.value_raw, doc.value_digits = extract_value(doc.content)

        doc.value_sec_raw, doc.value_sec_digits = extract_value_secondary(stem_clean)

        doc.all_value_digits = extract_all_values(stem_clean)
        if not doc.all_value_digits and doc.value_digits:
            doc.all_value_digits = [doc.value_digits]

        doc.installment = (extract_installment(stem_clean)
                           or extract_installment(doc.content[:2000]))

        doc.nf_keys      = extract_nf_keys(doc.content)
        # CNPJ: primeiro tenta extrair da chave NF-e (100% confiável),
        # depois faz fallback para regex no conteúdo
        _cnpj_from_key = next(
            (cnpj_from_nfe_key(k) for k in doc.nf_keys if cnpj_from_nfe_key(k)),
            None
        )
        doc.cnpj_emitter = _cnpj_from_key or extract_cnpj(doc.content[:4000])
        # Enriquece entity_name via cache CNPJ (background, sem bloquear)
        if doc.cnpj_emitter and _CNPJ_CACHE_OK and not doc.group_id:
            def _cb(result, d=doc):
                if result and result.get("nome"):
                    d.group_id = result["nome"][:60]
            try: _lookup_cnpj_async(doc.cnpj_emitter, _cb)
            except Exception: pass
        doc.due_dates    = extract_due_dates(doc.content)
        doc.doc_numbers  = extract_doc_numbers(doc.stem, doc.content)
        doc.period       = extract_period(stem_clean, doc.content)
        doc.fingerprint  = extract_fingerprint(doc.stem, doc.content)

        # v1.4.0 — SimHash e content_type
        doc.simhash      = simhash(doc.content[:8000]) if doc.content else 0
        doc.content_type = detect_content_type(doc.content)
        # Pagamentos diretos (PIX/TED/transferencia) nao precisam de boleto
        doc.is_direct    = doc.content_type in ("pix", "ted", "transferencia")

        # v1.7.0 — GNRE: substitui value_digits pelo "Total a Recolher"
        # O valor principal da GNRE nao inclui juros/multa, mas o comprovante
        # bancario registra o valor pago (total) como "Valor principal".
        # Sem esse override os dois docs ficam com valores diferentes e nao agrupam.
        if doc.content_type == "gnre" and doc.content:
            _gnre_raw, _gnre_digits = extract_gnre_total(doc.content)
            if _gnre_digits:
                doc.value_raw, doc.value_digits = _gnre_raw, _gnre_digits

        # v1.6.0 — classificação híbrida: regras + ML
        # Prioridade: sufixo -C no nome > GNRE (content_type) > segmento do nome > ML sobre conteúdo
        _ml_type, _ml_conf = classify(doc.content[:3000]) if doc.content else ("desconhecido", 0.0)
        doc.doc_type = (
            ("comprovante" if doc.suffix_c else None)
            or ("gnre" if doc.content_type == "gnre" else None)  # GNRE antes do ML — evita "nota"
            or classify_segment(doc.type_segment)
            or classify_segment(doc.stem)
            or (_ml_type if _ml_type != "desconhecido" and _ml_conf >= 0.50 else None)
            or classify_by_content(doc.content)
        )
        # v1.7.0 — PIX key e bank code (APÓS classificação — doc_type já definido)
        if doc.doc_type == "comprovante" and doc.content:
            doc.pix_key = extract_pix_key(doc.content)
        if doc.doc_type == "boleto":
            doc.bank_code = extract_bank_code(doc.content)
            # Extração estruturada via pdfplumber (só boletos, após classificar)
            import warnings as _w
            with _w.catch_warnings():
                _w.simplefilter("ignore")
                _bf = extract_boleto_fields(path)
            if _bf:
                if not doc.cnpj_emitter and _bf.get("cnpj_cedente"):
                    doc.cnpj_emitter = _bf["cnpj_cedente"]
                doc.cnpj_sacado = _bf.get("cnpj_sacado")
                if not doc.boleto_id:
                    doc.boleto_id = _bf.get("nosso_numero")
                if not doc.value_digits and _bf.get("valor_doc"):
                    doc.value_digits = _bf["valor_doc"]
                if not doc.period and _bf.get("vencimento"):
                    doc.period = _bf["vencimento"]

        if log_callback:
            sec  = f"  sec={doc.value_sec_raw}"  if doc.value_sec_raw  else ""
            inst = f"  parc={doc.installment}"   if doc.installment    else ""
            ct   = f"  ct={doc.content_type}"    if doc.content_type   else ""
            log_callback(
                f"    -> gid={doc.group_id!r}  tipo={doc.doc_type or '?'}  "
                f"val={doc.value_raw or '-'}{sec}{inst}{ct}  pgs={doc.pages}"
            )

        docs.append(doc)

    return docs
