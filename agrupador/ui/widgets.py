"""
ui/widgets.py — Componentes visuais AgrupadorPDF v1.6.3
Design System: Neobrutalista — Branco / Cinza / Azul Capri
"""
import tkinter as tk
from tkinter import ttk

from ..config import (
    VERSION,
    BG, SURFACE, CARD, CARD2, BORDER, BORDER2,
    ACC, ACC2, ACC3, ACC_GLOW, ACCDIM, FG, MUTED, SUBTLE,
    ELEV_1, ELEV_2,
    FONT_HERO, FONT_TITLE, FONT_HEADING, FONT_LABEL, FONT_LABEL_S,
    FONT_BODY, FONT_BODY_S, FONT_HINT, FONT_MONO, FONT_BADGE, FONT_NUM,
    SP_4, SP_6, SP_8, SP_10, SP_12, SP_14, SP_16,
    HEIGHT_INPUT, R_SM, R_MD, R_LG,
    DANGER, DANGER_BG, WARN, WARN_BG,
)


def draw_rounded_rect(canvas, x1, y1, x2, y2, r=0, **kw):
    """Retangulo. r ignorado no estilo brutalista (sem arredondamento)."""
    return canvas.create_rectangle(x1, y1, x2, y2, **kw)


def _hex_adjust(hex_c, delta):
    r, g, b = int(hex_c[1:3],16), int(hex_c[3:5],16), int(hex_c[5:7],16)
    clamp = lambda v: max(0, min(255, int(v)))
    if delta < 0:
        f = 1 + delta
        r, g, b = clamp(r*f), clamp(g*f), clamp(b*f)
    else:
        r = clamp(r + (255-r)*delta)
        g = clamp(g + (255-g)*delta)
        b = clamp(b + (255-b)*delta)
    return f"#{r:02x}{g:02x}{b:02x}"


