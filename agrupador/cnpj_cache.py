"""
cnpj_cache.py — Consulta CNPJ com cache SQLite offline-first.

Fluxo:
  1. Procura no cache SQLite local (~/.agrupadorpdf_cnpj.db)
  2. Se não encontrado ou expirado (>30 dias): consulta BrasilAPI → ReceitaWS → CNPJ.ws
  3. Salva resultado no cache

Retorna dict com razao_social, nome_fantasia, situacao_cadastral,
ou None se offline e não cacheado.

Funciona silenciosamente sem internet: retorna cache se disponível, None se não.
"""

import os
import json
import sqlite3
import threading
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# Cache em ~/.agrupadorpdf_cnpj.db — persiste entre sessões
_DB_PATH = os.path.join(os.path.expanduser("~"), ".agrupadorpdf_cnpj.db")
_CACHE_DAYS = 30          # validade do cache em dias
_TIMEOUT    = 4           # timeout de request em segundos
_lock = threading.Lock()  # thread-safe

# APIs em ordem de preferência
_APIS = [
    "https://brasilapi.com.br/api/cnpj/v1/{cnpj}",
    "https://publica.cnpj.ws/cnpj/{cnpj}",
    "https://receitaws.com.br/v1/cnpj/{cnpj}",
]


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cnpj_cache (
            cnpj         TEXT PRIMARY KEY,
            razao_social TEXT,
            nome_fantasia TEXT,
            situacao     TEXT,
            fetched_at   TEXT
        )
    """)
    conn.commit()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    _init_db(conn)
    return conn


def _fetch_api(cnpj14: str) -> dict | None:
    """Tenta cada API em sequência. Retorna dict normalizado ou None."""
    for url_tpl in _APIS:
        url = url_tpl.format(cnpj=cnpj14)
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "AgrupadorPDF/1.6 (python)"},
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            # Normaliza resposta entre as APIs
            razao = (
                data.get("razao_social")
                or data.get("nome")
                or data.get("company", {}).get("name", "")
                or ""
            ).strip().upper()

            fantasia = (
                data.get("nome_fantasia")
                or data.get("fantasia")
                or ""
            ).strip().upper()

            situacao = (
                data.get("situacao_cadastral")
                or data.get("situacao")
                or data.get("status")
                or "DESCONHECIDA"
            )
            if isinstance(situacao, int):
                situacao = {2: "ATIVA", 3: "SUSPENSA", 4: "INAPTA", 8: "BAIXADA"}.get(
                    situacao, str(situacao)
                )

            if razao:
                return {
                    "cnpj":          cnpj14,
                    "razao_social":  razao,
                    "nome_fantasia": fantasia,
                    "situacao":      str(situacao).upper(),
                }
        except Exception:
            continue   # tenta próxima API

    return None


def lookup_cnpj(cnpj14: str) -> dict | None:
    """
    Consulta CNPJ com cache. Thread-safe.

    Parâmetro: cnpj14 — string com exatamente 14 dígitos (sem pontuação).

    Retorna dict com:
        cnpj, razao_social, nome_fantasia, situacao
    Ou None se não encontrado (offline + não cacheado).
    """
    if not cnpj14 or len(cnpj14) != 14 or not cnpj14.isdigit():
        return None

    cutoff = (datetime.utcnow() - timedelta(days=_CACHE_DAYS)).isoformat()

    with _lock:
        try:
            conn = _get_conn()

            # Verifica cache
            row = conn.execute(
                "SELECT razao_social, nome_fantasia, situacao, fetched_at "
                "FROM cnpj_cache WHERE cnpj=?",
                (cnpj14,),
            ).fetchone()

            if row and row[3] >= cutoff:
                return {
                    "cnpj":          cnpj14,
                    "razao_social":  row[0],
                    "nome_fantasia": row[1],
                    "situacao":      row[2],
                    "source":        "cache",
                }

            # Cache miss ou expirado → consulta API
            data = _fetch_api(cnpj14)
            if data:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO cnpj_cache
                        (cnpj, razao_social, nome_fantasia, situacao, fetched_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        cnpj14,
                        data["razao_social"],
                        data["nome_fantasia"],
                        data["situacao"],
                        datetime.utcnow().isoformat(),
                    ),
                )
                conn.commit()
                data["source"] = "api"
                return data

        except Exception:
            pass   # nunca trava o app por falha de DB ou rede

    return None


def lookup_cnpj_async(cnpj14: str, callback) -> None:
    """
    Versão assíncrona: executa em thread daemon e chama callback(result).
    Callback é chamado com dict ou None.
    """
    def _worker():
        result = lookup_cnpj(cnpj14)
        try:
            callback(result)
        except Exception:
            pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def cache_stats() -> dict:
    """Retorna estatísticas do cache (total, válidos, expirados)."""
    cutoff = (datetime.utcnow() - timedelta(days=_CACHE_DAYS)).isoformat()
    try:
        conn = _get_conn()
        total   = conn.execute("SELECT COUNT(*) FROM cnpj_cache").fetchone()[0]
        validos = conn.execute(
            "SELECT COUNT(*) FROM cnpj_cache WHERE fetched_at >= ?", (cutoff,)
        ).fetchone()[0]
        return {"total": total, "validos": validos, "expirados": total - validos}
    except Exception:
        return {"total": 0, "validos": 0, "expirados": 0}
