"""Coleta OBMEP + OBM e gera data/medalhas.db.

Uso:
    python build_db.py            # usa o cache local quando existir
    python build_db.py --refresh  # apaga o cache e baixa tudo de novo
"""
import shutil
import sqlite3
import sys
import time

from scraper import obm, obmep
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
    municipio_busca TEXT
);
CREATE INDEX idx_chave  ON medalhas(escola_chave);
CREATE INDEX idx_nome   ON medalhas(nome_busca);
CREATE INDEX idx_escola ON medalhas(escola_busca);
CREATE INDEX idx_ano    ON medalhas(ano);
CREATE INDEX idx_uf     ON medalhas(uf);
CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT);
"""

COLUMNS = ["competicao", "ano", "nivel", "nome", "escola", "rede", "esfera",
           "municipio", "uf", "premio", "medalha", "pontos", "fonte"]


def main() -> None:
    if "--refresh" in sys.argv and CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)

    records = obmep.scrape() + obm.scrape()

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
        rows.append([row[c] for c in COLUMNS] + [
            normalize(nome), normalize(r.get("escola") or ""), termos, chave,
            normalize(r.get("municipio") or "")])
    con.executemany(
        f"INSERT INTO medalhas ({', '.join(COLUMNS)}, nome_busca, escola_busca, escola_termos, "
        f"escola_chave, municipio_busca) VALUES ({', '.join('?' * (len(COLUMNS) + 5))})", rows)
    con.execute("INSERT INTO meta VALUES ('atualizado_em', ?)", (time.strftime("%Y-%m-%d %H:%M"),))
    con.commit()
    con.close()
    DB_PATH.unlink(missing_ok=True)
    tmp.rename(DB_PATH)

    print(f"\n{len(rows)} registros gravados em {DB_PATH}")


if __name__ == "__main__":
    main()
