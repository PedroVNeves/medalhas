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
    p_impa          INTEGER NOT NULL,   -- IMPA, todos os níveis
    p_impa3         INTEGER NOT NULL,   -- IMPA oficial, só Nível 3
    p_site          INTEGER NOT NULL,   -- nossa versão
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


PONTOS = [m["coluna"] for m in olp.METODOS.values()]          # p_impa, p_impa3, p_site
POSICOES = [f"{c}_{k}" for c in PONTOS for k in ("pos", "pos_uf")]  # p_impa_pos, p_impa_pos_uf, ...

SUMMARY_SCHEMA = f"""
CREATE TABLE alunos (
    id TEXT PRIMARY KEY, nome TEXT, uf TEXT, competicoes TEXT, escola TEXT, escola_chave TEXT,
    municipio TEXT, ouro INT, prata INT, bronze INT, mencao INT, total INT, de INT, ate INT,
    {", ".join(f"{c} INT" for c in PONTOS + POSICOES)}
);
CREATE TABLE escolas (
    id TEXT PRIMARY KEY, nome TEXT, municipio TEXT, uf TEXT, rede TEXT, esfera TEXT, alunos INT,
    ouro INT, prata INT, bronze INT, mencao INT, total INT, de INT, ate INT,
    {", ".join(f"{c} INT" for c in PONTOS + POSICOES)}
);
{"".join(f"CREATE INDEX idx_alunos_{c} ON alunos({c} DESC); CREATE INDEX idx_escolas_{c} ON escolas({c} DESC);" for c in PONTOS)}
CREATE INDEX idx_alunos_uf ON alunos(uf);
CREATE INDEX idx_escolas_uf ON escolas(uf);
"""

MEDAL_FIELD = {"Ouro": "ouro", "Prata": "prata", "Bronze": "bronze", "Menção Honrosa": "mencao"}
ALUNO_COLS = ["id", "nome", "uf", "competicoes", "escola", "escola_chave", "municipio", "ouro", "prata",
              "bronze", "mencao", "total", "de", "ate"] + PONTOS + POSICOES
ESCOLA_COLS = ["id", "nome", "municipio", "uf", "rede", "esfera", "alunos", "ouro", "prata", "bronze",
               "mencao", "total", "de", "ate"] + PONTOS + POSICOES


def _rank(items: list[dict], pontos: str, key: str) -> None:
    """Preenche items[i][key] com RANK() pela coluna de pontos (empates dividem a posição)."""
    items.sort(key=lambda a: -a[pontos])
    pos, prev = 0, None
    for i, it in enumerate(items, 1):
        if it[pontos] != prev:
            pos, prev = i, it[pontos]
        it[key] = pos


def _novo(base: dict) -> dict:
    return {**base, "ouro": 0, "prata": 0, "bronze": 0, "mencao": 0, "total": 0, **{c: 0 for c in PONTOS}}


