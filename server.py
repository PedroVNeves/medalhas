"""Servidor local: API de busca, rankings, perfis e a interface web.

Uso:
    python server.py                 # abre em http://localhost:8000
    python server.py --port 9000 --no-browser
"""
import json
import mimetypes
import sqlite3
import sys
import threading
import traceback
import webbrowser
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import gamificacao as gm
import olimpiadas as olp
from scraper.common import normalize
from scraper.escolas import query_tokens

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "medalhas.db"
WEB_DIR = ROOT / "web"
MAX_RESULTS = 2000

# ---------------------------------------------------------------- helpers


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def rows_as_dicts(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


_cache: dict = {}
_cache_lock = threading.Lock()


def cached(key, fn):
    """Cache em memória invalidado quando a base é regerada."""
    stamp = DB_PATH.stat().st_mtime
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] == stamp:
            return hit[1]
    value = fn()
    with _cache_lock:
        _cache.pop(key, None)
        _cache[key] = (stamp, value)
        while len(_cache) > 60:  # cada agregado pode ter ~76 mil itens: mantém só os 60 mais recentes
            _cache.pop(next(iter(_cache)))
    return value


def build_filters(params: dict) -> tuple[list[str], list]:
    where, args = [], []
    # filtros de múltipla escolha: valores separados por vírgula ("OBMEP,OBM", "1,2,3,Universitário")
    for key in ("competicao", "nivel", "area"):
        valores = [v.strip() for v in (params.get(key) or "").split(",") if v.strip()]
        if valores:
            where.append(f"{key} IN ({','.join('?' * len(valores))})")
            args += valores
    for key in ("medalha", "uf", "rede", "escola_chave", "esfera"):
        if params.get(key):
            where.append(f"{key} = ?")
            args.append(params[key])
    if params.get("ano"):
        where.append("ano = ?")
        args.append(int(params["ano"]))
    if params.get("ano_de"):
        where.append("ano >= ?")
        args.append(int(params["ano_de"]))
    if params.get("ano_ate"):
        where.append("ano <= ?")
        args.append(int(params["ano_ate"]))
    if params.get("municipio"):
        where.append("municipio_busca = ?")
        args.append(normalize(params["municipio"]))
    if params.get("sem_mencao") == "1":
        where.append("medalha != 'Menção Honrosa'")
    return where, args


AGG = """SUM(medalha='Ouro') AS ouro, SUM(medalha='Prata') AS prata, SUM(medalha='Bronze') AS bronze,
         SUM(medalha='Menção Honrosa') AS mencao, COUNT(*) AS total, SUM(xp) AS xp, SUM(impa) AS impa,
         MIN(ano) AS de, MAX(ano) AS ate"""

# ---------------------------------------------------------------- busca

NOME = "(' ' || nome_busca)"
MUNICIPIO = "(' ' || municipio_busca)"
ESCOLA = "escola_termos"


def token_condition(campo: str, tok: str, expansion: list[str]) -> tuple[str, list[str]]:
    """Casa no início de palavra; para escolas, também casa pela expansão da sigla (IFAL -> ...)."""
    fields = {"nome": [NOME], "escola": [ESCOLA], "tudo": [NOME, ESCOLA, MUNICIPIO]}[campo]
    parts = [f"{f} LIKE ?" for f in fields]
    args = [f"% {tok}%"] * len(fields)
    if campo in ("escola", "tudo") and expansion != [tok]:
        parts.append("(" + " AND ".join(f"{ESCOLA} LIKE ?" for _ in expansion) + ")")
        args += [f"% {e}%" for e in expansion]
    return "(" + " OR ".join(parts) + ")", args


def search(con, params: dict) -> dict:
    campo = params.get("campo", "nome")
    if campo not in ("nome", "escola", "tudo"):
        campo = "nome"
    tokens = query_tokens(params.get("q", ""))
    where, args = build_filters(params)
    for tok, expansion in tokens:
        cond, cond_args = token_condition(campo, tok, expansion)
        where.append(cond)
        args += cond_args
    if not tokens and not any(params.get(k) for k in ("ano", "uf", "municipio", "escola_chave")):
        return {"total": 0, "resultados": []}

    sql_where = " AND ".join(where) or "1"
    order = "escola_chave, ano DESC, nome_busca" if campo == "escola" else "nome_busca, ano, competicao"
    total = con.execute(f"SELECT COUNT(*) FROM medalhas WHERE {sql_where}", args).fetchone()[0]
    rows = rows_as_dicts(con.execute(
        f"""SELECT competicao, ano, nivel, nome, escola, rede, esfera, municipio, uf, premio, medalha,
                   pontos, fonte, nome_busca, escola_chave, aluno_id, xp
            FROM medalhas WHERE {sql_where} ORDER BY {order} LIMIT {MAX_RESULTS}""", args))
    return {"total": total, "limite": MAX_RESULTS, "resultados": rows}

