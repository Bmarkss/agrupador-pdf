"""
ui/app.py — AgrupadorPDF v1.6.4
Design System: Neobrutalista — Branco / Cinza / Azul Capri
"""
import os, json, re, shutil, threading, webbrowser
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
# Auto-update via GitHub Releases API — detecta nova versão automaticamente
# quando um Release é publicado no repositório. Zero configuração manual.
UPDATE_CHECK_URL = (
    "https://api.github.com/repos/Bmarkss/agrupador-pdf/releases/latest"
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

    # ── Layout ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_footer()
        self._build_body()

    # ── Header ─────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = tk.Frame(self, bg=MUTED)   # cinza escuro no topo
        hdr.pack(fill="x")

        inner = tk.Frame(hdr, bg=MUTED)
        inner.pack(fill="x", padx=SP_20, pady=(SP_12, SP_10))

        left = tk.Frame(inner, bg=MUTED)
        left.pack(side="left")

        # Icone simples (quadrado capri com "A")
        icon_f = tk.Frame(left, bg=ACC, width=36, height=36)
        icon_f.pack(side="left")
        icon_f.pack_propagate(False)
        tk.Label(icon_f, text="A", font=("Segoe UI", 16, "bold"),
                 bg=ACC, fg=SURFACE).pack(expand=True)

        text_f = tk.Frame(left, bg=MUTED)
        text_f.pack(side="left", padx=(SP_12, 0))

        tk.Label(text_f, text="AgrupadorPDF",
                 font=FONT_HERO, bg=MUTED, fg=SURFACE).pack(anchor="w")
        tk.Label(text_f,
                 text="agrupamento automatico de documentos fiscais",
                 font=FONT_HINT, bg=MUTED, fg=BORDER).pack(anchor="w", pady=(2, 0))

        right = tk.Frame(inner, bg=MUTED)
        right.pack(side="right", anchor="center")

        # Badge versao
        badge_f = tk.Frame(right, bg=ACC)
        badge_f.pack(side="right", padx=(SP_10, 0))
        tk.Label(badge_f, text=f"v{VERSION}",
                 font=FONT_BADGE, bg=ACC, fg=SURFACE,
                 padx=SP_10, pady=SP_4).pack()

        # Icone info com tooltip
        info = tk.Label(right, text="i",
                        font=("Segoe UI", 11, "bold"), bg=MUTED, fg=BORDER2,
                        cursor="hand2")
        info.pack(side="right")
        Tooltip(info)

        # Linha capri fina na base do header
        tk.Frame(self, bg=ACC, height=3).pack(fill="x")

    # ── Footer ─────────────────────────────────────────────────────────────────

    def _build_footer(self):
        ft = tk.Frame(self, bg=MUTED)
        ft.pack(fill="x", side="bottom")
        tk.Frame(ft, bg=BORDER2, height=2).pack(fill="x")
        tk.Label(ft, text=f"AgrupadorPDF  v{VERSION}",
                 font=FONT_HINT, bg=MUTED, fg=BORDER, pady=5).pack()

    # ── Body ───────────────────────────────────────────────────────────────────

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

        # Contador de PDFs
        count_f = tk.Frame(body, bg=BG)
        count_f.pack(fill="x", pady=(0, SP_8))
        self._pdf_count_label = tk.Label(
            count_f, text="", font=FONT_HINT, bg=BG, fg=ACC2)
        self._pdf_count_label.pack(side="right")

        # Pasta de destino
        self._row_output = FolderRow(
            body, "Pasta de Destino",
            self.output_var, self._pick_output,
            show_dnd_hint=True, parent_bg=BG)
        self._row_output.pack(fill="x", pady=(0, SP_16))

        self._setup_dnd()

        # Divisor
        tk.Frame(body, bg=BORDER2, height=2).pack(fill="x", pady=(0, SP_12))

        # ── Opcoes inline ──────────────────────────────────────────────────
        self.open_after     = tk.BooleanVar(value=True)
        self.copy_unmatched = tk.BooleanVar(value=True)
        self.verbose_mode   = tk.BooleanVar(value=False)

        opts_frame = tk.Frame(body, bg=BORDER, padx=2, pady=2)
        opts_frame.pack(fill="x", pady=(0, SP_14))

        opts_inner = tk.Frame(opts_frame, bg=BG)
        opts_inner.pack(fill="x")

        for i, (text, sub, var) in enumerate([
            ("Abrir ao finalizar", "Abre pasta AGRUPADOS", self.open_after),
            ("Salvar CONFERIR",    "Copia sem comprovante", self.copy_unmatched),
            ("Log detalhado",      "Mostra todos os passos", self.verbose_mode),
        ]):
            if i > 0:
                tk.Frame(opts_inner, bg=BORDER, width=2).pack(side="left", fill="y")
            self._make_checkbox(opts_inner, text, sub, var)

        # ── Botao principal ────────────────────────────────────────────────
        self._btn_run = FlatButton(
            body, "  AGRUPAR PDFs", self._run,
            accent=True, font=FONT_TITLE,
            padx=32, pady=SP_14,
            full_width=True, parent_bg=BG)
        self._btn_run.pack(fill="x", pady=(0, SP_8))

        # ── Faixa secundaria ───────────────────────────────────────────────
        sec = tk.Frame(body, bg=ELEV_1,
                       highlightbackground=BORDER2, highlightthickness=2)
        sec.pack(fill="x", pady=(0, SP_12))
        sec_inner = tk.Frame(sec, bg=ELEV_1, padx=SP_8, pady=SP_6)
        sec_inner.pack(fill="x")

        self.btn_export = FlatButton(
            sec_inner, "Exportar Log", self._export_log,
            bg=ELEV_1, fg=MUTED, font=FONT_BODY,
            padx=SP_12, pady=4, parent_bg=ELEV_1)
        self.btn_export.pack(side="left")

        self.btn_cancel = FlatButton(
            sec_inner, "Cancelar", self._cancel,
            bg=MUTED, fg=SURFACE, font=FONT_BODY,
            padx=SP_12, pady=4, parent_bg=ELEV_1)
        self.btn_cancel.pack(side="right")
        self.btn_cancel.configure(state="disabled")

        # ── Progresso ──────────────────────────────────────────────────────
        prog_frame = tk.Frame(body, bg=BG)
        prog_frame.pack(fill="x", pady=(0, SP_10))

        prog_hd = tk.Frame(prog_frame, bg=BG)
        prog_hd.pack(fill="x", pady=(0, SP_4))
        tk.Label(prog_hd, text="PROGRESSO",
                 font=FONT_LABEL_S, bg=BG, fg=SUBTLE).pack(side="left")
        self.progress_label = tk.Label(prog_hd, text="",
                                       font=FONT_BADGE, bg=BG, fg=ACC2)
        self.progress_label.pack(side="right")

        self.progress = ProgressBar(prog_frame, height=10,
                                    bg_fill=ACC, bg_parent=BG)
        self.progress.pack(fill="x", pady=(0, SP_4))

        self._current_label = tk.Label(prog_frame, text="",
                                       font=FONT_HINT, bg=BG, fg=MUTED,
                                       anchor="w")
        self._current_label.pack(fill="x")

        # Placeholder para o resumo
        self._summary_frame = tk.Frame(body, bg=BG)
        self._summary_shown = False

        # ── Log ────────────────────────────────────────────────────────────
        self._log_card = tk.Frame(body, bg=MUTED, padx=2, pady=2)
        self._log_card.pack(fill="both", expand=True)

        log_wrap = tk.Frame(self._log_card, bg=CARD)
        log_wrap.pack(fill="both", expand=True)

        log_hdr = tk.Frame(log_wrap, bg=MUTED)
        log_hdr.pack(fill="x")

        self._log_dot_cv = tk.Canvas(log_hdr, width=8, height=8,
                                     bg=MUTED, highlightthickness=0)
        self._log_dot_cv.create_oval(1, 1, 7, 7, fill=BORDER2, outline="")
        self._log_dot_cv.pack(side="left", padx=(SP_10, SP_6), pady=SP_8)

        tk.Label(log_hdr, text="LOG DE PROCESSAMENTO",
                 font=FONT_LABEL_S, bg=MUTED, fg=BORDER, pady=6).pack(side="left")

        self._verbose_badge = tk.Label(log_hdr, text="",
                                       font=FONT_HINT, bg=MUTED, fg=ACC, pady=6)
        self._verbose_badge.pack(side="right", padx=SP_10)
        self.verbose_mode.trace_add("write",
            lambda *_: self._verbose_badge.config(
                text="DETALHADO" if self.verbose_mode.get() else ""))

        tk.Frame(log_wrap, bg=BORDER2, height=2).pack(fill="x")

        self.log = tk.Text(log_wrap,
                           font=FONT_MONO, bg=CARD2, fg=FG,
                           insertbackground=ACC,
                           bd=0, relief="flat",
                           state="disabled", padx=SP_12, pady=SP_10,
                           selectbackground=ACCDIM, selectforeground=FG)
        sc = ttk.Scrollbar(log_wrap, command=self.log.yview)
        self.log.configure(yscrollcommand=sc.set)
        sc.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)

        self.log.tag_config("success", foreground=SUCCESS)
        self.log.tag_config("warn",    foreground=WARN)
        self.log.tag_config("danger",  foreground=DANGER)
        self.log.tag_config("muted",   foreground=MUTED)
        self.log.tag_config("acc",     foreground=ACC2)
        self.log.tag_config("subtle",  foreground=SUBTLE)

    def _make_checkbox(self, parent, text, sub, var):
        """Checkbox neobrutalista: quadrado capri quando marcado."""
        frame = tk.Frame(parent, bg=BG, cursor="hand2")
        frame.pack(side="left", fill="both", expand=True,
                   padx=SP_10, pady=SP_8)

        box_f = tk.Frame(frame, bg=BG)
        box_f.pack(anchor="w")

        # Box visual
        box = tk.Canvas(box_f, width=14, height=14,
                        bg=BG, highlightthickness=0)
        box.pack(side="left", padx=(0, SP_6))

        def draw_box(*_):
            box.delete("all")
            if var.get():
                box.create_rectangle(0, 0, 13, 13, fill=ACC, outline=ACC2, width=2)
                box.create_rectangle(3, 3, 10, 10, fill=SURFACE, outline="")
            else:
                box.create_rectangle(0, 0, 13, 13, fill=SURFACE,
                                     outline=BORDER, width=2)

        var.trace_add("write", lambda *_: draw_box())
        draw_box()

        lbl = tk.Label(box_f, text=text,
                       font=FONT_BODY, bg=BG, fg=FG, cursor="hand2")
        lbl.pack(side="left")

        sub_lbl = tk.Label(frame, text=sub,
                           font=FONT_HINT, bg=BG, fg=SUBTLE)
        sub_lbl.pack(anchor="w", padx=(20, 0))

        def toggle(_e=None):
            var.set(not var.get())

        for w in (frame, box_f, box, lbl, sub_lbl):
            w.bind("<Button-1>", toggle)

    # ── Resumo pos-processamento ────────────────────────────────────────────────

    def _show_summary(self, ok, warn, err, conf, dst,
                      resultados: list | None = None):
        def _do():
            for w in self._summary_frame.winfo_children():
                w.destroy()

            card = tk.Frame(self._summary_frame, bg=BORDER, padx=2, pady=2)
            card.pack(fill="x")
            inn = tk.Frame(card, bg=CARD, padx=SP_14, pady=SP_10)
            inn.pack(fill="x")

            tk.Label(inn, text="RESULTADO",
                     font=FONT_LABEL_S, bg=CARD, fg=MUTED).pack(
                         anchor="w", pady=(0, SP_8))

            # Contadores
            grid = tk.Frame(inn, bg=CARD)
            grid.pack(fill="x", pady=(0, SP_10))

            for col, (count, label, bgc, fgc) in enumerate([
                (str(ok),   "agrupados", SUCCESS_BG, SUCCESS),
                (str(warn), "revisar",   WARN_BG,    WARN),
                (str(err),  "erros",     DANGER_BG,  DANGER),
                (str(conf), "conferir",  ELEV_1,     MUTED),
            ]):
                grid.columnconfigure(col, weight=1)
                c = tk.Frame(grid, bg=bgc,
                             highlightbackground=BORDER2, highlightthickness=2)
                c.grid(row=0, column=col,
                       padx=(0 if col == 0 else SP_6, 0), sticky="nsew")
                tk.Label(c, text=count,
                         font=FONT_NUM, bg=bgc, fg=fgc, pady=SP_6).pack()
                tk.Label(c, text=label,
                         font=FONT_LABEL_S, bg=bgc, fg=fgc,
                         pady=(0, SP_6)).pack()

            # Botões abrir pasta
            btn_f = tk.Frame(inn, bg=CARD)
            btn_f.pack(fill="x", pady=(0, SP_10))

            agrupados_dir = os.path.join(dst, "AGRUPADOS")
            conferir_dir  = os.path.join(dst, "CONFERIR")

            if os.path.isdir(agrupados_dir) and ok > 0:
                FlatButton(btn_f, "Abrir AGRUPADOS",
                           lambda p=agrupados_dir: os.startfile(p),
                           accent=True, font=FONT_BODY,
                           padx=SP_14, pady=5, parent_bg=CARD).pack(
                               side="left", padx=(0, SP_8))

            if os.path.isdir(conferir_dir) and conf > 0:
                FlatButton(btn_f, "Abrir CONFERIR",
                           lambda p=conferir_dir: os.startfile(p),
                           bg=MUTED, fg=SURFACE, font=FONT_BODY,
                           padx=SP_14, pady=5, parent_bg=CARD).pack(side="left")

            # ── Painel de feedback por grupo ───────────────────────────────
            if resultados:
                tk.Frame(inn, bg=BORDER2, height=2).pack(fill="x",
                                                          pady=(SP_8, SP_6))
                tk.Label(inn,
                         text="FEEDBACK  —  marque agrupamentos incorretos",
                         font=FONT_LABEL_S, bg=CARD, fg=MUTED).pack(
                             anchor="w", pady=(0, SP_6))

                fb_scroll_f = tk.Frame(inn, bg=CARD)
                fb_scroll_f.pack(fill="x")

                for gid, msg, gid_id in resultados:
                    row = tk.Frame(fb_scroll_f, bg=ELEV_1,
                                   highlightbackground=BORDER2,
                                   highlightthickness=1)
                    row.pack(fill="x", pady=(0, SP_4))

                    # Símbolo + nome do grupo
                    sym = chr(10004) if (chr(10004) in msg or "OK" in msg) else (
                          chr(9888) if (chr(9888) in msg or "REVISAR" in msg) else chr(10008))
                    sym_clr = SUCCESS if sym == chr(10004) else (
                              WARN if sym == chr(9888) else DANGER)

                    lbl_f = tk.Frame(row, bg=ELEV_1)
                    lbl_f.pack(side="left", fill="x", expand=True,
                               padx=SP_8, pady=SP_4)

                    tk.Label(lbl_f, text=sym, font=FONT_BADGE,
                             bg=ELEV_1, fg=sym_clr).pack(side="left")
                    disp = gid[:44] + "…" if len(gid) > 44 else gid
                    tk.Label(lbl_f, text=f"  {disp}",
                             font=FONT_BODY_S, bg=ELEV_1, fg=FG,
                             anchor="w").pack(side="left")

                    # Botões ✔ Correto / ✗ Incorreto
                    fb_btns = tk.Frame(row, bg=ELEV_1)
                    fb_btns.pack(side="right", padx=SP_6, pady=SP_4)

                    status_lbl = tk.Label(fb_btns, text="",
                                          font=FONT_HINT, bg=ELEV_1, fg=MUTED,
                                          width=8)
                    status_lbl.pack(side="right", padx=(SP_4, 0))

                    def _on_ok(gid_id=gid_id, lbl=status_lbl, r=row):
                        if gid_id:
                            try:
                                from ..feedback_store import record_acceptance
                                record_acceptance(gid_id, True)
                            except Exception: pass
                        lbl.config(text="Correto", fg=SUCCESS)
                        r.config(highlightbackground=SUCCESS,
                                 highlightthickness=2)

                    def _on_err(gid_id=gid_id, lbl=status_lbl, r=row):
                        if gid_id:
                            try:
                                from ..feedback_store import (
                                    record_acceptance, update_weights_from_feedback)
                                record_acceptance(gid_id, False)
                                update_weights_from_feedback()
                            except Exception: pass
                        lbl.config(text="Incorreto", fg=DANGER)
                        r.config(highlightbackground=DANGER,
                                 highlightthickness=2)

                    FlatButton(fb_btns, "Incorreto", _on_err,
                               bg=ELEV_1, fg=DANGER, font=FONT_BODY_S,
                               padx=SP_8, pady=3, parent_bg=ELEV_1).pack(
                                   side="right", padx=(SP_4, 0))

                    FlatButton(fb_btns, "Correto", _on_ok,
                               accent=True, font=FONT_BODY_S,
                               padx=SP_8, pady=3, parent_bg=ELEV_1).pack(
                                   side="right")

            if not self._summary_shown:
                self._summary_frame.pack(fill="x", pady=(0, SP_10),
                                         before=self._log_card)
                self._summary_shown = True

        self.after(0, _do)

    def _hide_summary(self):
        if self._summary_shown:
            self._summary_frame.pack_forget()
            self._summary_shown = False

    # ── Log ────────────────────────────────────────────────────────────────────

    def _make_log_cb(self):
        verbose = self.verbose_mode.get()
        _always = (
            "OK", "REVISAR", "ERRO", "CONFERIR",
            "Fase", "grupo(s)", "RESUMO",
            "PDFs lidos", "Grupos formados",
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

    # ── DnD ────────────────────────────────────────────────────────────────────

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

    # ── PDF count ──────────────────────────────────────────────────────────────

    def _update_pdf_count(self, folder):
        try:
            n = len([f for f in os.listdir(folder)
                     if f.lower().endswith(".pdf")
                     and not f.upper().endswith("_AGRUPADO.PDF")])
            self._pdf_count_label.config(
                text=f"{n} PDF{'s' if n != 1 else ''} encontrado{'s' if n != 1 else ''}"
                if n > 0 else "")
        except Exception:
            self._pdf_count_label.config(text="")

    # ── Selecao de pasta ───────────────────────────────────────────────────────

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

    # ── Processamento ──────────────────────────────────────────────────────────

    def _run(self):
        src = self.input_var.get().strip()
        dst = self.output_var.get().strip()
        if not src or not os.path.isdir(src):
            messagebox.showerror("Erro", "Selecione uma pasta de entrada valida.")
            return
        if not dst or not os.path.isdir(dst):
            messagebox.showerror("Erro", "Selecione uma pasta de saida valida.")
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
        resultados: list[tuple[str, str, int | None]] = []  # (gid, msg, grouping_id)

        try:
            groups, unclassified = scan_folder(
                src, log_callback=log_cb,
                cancel_flag=lambda: self._cancelled)

            if self._cancelled:
                self._log("\n  Cancelado.", WARN)
                return

            total = len(groups)
            if total == 0:
                self._log("\n  Nenhum grupo formado.", MUTED)
                self._show_summary(0, 0, 0, len(unclassified), dst, [])
                return

            def _init():
                self._progress_max = total
                self.progress_label.config(text="0%")
            self.after(0, _init)

            for i, (gid, files) in enumerate(sorted(groups.items()), 1):
                if self._cancelled:
                    self._log("\n  Cancelado.", WARN)
                    return

                short = gid[:54] + "..." if len(gid) > 54 else gid
                self._set_current(f"Mesclando: {short}")

                msg, grouping_id = merge_group(gid, files, dst)
                disp = gid[:48] + "..." if len(gid) > 48 else gid

                _sm  = re.search(r'\[([*!+])?\s*(\d+)%\]', msg)
                _pct = int(_sm.group(2)) if _sm else None

                if "OK" in msg or (chr(10004) in msg):
                    clr = SUCCESS if (_pct is None or _pct >= 80) else WARN
                    log_cb(f"  {i:>2}/{total}   {msg.replace(gid, disp)}", clr)
                    ok += 1
                elif "ERRO" in msg or (chr(10008) in msg):
                    log_cb(f"  {i:>2}/{total}   {msg.replace(gid, disp)}", DANGER)
                    err += 1
                else:
                    clr = WARN if (_pct is None or _pct >= 65) else DANGER
                    log_cb(f"  {i:>2}/{total}   {msg.replace(gid, disp)}", clr)
                    warn += 1

                resultados.append((gid, msg, grouping_id))

                pct = int(i / total * 100)
                self.after(0, lambda v=i, p=pct: (
                    self.progress.set(v, self._progress_max),
                    self.progress_label.config(text=f"{p}%"),
                ))

            # CONFERIR
            conf_count = len(unclassified)
            if unclassified:
                log_cb(f"\n  {conf_count} arquivo(s) para CONFERIR", WARN)
                for f in unclassified:
                    log_cb(f"    .  {f}", MUTED)
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

            total_str = f"{ok+warn+err} grupo(s)"
            log_cb(f"\n  {'─'*48}", SUBTLE)
            log_cb(f"  OK {ok}   Revisar {warn}   Erros {err}   Conferir {conf_count}   ({total_str})", FG)

            self._show_summary(ok, warn, err, conf_count, dst, resultados)
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
        color = ACC if active else BORDER2
        self.after(0, lambda: (
            self._log_dot_cv.delete("all"),
            self._log_dot_cv.create_oval(1, 1, 7, 7, fill=color, outline=""),
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

    # ── Persistencia ───────────────────────────────────────────────────────────

    def _load_last_folders(self):
        try:
            with open(_CFG) as f:
                d = json.load(f)
            src = d.get("src", ""); dst = d.get("dst", "")
            if os.path.isdir(src):
                self.input_var.set(src); self._update_pdf_count(src)
            if os.path.isdir(dst):
                self.output_var.set(dst)
        except Exception: pass

    def _save_last_folders(self, src, dst):
        try:
            with open(_CFG, "w") as f:
                json.dump({"src": src, "dst": dst}, f)
        except Exception: pass

    # ── Auto-update ────────────────────────────────────────────────────────────

    def _versao_para_tuple(self, v):
        nums = re.findall(r"\d+", v)
        return tuple(int(n) for n in nums)

    def _checar_updates(self):
        def _worker():
            try:
                req = __import__("urllib.request", fromlist=["Request"]).Request(
                    UPDATE_CHECK_URL,
                    headers={"User-Agent": f"AgrupadorPDF/{VERSION}"}
                )
                with urlopen(req, timeout=8) as r:
                    dados = json.loads(r.read().decode())

                # GitHub Releases API: tag_name = "v1.6.5", assets = [{...}]
                tag  = dados.get("tag_name", "")           # ex: "v1.6.5"
                vr   = tag.lstrip("v")                      # ex: "1.6.5"
                body = dados.get("body", "")                # changelog do release
                assets = dados.get("assets", [])
                # Pega o primeiro .exe nos assets
                url = next(
                    (a["browser_download_url"] for a in assets
                     if a.get("name", "").lower().endswith(".exe")),
                    dados.get("html_url", "")               # fallback: página do release
                )

                if vr and self._versao_para_tuple(vr) > self._versao_para_tuple(VERSION):
                    self.after(0, self._mostrar_aviso_update,
                               {"version": vr, "download_url": url, "changelog": body})
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _mostrar_aviso_update(self, dados):
        vn  = dados.get("version", "?")
        url = dados.get("download_url", "")
        cl  = dados.get("changelog", "")
        msg = f"Nova versao disponivel: v{vn}\nVersao atual: v{VERSION}\n"
        if cl:
            # Mostra apenas as primeiras 3 linhas do changelog
            linhas = [l for l in cl.splitlines() if l.strip()][:3]
            msg += "\nNovidades:\n" + "\n".join(f"  {l}" for l in linhas) + "\n"
        msg += "\nBaixar e instalar agora?"
        if url and messagebox.askyesno("Atualizacao disponivel", msg):
            webbrowser.open(url)
