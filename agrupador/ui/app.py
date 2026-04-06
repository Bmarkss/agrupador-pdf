"""
ui/app.py — Janela principal do AgrupadorPDF v1.2.0
Design System: Corporate Precision
"""

import os
import json
import shutil
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from urllib.request import urlopen

from ..config import (
    VERSION,
    BG, SURFACE, SURF2, CARD, CARD2, BORDER, ACC, ACC2, ACC3, ACC_GLOW,
    ACCDIM, FG, MUTED, SUBTLE, SUCCESS, SUCCESS_BG, WARN, WARN_BG,
    DANGER, DANGER_BG, INFO_BG, ELEV_1,
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
    _TkDnD  = None
    _DND_OK = False

from .widgets import (
    draw_rounded_rect, SinkButton, RoundCard, AccentCard,
    FocusEntry, Tooltip, ProgressBar, FolderRow, apply_ttk_style,
)

_LOGBG  = "#f5f9ff"
_LOGFG  = "#1a2535"
_BG_SEC = "#e2ecf6"      # fundo da faixa de botoes secundarios
_CFG    = os.path.join(os.path.expanduser("~"), ".agrupadorpdf.json")

# URL do Gist com a versao mais recente.
# O app consulta essa URL na inicializacao para avisar sobre updates.
UPDATE_CHECK_URL = "https://gist.githubusercontent.com/Bmarkss/placeholder/raw/agrupador_pdf_version.json"


_BaseApp = _TkDnD.Tk if _DND_OK else tk.Tk


class App(_BaseApp):

    def __init__(self):
        super().__init__()
        self.title("AgrupadorPDF")
        self.resizable(True, True)
        self.minsize(760, 700)
        self.configure(bg=BG)

        self._log_tag_idx   = 0
        self._cancelled     = False
        self._progress_max  = 1
        self._summary_shown = False

        apply_ttk_style()
        self._build_ui()

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"780x760+{(sw-780)//2}+{(sh-760)//2}")
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

        # Linha de brilho no topo
        tk.Frame(hdr, bg=ACC_GLOW, height=3).pack(fill="x")

        inner = tk.Frame(hdr, bg=SURFACE)
        inner.pack(fill="x", padx=SP_24, pady=(SP_12, SP_12))

        self._build_hdr_icon(inner)
        self._build_hdr_text(inner)
        self._build_hdr_right(inner)

        # Sombra degradê suave (8 tons)
        shad = tk.Canvas(self, height=8, bg=BG, highlightthickness=0)
        shad.pack(fill="x")
        def _shad(_e=None):
            shad.delete("all")
            w = shad.winfo_width()
            if w < 4:
                return
            stops = ["#aabdd6","#b8cade","#c6d6e6","#d2e0ec",
                     "#dee8f2","#e8f0f6","#f2f7fb","#f8fbfd"]
            for i, c in enumerate(stops):
                shad.create_rectangle(0, i, w, i+1, fill=c, outline="")
        shad.bind("<Configure>", _shad)

    def _build_hdr_icon(self, p):
        cv = tk.Canvas(p, width=54, height=44,
                       bg=SURFACE, highlightthickness=0)
        # doc 3 — azul escuro (fundo)
        cv.create_rectangle(20, 7, 36, 40, fill="#5aa4e8", outline="#3a84c8")
        cv.create_rectangle(29, 7, 36, 14, fill="#3a84c8", outline="")
        # doc 2 — azul medio
        cv.create_rectangle(11, 3, 27, 37, fill="#7bbef0", outline="#4a94d8")
        cv.create_rectangle(20, 3, 27, 11, fill="#4a94d8", outline="")
        # doc 1 — branco (frente)
        cv.create_rectangle(2, 0, 20, 36, fill="#ffffff", outline="#c0d4ec")
        cv.create_rectangle(13, 0, 20, 8,  fill="#c0d4ec", outline="")
        cv.create_polygon([13,0, 20,0, 20,8], fill="#dceaf8", outline="")
        for y in [14, 19, 24]:
            cv.create_rectangle(5, y, 17, y+2, fill="#a0c0df", outline="")
        # seta ->
        cv.create_polygon([37,19, 45,19, 45,16, 53,23, 45,30, 45,27, 37,27],
                          fill=ACC_GLOW, outline="")
        cv.pack(side="left", padx=(0, SP_16))

    def _build_hdr_text(self, p):
        f = tk.Frame(p, bg=SURFACE)
        f.pack(side="left")
        tk.Label(f, text="AgrupadorPDF",
                 font=FONT_HERO, bg=SURFACE, fg="#ffffff").pack(anchor="w")
        tk.Label(f,
                 text="Organize e agrupe automaticamente seus documentos fiscais",
                 font=FONT_HINT, bg=SURFACE, fg="#8ab8da",
                 ).pack(anchor="w", pady=(3, 0))

    def _build_hdr_right(self, p):
        right = tk.Frame(p, bg=SURFACE)
        right.pack(side="right", anchor="center")

        badge = tk.Canvas(right, width=66, height=24,
                          bg=SURFACE, highlightthickness=0)
        badge.pack(side="right", padx=(SP_10, 0))
        def _b(_e=None):
            badge.delete("all")
            draw_rounded_rect(badge, 1, 1, 65, 23, r=11,
                              fill=ACC3, outline="#003878")
            badge.create_text(33, 12, text=f"v{VERSION}",
                              font=FONT_BADGE, fill="#9dc8f0")
        badge.bind("<Configure>", _b)

        info = tk.Label(right, text="\u2139",
                        font=("Segoe UI", 15),
                        bg=SURFACE, fg="#8ab8da", cursor="hand2")
        info.pack(side="right")
        Tooltip(info)

    # ── Footer ────────────────────────────────────────────────────────────────

    def _build_footer(self):
        ft = tk.Frame(self, bg=SURFACE)
        ft.pack(fill="x", side="bottom")
        tk.Frame(ft, bg=ACC3, height=1).pack(fill="x")
        tk.Label(ft,
                 text="Agrupador de PDFs Fiscais  \u00b7  Brian Marques  \u00b7  Loglife Log\u00edstica",
                 font=FONT_HINT, bg=SURFACE, fg="#8ab8da", pady=6,
                 ).pack()

    # ── Body ──────────────────────────────────────────────────────────────────

    def _build_body(self):
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=SP_20, pady=SP_14)

        self.input_var  = tk.StringVar()
        self.output_var = tk.StringVar()

        # Pasta de origem
        self._row_input = FolderRow(
            body, "Pasta de Origem",
            self.input_var, self._pick_input,
            show_dnd_hint=True, parent_bg=BG)
        self._row_input.pack(fill="x", pady=(0, SP_4))

        count_f = tk.Frame(body, bg=BG)
        count_f.pack(fill="x", pady=(0, SP_4))
        self._pdf_count_label = tk.Label(
            count_f, text="", font=FONT_HINT, bg=BG, fg=ACC)
        self._pdf_count_label.pack(side="right")

        # Pasta de destino
        self._row_output = FolderRow(
            body, "Pasta de Destino",
            self.output_var, self._pick_output,
            show_dnd_hint=True, parent_bg=BG)
        self._row_output.pack(fill="x", pady=(0, SP_14))

        self._setup_dnd()

        # Separador
        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=(0, SP_10))

        # Opcoes
        opts = tk.Frame(body, bg=BG)
        opts.pack(fill="x", pady=(0, SP_12))
        self.open_after     = tk.BooleanVar(value=True)
        self.copy_unmatched = tk.BooleanVar(value=True)
        self.verbose_mode   = tk.BooleanVar(value=False)
        for text, var in [
            ("Abrir pasta ao finalizar",              self.open_after),
            ("Salvar nao identificados em CONFERIR",  self.copy_unmatched),
            ("Log detalhado",                         self.verbose_mode),
        ]:
            tk.Checkbutton(opts, text=text, variable=var,
                           font=FONT_BODY, bg=BG, fg=FG,
                           selectcolor=ACCDIM,
                           activebackground=BG, activeforeground=ACC,
                           cursor="hand2").pack(side="left", padx=(0, SP_20))

        # Botao AGRUPAR
        self._btn_run = SinkButton(
            body, "\u25b6   AGRUPAR PDFs", self._run,
            bg=ACC, fg="#ffffff", font=FONT_TITLE,
            padx=32, pady=SP_14, radius=R_MD,
            full_width=True, parent_bg=BG)
        self._btn_run.pack(fill="x", pady=(0, SP_8))

        # Faixa de botoes secundarios
        sec_strip = tk.Frame(body, bg=_BG_SEC,
                             highlightthickness=1,
                             highlightbackground=BORDER)
        sec_strip.pack(fill="x", pady=(0, SP_10))
        sec_inner = tk.Frame(sec_strip, bg=_BG_SEC, padx=SP_8, pady=SP_6)
        sec_inner.pack(fill="x")

        self.btn_export = SinkButton(
            sec_inner, "\u2193  Exportar log", self._export_log,
            bg="#ffffff", fg=MUTED, font=FONT_BODY,
            padx=SP_14, pady=4, radius=R_SM, parent_bg=_BG_SEC,
            shadow_color="#b0c0d8", hover_color="#eaf2fb",
            pressed_color=BORDER)
        self.btn_export.pack(side="left")

        self.btn_cancel = SinkButton(
            sec_inner, "\u2715  Cancelar", self._cancel,
            bg="#ffffff", fg=MUTED, font=FONT_BODY,
            padx=SP_14, pady=4, radius=R_SM, parent_bg=_BG_SEC,
            shadow_color="#b0c0d8", hover_color=DANGER_BG,
            pressed_color="#f5c6c2")
        self.btn_cancel.pack(side="right")
        self.btn_cancel.configure(state="disabled")

        # Card de progresso
        prog_card = RoundCard(body, radius=R_MD, bg_card=CARD,
                              bg_parent=BG, shadow=True, height=HEIGHT_PROG)
        prog_card.pack(fill="x", pady=(0, SP_10))
        inn = prog_card.inner

        top = tk.Frame(inn, bg=CARD)
        top.pack(fill="x", pady=(0, SP_4))
        tk.Label(top, text="PROGRESSO",
                 font=FONT_LABEL_S, bg=CARD, fg=SUBTLE).pack(side="left")
        self.progress_label = tk.Label(top, text="",
                                       font=FONT_BADGE, bg=CARD, fg=ACC)
        self.progress_label.pack(side="right")

        self.progress = ProgressBar(inn, height=8,
                                    bg_fill=ACC, bg_parent=CARD, radius=4)
        self.progress.pack(fill="x", pady=(0, SP_4))

        self._current_label = tk.Label(inn, text="",
                                       font=FONT_HINT, bg=CARD, fg=MUTED,
                                       anchor="w")
        self._current_label.pack(fill="x")

        # Frame de resumo (invisivel ate processar)
        self._summary_frame = tk.Frame(body, bg=BG)
        self._summary_shown = False

        # Card de log (expande)
        self._log_card = RoundCard(body, radius=R_LG, bg_card=CARD,
                                   bg_parent=BG, shadow=True,
                                   accent_top=True, height=200)
        self._log_card.pack(fill="both", expand=True)
        log_inn = self._log_card.inner

        log_hdr = tk.Frame(log_inn, bg=CARD2)
        log_hdr.pack(fill="x")

        dot = tk.Canvas(log_hdr, width=10, height=10,
                        bg=CARD2, highlightthickness=0)
        dot.create_oval(1, 1, 9, 9, fill=MUTED, outline="")
        dot.pack(side="left", padx=(SP_10, SP_6), pady=SP_6)
        self._log_dot = dot

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
                           bg=_LOGBG, fg=_LOGFG,
                           insertbackground=ACC,
                           bd=0, relief="flat",
                           state="disabled", padx=SP_12, pady=SP_10,
                           selectbackground=ACCDIM, selectforeground=FG)
        sc = ttk.Scrollbar(log_inn, command=self.log.yview)
        self.log.configure(yscrollcommand=sc.set)
        sc.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)

    # ── Painel de resumo ──────────────────────────────────────────────────────

    def _show_summary(self, ok, warn, err, conf, dst):
        def _do():
            for w in self._summary_frame.winfo_children():
                w.destroy()

            card = AccentCard(self._summary_frame, bg_card=CARD,
                              bg_parent=BG, padx=SP_14, pady=SP_10,
                              accent_left=False)
            card.pack(fill="x")
            inn = card.inner

            tk.Label(inn, text="RESULTADO DO PROCESSAMENTO",
                     font=FONT_LABEL_S, bg=CARD, fg=SUBTLE,
                     ).pack(anchor="w", pady=(0, SP_8))

            # Stat cards
            grid = tk.Frame(inn, bg=CARD)
            grid.pack(fill="x", pady=(0, SP_10))

            for col, (count, label, bgc, fgc) in enumerate([
                (str(ok),   "Agrupados", SUCCESS_BG, SUCCESS),
                (str(warn), "Avisos",    WARN_BG,    WARN),
                (str(err),  "Erros",     DANGER_BG,  DANGER),
                (str(conf), "Conferir",  INFO_BG,    MUTED),
            ]):
                grid.columnconfigure(col, weight=1)
                c = tk.Frame(grid, bg=bgc)
                c.grid(row=0, column=col,
                       padx=(0 if col == 0 else SP_6, 0), sticky="nsew")
                tk.Label(c, text=count,
                         font=FONT_NUM, bg=bgc, fg=fgc, pady=SP_6).pack()
                tk.Label(c, text=label,
                         font=FONT_LABEL_S, bg=bgc, fg=fgc,
                         pady=(0, SP_6)).pack()

            # Botoes
            agrupados = os.path.join(dst, "AGRUPADOS")
            conferir  = os.path.join(dst, "CONFERIR")
            btn_f = tk.Frame(inn, bg=CARD)
            btn_f.pack(fill="x")

            if os.path.isdir(agrupados) and ok > 0:
                SinkButton(btn_f, "\u2197  Abrir AGRUPADOS",
                           lambda p=agrupados: os.startfile(p),
                           bg=ACC, fg="#ffffff", font=FONT_BODY,
                           padx=SP_16, pady=5, radius=R_SM,
                           parent_bg=CARD).pack(side="left", padx=(0, SP_8))

            if os.path.isdir(conferir) and conf > 0:
                SinkButton(btn_f, "\u2197  Abrir CONFERIR",
                           lambda p=conferir: os.startfile(p),
                           bg=WARN_BG, fg=WARN, font=FONT_BODY,
                           padx=SP_16, pady=5, radius=R_SM,
                           parent_bg=CARD,
                           shadow_color="#d4b860",
                           hover_color="#fff8e1",
                           pressed_color="#ffe98a").pack(side="left")

            if not self._summary_shown:
                self._summary_frame.pack(fill="x", pady=(0, SP_10),
                                         before=self._log_card)
                self._summary_shown = True

        self.after(0, _do)

    def _hide_summary(self):
        if self._summary_shown:
            self._summary_frame.pack_forget()
            self._summary_shown = False

    # ── Log callback com filtro de verbosidade ────────────────────────────────

    def _make_log_cb(self):
        verbose = self.verbose_mode.get()
        # Tokens que SEMPRE aparecem (resultados e cabecalhos)
        _always = (
            "\u2714", "\u2718", "\u26a0", "\u21b7",   # resultados
            "Fase", "-- Fase", "Escaneando",           # cabecalhos
            "grupo(s)", "RESUMO", "\u2500",
            "PDFs lidos", "Grupos formados",
            "Agrupados com", "Erros no", "conferencia",
            "AGRUPADOS", "CONFERIR", "cancelado",
        )
        def _cb(msg, color=_LOGFG):
            if not msg.strip():
                if verbose:
                    self._log(msg, color)
                return
            if verbose or any(t in msg for t in _always):
                self._log(msg, color)
        return _cb

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _load_last_folders(self):
        try:
            with open(_CFG) as f:
                d = json.load(f)
            if d.get("input") and os.path.isdir(d["input"]):
                self.input_var.set(d["input"])
                self._update_pdf_count(d["input"])
            if d.get("output"):
                self.output_var.set(d["output"])
        except Exception:
            pass

    def _save_last_folders(self, src, dst):
        try:
            with open(_CFG, "w") as f:
                json.dump({"input": src, "output": dst}, f)
        except Exception:
            pass

    def _update_pdf_count(self, folder):
        try:
            n = sum(1 for f in os.listdir(folder) if f.lower().endswith(".pdf"))
            self._pdf_count_label.config(text=f"{n} PDF(s) encontrado(s)")
        except Exception:
            self._pdf_count_label.config(text="")

    def _pick_input(self):
        f = filedialog.askdirectory(title="Selecione a pasta com os PDFs")
        if f:
            self.input_var.set(f)
            self._update_pdf_count(f)
            if not self.output_var.get():
                self.output_var.set(f)

    def _pick_output(self):
        f = filedialog.askdirectory(title="Selecione a pasta de destino")
        if f:
            self.output_var.set(f)

    # ── Drag & Drop ───────────────────────────────────────────────────────────

    @staticmethod
    def _parse_drop(data):
        data = data.strip()
        if data.startswith("{"):
            end = data.find("}")
            if end != -1:
                return data[1:end]
        return data.split()[0] if " " in data and not data.startswith("/") else data

    def _setup_dnd(self):
        if not _DND_OK:
            return
        def _drop_input(ev):
            p = self._parse_drop(ev.data)
            if os.path.isdir(p):
                self.input_var.set(p)
                self._update_pdf_count(p)
                if not self.output_var.get():
                    self.output_var.set(p)
            elif os.path.isfile(p):
                d = os.path.dirname(p)
                self.input_var.set(d)
                self._update_pdf_count(d)
        def _drop_output(ev):
            p = self._parse_drop(ev.data)
            self.output_var.set(
                p if os.path.isdir(p) else os.path.dirname(p))
        self._row_input.register_drop(_drop_input)
        self._row_output.register_drop(_drop_output)

    # ── Log ───────────────────────────────────────────────────────────────────

    def _log(self, msg, color=_LOGFG):
        def _insert():
            self.log.configure(state="normal")
            tag = f"lt_{self._log_tag_idx % 128}"
            self._log_tag_idx += 1
            self.log.insert("end", msg + "\n", tag)
            self.log.tag_config(tag, foreground=color)
            self.log.see("end")
            self.log.configure(state="disabled")
        self.after(0, _insert)

    def _set_current(self, text):
        self.after(0, lambda: self._current_label.config(text=text))

    def _reset_ui(self):
        def _do():
            self._btn_run.configure(state="normal",
                                    text="\u25b6   AGRUPAR PDFs")
            self.btn_cancel.configure(state="disabled")
            self.btn_cancel._fg = MUTED
            self.btn_cancel._bg = "#ffffff"
            self.btn_cancel._redraw_ext()
            self._log_dot.itemconfig("all", fill=MUTED)
            self._current_label.config(text="")
        self.after(0, _do)


    # ── Auto-update ───────────────────────────────────────────────────────────

    def _versao_para_tuple(self, v_str: str) -> tuple:
        import re
        nums = re.findall(r"\d+", v_str)
        return tuple(int(n) for n in nums)

    def _checar_updates(self):
        """Verifica update em background, sem bloquear a UI."""
        if not UPDATE_CHECK_URL or "placeholder" in UPDATE_CHECK_URL:
            return
        def _worker():
            try:
                with urlopen(UPDATE_CHECK_URL, timeout=5) as resp:
                    dados = json.loads(resp.read().decode())
                versao_remota = dados.get("version", "")
                if self._versao_para_tuple(versao_remota) > self._versao_para_tuple(VERSION):
                    self.after(0, self._mostrar_aviso_update, dados)
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _mostrar_aviso_update(self, dados):
        """Exibe notificação de update disponível."""
        versao_nova = dados.get("version", "?")
        download_url = dados.get("download_url", "")
        changelog = dados.get("changelog", "")
        msg = f"Nova versao disponivel: v{versao_nova}\nVersao atual: {VERSION}\n"
        if changelog:
            msg += f"\nNovidades:\n{changelog}"
        msg += "\n\nDeseja abrir a pagina de download?"
        if download_url and messagebox.askyesno("Atualizacao disponivel", msg):
            webbrowser.open(download_url)

    # ── Processamento ─────────────────────────────────────────────────────────

    def _run(self):
        src = self.input_var.get().strip()
        dst = self.output_var.get().strip()
        if not src or not os.path.isdir(src):
            messagebox.showerror("Erro", "Selecione uma pasta de entrada valida.")
            return
        if not dst:
            messagebox.showerror("Erro", "Selecione uma pasta de destino.")
            return

        self._cancelled = False
        self._hide_summary()
        self._btn_run.configure(state="disabled", text="\u23f3  Processando\u2026")
        self.btn_cancel.configure(state="normal")
        self.btn_cancel._fg = DANGER
        self.btn_cancel._bg = DANGER_BG
        self.btn_cancel._redraw_ext()
        self._log_dot.itemconfig("all", fill=SUCCESS)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.progress_label.config(text="")
        self.progress.reset()
        self._current_label.config(text="")

        threading.Thread(target=self._process,
                         args=(src, dst), daemon=True).start()

    def _process(self, src, dst):
        ok = warn = err = conf_count = 0
        try:
            os.makedirs(dst, exist_ok=True)
            self._save_last_folders(src, dst)

            out_real = os.path.realpath(dst)
            in_real  = os.path.realpath(src)
            if out_real.startswith(in_real + os.sep) or out_real == in_real:
                self._log("  \u26a0 Destino dentro da origem "
                          "— agrupados anteriores serao ignorados.", WARN)

            from ..config import OCR_AVAILABLE
            if not OCR_AVAILABLE:
                self._log("  \u26a0 OCR nao disponivel "
                          "— escaneados classificados so pelo nome.", WARN)

            log_cb = self._make_log_cb()
            self._log(f"  Escaneando  \u2192  {src}", MUTED)

            groups, unclassified = scan_folder(
                src, log_callback=log_cb,
                cancel_flag=lambda: self._cancelled)

            if self._cancelled:
                self._log("\n  \u23f9 Processamento cancelado.", WARN)
                return

            if not groups:
                self._log("  Nenhum grupo encontrado. "
                          "Verifique os nomes dos arquivos.", DANGER)
                self._reset_ui()
                return

            # Reprocessamento seletivo
            agrupados_dir  = os.path.join(dst, "AGRUPADOS")
            existing_lower = set()
            if os.path.isdir(agrupados_dir):
                existing_lower = {
                    f.lower() for f in os.listdir(agrupados_dir)
                    if f.lower().endswith("_agrupado.pdf")
                }
            if existing_lower:
                new_g = {}
                skip  = 0
                for gid, docs in groups.items():
                    exp = (build_output_name(gid, docs) + "_AGRUPADO.pdf").lower()
                    if exp in existing_lower:
                        log_cb(f"  \u21b7  Ja processado: {gid[:55]}", MUTED)
                        skip += 1
                    else:
                        new_g[gid] = docs
                if skip:
                    log_cb(f"  \u21b7  {skip} grupo(s) ignorado(s)\n", MUTED)
                groups = new_g

            if not groups:
                self._log("  Todos os grupos ja foram processados.", SUCCESS)
                self._reset_ui()
                return

            total = len(groups)
            self._log(f"  {total} grupo(s) identificado(s)\n", MUTED)

            def _init(t=total):
                self.progress.set(0, t)
                self._progress_max = t
                self.progress_label.config(text="0%")
            self.after(0, _init)

            for i, (gid, files) in enumerate(sorted(groups.items()), 1):
                if self._cancelled:
                    self._log("\n  \u23f9 Cancelado.", WARN)
                    return

                short = gid[:54] + "\u2026" if len(gid) > 54 else gid
                self._set_current(f"Mesclando: {short}")

                msg  = merge_group(gid, files, dst)
                disp = gid[:48] + "\u2026" if len(gid) > 48 else gid

                if "\u2714" in msg:
                    self._log(
                        f"  {i:>2}/{total}   {msg.replace(gid, disp)}", SUCCESS)
                    ok += 1
                elif "\u2718" in msg:
                    self._log(
                        f"  {i:>2}/{total}   {msg.replace(gid, disp)}", DANGER)
                    err += 1
                else:
                    self._log(
                        f"  {i:>2}/{total}   {msg.replace(gid, disp)}", WARN)
                    warn += 1

                pct = int(i / total * 100)
                self.after(0, lambda v=i, p=pct: (
                    self.progress.set(v, self._progress_max),
                    self.progress_label.config(text=f"{p}%"),
                ))

            # CONFERIR
            conf_count = len(unclassified)
            if unclassified:
                self._log(f"\n  {conf_count} arquivo(s) \u2192 CONFERIR", WARN)
                for f in unclassified:
                    log_cb(f"    \u00b7  {f}", MUTED)
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
                        shutil.copy2(s, d)

            # Resumo no log
            total_docs = sum(len(v) for v in groups.values()) + conf_count
            self._log("", MUTED)
            self._log("  " + "\u2500"*52, MUTED)
            self._log("  RESUMO DO PROCESSAMENTO", MUTED)
            self._log("  " + "\u2500"*52, MUTED)
            self._log(f"  \U0001f4c4 PDFs lidos            {total_docs:>4}", MUTED)
            self._log(f"  \U0001f4e6 Grupos formados       {total:>4}", MUTED)
            self._log("", MUTED)
            if ok:
                self._log(f"  \u2714  Agrupados com sucesso  {ok:>4}", SUCCESS)
            if warn:
                self._log(f"  \u26a0  Agrupados com aviso    {warn:>4}", WARN)
            if err:
                self._log(f"  \u2718  Erros no merge         {err:>4}", DANGER)
            if unclassified:
                self._log(f"  \U0001f4c1 Para conferencia       {conf_count:>4}", WARN)
            self._log("", MUTED)
            self._log(f"  Agrupados  \u2192  {agrupados_dir}", MUTED)
            if unclassified:
                self._log(
                    f"  Conferir   \u2192  {os.path.join(dst,'CONFERIR')}", MUTED)
            self._log("  " + "\u2500"*52, MUTED)

            self.after(0, lambda: self.progress_label.config(text="100%"))
            self._show_summary(ok, warn, err, conf_count, dst)

            if self.open_after.get() and (ok > 0 or warn > 0):
                os.startfile(dst)

        except Exception as e:
            self._log(f"\n  Erro inesperado: {e}", DANGER)
        finally:
            self._reset_ui()

    def _cancel(self):
        self._cancelled = True
        self.btn_cancel.configure(state="disabled",
                                  text="Cancelando\u2026")

    def _export_log(self):
        path = filedialog.asksaveasfilename(
            title="Salvar log",
            defaultextension=".txt",
            filetypes=[("Texto", "*.txt"), ("Todos", "*.*")],
            initialfile="AgrupadorPDF_log.txt")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.log.get("1.0", "end"))
        except Exception as e:
            messagebox.showerror("Erro", f"Nao foi possivel salvar:\n{e}")
