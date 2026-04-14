"""
ui/app.py — AgrupadorPDF v1.6.2
Design System: Dark Precision
"""

import os
import json
import re
import shutil
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from urllib.request import urlopen

from ..config import (
    VERSION,
    BG, SURFACE, SURF2, CARD, CARD2, BORDER, BORDER2,
    ACC, ACC2, ACC3, ACC_GLOW, ACCDIM, FG, MUTED, SUBTLE,
    SUCCESS, SUCCESS_BG, WARN, WARN_BG, DANGER, DANGER_BG, INFO_BG,
    ELEV_1,
    FONT_HERO, FONT_TITLE, FONT_HEADING, FONT_LABEL, FONT_LABEL_S,
    FONT_BODY, FONT_BODY_S, FONT_HINT, FONT_MONO, FONT_BADGE, FONT_NUM,
    SP_4, SP_6, SP_8, SP_10, SP_12, SP_14, SP_16, SP_20, SP_24,
    HEIGHT_BTN_LG, HEIGHT_PROG, R_SM, R_MD, R_LG,
)
from ..merger import scan_folder, merge_group, build_output_name

try:
    from tkinterdnd2 import TkinterDnD as _TkDnD
    _DND_OK = True
except ImportError:
    _TkDnD = None
    _DND_OK = False

from .widgets import (
    draw_rounded_rect, FlatButton, SinkButton, RoundCard, AccentCard,
    FocusEntry, Tooltip, ProgressBar, FolderRow, apply_ttk_style,
)

_CFG = os.path.join(os.path.expanduser("~"), ".agrupadorpdf.json")
UPDATE_CHECK_URL = (
    "https://gist.githubusercontent.com/Bmarkss/"
    "0f1d2bf6af3b4fe583f1f7ef22b6beed/raw/agrupador_pdf_version.json"
)

_BaseApp = _TkDnD.Tk if _DND_OK else tk.Tk