def build_summaries(con: sqlite3.Connection) -> None:
    """Tabelas-resumo (alunos, escolas) com totais, pontos e posição nacional/estadual em cada método."""
    con.executescript(SUMMARY_SCHEMA)
    alunos: dict = {}
    escolas: dict = {}
    cur = con.execute(f"""SELECT aluno_id, nome, uf, competicao, ano, medalha, escola, escola_chave, municipio,
                                 rede, esfera, {", ".join(PONTOS)}
                          FROM medalhas ORDER BY ano DESC, competicao DESC""")
    for row in cur:
        aid, nome, uf, comp, ano, medalha, escola, chave, municipio, rede, esfera = row[:11]
        pts = dict(zip(PONTOS, row[11:]))
        a = alunos.get(aid)
        if a is None:
            a = alunos[aid] = _novo({"id": aid, "nome": nome, "uf": uf, "comps": set(), "escola": None,
                                     "escola_chave": None, "municipio": None, "de": ano, "ate": ano})
        if comp == "OBM" and a["nome"] != nome and "OBM" not in a["comps"]:
            a["nome"] = nome  # a OBM publica nomes com acento e caixa mista
        a["comps"].add(comp)
        a["uf"] = a["uf"] or uf  # 1ª UF não vazia, do registro mais recente
        a["escola"] = a["escola"] or escola
        a["escola_chave"] = a["escola_chave"] or (chave or None)
        a["municipio"] = a["municipio"] or municipio
        targets = [a]
        if chave:
            e = escolas.get(chave)
            if e is None:
                e = escolas[chave] = _novo({"id": chave, "nomes": {}, "municipio": municipio, "uf": uf, "rede": rede,
                                            "esfera": esfera, "alunos_set": set(), "de": ano, "ate": ano})
            e["nomes"][escola] = e["nomes"].get(escola, 0) + 1
            e["alunos_set"].add(aid)
            targets.append(e)
        for x in targets:
            x["total"] += 1
            for c in PONTOS:
                x[c] += pts[c]
            x["de"], x["ate"] = min(x["de"], ano), max(x["ate"], ano)
            if medalha in MEDAL_FIELD:
                x[MEDAL_FIELD[medalha]] += 1

    for group in (alunos, escolas):
        items = list(group.values())
        by_uf: dict = {}
        for it in items:
            by_uf.setdefault(it["uf"], []).append(it)
        for c in PONTOS:
            _rank(items, c, f"{c}_pos")
            for lst in by_uf.values():
                _rank(lst, c, f"{c}_pos_uf")

    for a in alunos.values():
        a["competicoes"] = ",".join(sorted(a["comps"], reverse=True))
    for e in escolas.values():
        e["nome"] = max(e["nomes"], key=e["nomes"].get)
        e["alunos"] = len(e["alunos_set"])
    con.executemany(f"INSERT INTO alunos ({', '.join(ALUNO_COLS)}) VALUES ({', '.join('?' * len(ALUNO_COLS))})",
                    [[a[c] for c in ALUNO_COLS] for a in alunos.values()])
    con.executemany(f"INSERT INTO escolas ({', '.join(ESCOLA_COLS)}) VALUES ({', '.join('?' * len(ESCOLA_COLS))})",
                    [[e[c] for c in ESCOLA_COLS] for e in escolas.values()])


def _subsequencia(curto: list[str], longo: list[str]) -> bool:
    """'ENZO HOLANDA' é subsequência de 'ENZO HOLANDA SAMPAIO' (mesma ordem, mesmo primeiro nome)."""
    if not curto or curto[0] != longo[0]:
        return False
    it = iter(longo)
    return all(tok in it for tok in curto)


def completar_identidades(records: list[dict], log=print) -> None:
    """Para quem veio sem UF (IMO, IMC…), descobre a pessoa nos outros registros.

    1. nome idêntico (sem acento) com uma única UF conhecida -> usa essa UF;
    2. nome abreviado ('Enzo Holanda') que é subsequência de um único nome completo de medalhista
       de olimpíada de alto nível (OBM ou internacionais) -> adota o nome completo e a UF.
    """
    ufs: dict = {}
    for r in records:
        if r.get("uf"):
            ufs.setdefault(normalize(r["nome"]), set()).add(r["uf"])
    alto_nivel = {}
    for r in records:
        if r.get("uf") and (r["competicao"] == "OBM" or olp.OLIMPIADAS.get(r["competicao"], {}).get("internacional")):
            alto_nivel.setdefault(normalize(r["nome"]), r["nome"])
    candidatos = [(n.split(), nome) for n, nome in alto_nivel.items()]
    exato = abreviado = 0
    for r in records:
        if r.get("uf"):
            continue
        chave = normalize(r["nome"])
        if len(ufs.get(chave, ())) == 1:
            r["uf"] = next(iter(ufs[chave])); exato += 1
            continue
        toks = chave.split()
        if len(toks) < 2:
            continue
        achados = {nome for c, nome in candidatos if len(c) > len(toks) and _subsequencia(toks, c)}
        if len(achados) == 1:
            r["nome"] = next(iter(achados)); abreviado += 1  # a UF é resolvida em atribuir_alunos
    log(f"Identidades: UF inferida pelo nome em {exato} registros; {abreviado} nomes abreviados completados")


PARTICULAS = {"DE", "DA", "DO", "DAS", "DOS", "E", "D"}


MAX_ANOS_CARREIRA = 12  # do 6º ano do fundamental ao fim da faculdade


