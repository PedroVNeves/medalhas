"""Coleta OBMEP + OBM e gera data/medalhas.db.

Uso:
    python build_db.py            # usa o cache local quando existir
    python build_db.py --refresh  # apaga o cache e baixa tudo de novo
"""
import shutil
import sqlite3
import sys
import time

import olimpiadas as olp
from scraper.common import CACHE_DIR, ROOT, normalize, title_case
from scraper.escolas import school_fields

DB_PATH = ROOT / "data" / "medalhas.db"

SCHEMA = """
CREATE TABLE medalhas (
    id              INTEGER PRIMARY KEY,
    competicao      TEXT NOT NULL,
    ano             INTEGER,
    nivel           TEXT,
    nome            TEXT NOT NULL,
    escola          TEXT,
    rede            TEXT,
    esfera          TEXT,
    municipio       TEXT,
    uf              TEXT,
    premio          TEXT,
    medalha         TEXT,
    pontos          TEXT,
    fonte           TEXT,
    nome_busca      TEXT NOT NULL,
    escola_busca    TEXT,
    escola_termos   TEXT,
    escola_chave    TEXT,
    municipio_busca TEXT,
    aluno_id        TEXT NOT NULL,
    xp              INTEGER NOT NULL,
    impa            INTEGER NOT NULL,
    area            TEXT
);
CREATE INDEX idx_aluno  ON medalhas(aluno_id);
CREATE INDEX idx_chave  ON medalhas(escola_chave);
CREATE INDEX idx_nome   ON medalhas(nome_busca);
CREATE INDEX idx_escola ON medalhas(escola_busca);
CREATE INDEX idx_ano    ON medalhas(ano);
CREATE INDEX idx_uf     ON medalhas(uf);
CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT);
"""

COLUMNS = ["competicao", "ano", "nivel", "nome", "escola", "rede", "esfera",
           "municipio", "uf", "premio", "medalha", "pontos", "fonte"]


SUMMARY_SCHEMA = """
CREATE TABLE alunos (
    id TEXT PRIMARY KEY, nome TEXT, uf TEXT, competicoes TEXT, escola TEXT, escola_chave TEXT,
    municipio TEXT, ouro INT, prata INT, bronze INT, mencao INT, total INT, xp INT, impa INT,
    de INT, ate INT, pos INT, pos_uf INT
);
CREATE TABLE escolas (
    id TEXT PRIMARY KEY, nome TEXT, municipio TEXT, uf TEXT, rede TEXT, esfera TEXT, alunos INT,
    ouro INT, prata INT, bronze INT, mencao INT, total INT, xp INT, impa INT, de INT, ate INT, pos INT, pos_uf INT
);
CREATE INDEX idx_alunos_xp ON alunos(xp DESC);
CREATE INDEX idx_alunos_uf ON alunos(uf, xp DESC);
CREATE INDEX idx_escolas_xp ON escolas(xp DESC);
CREATE INDEX idx_escolas_uf ON escolas(uf, xp DESC);
"""

MEDAL_FIELD = {"Ouro": "ouro", "Prata": "prata", "Bronze": "bronze", "Menção Honrosa": "mencao"}


def _rank(items: list[dict], key: str) -> None:
    """Preenche items[i][key] com RANK() por xp (empates dividem a posição)."""
    items.sort(key=lambda a: -a["xp"])
    pos, prev = 0, None
    for i, it in enumerate(items, 1):
        if it["xp"] != prev:
            pos, prev = i, it["xp"]
        it[key] = pos


