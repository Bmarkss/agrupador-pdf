"""
ui/widgets.py — Componentes visuais AgrupadorPDF v1.6.2
Design System: Dark Precision
  - Paleta carvão profundo + âmbar como acento único
  - Tipografia Segoe UI Light / Consolas
  - Bordas sutis, zero ornamentos
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
)


def draw_rounded_rect(canvas, x1, y1, x2, y2, r=R_MD, **kw):
    pts = [
        x1+r, y1,  x2-r, y1,  x2, y1,    x2, y1+r,
        x2, y2-r,  x2, y2,    x2-r, y2,  x1+r, y2,
        x1, y2,    x1, y2-r,  x1, y1+r,  x1, y1,  x1+r, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


def _hex_adjust(hex_c, delta):
    r,g,b = int(hex_c[1:3],16),int(hex_c[3:5],16),int(hex_c[5:7],16)
    clamp = lambda v: max(0,min(255,int(v)))
    if delta < 0:
        f = 1+delta
        r,g,b = clamp(r*f),clamp(g*f),clamp(b*f)
    else:
        r = clamp(r+(255-r)*delta)
        g = clamp(g+(255-g)*delta)
        b = clamp(b+(255-b)*delta)
    return f"#{r:02x}{g:02x}{b:02x}"


class FlatButton(tk.Canvas):
    """Botão flat escuro. Borda âmbar no hover, sem sombra 3D."""

    def __init__(self, parent, text, command=None, *,
                 bg=CARD, fg=FG, font=FONT_BODY,
                 padx=SP_14, pady=SP_8,
                 accent=False, danger=False,
                 radius=R_SM, full_width=False,
                 parent_bg=BG, **kw):
        super().__init__(parent, bg=parent_bg, highlightthickness=0, **kw)
        self._text = text; self._cmd = command
        self._bg = ACC if accent else bg
        self._fg = "#111418" if accent else fg
        self._font = font; self._padx = padx; self._pady = pady
        self._radius = radius; self._accent = accent; self._danger = danger
        self._pbg = parent_bg
        tmp = tk.Label(font=font, text=text)
        w = tmp.winfo_reqwidth() + padx*2
        h = tmp.winfo_reqheight() + pady*2
        self.config(width=w, height=h)
        self.bind("<Configure>", self._draw)
        self.bind("<ButtonPress-1>",   lambda _e: self._draw(pressed=True))
        self.bind("<ButtonRelease-1>", self._click)
        self.bind("<Enter>",           lambda _e: self._draw(hover=True))
        self.bind("<Leave>",           lambda _e: self._draw())
        self.config(cursor="hand2")

    def _draw(self, _e=None, hover=False, pressed=False):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4: return
        if self._accent:
            fill = _hex_adjust(self._bg, -0.12 if pressed else (0.08 if hover else 0))
            bord = _hex_adjust(fill, -0.15)
        elif self._danger:
            from ..config import DANGER, DANGER_BG
            fill = _hex_adjust(DANGER_BG, 0.05) if hover else DANGER_BG
            bord = DANGER; self._fg = DANGER
        else:
            fill = ELEV_1 if pressed else (ELEV_2 if hover else self._bg)
            bord = ACC if hover else BORDER
        draw_rounded_rect(self, 1, 1, w-1, h-1, r=self._radius,
                          fill=fill, outline=bord, width=1)
        self.create_text(w//2, h//2, text=self._text,
                         font=self._font, fill=self._fg, anchor="center")

    def _click(self, _e):
        self._draw(hover=True)
        if self._cmd:
            try: self._cmd()
            except Exception: pass

    def configure(self, **kw):
        if "state" in kw:
            s = kw.pop("state")
            self.config(cursor="hand2" if s=="normal" else "")
        super().configure(**kw)


# Alias de compatibilidade
SinkButton = FlatButton


class RoundCard(tk.Frame):
    def __init__(self, parent, *, bg_card=CARD, bg_parent=BG,
                 radius=R_MD, shadow=False, height=None,
                 accent_top=False, **kw):
        super().__init__(parent, bg=bg_card,
                         highlightbackground=BORDER, highlightthickness=1, **kw)
        if height: self.config(height=height)
        if accent_top:
            tk.Frame(self, bg=ACC, height=2).pack(fill="x", side="top")
        self.inner = tk.Frame(self, bg=bg_card)
        self.inner.pack(fill="both", expand=True, padx=SP_12, pady=SP_10)


class AccentCard(tk.Frame):
    def __init__(self, parent, *, bg_card=CARD, bg_parent=BG,
                 padx=SP_12, pady=SP_10, accent_left=True, **kw):
        super().__init__(parent, bg=bg_card,
                         highlightbackground=BORDER, highlightthickness=1, **kw)
        if accent_left:
            tk.Frame(self, bg=ACC, width=3).pack(fill="y", side="left")
        self.inner = tk.Frame(self, bg=bg_card)
        self.inner.pack(fill="both", expand=True, padx=padx, pady=pady)


class FocusEntry(tk.Entry):
    def __init__(self, parent, textvariable=None, placeholder="", **kw):
        kw.setdefault("bg",                  CARD2)
        kw.setdefault("fg",                  FG)
        kw.setdefault("insertbackground",    ACC_GLOW)
        kw.setdefault("relief",              "flat")
        kw.setdefault("font",                FONT_BODY)
        kw.setdefault("highlightthickness",  1)
        kw.setdefault("highlightbackground", BORDER)
        kw.setdefault("highlightcolor",      ACC)
        kw.setdefault("bd",                  0)
        super().__init__(parent, textvariable=textvariable, **kw)


class ProgressBar(tk.Canvas):
    def __init__(self, parent, *, height=4, bg_fill=ACC,
                 bg_parent=CARD, radius=2, **kw):
        super().__init__(parent, height=height,
                         bg=bg_parent, highlightthickness=0, **kw)
        self._fill = bg_fill; self._radius = radius; self._value = 0.0
        self.bind("<Configure>", self._draw)

    def set(self, value, maximum=100):
        self._value = min(1.0, value / max(maximum, 1))
        self._draw()

    def _draw(self, _e=None):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4: return
        self.create_rectangle(0, 0, w, h, fill=BORDER, outline="")
        fw = int(w * self._value)
        if fw > 1:
            draw_rounded_rect(self, 0, 0, fw, h, r=self._radius,
                              fill=self._fill, outline="")


class FolderRow(tk.Frame):
    def __init__(self, parent, label, textvariable, on_browse, *,
                 show_dnd_hint=False, parent_bg=BG, **kw):
        super().__init__(parent, bg=parent_bg, **kw)
        self._var = textvariable

        lbl_row = tk.Frame(self, bg=parent_bg)
        lbl_row.pack(fill="x", pady=(0, SP_4))
        tk.Label(lbl_row, text=label.upper(),
                 font=FONT_LABEL_S, bg=parent_bg, fg=MUTED).pack(side="left")
        if show_dnd_hint:
            tk.Label(lbl_row, text="drag & drop",
                     font=FONT_HINT, bg=parent_bg, fg=SUBTLE).pack(side="right")

        row = tk.Frame(self, bg=parent_bg)
        row.pack(fill="x")

        self._entry = tk.Entry(row, textvariable=textvariable,
                               font=FONT_MONO, bg=CARD2, fg=FG,
                               insertbackground=ACC_GLOW, relief="flat",
                               highlightthickness=1,
                               highlightbackground=BORDER,
                               highlightcolor=ACC, bd=0)
        self._entry.pack(side="left", fill="x", expand=True,
                         ipady=SP_8, padx=(0, SP_6))

        btn = FlatButton(row, "⋯", on_browse,
                         bg=CARD2, fg=MUTED,
                         font=("Segoe UI", 13),
                         padx=SP_12, pady=4,
                         parent_bg=parent_bg)
        btn.pack(side="left")

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
        "Score 0–100% por grupo.",
    ]

    def __init__(self, widget):
        super().__init__(widget)
        self.withdraw()
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.config(bg=BORDER)
        inner = tk.Frame(self, bg=SURFACE)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        pad = tk.Frame(inner, bg=SURFACE)
        pad.pack(fill="both", expand=True, padx=SP_12, pady=SP_10)
        for line in self._LINES:
            c = MUTED if "─" in line else (
                ACC if "AgrupadorPDF" in line else FG)
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

    def _hide(self, _e): self.withdraw()


def apply_ttk_style():
    s = ttk.Style()
    try: s.theme_use("clam")
    except Exception: pass
    s.configure("Vertical.TScrollbar",
                 troughcolor=CARD, background=BORDER2,
                 arrowcolor=MUTED, bordercolor=CARD,
                 relief="flat", width=8)
    s.map("Vertical.TScrollbar", background=[("active", ACC3)])