# ---------------------------------------------------------------- tabelas-resumo (pré-calculadas no build)

FILTER_KEYS = ("competicao", "area", "medalha", "uf", "rede", "nivel", "escola_chave", "esfera", "ano", "ano_de",
               "ano_ate", "municipio", "sem_mencao")
SUMMARY_COLS = {
    "alunos": "id, nome, uf, competicoes, escola, escola_chave, municipio, ouro, prata, bronze, mencao, total, xp, impa, de, ate",
    "escolas": "id, nome, municipio, uf, rede, esfera, alunos, ouro, prata, bronze, mencao, total, xp, impa, de, ate",
}


def summary_xp(con, table: str, ids: list[str]) -> dict:
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    return dict(con.execute(f"SELECT id, xp FROM {table} WHERE id IN ({marks})", ids).fetchall())


def latest_school(con, aluno_ids: list[str]) -> dict:
    if not aluno_ids:
        return {}
    marks = ",".join("?" * len(aluno_ids))
    return {r["id"]: {"escola": r["escola"], "escola_chave": r["escola_chave"], "municipio": r["municipio"]}
            for r in con.execute(f"SELECT id, escola, escola_chave, municipio FROM alunos WHERE id IN ({marks})", aluno_ids)}


SORT_KEYS = {
    "xp": lambda r: (-r["xp"], -r["ouro"], -r["prata"], -r["bronze"]),
    "medalhas": lambda r: (-r["ouro"], -r["prata"], -r["bronze"], -r["xp"]),
    "total": lambda r: (-(r["ouro"] + r["prata"] + r["bronze"]), -r["xp"]),
    "impa": lambda r: (-r["impa"], -r["xp"], -r["ouro"]),
}


def aggregate(con, tipo: str, params: dict) -> list[dict]:
    """Linhas agregadas (um item por aluno/escola/estado) para os filtros dados. Cacheado."""
    filtros = {k: params[k] for k in FILTER_KEYS if params.get(k)}

    def build():
        if tipo in SUMMARY_COLS and not filtros:
            return rows_as_dicts(con.execute(f"SELECT {SUMMARY_COLS[tipo]} FROM {tipo}"))
        where, args = build_filters(filtros)
        if tipo == "estados":
            where.append("uf IS NOT NULL")
            if not filtros:  # contagens de alunos/escolas vêm das tabelas-resumo
                rows = rows_as_dicts(con.execute(f"SELECT uf AS id, uf AS nome, {AGG} FROM medalhas WHERE uf IS NOT NULL GROUP BY uf || ''"))
                al = dict(con.execute("SELECT uf, COUNT(*) FROM alunos GROUP BY uf").fetchall())
                es = dict(con.execute("SELECT uf, COUNT(*) FROM escolas GROUP BY uf").fetchall())
                for r in rows:
                    r["alunos"], r["escolas"] = al.get(r["id"], 0), es.get(r["id"], 0)
                return rows
            return rows_as_dicts(con.execute(
                f"""SELECT uf AS id, uf AS nome, COUNT(DISTINCT aluno_id) AS alunos,
                           COUNT(DISTINCT NULLIF(escola_chave, '')) AS escolas, {AGG}
                    FROM medalhas WHERE {' AND '.join(where)} GROUP BY uf || ''""", args))
        if tipo == "escolas":
            where.append("escola_chave != ''")
            return rows_as_dicts(con.execute(
                f"""SELECT escola_chave AS id, MAX(escola) AS nome, MAX(municipio) AS municipio, MAX(uf) AS uf,
                           MAX(rede) AS rede, MAX(esfera) AS esfera, COUNT(DISTINCT aluno_id) AS alunos, {AGG}
                    FROM medalhas WHERE {' AND '.join(where)} GROUP BY escola_chave || ''""", args))
        return rows_as_dicts(con.execute(
            f"""SELECT aluno_id AS id, COALESCE(MAX(CASE WHEN competicao = 'OBM' THEN nome END), MAX(nome)) AS nome,
                       MAX(uf) AS uf, GROUP_CONCAT(DISTINCT competicao) AS competicoes, {AGG}
                FROM medalhas WHERE {' AND '.join(where) or '1'} GROUP BY aluno_id || ''""", args))

    return cached(("agg", tipo, tuple(sorted(filtros.items()))), build)