class App(_BaseApp):

    def __init__(self):
        super().__init__()
        self.title("AgrupadorPDF")
        self.resizable(True, True)
        self.minsize(780, 700)
        self.configure(bg=BG)

        self._cancelled     = False
        self._progress_max  = 1
        self._summary_shown = False

        apply_ttk_style()
        self._build_ui()

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"820x800+{(sw-820)//2}+{(sh-800)//2}")
        self._load_last_folders()
        self.after(3000, self._checar_updates)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_footer()
        self._build_body()

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = tk.Frame(self, bg=SURFACE)
        hdr.pack(fill="x")

        # Linha âmbar fina no topo
        tk.Frame(hdr, bg=ACC, height=2).pack(fill="x")

        inner = tk.Frame(hdr, bg=SURFACE)
        inner.pack(fill="x", padx=SP_24, pady=(SP_14, SP_12))

        # ícone + texto
        left = tk.Frame(inner, bg=SURFACE)
        left.pack(side="left")

        self._build_icon(left)

        text_f = tk.Frame(left, bg=SURFACE)
        text_f.pack(side="left", padx=(SP_14, 0))

        tk.Label(text_f, text="AgrupadorPDF",
                 font=FONT_HERO, bg=SURFACE, fg=FG).pack(anchor="w")
        tk.Label(text_f,
                 text="agrupamento automático de documentos fiscais",
                 font=FONT_HINT, bg=SURFACE, fg=MUTED).pack(anchor="w", pady=(2, 0))

        # badge versão + info
        right = tk.Frame(inner, bg=SURFACE)
        right.pack(side="right", anchor="center")

        badge = tk.Frame(right, bg=ELEV_1,
                         highlightbackground=BORDER, highlightthickness=1)
        badge.pack(side="right", padx=(SP_10, 0))
        tk.Label(badge, text=f"v{VERSION}",
                 font=FONT_BADGE, bg=ELEV_1, fg=ACC,
                 padx=SP_8, pady=SP_4).pack()

        info = tk.Label(right, text="ⓘ",
                        font=("Segoe UI", 14), bg=SURFACE, fg=MUTED,
                        cursor="hand2")
        info.pack(side="right")
        Tooltip(info)

        # Divider inferior
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

    def _build_icon(self, parent):
        """Ícone de três PDFs sobrepostos — paleta âmbar/carvão."""
        cv = tk.Canvas(parent, width=48, height=40,
                       bg=SURFACE, highlightthickness=0)
        # Doc 3 (fundo) — cor mais escura
        cv.create_rectangle(18, 6, 34, 37, fill=ELEV_1, outline=BORDER)
        cv.create_rectangle(27, 6, 34, 13, fill=BORDER, outline="")
        # Doc 2 (meio) — âmbar dim
        cv.create_rectangle(10, 3, 26, 35, fill=ACCDIM, outline=ACC3)
        cv.create_rectangle(19, 3, 26, 10, fill=ACC3, outline="")
        # Doc 1 (frente) — âmbar
        cv.create_rectangle(2, 0, 18, 33, fill=ACC, outline=ACC2)
        cv.create_rectangle(11, 0, 18, 7,  fill=ACC2, outline="")
        cv.create_polygon([11,0, 18,0, 18,7], fill=ACC_GLOW, outline="")
        for y in [13, 18, 23]:
            cv.create_rectangle(5, y, 15, y+2, fill=ACC2, outline="")
        cv.pack(side="left")

    # ── Footer ────────────────────────────────────────────────────────────────

    def _build_footer(self):
        ft = tk.Frame(self, bg=SURFACE)
        ft.pack(fill="x", side="bottom")
        tk.Frame(ft, bg=BORDER, height=1).pack(fill="x")
        tk.Label(ft, text=f"AgrupadorPDF  v{VERSION}",
                 font=FONT_HINT, bg=SURFACE, fg=SUBTLE, pady=5).pack()

    # ── Body ──────────────────────────────────────────────────────────────────

    def _build_body(self):
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=SP_20, pady=SP_16)

        self.input_var  = tk.StringVar()
        self.output_var = tk.StringVar()

        # Pasta de origem
        self._row_input = FolderRow(
            body, "Pasta de Origem",
            self.input_var, self._pick_input,
            show_dnd_hint=True, parent_bg=BG)
        self._row_input.pack(fill="x", pady=(0, SP_4))

        # contador de PDFs
        count_f = tk.Frame(body, bg=BG)
        count_f.pack(fill="x", pady=(0, SP_6))
        self._pdf_count_label = tk.Label(
            count_f, text="", font=FONT_HINT, bg=BG, fg=ACC)
        self._pdf_count_label.pack(side="right")

        # Pasta de destino
        self._row_output = FolderRow(
            body, "Pasta de Destino",
            self.output_var, self._pick_output,
            show_dnd_hint=True, parent_bg=BG)
        self._row_output.pack(fill="x", pady=(0, SP_16))

        self._setup_dnd()

        # Divisor
        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=(0, SP_12))

        # Opções inline
        opts = tk.Frame(body, bg=BG)
        opts.pack(fill="x", pady=(0, SP_14))
        self.open_after     = tk.BooleanVar(value=True)
        self.copy_unmatched = tk.BooleanVar(value=True)
        self.verbose_mode   = tk.BooleanVar(value=False)

        for text, var in [
            ("Abrir ao finalizar",          self.open_after),
            ("Salvar CONFERIR",             self.copy_unmatched),
            ("Log detalhado",               self.verbose_mode),
        ]:
            cb = tk.Checkbutton(opts, text=text, variable=var,
                                font=FONT_BODY, bg=BG, fg=MUTED,
                                selectcolor=ACCDIM,
                                activebackground=BG, activeforeground=ACC,
                                cursor="hand2",
                                disabledforeground=SUBTLE)
            cb.pack(side="left", padx=(0, SP_20))

        # Botão principal — AGRUPAR
        self._btn_run = FlatButton(
            body, "▶   AGRUPAR PDFs", self._run,
            accent=True, font=FONT_TITLE,
            padx=32, pady=SP_14, radius=R_SM,
            full_width=True, parent_bg=BG)
        self._btn_run.pack(fill="x", pady=(0, SP_8))

        # Faixa secundária
        sec = tk.Frame(body, bg=SURF2,
                       highlightbackground=BORDER, highlightthickness=1)
        sec.pack(fill="x", pady=(0, SP_10))
        sec_inner = tk.Frame(sec, bg=SURF2, padx=SP_8, pady=SP_6)
        sec_inner.pack(fill="x")

        self.btn_export = FlatButton(
            sec_inner, "↓  Exportar log", self._export_log,
            bg=SURF2, fg=MUTED, font=FONT_BODY,
            padx=SP_12, pady=4, radius=R_SM, parent_bg=SURF2)
        self.btn_export.pack(side="left")

        self.btn_cancel = FlatButton(
            sec_inner, "✕  Cancelar", self._cancel,
            danger=True, font=FONT_BODY,
            padx=SP_12, pady=4, radius=R_SM, parent_bg=SURF2)
        self.btn_cancel.pack(side="right")
        self.btn_cancel.configure(state="disabled")

        # Card de progresso
        prog_card = RoundCard(body, radius=R_MD, bg_card=CARD,
                              bg_parent=BG, height=HEIGHT_PROG)
        prog_card.pack(fill="x", pady=(0, SP_10))
        inn = prog_card.inner

        top = tk.Frame(inn, bg=CARD)
        top.pack(fill="x", pady=(0, SP_6))
        tk.Label(top, text="PROGRESSO",
                 font=FONT_LABEL_S, bg=CARD, fg=SUBTLE).pack(side="left")
        self.progress_label = tk.Label(top, text="",
                                       font=FONT_BADGE, bg=CARD, fg=ACC)
        self.progress_label.pack(side="right")

        self.progress = ProgressBar(inn, height=4,
                                    bg_fill=ACC, bg_parent=CARD, radius=2)
        self.progress.pack(fill="x", pady=(0, SP_6))

        self._current_label = tk.Label(inn, text="",
                                       font=FONT_HINT, bg=CARD, fg=MUTED,
                                       anchor="w")
        self._current_label.pack(fill="x")

        # Placeholder para resumo
        self._summary_frame = tk.Frame(body, bg=BG)
        self._summary_shown = False

        # Card de log
        self._log_card = RoundCard(body, radius=R_MD, bg_card=CARD,
                                   bg_parent=BG, accent_top=True, height=200)
        self._log_card.pack(fill="both", expand=True)
        log_inn = self._log_card.inner

        log_hdr = tk.Frame(log_inn, bg=CARD2)
        log_hdr.pack(fill="x")

        # Dot de status
        self._log_dot_cv = tk.Canvas(log_hdr, width=8, height=8,
                                     bg=CARD2, highlightthickness=0)
        self._log_dot_cv.create_oval(1, 1, 7, 7, fill=SUBTLE, outline="")
        self._log_dot_cv.pack(side="left", padx=(SP_10, SP_6), pady=SP_8)
        self._log_dot = self._log_dot_cv  # compat

        tk.Label(log_hdr, text="LOG DE PROCESSAMENTO",
                 font=FONT_LABEL_S, bg=CARD2, fg=MUTED, pady=6).pack(side="left")

        self._verbose_badge = tk.Label(log_hdr, text="",
                                       font=FONT_HINT, bg=CARD2, fg=ACC, pady=6)
        self._verbose_badge.pack(side="right", padx=SP_10)
        self.verbose_mode.trace_add("write",
            lambda *_: self._verbose_badge.config(
                text="DETALHADO" if self.verbose_mode.get() else ""))

        tk.Frame(log_inn, bg=BORDER, height=1).pack(fill="x")

        self.log = tk.Text(log_inn,
                           font=FONT_MONO,
                           bg=CARD, fg=FG,
                           insertbackground=ACC_GLOW,
                           bd=0, relief="flat",
                           state="disabled", padx=SP_12, pady=SP_10,
                           selectbackground=ACCDIM, selectforeground=FG)
        sc = ttk.Scrollbar(log_inn, command=self.log.yview)
        self.log.configure(yscrollcommand=sc.set)
        sc.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)

        # Tags de cor no log
        self.log.tag_config("success",  foreground=SUCCESS)
        self.log.tag_config("warn",     foreground=WARN)
        self.log.tag_config("danger",   foreground=DANGER)
        self.log.tag_config("muted",    foreground=MUTED)
        self.log.tag_config("acc",      foreground=ACC)
        self.log.tag_config("subtle",   foreground=SUBTLE)

    # ── Resumo pós-processamento ──────────────────────────────────────────────

    def _show_summary(self, ok, warn, err, conf, dst):
        def _do():
            for w in self._summary_frame.winfo_children():
                w.destroy()

            card = AccentCard(self._summary_frame, bg_card=CARD,
                              bg_parent=BG, padx=SP_14, pady=SP_10,
                              accent_left=True)
            card.pack(fill="x")
            inn = card.inner

            tk.Label(inn, text="RESULTADO",
                     font=FONT_LABEL_S, bg=CARD, fg=MUTED).pack(
                         anchor="w", pady=(0, SP_8))

            grid = tk.Frame(inn, bg=CARD)
            grid.pack(fill="x", pady=(0, SP_10))

            for col, (count, label, bgc, fgc) in enumerate([
                (str(ok),   "agrupados", SUCCESS_BG, SUCCESS),
                (str(warn), "revisar",   WARN_BG,    WARN),
                (str(err),  "erros",     DANGER_BG,  DANGER),
                (str(conf), "conferir",  CARD2,      MUTED),
            ]):
                grid.columnconfigure(col, weight=1)
                c = tk.Frame(grid, bg=bgc,
                             highlightbackground=BORDER, highlightthickness=1)
                c.grid(row=0, column=col,
                       padx=(0 if col==0 else SP_6, 0), sticky="nsew")
                tk.Label(c, text=count,
                         font=FONT_NUM, bg=bgc, fg=fgc, pady=SP_6).pack()
                tk.Label(c, text=label,
                         font=FONT_LABEL_S, bg=bgc, fg=fgc,
                         pady=(0, SP_6)).pack()

            btn_f = tk.Frame(inn, bg=CARD)
            btn_f.pack(fill="x")

            agrupados = os.path.join(dst, "AGRUPADOS")
            conferir  = os.path.join(dst, "CONFERIR")

            if os.path.isdir(agrupados) and ok > 0:
                FlatButton(btn_f, "↗  Abrir AGRUPADOS",
                           lambda p=agrupados: os.startfile(p),
                           accent=True, font=FONT_BODY,
                           padx=SP_14, pady=5, radius=R_SM,
                           parent_bg=CARD).pack(side="left", padx=(0, SP_8))

            if os.path.isdir(conferir) and conf > 0:
                FlatButton(btn_f, "↗  Abrir CONFERIR",
                           lambda p=conferir: os.startfile(p),
                           bg=WARN_BG, fg=WARN, font=FONT_BODY,
                           padx=SP_14, pady=5, radius=R_SM,
                           parent_bg=CARD).pack(side="left")

            if not self._summary_shown:
                self._summary_frame.pack(fill="x", pady=(0, SP_10),
                                         before=self._log_card)
                self._summary_shown = True

        self.after(0, _do)

    def _hide_summary(self):
        if self._summary_shown:
            self._summary_frame.pack_forget()
            self._summary_shown = False

    # ── Log ──────────────────────────────────────────────────────────────────

    def _make_log_cb(self):
        verbose = self.verbose_mode.get()
        _always = (
            "✔", "✘", "⚠", "↷",
            "Fase", "-- Fase", "Escaneando",
            "grupo(s)", "RESUMO", "─",
            "PDFs lidos", "Grupos formados",
            "Agrupados com", "Erros no", "conferencia",
            "AGRUPADOS", "CONFERIR", "cancelado",
        )
        def _cb(msg, color=FG):
            if not msg.strip():
                if verbose: self._log(msg, color)
                return
            if verbose or any(t in msg for t in _always):
                self._log(msg, color)
        return _cb

    def _log(self, msg, color=FG):
        def _insert():
            self.log.configure(state="normal")
            tag = f"_c{id(color)}"
            self.log.tag_config(tag, foreground=color)
            self.log.insert("end", msg + "\n", tag)
            self.log.see("end")
            self.log.configure(state="disabled")
        self.after(0, _insert)

    def _log_clear(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    # ── DnD ──────────────────────────────────────────────────────────────────

    def _setup_dnd(self):
        if not _DND_OK: return
        def _drop_input(path):
            if os.path.isdir(path):
                self.input_var.set(path)
                self._update_pdf_count(path)
        def _drop_output(path):
            if os.path.isdir(path):
                self.output_var.set(path)
        self._row_input.register_drop(_drop_input)
        self._row_output.register_drop(_drop_output)

    # ── PDF count ─────────────────────────────────────────────────────────────

    def _update_pdf_count(self, folder):
        try:
            n = len([f for f in os.listdir(folder)
                     if f.lower().endswith(".pdf")
                     and not f.upper().endswith("_AGRUPADO.PDF")])
            self._pdf_count_label.config(
                text=f"{n} PDF{'s' if n!=1 else ''} encontrado{'s' if n!=1 else ''}"
                if n > 0 else "")
        except Exception:
            self._pdf_count_label.config(text="")

    # ── Seleção de pasta ──────────────────────────────────────────────────────

    def _pick_input(self):
        p = filedialog.askdirectory(title="Selecionar Pasta de Origem")
        if p:
            self.input_var.set(p)
            self._update_pdf_count(p)
            if not self.output_var.get():
                self.output_var.set(p)

    def _pick_output(self):
        p = filedialog.askdirectory(title="Selecionar Pasta de Destino")
        if p:
            self.output_var.set(p)

    # ── Processamento ─────────────────────────────────────────────────────────

    def _run(self):
        src = self.input_var.get().strip()
        dst = self.output_var.get().strip()
        if not src or not os.path.isdir(src):
            messagebox.showerror("Erro", "Selecione uma pasta de entrada válida.")
            return
        if not dst or not os.path.isdir(dst):
            messagebox.showerror("Erro", "Selecione uma pasta de saída válida.")
            return

        self._hide_summary()
        self._log_clear()
        self._cancelled = False
        self._btn_run.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.progress.set(0, 1)
        self.progress_label.config(text="")
        self._set_current("")
        self._set_dot_active(True)

        threading.Thread(target=self._worker, args=(src, dst), daemon=True).start()

    def _worker(self, src, dst):
        log_cb = self._make_log_cb()
        ok = warn = err = 0

        try:
            # Guarda pastas AGRUPADOS existentes para não re-processar
            agrupados_dir = os.path.join(dst, "AGRUPADOS")
            existing = set()
            if os.path.isdir(agrupados_dir):
                existing = {
                    f.lower() for f in os.listdir(agrupados_dir)
                    if f.lower().endswith("_agrupado.pdf")
                }

            groups, unclassified = scan_folder(
                src, log_callback=log_cb,
                cancel_flag=lambda: self._cancelled)

            if self._cancelled:
                self._log("\n  ⏹ Cancelado.", WARN)
                return

            total = len(groups)
            if total == 0:
                self._log("\n  Nenhum grupo formado.", MUTED)
                self._show_summary(0, 0, 0, len(unclassified), dst)
                return

            def _init():
                self._progress_max = total
                self.progress_label.config(text="0%")
            self.after(0, _init)

            for i, (gid, files) in enumerate(sorted(groups.items()), 1):
                if self._cancelled:
                    self._log("\n  ⏹ Cancelado.", WARN)
                    return

                short = gid[:54] + "…" if len(gid) > 54 else gid
                self._set_current(f"Mesclando: {short}")

                msg  = merge_group(gid, files, dst)
                disp = gid[:48] + "…" if len(gid) > 48 else gid

                # v1.6.2 — cor baseada no score %
                _sm = re.search(r'\[([⚠✔✘])\s*(\d+)%\]', msg)
                _pct = int(_sm.group(2)) if _sm else None

                if "✔" in msg:
                    clr = SUCCESS if (_pct is None or _pct >= 80) else WARN
                    log_cb(f"  {i:>2}/{total}   {msg.replace(gid, disp)}", clr)
                    ok += 1
                elif "✘" in msg:
                    log_cb(f"  {i:>2}/{total}   {msg.replace(gid, disp)}", DANGER)
                    err += 1
                else:
                    clr = WARN if (_pct is None or _pct >= 65) else DANGER
                    log_cb(f"  {i:>2}/{total}   {msg.replace(gid, disp)}", clr)
                    warn += 1

                pct = int(i / total * 100)
                self.after(0, lambda v=i, p=pct: (
                    self.progress.set(v, self._progress_max),
                    self.progress_label.config(text=f"{p}%"),
                ))

            # CONFERIR
            conf_count = len(unclassified)
            if unclassified:
                log_cb(f"\n  {conf_count} arquivo(s) → CONFERIR", WARN)
                for f in unclassified:
                    log_cb(f"    ·  {f}", MUTED)
                if self.copy_unmatched.get():
                    conf_dir = os.path.join(dst, "CONFERIR")
                    os.makedirs(conf_dir, exist_ok=True)
                    for f in unclassified:
                        s = os.path.join(src, f)
                        d = os.path.join(conf_dir, f)
                        n = 2
                        base, ext = os.path.splitext(f)
                        while os.path.exists(d):
                            d = os.path.join(conf_dir, f"{base} ({n}){ext}")
                            n += 1
                        try: shutil.copy2(s, d)
                        except Exception: pass

            # Resumo final
            total_str = f"{ok+warn+err} grupo(s)"
            log_cb(f"\n  {'─'*50}", SUBTLE)
            log_cb(f"  ✔ {ok}  ⚠ {warn}  ✘ {err}  CONFERIR {conf_count}  ({total_str})", FG)

            self._show_summary(ok, warn, err, conf_count, dst)
            self._save_last_folders(src, dst)

            if self.open_after.get() and ok > 0:
                ag = os.path.join(dst, "AGRUPADOS")
                if os.path.isdir(ag):
                    self.after(500, lambda: os.startfile(ag))

        except Exception as e:
            log_cb(f"\n  ERRO: {e}", DANGER)
        finally:
            self.after(0, self._on_done)

    def _on_done(self):
        self._btn_run.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self._set_current("")
        self._set_dot_active(False)

    def _cancel(self):
        self._cancelled = True
        self._set_dot_active(False)

    def _set_current(self, text):
        self.after(0, lambda: self._current_label.config(text=text))

    def _set_dot_active(self, active):
        color = ACC if active else SUBTLE
        self.after(0, lambda: (
            self._log_dot.delete("all"),
            self._log_dot.create_oval(1, 1, 7, 7, fill=color, outline=""),
        ))

    def _export_log(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Texto", "*.txt"), ("Todos", "*.*")],
            title="Exportar log")
        if path:
            try:
                content = self.log.get("1.0", "end")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                messagebox.showerror("Erro", str(e))

    # ── Persistência ─────────────────────────────────────────────────────────

    def _load_last_folders(self):
        try:
            with open(_CFG) as f:
                d = json.load(f)
            src = d.get("src", ""); dst = d.get("dst", "")
            if os.path.isdir(src): self.input_var.set(src); self._update_pdf_count(src)
            if os.path.isdir(dst): self.output_var.set(dst)
        except Exception: pass

    def _save_last_folders(self, src, dst):
        try:
            with open(_CFG, "w") as f:
                json.dump({"src": src, "dst": dst}, f)
        except Exception: pass

    # ── Auto-update ───────────────────────────────────────────────────────────

    def _versao_para_tuple(self, v):
        nums = re.findall(r"\d+", v)
        return tuple(int(n) for n in nums)

    def _checar_updates(self):
        if not UPDATE_CHECK_URL or "placeholder" in UPDATE_CHECK_URL:
            return
        def _worker():
            try:
                with urlopen(UPDATE_CHECK_URL, timeout=5) as r:
                    dados = json.loads(r.read().decode())
                vr = dados.get("version", "")
                if self._versao_para_tuple(vr) > self._versao_para_tuple(VERSION):
                    self.after(0, self._mostrar_aviso_update, dados)
            except Exception: pass
        threading.Thread(target=_worker, daemon=True).start()

    def _mostrar_aviso_update(self, dados):
        vn  = dados.get("version", "?")
        url = dados.get("download_url", "")
        cl  = dados.get("changelog", "")
        msg = f"Nova versão disponível: v{vn}\nVersão atual: v{VERSION}\n"
        if cl: msg += f"\nNovidades:\n{cl}"
        msg += "\n\nAbrir página de download?"
        if url and messagebox.askyesno("Atualização disponível", msg):
            webbrowser.open(url)
