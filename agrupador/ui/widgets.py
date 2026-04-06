"""
ui/widgets.py — Componentes visuais do AgrupadorPDF v1.2.0

Design System: Corporate Precision
  - Elevacao em 3 niveis com sombras reais
  - SinkButton com geometria corrigida (texto sempre centrado)
  - AccentCard: altura dinamica, zero clipping
  - FocusEntry: borda animada, placeholder, sem canvas aninhado
"""

import tkinter as tk
from tkinter import ttk

from ..config import (
    VERSION,
    BG, SURFACE, CARD, CARD2, BORDER, BORDER2,
    ACC, ACC2, ACC3, ACC_GLOW, ACCDIM, FG, MUTED, SUBTLE,
    ELEV_1, ELEV_2, ELEV_3,
    FONT_HERO, FONT_TITLE, FONT_HEADING, FONT_LABEL, FONT_LABEL_S,
    FONT_BODY, FONT_BODY_S, FONT_HINT, FONT_MONO, FONT_BADGE, FONT_NUM,
    SP_4, SP_6, SP_8, SP_10, SP_12, SP_14, SP_16,
    HEIGHT_INPUT, R_SM, R_MD, R_LG,
)


# ── Helpers de canvas ─────────────────────────────────────────────────────────

def draw_rounded_rect(canvas, x1, y1, x2, y2, r=R_MD, **kw):
    """Poligono com cantos arredondados (smooth=True)."""
    pts = [
        x1+r, y1,  x2-r, y1,  x2, y1,    x2, y1+r,
        x2, y2-r,  x2, y2,    x2-r, y2,  x1+r, y2,
        x1, y2,    x1, y2-r,  x1, y1+r,  x1, y1,  x1+r, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


def _color_adjust(hex_c: str, delta: float) -> str:
    """
    Escurece (delta < 0) ou clareia (delta > 0) uma cor hex.
    delta em [-1.0, 1.0].
    """
    r, g, b = int(hex_c[1:3], 16), int(hex_c[3:5], 16), int(hex_c[5:7], 16)
    if delta < 0:
        f = 1 + delta
        r, g, b = int(r*f), int(g*f), int(b*f)
    else:
        r = int(r + (255-r)*delta)
        g = int(g + (255-g)*delta)
        b = int(b + (255-b)*delta)
    return f"#{max(0,min(255,r)):02x}{max(0,min(255,g)):02x}{max(0,min(255,b)):02x}"


# ── SinkButton ────────────────────────────────────────────────────────────────

class SinkButton(tk.Frame):
    """
    Botao com efeito 3D sink ao pressionar.
    Geometria corrigida: cy = (body_top + body_bot) // 2
    """

    def __init__(self, parent, text, command,
                 bg=ACC, fg="#ffffff",
                 font=FONT_HEADING,
                 padx=SP_16, pady=SP_6,
                 radius=R_SM, full_width=False, parent_bg=BG,
                 shadow_color=None, hover_color=None, pressed_color=None,
                 **kw):
        super().__init__(parent, bg=parent_bg, **kw)

        self._bg      = bg
        self._fg      = fg
        self._text    = text
        self._cmd     = command
        self._r       = radius
        self._font    = font
        self._state   = "normal"
        self._pressed = False
        self._hover   = False

        self._col_shadow  = shadow_color  or _color_adjust(bg, -0.22)
        self._col_hover   = hover_color   or _color_adjust(bg,  0.12)
        self._col_pressed = pressed_color or _color_adjust(bg, -0.14)

        self._body_h = pady * 2 + 22
        total_h      = self._body_h + 7

        self._cv = tk.Canvas(self, height=total_h, bg=parent_bg,
                             highlightthickness=0, cursor="hand2")
        self._cv.pack(fill="x" if full_width else None)

        for ev, fn in [
            ("<Configure>",       self._redraw),
            ("<Enter>",           lambda _: self._hover_set(True)),
            ("<Leave>",           lambda _: self._hover_set(False, False)),
            ("<ButtonPress-1>",   lambda _: self._press_set(True)),
            ("<ButtonRelease-1>", self._on_release),
        ]:
            self._cv.bind(ev, fn)

    def _hover_set(self, on: bool, pressed: bool = None):
        if self._state != "normal":
            return
        self._hover = on
        if pressed is not None:
            self._pressed = pressed
        self._redraw()

    def _press_set(self, on: bool):
        if self._state != "normal":
            return
        self._pressed = on
        self._redraw()

    def _redraw(self, _e=None):
        cv = self._cv
        cv.delete("all")
        w = cv.winfo_width()
        h = cv.winfo_height()
        if w < 6:
            return
        r = self._r

        body_top = 4 if self._pressed else 1
        body_bot = body_top + self._body_h

        # Sombra (so quando nao pressionado)
        if not self._pressed:
            draw_rounded_rect(cv, 2, body_top+4, w-2, body_bot+4,
                              r=r, fill=self._col_shadow, outline="")

        # Corpo
        fill = (self._col_pressed if self._pressed
                else self._col_hover if self._hover
                else self._bg)
        draw_rounded_rect(cv, 1, body_top, w-3, body_bot,
                          r=r, fill=fill, outline="")

        # Texto centralizado no corpo
        cx = w // 2
        cy = (body_top + body_bot) // 2
        cv.create_text(cx, cy, text=self._text, font=self._font,
                       fill=self._fg if self._state == "normal" else MUTED,
                       anchor="center")

    def _on_release(self, _e=None):
        if self._state != "normal":
            return
        was = self._pressed
        self._pressed = False
        self._redraw()
        if was and self._cmd:
            self._cmd()

    def configure(self, **kw):
        if "state" in kw:
            self._state = kw.pop("state")
            self._cv.configure(
                cursor="hand2" if self._state == "normal" else "")
        if "text" in kw:
            self._text = kw.pop("text")
        if "_fg" in kw:
            self._fg = kw.pop("_fg")
        if "_bg" in kw:
            self._bg = kw.pop("_bg")
        self._redraw()
        if kw:
            super().configure(**kw)

    def config(self, **kw):
        self.configure(**kw)

    def _redraw_ext(self):
        self._redraw()


# ── RoundCard ─────────────────────────────────────────────────────────────────

class RoundCard(tk.Frame):
    """
    Card canvas de ALTURA FIXA — cantos arredondados, sombra em 2 camadas,
    acento opcional no topo. Use apenas quando a altura e conhecida.
    """

    def __init__(self, parent, radius=R_LG, bg_card=CARD, bg_parent=BG,
                 shadow=True, accent_top=False, height=None, **kw):
        super().__init__(parent, bg=bg_parent, **kw)
        self._r       = radius
        self._bg_card = bg_card
        self._bg_par  = bg_parent
        self._shadow  = shadow
        self._accent  = accent_top

        self._cv = tk.Canvas(self, bg=bg_parent, highlightthickness=0)
        if height:
            self._cv.configure(height=height)
        self._cv.pack(fill="both", expand=True)
        self._cv.bind("<Configure>", self._draw)
        self.inner = tk.Frame(self._cv, bg=bg_card)

    def _draw(self, _e=None):
        cv = self._cv
        cv.delete("all")
        w = cv.winfo_width()
        h = cv.winfo_height()
        if w < 6:
            return
        r = self._r

        if self._shadow:
            draw_rounded_rect(cv, 3, 6, w-1, h+2,
                              r=r, fill=ELEV_2, outline="")
            draw_rounded_rect(cv, 2, 4, w-2, h,
                              r=r, fill=ELEV_1, outline="")

        draw_rounded_rect(cv, 1, 1, w-3, h-4,
                          r=r, fill=self._bg_card, outline=BORDER)

        if self._accent:
            cv.create_rectangle(r, 1, w-r-2, 4, fill=ACC, outline="")

        pad = SP_14
        iw  = max(w - pad*2, 10)
        ih  = max(h - pad*2 - 4, 10)
        cv.create_window(pad, pad, window=self.inner,
                         anchor="nw", width=iw, height=ih)

    def force_draw(self):
        self._draw()


# ── AccentCard ────────────────────────────────────────────────────────────────

class AccentCard(tk.Frame):
    """
    Card de ALTURA DINAMICA — sem canvas fixo, zero clipping.
    Usa frames empilhados para sombra real + borda + acento lateral opcional.
    Ideal para: folder rows, stat cards, summary panels.
    """

    def __init__(self, parent, bg_card=CARD, bg_parent=BG,
                 padx=SP_14, pady=SP_10,
                 accent_left=True, accent_color=ACC,
                 accent_width=4, **kw):
        super().__init__(parent, bg=bg_parent, **kw)

        # Sombra: frame levemente maior e mais escuro, 3px abaixo
        shad = tk.Frame(self, bg=ELEV_2)
        shad.pack(fill="x", padx=(2, 0))

        shad2 = tk.Frame(shad, bg=ELEV_1)
        shad2.pack(fill="x", pady=(0, 2))

        # Card com borda 1px
        card_f = tk.Frame(shad2, bg=CARD,
                          highlightthickness=1,
                          highlightbackground=BORDER)
        card_f.pack(fill="x", pady=(0, 2))

        # Acento lateral
        if accent_left:
            acc = tk.Frame(card_f, bg=accent_color, width=accent_width)
            acc.pack(side="left", fill="y")

        self.inner = tk.Frame(card_f, bg=CARD, padx=padx, pady=pady)
        self.inner.pack(side="left", fill="both", expand=True)

    def force_draw(self):
        pass


# ── FocusEntry ────────────────────────────────────────────────────────────────

class FocusEntry(tk.Canvas):
    """Campo de texto com borda azul ao focar e placeholder."""

    def __init__(self, parent, textvariable=None, placeholder="",
                 parent_bg=CARD, height=HEIGHT_INPUT, **kw):
        super().__init__(parent, height=height, bg=parent_bg,
                         highlightthickness=0, **kw)
        self._focused      = False
        self._placeholder  = placeholder
        self._has_ph       = False
        self._textvariable = textvariable

        self._entry = tk.Entry(self, textvariable=textvariable,
                               font=FONT_BODY, bg=CARD,
                               fg=FG, bd=0, relief="flat",
                               insertbackground=ACC)
        self._entry.bind("<FocusIn>",  self._on_focus_in)
        self._entry.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Configure>", self._layout)

        if placeholder and (not textvariable or not textvariable.get()):
            self._entry.insert(0, placeholder)
            self._entry.config(fg=SUBTLE)
            self._has_ph = True

        if textvariable:
            textvariable.trace_add("write", self._on_var_write)

    def _on_var_write(self, *_):
        val = self._textvariable.get() if self._textvariable else ""
        if val and self._has_ph:
            self._entry.delete(0, "end")
            self._entry.insert(0, val)
            self._entry.config(fg=FG)
            self._has_ph = False
        elif not val and not self._focused and self._placeholder:
            self._entry.delete(0, "end")
            self._entry.insert(0, self._placeholder)
            self._entry.config(fg=SUBTLE)
            self._has_ph = True

    def _on_focus_in(self, _e=None):
        if self._has_ph:
            self._entry.delete(0, "end")
            self._entry.config(fg=FG)
            self._has_ph = False
        self._focused = True
        self._draw()

    def _on_focus_out(self, _e=None):
        val = self._textvariable.get() if self._textvariable else self._entry.get()
        if not val and self._placeholder:
            self._entry.delete(0, "end")
            self._entry.insert(0, self._placeholder)
            self._entry.config(fg=SUBTLE)
            self._has_ph = True
        self._focused = False
        self._draw()

    def _layout(self, _e=None):
        w = self.winfo_width()
        h = self.winfo_height()
        if w > 16:
            self._entry.place(x=SP_10, y=4, width=w-SP_10*2, height=h-8)
        self._draw()

    def _draw(self, _e=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 6:
            return
        draw_rounded_rect(self, 0, 0, w-1, h-1, r=R_SM,
                          fill=CARD,
                          outline=ACC if self._focused else BORDER,
                          width=2 if self._focused else 1)


# ── Tooltip ───────────────────────────────────────────────────────────────────

class Tooltip:
    """Tooltip flutuante com info do app."""

    def __init__(self, widget):
        self._widget = widget
        self._win    = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _e=None):
        if self._win:
            return
        x = self._widget.winfo_rootx() - 180
        y = self._widget.winfo_rooty() + 30
        self._win = tk.Toplevel(self._widget)
        self._win.wm_overrideredirect(True)
        self._win.wm_geometry(f"+{x}+{y}")
        f = tk.Frame(self._win, bg=SURFACE, padx=SP_14, pady=SP_10)
        f.pack()
        tk.Label(f, text="AgrupadorPDF",
                 font=FONT_HEADING, bg=SURFACE, fg="#ffffff").pack(anchor="w")
        tk.Label(f, text=f"Versao {VERSION}",
                 font=FONT_BODY_S, bg=SURFACE, fg="#9dc8f0").pack(anchor="w")
        tk.Frame(f, bg=ACC3, height=1).pack(fill="x", pady=SP_6)
        for line in [
            "Padrao: ENTIDADE - TIPO - VALOR",
            "Tipos: BOLETO  NF  NFS  CTE  -C",
        ]:
            tk.Label(f, text=line, font=FONT_BODY_S,
                     bg=SURFACE, fg="#ddeeff").pack(anchor="w")

    def _hide(self, _e=None):
        if self._win:
            self._win.destroy()
            self._win = None


# ── ProgressBar ───────────────────────────────────────────────────────────────

class ProgressBar(tk.Canvas):
    """Barra de progresso com cantos arredondados."""

    def __init__(self, parent, height=8, bg_track=CARD2,
                 bg_fill=ACC, bg_parent=CARD, radius=4, **kw):
        super().__init__(parent, height=height, bg=bg_parent,
                         highlightthickness=0, **kw)
        self._bg_track = bg_track
        self._bg_fill  = bg_fill
        self._r        = radius
        self._val      = 0
        self._max      = 1
        self.bind("<Configure>", self._draw)

    def set(self, val, max_val):
        self._val = val
        self._max = max(max_val, 1)
        self._draw()

    def reset(self):
        self._val = 0
        self._max = 1
        self._draw()

    def _draw(self, _e=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 4:
            return
        draw_rounded_rect(self, 0, 0, w, h, r=self._r,
                          fill=self._bg_track, outline="")
        fw = max(int(w * min(self._val / self._max, 1.0)), 0)
        if fw > self._r * 2:
            draw_rounded_rect(self, 0, 0, fw, h, r=self._r,
                              fill=self._bg_fill, outline="")
        elif fw > 0:
            self.create_rectangle(0, 0, fw, h,
                                  fill=self._bg_fill, outline="")


# ── FolderRow ─────────────────────────────────────────────────────────────────

class FolderRow(tk.Frame):
    """
    Card de selecao de pasta.
    AccentCard (altura dinamica) + dica de DnD fora do card.
    """

    def __init__(self, parent, short_label: str, var, cmd,
                 show_dnd_hint=True, **kw):
        pbg = kw.pop("parent_bg", BG)
        super().__init__(parent, bg=pbg, **kw)

        card = AccentCard(self, bg_card=CARD, bg_parent=pbg,
                          padx=SP_14, pady=SP_10,
                          accent_left=True, accent_color=ACC)
        card.pack(fill="x")
        inn = card.inner

        # Label com icone de pasta
        lbl_row = tk.Frame(inn, bg=CARD)
        lbl_row.pack(fill="x", pady=(0, SP_6))

        ic = tk.Canvas(lbl_row, width=14, height=14,
                       bg=CARD, highlightthickness=0)
        ic.create_rectangle(1, 5, 13, 13, fill=BORDER2, outline="")
        ic.create_rectangle(1, 2, 8,  6,  fill=BORDER2, outline="")
        ic.pack(side="left", padx=(0, SP_6))

        tk.Label(lbl_row, text=short_label.upper(),
                 font=FONT_LABEL_S, bg=CARD, fg=MUTED).pack(side="left")

        # Campo + botao
        row = tk.Frame(inn, bg=CARD)
        row.pack(fill="x")

        FocusEntry(row, textvariable=var,
                   placeholder="Selecione ou arraste uma pasta aqui\u2026",
                   parent_bg=CARD, height=HEIGHT_INPUT,
                   ).pack(side="left", fill="x", expand=True, padx=(0, SP_10))

        SinkButton(row, "Procurar", cmd,
                   bg=ACC, fg="#ffffff", font=FONT_BODY,
                   padx=SP_14, pady=5, radius=R_SM,
                   parent_bg=CARD).pack(side="right", anchor="center")

        # Dica DnD — fora do card, sem risco de overflow
        if show_dnd_hint:
            hint = tk.Frame(self, bg=pbg)
            hint.pack(fill="x", pady=(SP_4, 0))
            tk.Label(hint,
                     text="\u2193  arraste uma pasta diretamente para o campo",
                     font=FONT_HINT, bg=pbg, fg=SUBTLE,
                     ).pack(side="right")

    def force_draw(self):
        pass

    def register_drop(self, callback):
        try:
            from tkinterdnd2 import DND_FILES
            def _reg(w):
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", callback)
                except Exception:
                    pass
                for child in w.winfo_children():
                    _reg(child)
            _reg(self)
        except ImportError:
            pass


# ── Estilo TTK ────────────────────────────────────────────────────────────────

def apply_ttk_style():
    s = ttk.Style()
    s.theme_use("clam")
    s.configure("Vertical.TScrollbar",
                 troughcolor=CARD2, background=BORDER,
                 bordercolor=CARD2, arrowcolor=MUTED)
