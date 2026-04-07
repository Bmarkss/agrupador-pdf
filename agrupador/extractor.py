"""
extractor.py — Fase 1: leitura, extracao e classificacao de PDFs.

v1.4.0:
  - compute_simhash() para deteccao de duplicatas
  - detect_content_type() — 'pix','ted','transferencia','gnre'
  - extract_period() tambem detecta datas VENCIMENTO DD-MM-YYYY do nome
  - extract_group_id() remove tokens de VENCIMENTO do gid
"""

import os, re
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
    from pypdf import PdfReader
except ImportError:
    from PyPDF2 import PdfReader


# ── Extracao de texto ─────────────────────────────────────────────────────────

def extract_text(path: str) -> tuple[str, int]:
    text = ""; pages = 1
    try:
        reader = PdfReader(path)
        pages  = len(reader.pages)
        text   = " ".join(p.extract_text() or "" for p in reader.pages).strip()
    except Exception:
        pass
    if len(text) >= MIN_TEXT_CHARS:
        return text.lower(), pages
    if OCR_AVAILABLE:
        try:
            kw = {"poppler_path": _POPPLER} if os.path.isdir(_POPPLER) else {}
            imgs  = convert_from_path(path, dpi=200, **kw)
            pages = len(imgs)
            text  = " ".join(pytesseract.image_to_string(i, lang="por") for i in imgs).strip()
        except Exception:
            pass
    return text.lower(), pages


# ── Deteccao de tipo de pagamento pelo conteudo ───────────────────────────────

_CONTENT_TYPE_KW: dict[str, list[str]] = {
    "pix":           ["pagamento via pix", "pix efetuado", "transferencia pix",
                      "chave pix", "qr code pix", "tipo de pagamento: pix"],
    "ted":           ["ted realizada", "ted efetuada", "transferencia ted",
                      "tipo ted", "transferencia entre bancos"],
    "transferencia": ["comprovante de transferencia", "transferencia realizada",
                      "transferencia entre contas", "dados da conta debitada"],
    "gnre":          ["guia nacional de recolhimento", "gnre", "receita estadual",
                      "sefaz", "codigo de receita gnre"],
    "boleto_pago":   ["comprovante de pagamento de boleto", "boleto pago",
                      "codigo de barras", "nosso numero", "linha digitavel"],
}

def detect_content_type(text: str) -> str | None:
    """
    Detecta o tipo especifico de pagamento pelo conteudo do PDF.
    Retorna: 'pix', 'ted', 'transferencia', 'gnre', 'boleto_pago', ou None.
    Prioridade: tipos mais especificos primeiro.
    """
    if not text:
        return None
    for ctype in ("pix", "ted", "gnre", "boleto_pago", "transferencia"):
        if any(kw in text for kw in _CONTENT_TYPE_KW[ctype]):
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


def extract_group_id(stem: str) -> str | None:
    """
    Extrai a ENTIDADE do nome do arquivo.
    v1.4.0: remove tokens VENCIMENTO antes de processar.
    """
    # Remove VENCIMENTO DD-MM-YYYY do stem (nao e parte da entidade)
    stem = RE_VENCIMENTO.sub("", stem).strip()
    stem = re.sub(r"  +", " - ", stem)
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
        if re.search(r"\b" + re.escape(word) + r"\b", s):
            return tipo
    return "nota"


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

    for idx, fname in enumerate(files, 1):
        if cancel_flag and cancel_flag():
            return []
        path = os.path.join(folder, fname)
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
        doc.due_dates    = extract_due_dates(doc.content)
        doc.doc_numbers  = extract_doc_numbers(doc.stem, doc.content)
        doc.period       = extract_period(stem_clean, doc.content)
        doc.fingerprint  = extract_fingerprint(doc.stem, doc.content)

        # v1.4.0 — SimHash e content_type
        doc.simhash      = simhash(doc.content[:8000]) if doc.content else 0
        doc.content_type = detect_content_type(doc.content)
        # Pagamentos diretos (PIX/TED/transferencia) nao precisam de boleto
        doc.is_direct    = doc.content_type in ("pix", "ted", "transferencia")

        # v1.6.0 — classificação híbrida: regras + ML
        # Prioridade: sufixo -C no nome > segmento do nome > ML sobre conteúdo
        _ml_type, _ml_conf = classify(doc.content[:3000]) if doc.content else ("desconhecido", 0.0)
        doc.doc_type = (
            ("comprovante" if doc.suffix_c else None)
            or classify_segment(doc.type_segment)
            or classify_segment(doc.stem)
            or (_ml_type if _ml_type != "desconhecido" and _ml_conf >= 0.50 else None)
            or classify_by_content(doc.content)
        )

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
