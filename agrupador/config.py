"""
config.py — Design System, constantes globais e regex compilados.
"""
import os, sys, re

def _bundled(r):
    base = getattr(sys,"_MEIPASS",os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base,r)

_TESS_EXE = _bundled(os.path.join("tesseract","tesseract.exe"))
_POPPLER   = _bundled(os.path.join("poppler","Library","bin"))

try:
    import pytesseract
    from pdf2image import convert_from_path as _pdf2img
    if os.path.isfile(_TESS_EXE): pytesseract.pytesseract.tesseract_cmd=_TESS_EXE
    OCR_AVAILABLE=True; convert_from_path=_pdf2img
except ImportError:
    OCR_AVAILABLE=False; pytesseract=None; convert_from_path=None

if os.path.isdir(_POPPLER) and _POPPLER not in os.environ.get("PATH",""):
    os.environ["PATH"]=_POPPLER+os.pathsep+os.environ.get("PATH","")

if sys.platform=="win32":
    import subprocess as _sp
    _Po=_sp.Popen.__init__
    def _pnw(self,*a,**k):
        k.setdefault("creationflags",0); k["creationflags"]|=0x08000000
        si=k.get("startupinfo") or _sp.STARTUPINFO()
        si.dwFlags|=_sp.STARTF_USESHOWWINDOW; si.wShowWindow=0
        k["startupinfo"]=si; _Po(self,*a,**k)
    _sp.Popen.__init__=_pnw

# ── Versao ────────────────────────────────────────────────────────────────────
VERSION        = "1.6.0"
ORDER_MERGE    = ["comprovante","boleto","nota"]
MIN_TEXT_CHARS = 80
NF_KEY_LEN     = 44

# ── SimHash ───────────────────────────────────────────────────────────────────
SIMHASH_BITS          = 64   # bits do fingerprint
SIMHASH_DUP_THRESHOLD = 0    # Hamming == 0 = conteudo identico (duplicata exata)
SIMHASH_NEAR_THRESHOLD = 3    # Hamming <= 3 + mesmo grupo/valor = quase-duplicata
SIMHASH_SIM_THRESHOLD  = 14   # Hamming <= 14 = muito similar (referencia futura)

# ── Vocabulario ───────────────────────────────────────────────────────────────
TYPE_GROUPS: dict[str,list[str]] = {
    "comprovante": ["comp","comprov","comprovante","pag","pago","pagamento",
                    "pix","ted","transf","transferencia","qit","autent"],
    "boleto":      ["bol","blt","boleto","ban","cob","cobr","tit","titulo",
                    "linha","carne"],
    "nota":        ["nf","nfe","nfs","nfse","nf-e","nfs-e","fat","fatura",
                    "faturamento","cte","ct-e","cte-e","dacte","dacte-e",
                    "danfe","nota","fiscal","rpa","recibo_fiscal","serv",
                    "servico","relatorio","relacao"],
    "gnre":        ["gnre","estado"],   # "ESTADO DE XX" → sempre GNRE
}
SEG_MAP: dict[str,str] = {w:t for t,ws in TYPE_GROUPS.items() for w in ws}

ENTITY_STOP: frozenset = frozenset({
    "comp","comprov","comprovante","pix","ted","transf","transferencia","qit","autent",
    "bol","blt","boleto","cob","cobr","tit","titulo","guia","carne",
    "nf","nfe","nfs","nfse","fat","fatura","faturamento",
    "cte","dacte","danfe","fiscal","rpa",
    "relacao","relatorio",
    "vencimento","vence","vencimneto",
})

FUNC_DESCRIPTORS: frozenset = frozenset({
    "funcionarios","rescisao","ferias","fgts","calculo","benef","beneficio",
    "relacao","relatorio","folha","holerite","contracheque","salario",
    "remuneracao","inss","irrf","crf","darf","vencimento","vence","base",
    "plano","adiantamento","abono","bonus","aluguel","telefonia","pedagio","reembolso",
})

# Sufixos legais que NAO distinguem fornecedores — removidos antes do fuzzy match
LEGAL_SUFFIXES: frozenset = frozenset({
    "ltda","sa","s/a","me","eireli","epp","ss","comercio","servicos",
    "industria","transportes","logistica","express","solucoes","e","do","da","de",
})

