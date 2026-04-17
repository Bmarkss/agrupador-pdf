"""
config.py — Design System, constantes globais e regex compilados.
v1.6.2 — Neobrutalista: Branco / Cinza / Azul Capri
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

# ── Versao ─────────────────────────────────────────────────────────────────────
VERSION        = "1.6.6"
ORDER_MERGE    = ["comprovante","gnre","boleto","nota"]
MIN_TEXT_CHARS = 80
NF_KEY_LEN     = 44

# ── SimHash ────────────────────────────────────────────────────────────────────
SIMHASH_BITS           = 64
SIMHASH_DUP_THRESHOLD  = 0
SIMHASH_NEAR_THRESHOLD = 3
SIMHASH_SIM_THRESHOLD  = 14

# ── Vocabulario ────────────────────────────────────────────────────────────────
TYPE_GROUPS: dict[str,list[str]] = {
    "comprovante": ["comp","comprov","comprovante","pag","pago","pagamento",
                    "pix","ted","transf","transferencia","qit","autent"],
    "boleto":      ["bol","blt","boleto","ban","cob","cobr","tit","titulo",
                    "linha","carne"],
    "nota":        ["nf","nfe","nfs","nfse","nf-e","nfs-e","fat","fatura",
                    "faturamento","cte","ct-e","cte-e","dacte","dacte-e",
                    "danfe","nota","fiscal","rpa","recibo_fiscal","serv",
                    "servico","relatorio","relacao"],
    "gnre":        ["gnre","estado"],
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

LEGAL_SUFFIXES: frozenset = frozenset({
    "ltda","sa","s/a","me","eireli","epp","ss","comercio","servicos",
    "industria","transportes","logistica","express","solucoes","e","do","da","de",
})

# ── Regex ──────────────────────────────────────────────────────────────────────
RE_VALUE      = re.compile(r"R?\$\s*([\d.,]+)", re.IGNORECASE)
RE_VALUE_SEC  = re.compile(r"\(R?\$\s*([\d.,]+)\)", re.IGNORECASE)
RE_PERIOD     = re.compile(
    r"(janeiro|fevereiro|mar[cç]o|abril|maio|junho|"
    r"julho|agosto|setembro|outubro|novembro|dezembro)[.\s]?(\d{2,4})"
    r"|(?<!\d)(0?[1-9]|1[0-2])/(20\d{2}|\d{2})(?!\d)", re.IGNORECASE)
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
    r"(?:(?:^|[\s_]+-[\s_]+)C(?:[\s_]+-[\s_]+|[\s_]*-[\s_]*(?=\d|R?\$)|$))"
    r"|(?:[\s_]*-[\s_]*C$)", re.IGNORECASE)
RE_STRIP_C     = re.compile(
    r"[\s_]+-[\s_]+C(?=[\s_]+-|[\s_]*-[\s_]*(?=\d|R?\$))"
    r"|[\s_]*-[\s_]*C[\s_]*-[\s_]*(?=\d|R?\$)"
    r"|[\s_]*-[\s_]*C[\s_]*$", re.IGNORECASE)
RE_DIGITS_ONLY = re.compile(r"[^\d]")
RE_DOC_NUMBER  = re.compile(
    r"\b(?:nf|nfe|nfs|nfse|cte|ct-e|bol)\s*[:\s]?\s*(\d{3,10})\b",
    re.IGNORECASE)

# ── Design System v1.6.2 — Neobrutalista: Branco / Cinza / Azul Capri ─────────
# Sem preto como cor de fundo. Bordas e sombras em cinza escuro.
# Acento unico: Azul Capri (#00BFFF).

# Backgrounds
BG       = "#F4F4F4"   # cinza muito claro — fundo geral
SURFACE  = "#FFFFFF"   # branco puro — superficies principais
SURF2    = "#EEEEEE"   # cinza leve — faixas secundarias
CARD     = "#FFFFFF"   # branco — cards
CARD2    = "#F0F0F0"   # cinza clarinho — cards internos / log

# Bordas
BORDER   = "#999999"   # cinza medio — borda padrao
BORDER2  = "#CCCCCC"   # cinza claro — borda suave

# Acento — Azul Capri
ACC      = "#00BFFF"   # capri principal
ACC2     = "#009ACC"   # capri escuro (hover)
ACC3     = "#007AAA"   # capri mais escuro
ACC_GLOW = "#33CFFF"   # capri claro (cursor)
ACCDIM   = "#E0F7FF"   # capri muito claro (fundo selecionado)

# Texto
FG       = "#222222"   # cinza muito escuro — texto principal
MUTED    = "#666666"   # cinza medio — texto secundario
SUBTLE   = "#999999"   # cinza claro — dicas / labels

# Semanticos
SUCCESS    = "#007A99"   # capri escuro — sucesso
SUCCESS_BG = "#E0F7FF"   # capri muito claro — fundo sucesso
WARN       = "#555555"   # cinza escuro — aviso (sem amarelo)
WARN_BG    = "#E8E8E8"   # cinza claro — fundo aviso
DANGER     = "#CC3333"   # vermelho moderado — erro
DANGER_BG  = "#FFE8E8"   # vermelho muito claro — fundo erro
INFO_BG    = "#E0F7FF"   # capri muito claro — info

# Elevacao (botoes, cards)
ELEV_1   = "#EBEBEB"
ELEV_2   = "#E2E2E2"
ELEV_3   = "#D8D8D8"

# Tipografia — Segoe UI para interface
FONT_HERO    = ("Segoe UI",    18, "bold")
FONT_TITLE   = ("Segoe UI",    11, "bold")
FONT_HEADING = ("Segoe UI",    10)
FONT_LABEL   = ("Segoe UI",     8, "bold")
FONT_LABEL_S = ("Segoe UI",     7, "bold")
FONT_BODY    = ("Segoe UI",     9)
FONT_BODY_S  = ("Segoe UI",     8)
FONT_HINT    = ("Segoe UI",     7)
FONT_MONO    = ("Consolas",     9)
FONT_BADGE   = ("Segoe UI",     9, "bold")
FONT_NUM     = ("Segoe UI",    24, "bold")

# Espacamento
SP_2=2; SP_4=4; SP_6=6; SP_8=8; SP_10=10
SP_12=12; SP_14=14; SP_16=16; SP_20=20; SP_24=24; SP_32=32

# Dimensoes
HEIGHT_INPUT  = 34
HEIGHT_BTN_SM = 34
HEIGHT_BTN_LG = 48
HEIGHT_PROG   = 60
R_SM=0; R_MD=0; R_LG=0   # Neobrutalista: zero arredondamento
