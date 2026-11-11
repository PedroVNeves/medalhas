"""Consultas da API pública v1. Recebem critérios já validados e devolvem linhas da base;
o formato das respostas é responsabilidade do adaptador HTTP."""
import sqlite3
from collections.abc import Iterator

from ...aplicacao.portas import Criterios
from ...dominio.texto import normalizar
from .conexao import Conexao, marcadores
from .filtros import where_de

COLUNAS_PREMIACAO = ("id, competicao, area, ano, nivel, medalha, premio, nome, aluno_id, escola, escola_chave, "
                     "municipio, uf, rede, esfera, pontos, p_impa, p_impa3, p_site, fonte")
_ORDEM_MEDALHISTAS = {"nome": "MIN(nome_busca)", "recentes": "MAX(ano) DESC, MIN(nome_busca)"}


def _por_aluno(con: Conexao, sql_where: str, args: list, ids: list[str]) -> dict[str, list[sqlite3.Row]]:
    """Premiações de cada aluno da página (mais recentes primeiro)."""
    agrupado: dict[str, list] = {i: [] for i in ids}
    if ids:
        for r in con.execute(f"SELECT {COLUNAS_PREMIACAO} FROM medalhas WHERE {sql_where} "
                             f"AND aluno_id IN ({marcadores(len(ids))}) ORDER BY ano DESC, competicao", [*args, *ids]):
            agrupado[r["aluno_id"]].append(r)
    return agrupado


def _resumos(con: Conexao, tabela: str, ids: list[str], colunas: str = "*") -> dict[str, sqlite3.Row]:
    if not ids:
        return {}
    sql = f"SELECT {colunas} FROM {tabela} WHERE id IN ({marcadores(len(ids))})"
    return {r["id"]: r for r in con.execute(sql, ids)}


# ---------------------------------------------------------------- referência

def resumo_base(con: Conexao) -> dict:
    meta = dict(con.execute("SELECT chave, valor FROM meta").fetchall())
    total = con.execute("SELECT COUNT(*) FROM medalhas").fetchone()[0]
    return {"atualizado_em": meta.get("atualizado_em"), "premiacoes": total}


def estatisticas_olimpiadas(con: Conexao) -> dict:
    """{"premiacoes": {sigla: (total, primeiro ano, último ano)}, "niveis": {sigla: [{nivel, premiacoes}]}}"""
    def calcular() -> dict:
        totais = {r[0]: tuple(r[1:]) for r in con.execute(
            "SELECT competicao, COUNT(*), MIN(ano), MAX(ano) FROM medalhas GROUP BY competicao || ''")}
        niveis: dict[str, list] = {}
        for sigla, nivel, n in con.execute("SELECT competicao, nivel, COUNT(*) FROM medalhas WHERE nivel IS NOT NULL "
                                           "GROUP BY competicao || '', nivel"):
            niveis.setdefault(sigla, []).append({"nivel": nivel, "premiacoes": n})
        return {"premiacoes": totais, "niveis": niveis}
    return con.em_cache("v1_estatisticas", calcular)


def niveis(con: Conexao) -> set[str]:
    return con.em_cache("v1_niveis", lambda: {r[0] for r in con.execute(
        "SELECT DISTINCT nivel FROM medalhas WHERE nivel IS NOT NULL")})