def build_summaries(con: sqlite3.Connection) -> None:
    """Tabelas-resumo (alunos, escolas) com totais e posição nacional/estadual pré-calculados."""
    con.executescript(SUMMARY_SCHEMA)
    alunos: dict = {}
    escolas: dict = {}
    for (aid, nome, uf, comp, ano, medalha, xp, impa, escola, chave, municipio, rede, esfera) in con.execute(
            """SELECT aluno_id, nome, uf, competicao, ano, medalha, xp, impa, escola, escola_chave, municipio, rede, esfera
               FROM medalhas ORDER BY ano DESC, competicao DESC"""):
        a = alunos.get(aid)
        if a is None:
            a = alunos[aid] = {"id": aid, "nome": nome, "uf": uf, "comps": set(), "escola": None,
                               "escola_chave": None, "municipio": None, "ouro": 0, "prata": 0, "bronze": 0,
                               "mencao": 0, "total": 0, "xp": 0, "impa": 0, "de": ano, "ate": ano}
        if comp == "OBM" and a["nome"] != nome and "OBM" not in a["comps"]:
            a["nome"] = nome  # a OBM publica nomes com acento e caixa mista
        a["comps"].add(comp)
        a["escola"] = a["escola"] or escola
        a["escola_chave"] = a["escola_chave"] or (chave or None)
        a["municipio"] = a["municipio"] or municipio
        a["total"] += 1
        a["xp"] += xp
        a["impa"] += impa
        a["de"], a["ate"] = min(a["de"], ano), max(a["ate"], ano)
        if medalha in MEDAL_FIELD:
            a[MEDAL_FIELD[medalha]] += 1

        if chave:
            e = escolas.get(chave)
            if e is None:
                e = escolas[chave] = {"id": chave, "nomes": {}, "municipio": municipio, "uf": uf, "rede": rede,
                                      "esfera": esfera, "alunos": set(), "ouro": 0, "prata": 0, "bronze": 0,
                                      "mencao": 0, "total": 0, "xp": 0, "impa": 0, "de": ano, "ate": ano}
            e["nomes"][escola] = e["nomes"].get(escola, 0) + 1
            e["alunos"].add(aid)
            e["total"] += 1
            e["xp"] += xp
            e["impa"] += impa
            e["de"], e["ate"] = min(e["de"], ano), max(e["ate"], ano)
            if medalha in MEDAL_FIELD:
                e[MEDAL_FIELD[medalha]] += 1

    for group in (alunos, escolas):
        items = list(group.values())
        _rank(items, "pos")
        by_uf: dict = {}
        for it in items:
            by_uf.setdefault(it["uf"], []).append(it)
        for lst in by_uf.values():
            _rank(lst, "pos_uf")

    con.executemany(
        "INSERT INTO alunos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(a["id"], a["nome"], a["uf"], ",".join(sorted(a["comps"], reverse=True)), a["escola"], a["escola_chave"],
          a["municipio"], a["ouro"], a["prata"], a["bronze"], a["mencao"], a["total"], a["xp"], a["impa"], a["de"], a["ate"],
          a["pos"], a["pos_uf"]) for a in alunos.values()])
    con.executemany(
        "INSERT INTO escolas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(e["id"], max(e["nomes"], key=e["nomes"].get), e["municipio"], e["uf"], e["rede"], e["esfera"],
          len(e["alunos"]), e["ouro"], e["prata"], e["bronze"], e["mencao"], e["total"], e["xp"], e["impa"], e["de"], e["ate"],
          e["pos"], e["pos_uf"]) for e in escolas.values()])


def main() -> None:
    if "--refresh" in sys.argv and CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)

    records = []
    for sigla, info in olp.OLIMPIADAS.items():
        records += info["scrape"]()

    DB_PATH.parent.mkdir(exist_ok=True)
    tmp = DB_PATH.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    rows = []
    for r in records:
        nome = r["nome"]
        if nome.isupper():
            nome = title_case(nome)
        row = dict(r, nome=nome)
        termos, chave = school_fields(r.get("escola"), r.get("municipio"), r.get("uf"))
        nome_busca = normalize(nome)
        rows.append([row[c] for c in COLUMNS] + [
            nome_busca, normalize(r.get("escola") or ""), termos, chave,
            normalize(r.get("municipio") or ""), f"{nome_busca}|{r.get('uf') or ''}",
            olp.pontos(r["competicao"], r["medalha"]), olp.pontos_impa(r["competicao"], r["medalha"], r.get("nivel")),
            olp.area(r["competicao"])])
    con.executemany(
        f"INSERT INTO medalhas ({', '.join(COLUMNS)}, nome_busca, escola_busca, escola_termos, "
        f"escola_chave, municipio_busca, aluno_id, xp, impa, area) VALUES ({', '.join('?' * (len(COLUMNS) + 9))})", rows)
    con.execute("INSERT INTO meta VALUES ('atualizado_em', ?)", (time.strftime("%Y-%m-%d %H:%M"),))
    build_summaries(con)
    con.commit()
    con.close()
    DB_PATH.unlink(missing_ok=True)
    tmp.rename(DB_PATH)

    print(f"\n{len(rows)} registros gravados em {DB_PATH}")


if __name__ == "__main__":
    main()