class FlatButton(tk.Canvas):
    """Botao neobrutalista. Borda cinza escura, sombra hard offset."""

    def __init__(self, parent, text, command=None, *,
                 bg=CARD, fg=FG, font=FONT_BODY,
                 padx=SP_14, pady=SP_8,
                 accent=False, danger=False,
                 radius=0, full_width=False,
                 parent_bg=BG, **kw):
        super().__init__(parent, bg=parent_bg, highlightthickness=0, **kw)
        self._text    = text
        self._cmd     = command
        self._accent  = accent
        self._danger  = danger
        self._font    = font
        self._padx    = padx
        self._pady    = pady
        self._pbg     = parent_bg
        self._pressed = False
        self._hover   = False
        self._enabled = True

        if accent:
            self._bg = ACC
            self._fg = FG          # cinza escuro legivel sobre capri
        elif danger:
            self._bg = DANGER_BG
            self._fg = DANGER
        else:
            self._bg = bg
            self._fg = fg

        tmp = tk.Label(font=font, text=text)
        w = tmp.winfo_reqwidth() + padx * 2 + 6
        h = tmp.winfo_reqheight() + pady * 2 + 4
        self.config(width=w, height=h)
        self.bind("<Configure>",       lambda _e: self._draw())
        self.bind("<ButtonPress-1>",   self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>",           self._on_enter)
        self.bind("<Leave>",           self._on_leave)
        self.config(cursor="hand2")

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4: return

        # Cores por estado
        if not self._enabled:
            fill = ELEV_2
            text_c = SUBTLE
            border = BORDER2
            sh_off = 2
        elif self._pressed:
            fill = ACC2 if self._accent else ELEV_1
            text_c = "#FFFFFF" if self._accent else self._fg
            border = BORDER
            sh_off = 0
        elif self._hover:
            fill = ACC2 if self._accent else ELEV_1
            text_c = "#FFFFFF" if self._accent else self._fg
            border = BORDER
            sh_off = 3
        else:
            fill = self._bg
            text_c = self._fg
            border = BORDER
            sh_off = 3

        # Sombra hard offset (brutalista)
        if sh_off > 0 and self._enabled:
            self.create_rectangle(sh_off, sh_off, w-1+sh_off, h-1+sh_off,
                                  fill=BORDER, outline="")

        # Corpo do botao
        self.create_rectangle(0, 0, w-1-sh_off, h-1-sh_off,
                              fill=fill, outline=border, width=2)

        # Texto
        ox = -sh_off//2 if self._pressed else 0
        oy = -sh_off//2 if self._pressed else 0
        cx = (w - sh_off) // 2 + ox
        cy = (h - sh_off) // 2 + oy
        self.create_text(cx, cy, text=self._text,
                         font=self._font, fill=text_c, anchor="center")

    def _on_press(self, _e):
        if not self._enabled: return
        self._pressed = True; self._draw()

    def _on_release(self, _e):
        if not self._enabled: return
        self._pressed = False; self._hover = True; self._draw()
        if self._cmd:
            try: self._cmd()
            except Exception: pass

    def _on_enter(self, _e):
        if not self._enabled: return
        self._hover = True; self._draw()

    def _on_leave(self, _e):
        self._hover = False; self._pressed = False; self._draw()

    def configure(self, **kw):
        if "state" in kw:
            s = kw.pop("state")
            self._enabled = (s == "normal")
            self.config(cursor="hand2" if self._enabled else "")
            self._draw()
        if "text" in kw:
            self._text = kw.pop("text")
            self._draw()
        super().configure(**kw)


# Alias
SinkButton = FlatButton


class RoundCard(tk.Frame):
    """Card com borda cinza — sem arredondamento no estilo brutalista."""
    def __init__(self, parent, *, bg_card=CARD, bg_parent=BG,
                 radius=0, shadow=False, height=None,
                 accent_top=False, **kw):
        super().__init__(parent, bg=bg_card,
                         highlightbackground=BORDER, highlightthickness=2, **kw)
        if height: self.config(height=height)
        if accent_top:
            tk.Frame(self, bg=ACC, height=3).pack(fill="x", side="top")
        self.inner = tk.Frame(self, bg=bg_card)
        self.inner.pack(fill="both", expand=True, padx=SP_12, pady=SP_10)


class AccentCard(tk.Frame):
    def __init__(self, parent, *, bg_card=CARD, bg_parent=BG,
                 padx=SP_12, pady=SP_10, accent_left=True, **kw):
        super().__init__(parent, bg=bg_card,
                         highlightbackground=BORDER, highlightthickness=2, **kw)
        if accent_left:
            tk.Frame(self, bg=ACC, width=4).pack(fill="y", side="left")
        self.inner = tk.Frame(self, bg=bg_card)
        self.inner.pack(fill="both", expand=True, padx=padx, pady=pady)


class FocusEntry(tk.Entry):
    def __init__(self, parent, textvariable=None, placeholder="", **kw):
        kw.setdefault("bg",                 CARD2)
        kw.setdefault("fg",                 FG)
        kw.setdefault("insertbackground",   ACC)
        kw.setdefault("relief",             "flat")
        kw.setdefault("font",               FONT_MONO)
        kw.setdefault("highlightthickness", 2)
        kw.setdefault("highlightbackground", BORDER)
        kw.setdefault("highlightcolor",     ACC)
        kw.setdefault("bd",                 0)
        super().__init__(parent, textvariable=textvariable, **kw)


class ProgressBar(tk.Canvas):
    def __init__(self, parent, *, height=10, bg_fill=ACC,
                 bg_parent=CARD, radius=0, **kw):
        super().__init__(parent, height=height,
                         bg=ELEV_2, highlightthickness=2,
                         highlightbackground=BORDER, **kw)
        self._fill = bg_fill
        self._value = 0.0
        self.bind("<Configure>", self._draw)

    def set(self, value, maximum=100):
        self._value = min(1.0, value / max(maximum, 1))
        self._draw()

    def _draw(self, _e=None):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4: return
        fw = int(w * self._value)
        if fw > 1:
            self.create_rectangle(0, 0, fw, h, fill=self._fill, outline="")


class FolderRow(tk.Frame):
    """Linha de selecao de pasta com label, campo mono e botao capri."""
    def __init__(self, parent, label, textvariable, on_browse, *,
                 show_dnd_hint=False, parent_bg=BG, **kw):
        super().__init__(parent, bg=parent_bg, **kw)
        self._var = textvariable

        # Label superior
        lbl_row = tk.Frame(self, bg=parent_bg)
        lbl_row.pack(fill="x", pady=(0, SP_4))
        tk.Label(lbl_row, text=label.upper(),
                 font=FONT_LABEL_S, bg=parent_bg, fg=MUTED).pack(side="left")
        if show_dnd_hint:
            tk.Label(lbl_row, text="arraste a pasta para o campo abaixo",
                     font=FONT_HINT, bg=parent_bg, fg=SUBTLE).pack(side="right")

        # Linha: campo + botao
        row = tk.Frame(self, bg=parent_bg)
        row.pack(fill="x")

        # Frame de borda unica ao redor do conjunto campo+botao
        wrap = tk.Frame(row, bg=BORDER, padx=2, pady=2)
        wrap.pack(fill="x", expand=True)

        inner = tk.Frame(wrap, bg=parent_bg)
        inner.pack(fill="x")

        self._entry = tk.Entry(inner, textvariable=textvariable,
                               font=FONT_MONO, bg=CARD2, fg=FG,
                               insertbackground=ACC, relief="flat",
                               highlightthickness=0, bd=0)
        self._entry.pack(side="left", fill="x", expand=True, ipady=SP_8)

        # Separador vertical
        tk.Frame(inner, bg=BORDER, width=2).pack(side="left", fill="y")

        # Botao selecionar — capri
        btn_f = tk.Frame(inner, bg=ACC, cursor="hand2")
        btn_f.pack(side="left")
        btn_lbl = tk.Label(btn_f, text="Selecionar",
                           font=FONT_LABEL, bg=ACC, fg=SURFACE,
                           padx=SP_12, pady=SP_8, cursor="hand2")
        btn_lbl.pack()
        for w in (btn_f, btn_lbl):
            w.bind("<Button-1>", lambda _e: on_browse())
            w.bind("<Enter>",    lambda _e, f=btn_f, l=btn_lbl: (
                f.config(bg=ACC2), l.config(bg=ACC2)))
            w.bind("<Leave>",    lambda _e, f=btn_f, l=btn_lbl: (
                f.config(bg=ACC),  l.config(bg=ACC)))

    def register_drop(self, callback):
        try:
            self._entry.drop_target_register("DND_Files")
            self._entry.dnd_bind("<<Drop>>",
                lambda e: callback(e.data.strip("{}")))
        except Exception:
            pass


class Tooltip(tk.Toplevel):
    _LINES = [
        f"AgrupadorPDF  v{VERSION}",
        "─" * 28,
        "Agrupa boletos, comprovantes e",
        "notas fiscais automaticamente.",
        "",
        "Drag-and-drop nas pastas.",
        "Score 0-100% por grupo.",
    ]

    def __init__(self, widget):
        super().__init__(widget)
        self.withdraw()
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.config(bg=BORDER)
        inner = tk.Frame(self, bg=SURFACE)
        inner.pack(fill="both", expand=True, padx=2, pady=2)
        pad = tk.Frame(inner, bg=SURFACE)
        pad.pack(fill="both", expand=True, padx=SP_12, pady=SP_10)
        for line in self._LINES:
            c = SUBTLE if "─" in line else (ACC2 if "AgrupadorPDF" in line else FG)
            fnt = FONT_HINT if (not line or "─" in line) else FONT_BODY
            tk.Label(pad, text=line, font=fnt, bg=SURFACE, fg=c,
                     anchor="w").pack(anchor="w")
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, e):
        x = e.widget.winfo_rootx() - 200
        y = e.widget.winfo_rooty() + 30
        self.geometry(f"+{x}+{y}")
        self.deiconify()

    def _hide(self, _e):
        self.withdraw()


def apply_ttk_style():
    s = ttk.Style()
    try: s.theme_use("clam")
    except Exception: pass
    s.configure("Vertical.TScrollbar",
                 troughcolor=ELEV_2, background=BORDER,
                 arrowcolor=MUTED, bordercolor=BORDER2,
                 relief="flat", width=8)
    s.map("Vertical.TScrollbar", background=[("active", ACC2)])