def ranking(con, params: dict) -> dict:
    tipo = params.get("tipo", "alunos")
    if tipo not in ("alunos", "escolas", "estados"):
        tipo = "alunos"
    ordem = params.get("ordem", "xp") if params.get("ordem") in SORT_KEYS else "xp"
    limite = min(int(params.get("limite", 50)), 200)
    offset = max(int(params.get("offset", 0)), 0)

    key = SORT_KEYS[ordem]
    ordered = cached(("sorted", tipo, ordem, tuple(sorted((k, params[k]) for k in FILTER_KEYS if params.get(k)))),
                     lambda: sorted(aggregate(con, tipo, params), key=lambda r: (key(r), r["nome"] or "")))

    # RANK(): empates (mesma chave de ordenação) dividem a posição
    page = []
    pos, prev = 0, None
    for i, r in enumerate(ordered[: offset + limite], 1):
        k = key(r)
        if k != prev:
            pos, prev = i, k
        if i > offset:
            page.append(dict(r, pos=pos))

    if tipo == "alunos":
        info = latest_school(con, [it["id"] for it in page])
        xp = summary_xp(con, "alunos", [it["id"] for it in page])
        for it in page:
            it.update({k: v for k, v in info.get(it["id"], {}).items() if not it.get(k)})
            it["tier"] = gm.tier(xp.get(it["id"], it["xp"]))
    elif tipo == "escolas":
        xp = summary_xp(con, "escolas", [it["id"] for it in page])
        for it in page:
            it["tier"] = gm.tier(xp.get(it["id"], it["xp"]), escola=True)
    return {"tipo": tipo, "total": len(ordered), "offset": offset, "limite": limite, "itens": page}

# ---------------------------------------------------------------- perfis


def perfil_aluno(con, aluno_id: str) -> dict:
    rows = rows_as_dicts(con.execute(
        """SELECT competicao, ano, nivel, nome, escola, escola_chave, rede, esfera, municipio, uf,
                  premio, medalha, pontos, fonte, xp, impa, aluno_id
           FROM medalhas WHERE aluno_id = ? ORDER BY ano DESC, competicao""", (aluno_id,)))
    if not rows:
        return {"erro": "Aluno não encontrado"}
    resumo = con.execute("SELECT * FROM alunos WHERE id = ?", (aluno_id,)).fetchone()
    xp, pos, pos_uf, nome, uf = resumo["xp"], resumo["pos"], resumo["pos_uf"], resumo["nome"], resumo["uf"]
    total = con.execute("SELECT COUNT(*) FROM alunos").fetchone()[0]
    total_uf = con.execute("SELECT COUNT(*) FROM alunos WHERE uf IS ?", (uf,)).fetchone()[0]
    rank_impa = (con.execute("SELECT COUNT(*) FROM alunos WHERE impa > ?", (resumo["impa"],)).fetchone()[0] + 1
                 if resumo["impa"] else None)

    # quem está logo acima no ranking nacional ("próximo alvo")
    alvo = con.execute("SELECT id, nome, xp FROM alunos WHERE xp > ? ORDER BY xp, nome LIMIT 1", (xp,)).fetchone()
    acima = {"id": alvo["id"], "nome": alvo["nome"], "xp": alvo["xp"], "diferenca": alvo["xp"] - xp} if alvo else None

    escolas = []
    for r in rows:
        if r["escola_chave"] and r["escola_chave"] not in {e["escola_chave"] for e in escolas}:
            escolas.append({"escola": r["escola"], "escola_chave": r["escola_chave"], "municipio": r["municipio"]})

    return {
        "id": aluno_id, "nome": nome, "uf": uf,
        "municipios": sorted({r["municipio"] for r in rows if r["municipio"]}),
        "escolas": escolas, "xp": xp, "tier": gm.tier(xp),
        "rank": pos, "rank_total": total, "rank_uf": pos_uf, "rank_uf_total": total_uf,
        "impa": resumo["impa"], "rank_impa": rank_impa,
        "medalhas": gm.medal_counts(rows), "anos": sorted({r["ano"] for r in rows if r["ano"]}),
        "conquistas": gm.conquistas_aluno(rows), "acima": acima, "premiacoes": rows,
    }


