"""
feedback_store.py — Armazena correções do usuário e alimenta calibração de pesos.

Tabelas:
  groupings     — histórico de agrupamentos com score e resultado
  corrections   — correções manuais (split/merge)
  cnpj_aliases  — pares de CNPJs confirmados como mesmo fornecedor
  signal_weights — pesos aprendidos por Fellegi-Sunter empírico

Banco em ~/.agrupadorpdf_feedback.db
"""

import os, json, sqlite3, threading, math

_DB_PATH = os.path.join(os.path.expanduser("~"), ".agrupadorpdf_feedback.db")
_lock    = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS groupings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    gid        TEXT    NOT NULL,
    doc_types  TEXT,
    score      REAL,
    signals    TEXT,
    accepted   INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS corrections (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    type       TEXT NOT NULL,
    gid_from   TEXT,
    gid_to     TEXT,
    reason     TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS cnpj_aliases (
    cnpj_a     TEXT NOT NULL,
    cnpj_b     TEXT NOT NULL,
    confirmed  INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (cnpj_a, cnpj_b)
);
CREATE TABLE IF NOT EXISTS signal_weights (
    signal     TEXT PRIMARY KEY,
    weight     REAL NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

_DEFAULT_WEIGHTS = {
    "nf_key": 0.50,
    "cnpj":   0.30,
    "value":  0.15,
    "entity": 0.10,
    "period": 0.05,
}


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH, check_same_thread=False)
    c.executescript(_SCHEMA)
    c.commit()
    return c


def _ensure_weights(c: sqlite3.Connection) -> None:
    if c.execute("SELECT COUNT(*) FROM signal_weights").fetchone()[0] == 0:
        c.executemany(
            "INSERT OR IGNORE INTO signal_weights (signal,weight) VALUES (?,?)",
            list(_DEFAULT_WEIGHTS.items())
        )
        c.commit()


# ── Gravação ──────────────────────────────────────────────────────────────────

def record_grouping(gid: str, doc_types: list, score: float, signals: dict) -> int | None:
    with _lock:
        try:
            c = _conn()
            r = c.execute(
                "INSERT INTO groupings (gid,doc_types,score,signals) VALUES (?,?,?,?)",
                (gid, json.dumps(doc_types), score, json.dumps(signals))
            )
            c.commit(); return r.lastrowid
        except Exception: return None


def record_acceptance(grouping_id: int, accepted: bool) -> None:
    with _lock:
        try:
            c = _conn()
            c.execute("UPDATE groupings SET accepted=? WHERE id=?",
                      (1 if accepted else 0, grouping_id))
            c.commit()
        except Exception: pass


def record_correction(type_: str, gid_from: str, gid_to: str=None, reason: str=None) -> None:
    with _lock:
        try:
            c = _conn()
            c.execute("INSERT INTO corrections (type,gid_from,gid_to,reason) VALUES (?,?,?,?)",
                      (type_, gid_from, gid_to, reason))
            c.commit()
        except Exception: pass


def confirm_cnpj_alias(cnpj_a: str, cnpj_b: str) -> None:
    if not cnpj_a or not cnpj_b or cnpj_a == cnpj_b: return
    a, b = sorted([cnpj_a, cnpj_b])
    with _lock:
        try:
            c = _conn()
            c.execute("INSERT OR IGNORE INTO cnpj_aliases (cnpj_a,cnpj_b) VALUES (?,?)", (a,b))
            c.commit()
        except Exception: pass


# ── Leitura ───────────────────────────────────────────────────────────────────

def get_cnpj_aliases() -> set[tuple[str,str]]:
    with _lock:
        try:
            c = _conn()
            return {(r[0],r[1]) for r in
                    c.execute("SELECT cnpj_a,cnpj_b FROM cnpj_aliases WHERE confirmed=1").fetchall()}
        except Exception: return set()


def get_learned_weights() -> dict[str,float]:
    with _lock:
        try:
            c = _conn(); _ensure_weights(c)
            rows = c.execute("SELECT signal,weight FROM signal_weights").fetchall()
            if rows: return {r[0]:r[1] for r in rows}
        except Exception: pass
    return dict(_DEFAULT_WEIGHTS)


# ── Calibração Fellegi-Sunter empírico ────────────────────────────────────────

def update_weights_from_feedback() -> dict[str,float] | None:
    """
    Recalcula pesos usando histórico de aceites/rejeições.
    Retorna novos pesos ou None se dados insuficientes (<10 revisados).

    Algoritmo:
      m_prob = P(sinal bate | par é correto)  → fração de grupos aceitos com sinal ✔
      u_prob = P(sinal bate | par é incorreto) → fração de grupos rejeitados com sinal ✔
      peso   = log2(m_prob / u_prob), normalizado para [0.02, 0.60]
    """
    with _lock:
        try:
            c = _conn(); _ensure_weights(c)
            rows = c.execute(
                "SELECT signals,accepted FROM groupings WHERE accepted IS NOT NULL"
            ).fetchall()

            if len(rows) < 10: return None

            stats: dict[str,dict] = {
                s: {"cm":0,"ct":0,"wm":0,"wt":0} for s in _DEFAULT_WEIGHTS
            }
            for sig_json, accepted in rows:
                try: signals = json.loads(sig_json or "{}")
                except Exception: continue
                for sig in _DEFAULT_WEIGHTS:
                    matched = str(signals.get(sig,"")).startswith("✔")
                    if accepted:
                        stats[sig]["ct"] += 1
                        if matched: stats[sig]["cm"] += 1
                    else:
                        stats[sig]["wt"] += 1
                        if matched: stats[sig]["wm"] += 1

            new_w: dict[str,float] = {}
            for sig, s in stats.items():
                if s["ct"] < 3 or s["wt"] < 3:
                    new_w[sig] = _DEFAULT_WEIGHTS[sig]; continue
                m = (s["cm"] + 0.5) / (s["ct"] + 1)
                u = (s["wm"] + 0.5) / (s["wt"] + 1)
                new_w[sig] = max(0.02, min(0.60, math.log2(m / u) if u > 0 else 0.02))

            total = sum(new_w.values())
            if total > 0:
                new_w = {k: round(v/total, 4) for k,v in new_w.items()}

            c.executemany(
                "INSERT OR REPLACE INTO signal_weights (signal,weight,updated_at) VALUES (?,?,datetime('now'))",
                list(new_w.items())
            )
            c.commit()
            return new_w
        except Exception: return None


def stats() -> dict:
    with _lock:
        try:
            c = _conn(); _ensure_weights(c)
            return {
                "groupings_total":    c.execute("SELECT COUNT(*) FROM groupings").fetchone()[0],
                "groupings_accepted": c.execute("SELECT COUNT(*) FROM groupings WHERE accepted=1").fetchone()[0],
                "groupings_rejected": c.execute("SELECT COUNT(*) FROM groupings WHERE accepted=0").fetchone()[0],
                "corrections":        c.execute("SELECT COUNT(*) FROM corrections").fetchone()[0],
                "cnpj_aliases":       c.execute("SELECT COUNT(*) FROM cnpj_aliases").fetchone()[0],
            }
        except Exception: return {}