# ── Regex ─────────────────────────────────────────────────────────────────────
RE_VALUE      = re.compile(r"R?\$\s*([\d.,]+)", re.IGNORECASE)
RE_VALUE_SEC  = re.compile(r"\(R?\$\s*([\d.,]+)\)", re.IGNORECASE)
RE_PERIOD     = re.compile(
    r"(janeiro|fevereiro|mar[cç]o|abril|maio|junho|"
    r"julho|agosto|setembro|outubro|novembro|dezembro)[.\s]?(\d{2,4})"
    r"|(?<!\d)(0?[1-9]|1[0-2])/(20\d{2}|\d{2})(?!\d)", re.IGNORECASE)

# Datas de vencimento no nome: VENCIMENTO DD-MM-YYYY ou VENCIMNETO (typo)
RE_VENCIMENTO = re.compile(
    r"\bvenc(?:imento|imneto|e)?\s*(\d{2})[-./](\d{2})[-./](\d{4})\b",
    re.IGNORECASE)

RE_INSTALLMENT = re.compile(
    r"parc(?:ela)?\s*[:\s]?(\d{1,2})\s*(?:[/\-]\s*|de\s*)(\d{1,2})"
    r"|(\d{1,2})\s*/\s*(\d{1,2})\s*parc(?:ela)?"
    r"|(\d{1,2})[a\xaa]\s*(?:de\s*)?(\d{1,2})\s*parc(?:ela)?",
    re.IGNORECASE)

RE_NF_KEY      = re.compile(r"\b(\d{44})\b")
RE_CNPJ        = re.compile(
    r"\b(\d{2})[.\s]?(\d{3})[.\s]?(\d{3})[/\s]?(\d{4})[-\s]?(\d{2})\b")
RE_DUE_DATE    = re.compile(
    r"venc(?:imento|e)?\W{0,4}(\d{2})[/.\-](\d{2})[/.\-](\d{4})"
    r"|(\d{2})[/.\-](\d{2})[/.\-](\d{4})\W{0,6}venc", re.IGNORECASE)
RE_COMP_C      = re.compile(
    r"(?:(?:^|\s+-\s+)C(?:\s+-\s+|\s*-\s*(?=\d|R?\$)|$))"
    r"|(?:\s*-\s*C$)", re.IGNORECASE)
RE_STRIP_C     = re.compile(
    r"\s+-\s+C(?=\s+-|\s*-\s*(?=\d|R?\$))"
    r"|\s*-\s*C\s*-\s*(?=\d|R?\$)"
    r"|\s*-\s*C\s*$", re.IGNORECASE)
RE_DIGITS_ONLY = re.compile(r"[^\d]")
RE_DOC_NUMBER  = re.compile(
    r"\b(?:nf|nfe|nfs|nfse|cte|ct-e|bol)\s*[:\s]?\s*(\d{3,10})\b",
    re.IGNORECASE)

# ── Design System v1.6.0 — Dark Precision ────────────────────────────────────
# Paleta: carvão profundo + marfim + laranja âmbar como único acento
# Tipografia: Consolas mono para dados, Segoe UI Light para texto
BG="#111418";SURFACE="#1a1e24";SURF2="#20252d";CARD="#1e232b";CARD2="#252b35"
BORDER="#2e3542";BORDER2="#3a4455"
ACC="#e8924a";ACC2="#d07a35";ACC3="#b86420";ACC_GLOW="#f0a060";ACCDIM="#3a2410"
FG="#e8e2d9";MUTED="#7a8494";SUBTLE="#4a5568"
SUCCESS="#4caf7d";SUCCESS_BG="#0d2318";WARN="#e8b84a";WARN_BG="#241a08"
DANGER="#e05555";DANGER_BG="#2a0e0e";INFO_BG="#131c28"
ELEV_1="#232931";ELEV_2="#2a3040";ELEV_3="#313850"
FONT_HERO=("Segoe UI Light",20);FONT_TITLE=("Segoe UI Semibold",11)
FONT_HEADING=("Segoe UI",10);FONT_LABEL=("Segoe UI",8)
FONT_LABEL_S=("Segoe UI",7);FONT_BODY=("Segoe UI",9)
FONT_BODY_S=("Segoe UI",8);FONT_HINT=("Segoe UI",7);FONT_MONO=("Consolas",9)
FONT_BADGE=("Consolas",9);FONT_NUM=("Segoe UI Light",24)
SP_2=2;SP_4=4;SP_6=6;SP_8=8;SP_10=10
SP_12=12;SP_14=14;SP_16=16;SP_20=20;SP_24=24;SP_32=32
HEIGHT_INPUT=34;HEIGHT_BTN_SM=34;HEIGHT_BTN_LG=48;HEIGHT_PROG=60
R_SM=4;R_MD=6;R_LG=10