def perfil_escola(con, chave: str) -> dict:
    rows = rows_as_dicts(con.execute(
        """SELECT competicao, ano, nivel, nome, escola, rede, esfera, municipio, uf, premio, medalha,
                  fonte, xp, impa, aluno_id
           FROM medalhas WHERE escola_chave = ? ORDER BY ano DESC, nome""", (chave,)))
    if not rows:
        return {"erro": "Escola não encontrada"}
    resumo = con.execute("SELECT * FROM escolas WHERE id = ?", (chave,)).fetchone()
    xp, pos, pos_uf, uf = resumo["xp"], resumo["pos"], resumo["pos_uf"], resumo["uf"]
    total = con.execute("SELECT COUNT(*) FROM escolas").fetchone()[0]
    total_uf = con.execute("SELECT COUNT(*) FROM escolas WHERE uf IS ?", (uf,)).fetchone()[0]

    variantes: dict = {}
    for r in rows:
        variantes[r["escola"]] = variantes.get(r["escola"], 0) + 1
    nomes = sorted(variantes, key=lambda k: -variantes[k])

    serie: dict = {}
    for r in rows:
        s = serie.setdefault(r["ano"], {"ano": r["ano"], "Ouro": 0, "Prata": 0, "Bronze": 0})
        if r["medalha"] in s:
            s[r["medalha"]] += 1

    alunos: dict = {}
    for r in rows:
        a = alunos.setdefault(r["aluno_id"], {"id": r["aluno_id"], "nome": r["nome"], "xp": 0,
                                              "ouro": 0, "prata": 0, "bronze": 0, "anos": set()})
        a["xp"] += r["xp"]
        a["anos"].add(r["ano"])
        key = {"Ouro": "ouro", "Prata": "prata", "Bronze": "bronze"}.get(r["medalha"])
        if key:
            a[key] += 1
    top = sorted(alunos.values(), key=lambda a: (-a["xp"], a["nome"]))[:15]
    for a in top:
        a["anos"] = sorted(a["anos"])

    return {
        "id": chave, "nome": nomes[0], "variantes": nomes[1:], "municipio": rows[0]["municipio"], "uf": uf,
        "rede": rows[0]["rede"], "esfera": rows[0]["esfera"], "xp": xp, "tier": gm.tier(xp, escola=True),
        "rank": pos, "rank_total": total, "rank_uf": pos_uf, "rank_uf_total": total_uf,
        "impa": resumo["impa"], "medalhas": gm.medal_counts(rows), "alunos": len(alunos),
        "anos": sorted({r["ano"] for r in rows}), "serie": [serie[a] for a in sorted(serie)],
        "top_alunos": top, "conquistas": gm.conquistas_escola(rows, pos, pos_uf),
        "recentes": rows[:60],
    }

# ---------------------------------------------------------------- visão geral