def atribuir_alunos(records: list[dict], log=print) -> None:
    """Define r["_aluno"]: quais premiações são da mesma pessoa.

    Por padrão, mesma pessoa = mesmo nome (sem acento) + mesma UF. Mas alunos de ponta mudam de estado
    (ex.: vão estudar em Fortaleza), então o mesmo nome em UFs diferentes é unido quando:
      - não há conflito (o nome premiado na mesma olimpíada e no mesmo ano em duas UFs = homônimos);
      - as premiações cabem numa carreira escolar (≤ MAX_ANOS_CARREIRA anos);
      - o nome é raro: o número esperado de pessoas diferentes com esse nome, estimado pela frequência
        de cada palavra entre todos os nomes, é < 0,3 (ou < 3 se a pessoa tem OBM/internacional em 2+ UFs).
    Registros sem UF entram na pessoa quando ela é única.
    """
    por_nome: dict = {}
    for r in records:
        por_nome.setdefault(normalize(r["nome"]), []).append(r)

    # frequência de cada palavra entre os nomes distintos -> estimativa de homônimos
    total = len(por_nome)
    df: dict = {}
    for nome in por_nome:
        for tok in set(nome.split()) - PARTICULAS:
            df[tok] = df.get(tok, 0) + 1

    def homonimos_esperados(nome: str) -> float:
        e = float(total)
        for tok in set(nome.split()) - PARTICULAS:
            e *= df[tok] / total
        return e

    def alto_nivel(rs) -> bool:
        return any(r["competicao"] == "OBM" or olp.OLIMPIADAS.get(r["competicao"], {}).get("internacional") for r in rs)

    unidos = 0
    for nome, recs in por_nome.items():
        por_uf: dict = {}
        sem_uf = []
        for r in recs:
            (por_uf.setdefault(r["uf"], []) if r.get("uf") else sem_uf).append(r)
        grupos = list(por_uf.values())
        if len(grupos) > 1:
            dono: dict = {}
            conflito = False
            for uf, rs in por_uf.items():
                for chave in {(r["competicao"], r["ano"]) for r in rs}:
                    conflito |= dono.setdefault(chave, uf) != uf
            anos = [r["ano"] for r in recs if r["ano"]]
            cabe = max(anos) - min(anos) <= MAX_ANOS_CARREIRA
            limite = 3.0 if sum(alto_nivel(rs) for rs in grupos) >= 2 else 0.3
            if not conflito and cabe and homonimos_esperados(nome) < limite:
                grupos = [[r for rs in grupos for r in rs]]
                unidos += 1
        ids = []
        for g in grupos:
            # UF "principal" = a do registro mais recente (é a que aparece no perfil e no ranking por estado)
            principal = max(g, key=lambda r: (r["ano"] or 0, r["competicao"] != "OBMEP"))["uf"]
            ident = f"{nome}|{principal}"
            ids.append(ident)
            for r in g:
                r["_aluno"] = ident
        for r in sem_uf:
            r["_aluno"] = ids[0] if len(ids) == 1 else f"{nome}|"
    log(f"Identidades: {unidos} pessoas reunidas entre estados diferentes")


def main() -> None:
    if "--refresh" in sys.argv and CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)

    records, falhas = [], []
    for sigla, info in olp.OLIMPIADAS.items():
        try:
            records += info["scrape"]()
        except Exception as e:  # noqa: BLE001 — uma fonte fora do ar não derruba as outras
            falhas.append(f"{sigla}: {type(e).__name__}: {e}")
    completar_identidades(records)
    atribuir_alunos(records)

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
            normalize(r.get("municipio") or ""), r["_aluno"],
            olp.pontos(r["competicao"], r["medalha"]), olp.pontos_impa(r["competicao"], r["medalha"], r.get("nivel")),
            olp.pontos_site(r["competicao"], r["medalha"]), olp.area(r["competicao"])])
    con.executemany(
        f"INSERT INTO medalhas ({', '.join(COLUMNS)}, nome_busca, escola_busca, escola_termos, "
        f"escola_chave, municipio_busca, aluno_id, p_impa, p_impa3, p_site, area) VALUES ({', '.join('?' * (len(COLUMNS) + 10))})", rows)
    con.execute("INSERT INTO meta VALUES ('atualizado_em', ?)", (time.strftime("%Y-%m-%d %H:%M"),))
    build_summaries(con)
    con.commit()
    con.close()
    DB_PATH.unlink(missing_ok=True)
    tmp.rename(DB_PATH)

    print(f"\n{len(rows)} registros gravados em {DB_PATH}")
    if falhas:
        print("\nATENÇÃO: fontes que falharam (rode de novo para tentar baixar):")
        for f in falhas:
            print("  -", f)


if __name__ == "__main__":
    main()
