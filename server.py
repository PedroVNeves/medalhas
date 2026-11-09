"""Servidor local de busca de medalhistas.

Uso:
    python server.py            # abre em http://localhost:8000
    python server.py --port 9000
"""
import json
from contextlib import closing
import sqlite3
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scraper.common import normalize
from scraper.escolas import query_tokens

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "medalhas.db"
INDEX_HTML = ROOT / "web" / "index.html"
MAX_RESULTS = 2000

NOME = "(' ' || nome_busca)"
MUNICIPIO = "(' ' || municipio_busca)"
ESCOLA = "escola_termos"  # já guardado com espaço no início e no fim


def token_condition(campo: str, tok: str, expansion: list[str]) -> tuple[str, list[str]]:
    """Condição SQL para uma palavra digitada. Casa no início de palavra (' TOK%').

    Para escolas, a palavra também casa se TODAS as palavras da sua expansão aparecerem
    (ex.: IFAL -> INSTITUTO FEDERAL ALAGOAS)."""
    fields = {"nome": [NOME], "escola": [ESCOLA], "tudo": [NOME, ESCOLA, MUNICIPIO]}[campo]
    parts = [f"{f} LIKE ?" for f in fields]
    args = [f"% {tok}%"] * len(fields)
    if campo in ("escola", "tudo") and expansion != [tok]:
        parts.append("(" + " AND ".join(f"{ESCOLA} LIKE ?" for _ in expansion) + ")")
        args += [f"% {e}%" for e in expansion]
    return "(" + " OR ".join(parts) + ")", args


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def search(con, params: dict) -> dict:
    campo = params.get("campo", "nome")
    if campo not in ("nome", "escola", "tudo"):
        campo = "nome"
    tokens = query_tokens(params.get("q", ""))
    where, args = [], []

    for tok, expansion in tokens:
        cond, cond_args = token_condition(campo, tok, expansion)
        where.append(cond)
        args += cond_args

    if params.get("escola_chave"):
        where.append("escola_chave = ?")
        args.append(params["escola_chave"])

    for key in ("competicao", "medalha", "uf", "rede"):
        if params.get(key):
            where.append(f"{key} = ?")
            args.append(params[key])
    if params.get("ano"):
        where.append("ano = ?")
        args.append(int(params["ano"]))
    if params.get("municipio"):
        where.append("municipio_busca = ?")
        args.append(normalize(params["municipio"]))
    if params.get("sem_mencao") == "1":
        where.append("medalha != 'Menção Honrosa'")

    if not tokens and not any(params.get(k) for k in ("ano", "uf", "municipio", "escola_chave")):
        return {"total": 0, "resultados": [], "aviso": "Digite um nome ou escola."}

    sql_where = " AND ".join(where) or "1"
    order = "escola_chave, ano DESC, nome_busca" if campo == "escola" else "nome_busca, ano, competicao"
    total = con.execute(f"SELECT COUNT(*) FROM medalhas WHERE {sql_where}", args).fetchone()[0]
    rows = con.execute(
        f"""SELECT competicao, ano, nivel, nome, escola, rede, esfera, municipio, uf,
                   premio, medalha, pontos, fonte, nome_busca, escola_chave
            FROM medalhas WHERE {sql_where}
            ORDER BY {order} LIMIT {MAX_RESULTS}""",
        args,
    ).fetchall()
    return {"total": total, "limite": MAX_RESULTS, "resultados": [dict(r) for r in rows]}


def stats(con) -> dict:
    by_comp = con.execute(
        "SELECT competicao, COUNT(*) n, MIN(ano) de, MAX(ano) ate FROM medalhas GROUP BY competicao"
    ).fetchall()
    ufs = [r[0] for r in con.execute("SELECT DISTINCT uf FROM medalhas WHERE uf IS NOT NULL ORDER BY uf")]
    anos = [r[0] for r in con.execute("SELECT DISTINCT ano FROM medalhas ORDER BY ano DESC")]
    meta = dict(con.execute("SELECT chave, valor FROM meta").fetchall())
    return {"competicoes": [dict(r) for r in by_comp], "ufs": ufs, "anos": anos, **meta}


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, ctype: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path in ("/", "/index.html"):
                self._send(INDEX_HTML.read_bytes(), "text/html; charset=utf-8")
            elif url.path in ("/api/busca", "/api/stats"):
                with closing(connect()) as con:
                    self._json(search(con, params) if url.path == "/api/busca" else stats(con))
            else:
                self._send(b"Not found", "text/plain", 404)
        except Exception as e:  # noqa: BLE001
            self._json({"erro": str(e)}, 500)

    def _json(self, data, status=200) -> None:
        self._send(json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status)

    def log_message(self, *args) -> None:
        pass


def main() -> None:
    if not DB_PATH.exists():
        sys.exit("Base não encontrada. Rode primeiro: python build_db.py")
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8000
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}"
    print(f"Busca de medalhistas rodando em {url}  (Ctrl+C para sair)")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