def overview(con) -> dict:
    def build():
        tot = dict(con.execute(f"SELECT {AGG} FROM medalhas").fetchone())
        tot["alunos"] = con.execute("SELECT COUNT(*) FROM alunos").fetchone()[0]
        tot["escolas"] = con.execute("SELECT COUNT(*) FROM escolas").fetchone()[0]
        serie = rows_as_dicts(con.execute(
            """SELECT ano, competicao, SUM(medalha='Ouro') AS ouro, SUM(medalha='Prata') AS prata,
                      SUM(medalha='Bronze') AS bronze, COUNT(*) AS total
               FROM medalhas GROUP BY ano, competicao ORDER BY ano"""))
        comps = rows_as_dicts(con.execute(
            "SELECT competicao, COUNT(*) AS n, MIN(ano) AS de, MAX(ano) AS ate FROM medalhas GROUP BY competicao"))
        stats = {c["competicao"]: c for c in comps}
        olimpiadas = [dict(o, **{k: stats.get(o["sigla"], {}).get(k) for k in ("n", "de", "ate")})
                      for o in olp.catalogo()]
        areas = sorted({o["area"] for o in olimpiadas})
        ordem_nivel = {"1": 1, "2": 2, "3": 3, "Universitário": 9}
        niveis = [{"id": r[0], "n": r[1], "competicoes": r[2].split(",")} for r in con.execute(
            """SELECT nivel, COUNT(*), GROUP_CONCAT(DISTINCT competicao) FROM medalhas
               WHERE nivel IS NOT NULL GROUP BY nivel""")]
        niveis.sort(key=lambda n: (ordem_nivel.get(n["id"], 5), n["id"]))
        meta = dict(con.execute("SELECT chave, valor FROM meta").fetchall())
        ufs = [r[0] for r in con.execute("SELECT DISTINCT uf FROM medalhas WHERE uf IS NOT NULL ORDER BY uf")]
        anos = [r[0] for r in con.execute("SELECT DISTINCT ano FROM medalhas ORDER BY ano DESC")]
        return {"totais": tot, "serie": serie, "competicoes": comps, "ufs": ufs, "anos": anos,
                "olimpiadas": olimpiadas, "areas": areas, "niveis": niveis, "fonte_pontos": gm.FONTE_PONTOS,
                "tiers_aluno": [{"nome": n, "min": m, "cor": c} for n, m, c in gm.TIERS_ALUNO],
                "tiers_escola": [{"nome": n, "min": m, "cor": c} for n, m, c in gm.TIERS_ESCOLA],
                "conquistas_aluno": gm.conquistas_aluno([]),
                "conquistas_escola": gm.conquistas_escola([], None, None), **meta}
    data = dict(cached("overview", build))
    data["top_alunos"] = cached("top_alunos", lambda: ranking(con, {"tipo": "alunos", "limite": 10})["itens"])
    data["top_escolas"] = cached("top_escolas", lambda: ranking(con, {"tipo": "escolas", "limite": 10})["itens"])
    data["estados"] = cached("estados", lambda: ranking(con, {"tipo": "estados", "limite": 30})["itens"])
    return data

# ---------------------------------------------------------------- HTTP


ROUTES = {
    "/api/busca": lambda con, p: search(con, p),
    "/api/ranking": lambda con, p: ranking(con, p),
    "/api/aluno": lambda con, p: perfil_aluno(con, p.get("id", "")),
    "/api/escola": lambda con, p: perfil_escola(con, p.get("id", "")),
    "/api/overview": lambda con, p: overview(con),
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, ctype: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status=200) -> None:
        self._send(json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path in ROUTES:
                with closing(connect()) as con:
                    self._json(ROUTES[url.path](con, params))
                return
            rel = "index.html" if url.path in ("/", "") else unquote(url.path.lstrip("/"))
            target = (WEB_DIR / rel).resolve()
            if WEB_DIR.resolve() in target.parents and target.is_file():
                ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype.endswith("javascript"):
                    ctype += "; charset=utf-8"
                self._send(target.read_bytes(), ctype)
            else:
                self._send(b"Not found", "text/plain", 404)
        except ValueError as e:  # ex.: ano=abc, offset=xyz
            self._json({"erro": f"parâmetro inválido: {e}"}, 400)
        except Exception as e:  # noqa: BLE001 — bug do servidor: registra no terminal com o traceback
            traceback.print_exc()
            self._json({"erro": f"erro interno do servidor ({type(e).__name__}: {e})"}, 500)

    def log_message(self, *args) -> None:
        pass


def warm_up() -> None:
    """Pré-calcula as consultas pesadas para a primeira visita ser instantânea."""
    with closing(connect()) as con:
        overview(con)
        for tipo in ("alunos", "escolas", "estados"):
            for ordem in SORT_KEYS:
                ranking(con, {"tipo": tipo, "ordem": ordem})


def main() -> None:
    if not DB_PATH.exists():
        sys.exit("Base não encontrada. Rode primeiro: python build_db.py")
    mimetypes.add_type("text/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8000
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=warm_up, daemon=True).start()
    url = f"http://localhost:{port}"
    print(f"Medalhas rodando em {url}  (Ctrl+C para sair)")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