def ultima_escola_dos_alunos(con: Conexao) -> dict[str, tuple[str | None, str | None]]:
    """(escola, município) mais recentes de cada aluno, para completar rankings filtrados."""
    return con.em_cache("v1_escola_aluno", lambda: {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT id, escola, municipio FROM alunos")})


# ---------------------------------------------------------------- alunos

def buscar_alunos(con: Conexao, criterios: Criterios, nome: str, coluna: str, offset: int,
                  limite: int) -> tuple[int, list[tuple[sqlite3.Row, list[sqlite3.Row]]]]:
    """Alunos com premiações no recorte. Quem tem exatamente o nome buscado vem primeiro, depois os
    que mais pontuam no método."""
    sql_where, args = where_de(criterios)
    grupos = con.execute(
        f"""SELECT aluno_id, MAX(nome_busca = ?) AS exato, SUM({coluna}) AS pts FROM medalhas
            WHERE {sql_where} GROUP BY aluno_id || ''
            ORDER BY exato DESC, pts DESC, aluno_id""", [normalizar(nome), *args]).fetchall()
    ids = [g["aluno_id"] for g in grupos[offset:offset + limite]]
    premiacoes = _por_aluno(con, sql_where, args, ids)
    resumos = _resumos(con, "alunos", ids)
    return len(grupos), [(resumos[i], premiacoes[i]) for i in ids]


def aluno(con: Conexao, aluno_id: str, criterios: Criterios) -> tuple[sqlite3.Row, list[sqlite3.Row]] | None:
    resumo = con.execute("SELECT * FROM alunos WHERE id = ?", (aluno_id,)).fetchone()
    if not resumo:
        return None
    sql_where, args = where_de(criterios)
    premiacoes = con.execute(f"SELECT {COLUNAS_PREMIACAO} FROM medalhas WHERE aluno_id = ? AND {sql_where} "
                             "ORDER BY ano DESC, competicao", [aluno_id, *args]).fetchall()
    return resumo, premiacoes


# ---------------------------------------------------------------- escolas

def buscar_escolas(con: Conexao, criterios: Criterios, coluna: str, offset: int,
                   limite: int) -> tuple[int, list[sqlite3.Row]]:
    """Escolas com premiações no recorte, das que mais pontuam para as que menos."""
    sql_where, args = where_de(criterios)
    grupos = con.execute(
        f"""SELECT escola_chave, SUM({coluna}) AS pts, COUNT(*) AS n FROM medalhas
            WHERE {sql_where} AND escola_chave IS NOT NULL GROUP BY escola_chave || ''
            ORDER BY pts DESC, n DESC, escola_chave""", args).fetchall()
    ids = [g["escola_chave"] for g in grupos[offset:offset + limite]]
    resumos = _resumos(con, "escolas", ids)
    return len(grupos), [resumos[i] for i in ids if i in resumos]


def escola(con: Conexao, escola_id: str) -> tuple[sqlite3.Row, list[str]] | None:
    """Resumo da escola e as grafias do nome nas listas oficiais (mais frequente primeiro)."""
    resumo = con.execute("SELECT * FROM escolas WHERE id = ?", (escola_id,)).fetchone()
    if not resumo:
        return None
    grafias = [r[0] for r in con.execute(
        "SELECT escola FROM medalhas WHERE escola_chave = ? GROUP BY escola ORDER BY COUNT(*) DESC", (escola_id,))]
    return resumo, grafias


def medalhistas(con: Conexao, escola_id: str, criterios: Criterios, ordem: str, coluna: str, offset: int,
                limite: int) -> tuple[sqlite3.Row, int, list[tuple[str, sqlite3.Row | None, list[sqlite3.Row]]]] | None:
    """Alunos premiados pela escola, cada um com as premiações por ela. ordem: pontos | nome | recentes."""
    resumo = con.execute("SELECT * FROM escolas WHERE id = ?", (escola_id,)).fetchone()
    if not resumo:
        return None
    sql_where, args = where_de(Criterios({**criterios.filtros, "escola_chave": escola_id}, criterios.textos,
                                         criterios.aluno_id))
    ordenacao = _ORDEM_MEDALHISTAS.get(ordem, f"SUM({coluna}) DESC, MIN(nome_busca)")
    grupos = con.execute(f"SELECT aluno_id FROM medalhas WHERE {sql_where} GROUP BY aluno_id ORDER BY {ordenacao}",
                         args).fetchall()
    ids = [g[0] for g in grupos[offset:offset + limite]]
    premiacoes = _por_aluno(con, sql_where, args, ids)
    alunos = _resumos(con, "alunos", ids, "id, nome, uf")
    return resumo, len(grupos), [(i, alunos.get(i), premiacoes[i]) for i in ids]


# ---------------------------------------------------------------- premiações

def premiacoes(con: Conexao, criterios: Criterios, offset: int, limite: int) -> tuple[int, list[sqlite3.Row]]:
    """Uma página de premiações em ordem estável (id)."""
    sql_where, args = where_de(criterios)
    total = con.execute(f"SELECT COUNT(*) FROM medalhas WHERE {sql_where}", args).fetchone()[0]
    linhas = con.execute(f"SELECT {COLUNAS_PREMIACAO} FROM medalhas WHERE {sql_where} ORDER BY id LIMIT ? OFFSET ?",
                         [*args, limite, offset]).fetchall()
    return total, linhas


def iterar_premiacoes(con: Conexao, criterios: Criterios) -> Iterator[sqlite3.Row]:
    """Todas as premiações do recorte, em fluxo (para exportar sem carregar tudo na memória)."""
    sql_where, args = where_de(criterios)
    yield from con.execute(f"SELECT {COLUNAS_PREMIACAO} FROM medalhas WHERE {sql_where} ORDER BY id", args)
