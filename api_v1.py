"""API pública v1: consulta de alunos, escolas e premiações, rankings e exportação (CSV/JSON).

Rotas estáveis para outros sistemas. A API interna do site (/api/busca, /api/ranking…) pode mudar;
estas só mudam numa nova versão (/api/v2). Documentação: página "API" do site, GET /api/v1 e
GET /api/v1/openapi.json.
"""
import csv
import gzip
import io
import json
import re
import shutil
import tempfile
import threading
import time
from urllib.parse import quote, unquote

import limites
import olimpiadas as olp
from consultas import (DB_PATH, ROOT, build_filters, cached, com_posicoes, connect, metodo_de, ranking_ordenado,
                       token_condition)
from scraper.common import normalize
from scraper.escolas import query_tokens

VERSAO = "1.1.0"
LIMITE_PADRAO = 20
LIMITE_MAX = {"alunos": 100, "escolas": 100, "medalhistas": 500, "premiacoes": 1000, "ranking": 500}
MAX_TEXTO, MAX_PALAVRAS = 100, 8
EXPORT_DIR = ROOT / "data" / "exportar"
MEDALHAS = ("Ouro", "Prata", "Bronze", "Menção Honrosa")
UFS = {"AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
       "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"}
COLS = ("id, competicao, area, ano, nivel, medalha, premio, nome, aluno_id, escola, escola_chave, municipio, uf, "
        "rede, esfera, pontos, p_impa, p_impa3, p_site, fonte")


class ParametroInvalido(ValueError):
    pass


class NaoEncontrado(LookupError):
    pass


class Download:
    """Resposta em arquivo: `arquivo` é um caminho já gerado (gzip) ou um arquivo temporário aberto."""

    def __init__(self, nome: str, ctype: str, arquivo, gzipado: bool, linhas: int):
        self.nome, self.ctype, self.arquivo, self.gzipado, self.linhas = nome, ctype, arquivo, gzipado, linhas


# ---------------------------------------------------------------- validação de parâmetros

def _bool(params: dict, key: str, padrao: bool) -> bool:
    v = (params.get(key) or "").strip().lower()
    return padrao if not v else v in ("1", "true", "sim", "s", "yes")


def _int(params: dict, key: str, padrao=None, minimo=None, maximo=None):
    v = (params.get(key) or "").strip()
    if not v:
        return padrao
    if not re.fullmatch(r"-?\d+", v):
        raise ParametroInvalido(f"'{key}' deve ser um número inteiro (recebido: {v[:20]!r})")
    n = int(v)
    if minimo is not None:
        n = max(n, minimo)
    if maximo is not None:
        n = min(n, maximo)
    return n


def _paginacao(params: dict, rota: str) -> tuple[int, int]:
    return (_int(params, "limite", LIMITE_PADRAO, 1, LIMITE_MAX[rota]), _int(params, "offset", 0, 0))


def _texto(params: dict, key: str, obrigatorio: bool = False) -> list:
    """Palavras de busca (acentos e ordem ignorados). Limita o tamanho para a consulta não pesar."""
    v = (params.get(key) or "").strip()
    if len(v) > MAX_TEXTO:
        raise ParametroInvalido(f"'{key}' pode ter no máximo {MAX_TEXTO} caracteres")
    tokens = query_tokens(v)
    if obrigatorio and not tokens:
        raise ParametroInvalido(f"informe o parâmetro '{key}' (ex.: ?{key}=maria silva)")
    if len(tokens) > MAX_PALAVRAS:
        raise ParametroInvalido(f"'{key}' pode ter no máximo {MAX_PALAVRAS} palavras")
    return tokens


def _lista(params: dict, key: str, validos, nome: str) -> str | None:
    v = (params.get(key) or "").strip()
    if not v:
        return None
    itens = [x.strip() for x in v.split(",") if x.strip()]
    errados = [x for x in itens if x not in validos]
    if errados:
        raise ParametroInvalido(f"valor desconhecido em '{key}' ({nome}): {', '.join(errados)[:80]}. "
                                "Valores aceitos em GET /api/v1/olimpiadas")
    return ",".join(itens)


def _niveis() -> set:
    return cached("v1_niveis", lambda: _com_con(lambda con: {r[0] for r in con.execute(
        "SELECT DISTINCT nivel FROM medalhas WHERE nivel IS NOT NULL")}))


def _com_con(fn):
    con = connect()
    try:
        return fn(con)
    finally:
        con.close()


def _filtros(params: dict) -> dict:
    """Valida e normaliza os filtros comuns. Devolve no formato de consultas.build_filters."""
    siglas = {o["sigla"] for o in olp.catalogo()}
    areas = {o["area"] for o in olp.catalogo()}
    f = {}
    if params.get("uf"):
        ufs = (params["uf"] or "").upper().strip()
        if ufs not in UFS:
            raise ParametroInvalido(f"UF inválida: {params['uf'][:10]!r} (use a sigla, ex.: SP)")
        f["uf"] = ufs
    if params.get("medalha"):
        m = {normalize(x): x for x in MEDALHAS}.get(normalize(params["medalha"]))
        if not m:
            raise ParametroInvalido(f"medalha inválida: {params['medalha'][:20]!r} (use {', '.join(MEDALHAS)})")
        f["medalha"] = m
    for key, validos, nome in (("competicao", siglas, "olimpíada"), ("area", areas, "área"),
                               ("nivel", _niveis(), "nível")):
        v = _lista(params, key, validos, nome)
        if v:
            f[key] = v
    for key in ("ano", "ano_de", "ano_ate"):
        n = _int(params, key)
        if n is not None:
            f[key] = n
    if params.get("rede"):
        rede = {"publica": "Pública", "privada": "Privada"}.get(normalize(params["rede"]).lower())
        if not rede:
            raise ParametroInvalido("rede deve ser 'publica' ou 'privada'")
        f["rede"] = rede
    if params.get("municipio"):
        f["municipio"] = params["municipio"][:MAX_TEXTO]
    if params.get("escola_id"):
        f["escola_chave"] = params["escola_id"]
    return f


def _where(params: dict, extra_campos=("nome", "escola", "busca")) -> tuple[str, list]:
    """WHERE das premiações: filtros + busca por texto (nome do aluno, escola ou qualquer campo)."""
    where, args = build_filters(_filtros(params))
    if params.get("aluno_id"):
        where.append("aluno_id = ?")
        args.append(params["aluno_id"])
    for key, campo in (("nome", "nome"), ("escola", "escola"), ("busca", "tudo")):
        if key not in extra_campos:
            continue
        for tok, expansion in _texto(params, key):
            cond, cond_args = token_condition(campo, tok, expansion)
            where.append(cond)
            args += cond_args
    return " AND ".join(where) or "1", args


# ---------------------------------------------------------------- formatação das respostas

def _base(params: dict) -> str:
    return params.get("_base", "")


def _link_site(params, rota, ident):
    return f"{_base(params)}/#/{rota}/{quote(ident, safe='')}"


def _link_api(params, rota, ident, sufixo=""):
    return f"{_base(params)}/api/v1/{rota}/{quote(ident, safe='')}{sufixo}"


def _nomes_olimpiadas() -> dict:
    return {o["sigla"]: o["nome"] for o in olp.catalogo()}


def _pontos(r) -> dict:
    return {m: r[i["coluna"]] or 0 for m, i in olp.METODOS.items()}


def _premiacao(r, nomes: dict) -> dict:
    return {
        "id": r["id"], "olimpiada": r["competicao"], "olimpiada_nome": nomes.get(r["competicao"], r["competicao"]),
        "area": r["area"], "ano": r["ano"], "nivel": r["nivel"], "medalha": r["medalha"], "premio": r["premio"],
        "nome_na_lista": r["nome"], "aluno_id": r["aluno_id"], "escola": r["escola"], "escola_id": r["escola_chave"],
        "municipio": r["municipio"], "uf": r["uf"], "rede": r["rede"], "nota": r["pontos"],
        "pontos": _pontos(r), "fonte": r["fonte"],
    }


def _medalhas(r) -> dict:
    return {"ouro": r["ouro"], "prata": r["prata"], "bronze": r["bronze"], "mencao_honrosa": r["mencao"],
            "total": r["total"]}


def _posicoes(resumo) -> dict:
    return {m: ({"nacional": resumo[f"{i['coluna']}_pos"], "estadual": resumo[f"{i['coluna']}_pos_uf"]}
                if resumo[i["coluna"]] else None) for m, i in olp.METODOS.items()}


def _sem_repetir(valores) -> list[str]:
    """Une grafias do mesmo valor ("SAO PAULO", "São Paulo"), ficando com a mais legível."""
    grupos: dict = {}
    for v in valores:
        if v:
            grupos.setdefault(normalize(v), []).append(v)
    legivel = lambda v: (sum(c.islower() for c in v), sum(not c.isascii() for c in v))  # noqa: E731
    return [max(vs, key=legivel) for vs in grupos.values()]


def _aluno(resumo, rows: list, params: dict, incluir: bool) -> dict:
    nomes = _nomes_olimpiadas()
    escolas: dict = {}
    for r in rows:  # mais recente primeiro; grafias da mesma escola (mesma chave) viram um item só
        if r["escola_chave"]:
            escolas.setdefault(r["escola_chave"], []).append(r["escola"])
    item = {
        "id": resumo["id"], "nome": resumo["nome"], "uf": resumo["uf"],
        "escolas": [{"id": k, "nome": _sem_repetir(v)[0], "api": _link_api(params, "escolas", k),
                     "perfil": _link_site(params, "escola", k)} for k, v in escolas.items()],
        "municipios": sorted(_sem_repetir(r["municipio"] for r in rows), key=normalize),
        "olimpiadas": sorted({r["competicao"] for r in rows}),
        "anos": {"de": resumo["de"], "ate": resumo["ate"]},
        "medalhas": _medalhas(resumo), "pontos": _pontos(resumo), "posicao": _posicoes(resumo),
        "premiacoes_encontradas": len(rows),
        "api": _link_api(params, "alunos", resumo["id"]), "perfil": _link_site(params, "aluno", resumo["id"]),
    }
    if incluir:
        item["premiacoes"] = [_premiacao(r, nomes) for r in rows]
    return item


def _escola(resumo, params: dict) -> dict:
    return {
        "id": resumo["id"], "nome": resumo["nome"], "municipio": resumo["municipio"], "uf": resumo["uf"],
        "rede": resumo["rede"], "esfera": resumo["esfera"], "alunos_premiados": resumo["alunos"],
        "anos": {"de": resumo["de"], "ate": resumo["ate"]},
        "medalhas": _medalhas(resumo), "pontos": _pontos(resumo), "posicao": _posicoes(resumo),
        "api": _link_api(params, "escolas", resumo["id"]),
        "medalhistas": _link_api(params, "escolas", resumo["id"], "/medalhistas"),
        "perfil": _link_site(params, "escola", resumo["id"]),
    }


def _consulta(params: dict) -> dict:
    return {k: v for k, v in params.items() if not k.startswith("_")}


# ---------------------------------------------------------------- rotas

def indice(con, params: dict) -> dict:
    b = _base(params)
    meta = dict(con.execute("SELECT chave, valor FROM meta").fetchall())
    total = con.execute("SELECT COUNT(*) FROM medalhas").fetchone()[0]
    return {
        "nome": "Medalhas API", "versao": VERSAO, "atualizado_em": meta.get("atualizado_em"),
        "premiacoes": total,
        "documentacao": f"{b}/#/api", "openapi": f"{b}/api/v1/openapi.json",
        "rotas": {
            "GET /api/v1/alunos?nome=": "busca alunos pelo nome",
            "GET /api/v1/alunos/{id}": "um aluno e todas as premiações dele",
            "GET /api/v1/escolas?nome=": "busca escolas pelo nome ou sigla",
            "GET /api/v1/escolas/{id}": "resumo de uma escola",
            "GET /api/v1/escolas/{id}/medalhistas": "todos os alunos premiados de uma escola",
            "GET /api/v1/premiacoes": "todas as premiações, com filtros e paginação",
            "GET /api/v1/ranking/{alunos|escolas|estados}": "rankings com filtros",
            "GET /api/v1/exportar": "baixa premiações ou rankings em CSV/JSON (base inteira ou filtrada)",
            "GET /api/v1/olimpiadas": "olimpíadas, níveis e valores aceitos nos filtros",
        },
        "exemplos": {
            "medalhas de um aluno": f"{b}/api/v1/alunos?nome=erick+akira+koga",
            "medalhistas de uma escola": f"{b}/api/v1/escolas?nome=ifal  ->  {b}/api/v1/escolas/{{id}}/medalhistas",
            "base inteira": f"{b}/api/v1/exportar?formato=csv",
        },
        "limites": limites.resumo(),
    }


def olimpiadas(con, params: dict) -> dict:
    return cached("v1_olimpiadas", lambda: _olimpiadas(con))


def _olimpiadas(con) -> dict:
    stats = {r[0]: r[1:] for r in con.execute(
        "SELECT competicao, COUNT(*), MIN(ano), MAX(ano) FROM medalhas GROUP BY competicao || ''")}
    niveis: dict = {}
    for comp, nivel, n in con.execute(
            "SELECT competicao, nivel, COUNT(*) FROM medalhas WHERE nivel IS NOT NULL GROUP BY competicao || '', nivel"):
        niveis.setdefault(comp, []).append({"nivel": nivel, "premiacoes": n})
    return {
        "olimpiadas": [{
            "sigla": o["sigla"], "nome": o["nome"], "area": o["area"], "internacional": o["internacional"],
            "premiacoes": stats.get(o["sigla"], (0,))[0], "anos": {"de": stats.get(o["sigla"], (0, None, None))[1],
                                                                "ate": stats.get(o["sigla"], (0, None, None))[2]},
            "niveis": niveis.get(o["sigla"], []), "site_oficial": o["site"],
            "pontos": {"impa": o["pontos"], "impa3_niveis": o["impa_niveis"], "site": o["pontos_site"]},
        } for o in olp.catalogo()],
        "medalhas": list(MEDALHAS), "ufs": sorted(UFS), "areas": sorted({o["area"] for o in olp.catalogo()}),
        "redes": ["publica", "privada"], "metodos": olp.metodos(),
    }


def buscar_alunos(con, params: dict) -> dict:
    _texto(params, "nome", obrigatorio=True)
    limite, offset = _paginacao(params, "alunos")
    metodo, col = metodo_de(params)
    sql_where, args = _where(params, ("nome", "escola"))
    alvo = normalize(params["nome"])
    grupos = con.execute(
        f"""SELECT aluno_id, MAX(nome_busca = ?) AS exato, SUM({col}) AS pts FROM medalhas
            WHERE {sql_where} GROUP BY aluno_id || ''   -- sem o índice: uma varredura só (bem mais rápido)
            ORDER BY exato DESC, pts DESC, aluno_id""", [alvo, *args]).fetchall()
    ids = [g["aluno_id"] for g in grupos[offset:offset + limite]]
    rows: dict = {i: [] for i in ids}
    resumos: dict = {}
    if ids:
        marks = ",".join("?" * len(ids))
        for r in con.execute(f"SELECT {COLS} FROM medalhas WHERE {sql_where} AND aluno_id IN ({marks}) "
                             "ORDER BY ano DESC, competicao", [*args, *ids]):
            rows[r["aluno_id"]].append(r)
        resumos = {r["id"]: r for r in con.execute(f"SELECT * FROM alunos WHERE id IN ({marks})", ids)}
    incluir = _bool(params, "premiacoes", True)
    return {"consulta": _consulta(params), "metodo": metodo, "total": len(grupos), "offset": offset,
            "limite": limite, "alunos": [_aluno(resumos[i], rows[i], params, incluir) for i in ids]}


def aluno(con, params: dict, aluno_id: str) -> dict:
    resumo = con.execute("SELECT * FROM alunos WHERE id = ?", (aluno_id,)).fetchone()
    if not resumo:
        raise NaoEncontrado(f"aluno não encontrado: {aluno_id!r}. Busque o id em GET /api/v1/alunos?nome=")
    sql_where, args = _where(params, ())
    rows = con.execute(f"SELECT {COLS} FROM medalhas WHERE aluno_id = ? AND {sql_where} ORDER BY ano DESC, competicao",
                       [aluno_id, *args]).fetchall()
    return {"aluno": _aluno(resumo, rows, params, True)}


def buscar_escolas(con, params: dict) -> dict:
    tokens = _texto(params, "nome", obrigatorio=True)
    limite, offset = _paginacao(params, "escolas")
    metodo, col = metodo_de(params)
    where, args = build_filters(_filtros(params))
    for tok, expansion in tokens:
        cond, cond_args = token_condition("escola", tok, expansion)
        where.append(cond)
        args += cond_args
    grupos = con.execute(
        f"""SELECT escola_chave, SUM({col}) AS pts, COUNT(*) AS n FROM medalhas
            WHERE {' AND '.join(where)} AND escola_chave IS NOT NULL GROUP BY escola_chave || ''
            ORDER BY pts DESC, n DESC, escola_chave""", args).fetchall()
    ids = [g["escola_chave"] for g in grupos[offset:offset + limite]]
    resumos = {}
    if ids:
        marks = ",".join("?" * len(ids))
        resumos = {r["id"]: r for r in con.execute(f"SELECT * FROM escolas WHERE id IN ({marks})", ids)}
    return {"consulta": _consulta(params), "metodo": metodo, "total": len(grupos), "offset": offset,
            "limite": limite, "escolas": [_escola(resumos[i], params) for i in ids if i in resumos]}


def escola(con, params: dict, escola_id: str) -> dict:
    resumo = con.execute("SELECT * FROM escolas WHERE id = ?", (escola_id,)).fetchone()
    if not resumo:
        raise NaoEncontrado(f"escola não encontrada: {escola_id!r}. Busque o id em GET /api/v1/escolas?nome=")
    variantes = [r[0] for r in con.execute(
        "SELECT escola FROM medalhas WHERE escola_chave = ? GROUP BY escola ORDER BY COUNT(*) DESC", (escola_id,))]
    return {"escola": {**_escola(resumo, params), "grafias": variantes}}


def medalhistas(con, params: dict, escola_id: str) -> dict:
    resumo = con.execute("SELECT * FROM escolas WHERE id = ?", (escola_id,)).fetchone()
    if not resumo:
        raise NaoEncontrado(f"escola não encontrada: {escola_id!r}. Busque o id em GET /api/v1/escolas?nome=")
    limite, offset = _paginacao(params, "medalhistas")
    metodo, col = metodo_de(params)
    sql_where, args = _where({**params, "escola_id": escola_id}, ("nome",))
    ordem = {"nome": "MIN(nome_busca)", "recentes": "MAX(ano) DESC, MIN(nome_busca)"}.get(
        params.get("ordem", ""), f"SUM({col}) DESC, MIN(nome_busca)")
    grupos = con.execute(f"SELECT aluno_id FROM medalhas WHERE {sql_where} GROUP BY aluno_id ORDER BY {ordem}",
                         args).fetchall()
    ids = [g[0] for g in grupos[offset:offset + limite]]
    nomes = _nomes_olimpiadas()
    por_aluno: dict = {i: [] for i in ids}
    if ids:
        marks = ",".join("?" * len(ids))
        for r in con.execute(f"SELECT {COLS} FROM medalhas WHERE {sql_where} AND aluno_id IN ({marks}) "
                             "ORDER BY ano DESC, competicao", [*args, *ids]):
            por_aluno[r["aluno_id"]].append(r)
        info = {r["id"]: r for r in con.execute(f"SELECT id, nome, uf FROM alunos WHERE id IN ({marks})", ids)}
    lista = []
    for i in ids:
        rows = por_aluno[i]
        cont = {m: sum(r["medalha"] == m for r in rows) for m in MEDALHAS}
        lista.append({
            "id": i, "nome": info[i]["nome"] if i in info else rows[0]["nome"], "uf": info[i]["uf"] if i in info else None,
            "anos": sorted({r["ano"] for r in rows}),
            "medalhas_nesta_escola": {"ouro": cont["Ouro"], "prata": cont["Prata"], "bronze": cont["Bronze"],
                                      "mencao_honrosa": cont["Menção Honrosa"], "total": len(rows)},
            "pontos_nesta_escola": {m: sum(r[c["coluna"]] or 0 for r in rows) for m, c in olp.METODOS.items()},
            "api": _link_api(params, "alunos", i), "perfil": _link_site(params, "aluno", i),
            "premiacoes": [_premiacao(r, nomes) for r in rows],
        })
    return {"escola": {"id": resumo["id"], "nome": resumo["nome"], "municipio": resumo["municipio"], "uf": resumo["uf"],
                       "api": _link_api(params, "escolas", escola_id)},
            "consulta": _consulta(params), "metodo": metodo, "total": len(grupos), "offset": offset,
            "limite": limite, "medalhistas": lista}


def premiacoes(con, params: dict) -> dict:
    limite, offset = _paginacao(params, "premiacoes")
    sql_where, args = _where(params)
    total = con.execute(f"SELECT COUNT(*) FROM medalhas WHERE {sql_where}", args).fetchone()[0]
    rows = con.execute(f"SELECT {COLS} FROM medalhas WHERE {sql_where} ORDER BY id LIMIT ? OFFSET ?",
                       [*args, limite, offset]).fetchall()
    nomes = _nomes_olimpiadas()
    proximo = None
    if offset + limite < total:
        q = {k: v for k, v in _consulta(params).items() if k not in ("offset",)}
        q["offset"] = offset + limite
        proximo = f"{_base(params)}/api/v1/premiacoes?" + "&".join(f"{k}={quote(str(v))}" for k, v in q.items())
    return {"consulta": _consulta(params), "total": total, "offset": offset, "limite": limite, "proxima_pagina": proximo,
            "premiacoes": [_premiacao(r, nomes) for r in rows]}


def _params_ranking(params: dict, tipo: str) -> dict:
    if tipo not in ("alunos", "escolas", "estados"):
        raise NaoEncontrado("ranking inexistente: use /api/v1/ranking/alunos, /escolas ou /estados")
    p = {**_filtros(params), "tipo": tipo, "metodo": params.get("metodo", ""), "ordem": params.get("ordem", "xp")}
    if p["ordem"] not in ("xp", "medalhas", "total"):
        raise ParametroInvalido("ordem deve ser xp (pontos), medalhas (quadro de medalhas) ou total")
    return {k: str(v) for k, v in p.items() if v not in (None, "")}


def _item_ranking(r: dict, tipo: str, params: dict) -> dict:
    item = {"posicao": r["pos"], "id": r["id"], "nome": r["nome"]}
    if tipo == "alunos":
        item.update({"uf": r.get("uf"), "escola": r.get("escola"), "municipio": r.get("municipio")})
    elif tipo == "escolas":
        item.update({"municipio": r.get("municipio"), "uf": r.get("uf"), "rede": r.get("rede"),
                     "alunos_premiados": r.get("alunos")})
    else:
        item.update({"alunos_premiados": r.get("alunos"), "escolas": r.get("escolas")})
    item.update({"medalhas": _medalhas(r), "pontos": r["xp"], "pontos_metodos": _pontos(r),
                 "anos": {"de": r.get("de"), "ate": r.get("ate")}})
    if tipo != "estados":
        item["api"] = _link_api(params, tipo, r["id"])
    return item


def _escolas_dos_alunos(con) -> dict:
    """Última escola de cada aluno (para rankings filtrados, que não trazem a escola)."""
    return cached("v1_escola_aluno", lambda: {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT id, escola, municipio FROM alunos")})


def ranking(con, params: dict, tipo: str) -> dict:
    limite, offset = _paginacao(params, "ranking")
    o = ranking_ordenado(con, _params_ranking(params, tipo))
    itens = list(com_posicoes(o, offset, limite))
    if tipo == "alunos":
        esc = _escolas_dos_alunos(con)
        for r in itens:
            if not r.get("escola"):
                r["escola"], r["municipio"] = esc.get(r["id"], (None, None))
    return {"consulta": _consulta(params), "tipo": tipo, "metodo": o["metodo"], "ordem": o["ordem"],
            "niveis_considerados": o["params"].get("nivel"), "total": len(o["itens"]), "offset": offset,
            "limite": limite, "itens": [_item_ranking(r, tipo, params) for r in itens]}


# ---------------------------------------------------------------- exportação (CSV / JSON)

CAMPOS_PREMIACAO = ["id", "olimpiada", "olimpiada_nome", "area", "ano", "nivel", "medalha", "premio", "nome",
                    "aluno_id", "escola", "escola_id", "municipio", "uf", "rede", "esfera", "nota",
                    "pontos_impa", "pontos_impa_n3", "pontos_nossa", "fonte"]
CAMPOS_RANKING = {
    "alunos": ["posicao", "id", "nome", "uf", "escola", "municipio"],
    "escolas": ["posicao", "id", "nome", "municipio", "uf", "rede", "alunos_premiados"],
    "estados": ["posicao", "uf", "alunos_premiados", "escolas"],
}
CAMPOS_RANKING_FIM = ["ouro", "prata", "bronze", "mencao_honrosa", "total", "pontos", "pontos_impa",
                      "pontos_impa_n3", "pontos_nossa", "de", "ate"]
_gerando = threading.Lock()


def _linha_premiacao(r, nomes: dict) -> dict:
    return {"id": r["id"], "olimpiada": r["competicao"], "olimpiada_nome": nomes.get(r["competicao"], r["competicao"]),
            "area": r["area"], "ano": r["ano"], "nivel": r["nivel"], "medalha": r["medalha"], "premio": r["premio"],
            "nome": r["nome"], "aluno_id": r["aluno_id"], "escola": r["escola"], "escola_id": r["escola_chave"],
            "municipio": r["municipio"], "uf": r["uf"], "rede": r["rede"], "esfera": r["esfera"], "nota": r["pontos"],
            "pontos_impa": r["p_impa"], "pontos_impa_n3": r["p_impa3"], "pontos_nossa": r["p_site"], "fonte": r["fonte"]}


def _linha_ranking(r: dict, tipo: str, esc: dict) -> dict:
    d = {"posicao": r["pos"], "id": r["id"], "nome": r["nome"], "uf": r.get("uf") if tipo != "estados" else r["id"],
         "escola": r.get("escola"), "municipio": r.get("municipio"), "rede": r.get("rede"),
         "alunos_premiados": r.get("alunos"), "escolas": r.get("escolas"),
         "ouro": r["ouro"], "prata": r["prata"], "bronze": r["bronze"], "mencao_honrosa": r["mencao"],
         "total": r["total"], "pontos": r["xp"], "pontos_impa": r["p_impa"], "pontos_impa_n3": r["p_impa3"],
         "pontos_nossa": r["p_site"], "de": r.get("de"), "ate": r.get("ate")}
    if tipo == "alunos" and not d["escola"]:
        d["escola"], d["municipio"] = esc.get(r["id"], (None, None))
    return d


def _escrever(saida, linhas, campos: list, formato: str, separador: str, meta: dict) -> int:
    """Escreve CSV (com BOM, para o Excel reconhecer UTF-8) ou JSON em fluxo. Devolve o nº de linhas."""
    texto = io.TextIOWrapper(saida, encoding="utf-8", newline="", write_through=False)
    n = 0
    if formato == "csv":
        texto.write("﻿")
        w = csv.DictWriter(texto, fieldnames=campos, delimiter=separador, extrasaction="ignore")
        w.writeheader()
        for d in linhas:
            w.writerow(d)
            n += 1
    else:
        texto.write(json.dumps(meta, ensure_ascii=False)[:-1] + ', "dados": [\n')
        for d in linhas:
            texto.write(("," if n else "") + json.dumps({k: d.get(k) for k in campos}, ensure_ascii=False) + "\n")
            n += 1
        texto.write(f'], "total": {n}}}\n')
    texto.flush()
    texto.detach()
    return n


def _gerar(con, params: dict, conjunto: str, formato: str, separador: str, destino) -> int:
    meta = {"fonte": "Medalhas", "gerado_em": time.strftime("%Y-%m-%d %H:%M"), "conjunto": conjunto,
            "filtros": _consulta(params)}
    if conjunto == "premiacoes":
        sql_where, args = _where(params)
        nomes = _nomes_olimpiadas()
        cur = con.execute(f"SELECT {COLS} FROM medalhas WHERE {sql_where} ORDER BY id", args)
        linhas = (_linha_premiacao(r, nomes) for r in cur)
        campos = CAMPOS_PREMIACAO
    else:
        o = ranking_ordenado(con, _params_ranking(params, conjunto))
        meta.update({"metodo": o["metodo"], "ordem": o["ordem"]})
        esc = _escolas_dos_alunos(con) if conjunto == "alunos" else {}
        linhas = (_linha_ranking(r, conjunto, esc) for r in com_posicoes(o))
        campos = CAMPOS_RANKING[conjunto] + CAMPOS_RANKING_FIM
    return _escrever(destino, linhas, campos, formato, separador, meta)


def _base_inteira(formato: str, separador: str) -> tuple:
    """Arquivo da base inteira (gzip), gerado uma vez por versão da base e reaproveitado."""
    stamp = int(DB_PATH.stat().st_mtime)
    sufixo = "csv" if formato == "csv" else "json"
    nome = f"premiacoes-{stamp}-{'pv' if separador == ';' else 'v'}.{sufixo}.gz"
    caminho = EXPORT_DIR / nome
    with _gerando:
        if not caminho.exists():
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            for velho in EXPORT_DIR.glob("premiacoes-*"):  # versões de bases antigas
                if f"-{stamp}-" not in velho.name:
                    velho.unlink(missing_ok=True)
            tmp = caminho.with_suffix(".tmp")
            with closing_con() as con, open(tmp, "wb") as bruto, gzip.GzipFile(fileobj=bruto, mode="wb",
                                                                                 compresslevel=6, mtime=0) as gz:
                n = _gerar(con, {}, "premiacoes", formato, separador, gz)
            tmp.replace(caminho)
            (caminho.with_suffix(".linhas")).write_text(str(n))
    linhas = int((caminho.with_suffix(".linhas")).read_text() or 0) if caminho.with_suffix(".linhas").exists() else 0
    return caminho, linhas


class closing_con:
    def __enter__(self):
        self.con = connect()
        return self.con

    def __exit__(self, *exc):
        self.con.close()


FILTROS_EXPORTACAO = ("uf", "municipio", "competicao", "area", "medalha", "nivel", "ano", "ano_de", "ano_ate", "rede",
                      "escola_id", "aluno_id", "nome", "escola", "busca")


def exportar(con, params: dict, aceita_gzip: bool) -> Download:
    formato = (params.get("formato") or "csv").lower()
    if formato not in ("csv", "json"):
        raise ParametroInvalido("formato deve ser csv ou json")
    separador = ";" if params.get("separador") in (";", "ponto-e-virgula", "excel") else ","
    conjunto = (params.get("conjunto") or "premiacoes").lower()
    if conjunto not in ("premiacoes", "alunos", "escolas", "estados"):
        raise ParametroInvalido("conjunto deve ser premiacoes, alunos, escolas ou estados")
    _filtros(params)  # valida antes de gerar
    _where(params)
    filtrado = any(params.get(k) for k in FILTROS_EXPORTACAO)
    partes = [conjunto if conjunto == "premiacoes" else f"ranking-{conjunto}"]
    for k in ("aluno_id", "escola_id", "nome", "escola", "busca", "uf", "competicao", "ano", "ano_de", "ano_ate", "nivel",
              "medalha"):
        if params.get(k):
            partes.append(re.sub(r"[^a-z0-9]+", "-", normalize(params[k]).lower())[:40].strip("-"))
    if conjunto != "premiacoes":
        partes.append(metodo_de(params)[0])
    nome = "medalhas-" + "-".join(p for p in partes if p) + f".{formato}"
    ctype = "text/csv; charset=utf-8" if formato == "csv" else "application/json; charset=utf-8"

    if conjunto == "premiacoes" and not filtrado:
        caminho, linhas = _base_inteira(formato, separador)
        return Download(nome, ctype, caminho, True, linhas)

    # filtrado: gera num arquivo temporário (memória até 8 MB, depois disco) e libera a base antes de enviar
    tmp = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    if aceita_gzip:
        with gzip.GzipFile(fileobj=tmp, mode="wb", compresslevel=5, mtime=0) as gz:
            linhas = _gerar(con, params, conjunto, formato, separador, gz)
    else:
        linhas = _gerar(con, params, conjunto, formato, separador, tmp)
    tmp.seek(0)
    return Download(nome, ctype, tmp, aceita_gzip, linhas)


def enviar_arquivo(dl: Download, wfile, aceita_gzip: bool) -> None:
    """Copia o arquivo para a conexão; descompacta se o cliente não aceitar gzip."""
    arquivo = open(dl.arquivo, "rb") if not hasattr(dl.arquivo, "read") else dl.arquivo
    try:
        if dl.gzipado and not aceita_gzip:
            with gzip.GzipFile(fileobj=arquivo, mode="rb") as gz:
                shutil.copyfileobj(gz, wfile, 256 * 1024)
        else:
            shutil.copyfileobj(arquivo, wfile, 256 * 1024)
    finally:
        arquivo.close()


# ---------------------------------------------------------------- roteamento

def rota(path: str):
    """(função, grupo de limite) para um caminho /api/v1/..., ou None. IDs vêm codificados no caminho."""
    partes = [unquote(p) for p in path.split("/")[3:] if p]  # depois de /api/v1/
    simples = {(): indice, ("olimpiadas",): olimpiadas, ("alunos",): buscar_alunos, ("escolas",): buscar_escolas,
               ("premiacoes",): premiacoes, ("openapi.json",): lambda con, p: openapi(p)}
    if tuple(partes) in simples:
        return simples[tuple(partes)], "v1"
    if partes == ["exportar"]:
        return "exportar", "exportar"
    if len(partes) == 2 and partes[0] == "alunos":
        return (lambda con, p: aluno(con, p, partes[1])), "v1"
    if len(partes) == 2 and partes[0] == "escolas":
        return (lambda con, p: escola(con, p, partes[1])), "v1"
    if len(partes) == 3 and partes[0] == "escolas" and partes[2] == "medalhistas":
        return (lambda con, p: medalhistas(con, p, partes[1])), "v1"
    if len(partes) == 2 and partes[0] == "ranking":
        return (lambda con, p: ranking(con, p, partes[1])), "v1"
    return None


# ---------------------------------------------------------------- OpenAPI 3.1

def _param(nome, descricao, tipo="string", onde="query", obrigatorio=False, exemplo=None):
    p = {"name": nome, "in": onde, "required": obrigatorio or onde == "path", "description": descricao,
         "schema": {"type": tipo}}
    if exemplo is not None:
        p["example"] = exemplo
    return p


FILTROS_DOC = [
    _param("uf", "Sigla do estado (ex.: SP)", exemplo="SP"),
    _param("municipio", "Município (acentos ignorados)"),
    _param("competicao", "Uma ou mais olimpíadas separadas por vírgula (siglas em /olimpiadas)", exemplo="OBMEP,OBM"),
    _param("area", "Área (Matemática, Informática…)"),
    _param("medalha", "Ouro, Prata, Bronze ou Menção Honrosa"),
    _param("nivel", "Um ou mais níveis separados por vírgula (ex.: 3 ou 1,2,3,Universitário)", exemplo="3"),
    _param("ano", "Ano exato", "integer"), _param("ano_de", "A partir do ano", "integer"),
    _param("ano_ate", "Até o ano", "integer"), _param("rede", "publica ou privada"),
]
PAGINA_DOC = [_param("limite", "Itens por página", "integer"), _param("offset", "Quantos itens pular", "integer")]
METODO_DOC = _param("metodo", "Método de pontuação que ordena os resultados: impa (padrão), impa3 ou site")


def _resp(descricao, exemplo=None):
    r = {"description": descricao, "content": {"application/json": {"schema": {"type": "object"}}}}
    if exemplo:
        r["content"]["application/json"]["example"] = exemplo
    return r


ERROS_DOC = {
    "400": _resp("Parâmetro inválido", {"erro": "parâmetro inválido: informe o parâmetro 'nome'"}),
    "404": _resp("Aluno, escola ou rota não encontrados", {"erro": "aluno não encontrado"}),
    "429": {"description": "Limite de consultas atingido; veja o cabeçalho Retry-After (segundos)",
            "headers": {"Retry-After": {"schema": {"type": "integer"}}}},
    "503": {"description": "Servidor ocupado; tente de novo em alguns segundos"},
}


def openapi(params: dict) -> dict:
    def op(resumo, descricao, parametros, exemplo=None, tag="Consulta"):
        return {"get": {"tags": [tag], "summary": resumo, "description": descricao, "parameters": parametros,
                        "responses": {"200": _resp("OK", exemplo), **ERROS_DOC}}}

    id_aluno = _param("id", "Id do aluno (campo `id` da busca), codificado na URL", onde="path",
                      exemplo="ERICK AKIRA KOGA|SP")
    id_escola = _param("id", "Id da escola (campo `id` da busca), codificado na URL", onde="path")
    return {
        "openapi": "3.1.0",
        "info": {"title": "Medalhas API", "version": VERSAO,
                 "description": "Medalhistas brasileiros em olimpíadas científicas (OBMEP, OBM, OBI, IMO, Ibero…). "
                                "Sem autenticação. Limite por IP: " + json.dumps(limites.resumo(), ensure_ascii=False)},
        "servers": [{"url": _base(params) or "/"}],
        "tags": [{"name": "Consulta"}, {"name": "Dados completos"}, {"name": "Referência"}],
        "paths": {
            "/api/v1/alunos": op("Buscar alunos pelo nome",
                                 "Todas as palavras precisam aparecer no nome (em qualquer ordem; acentos ignorados). "
                                 "Quem tem exatamente o nome pesquisado vem primeiro.",
                                 [_param("nome", "Nome ou parte do nome", obrigatorio=True, exemplo="erick akira koga"),
                                  _param("escola", "Só premiações por esta escola (aceita siglas)"),
                                  _param("premiacoes", "1 (padrão) inclui a lista de premiações; 0 só o resumo"),
                                  METODO_DOC, *FILTROS_DOC, *PAGINA_DOC]),
            "/api/v1/alunos/{id}": op("Um aluno e todas as premiações dele",
                                      "Use o `id` devolvido pela busca. Aceita os mesmos filtros para restringir as premiações.",
                                      [id_aluno, *FILTROS_DOC]),
            "/api/v1/escolas": op("Buscar escolas pelo nome",
                                  "Aceita siglas (IFAL, ETEC, EEEFM…) e ignora acentos e ordem das palavras.",
                                  [_param("nome", "Nome ou sigla da escola", obrigatorio=True, exemplo="ifal"),
                                   METODO_DOC, *FILTROS_DOC, *PAGINA_DOC]),
            "/api/v1/escolas/{id}": op("Resumo de uma escola", "Medalhas, pontos, posições e grafias do nome.",
                                       [id_escola]),
            "/api/v1/escolas/{id}/medalhistas": op(
                "Todos os medalhistas de uma escola",
                "Cada aluno premiado pela escola com as premiações por ela. Pagine com limite/offset (até 500).",
                [id_escola, _param("nome", "Filtra alunos pelo nome"),
                 _param("ordem", "pontos (padrão), nome ou recentes"), METODO_DOC, *FILTROS_DOC, *PAGINA_DOC]),
            "/api/v1/premiacoes": op("Todas as premiações (paginado)",
                                     "Base inteira ou filtrada, uma premiação por item, em ordem estável. Até 1000 por "
                                     "página; siga `proxima_pagina`. Para baixar tudo de uma vez, use /exportar.",
                                     [_param("nome", "Nome do aluno"), _param("escola", "Nome ou sigla da escola"),
                                      _param("busca", "Texto em nome, escola ou município"),
                                      _param("aluno_id", "Só deste aluno"), _param("escola_id", "Só desta escola"),
                                      *FILTROS_DOC, *PAGINA_DOC], tag="Dados completos"),
            "/api/v1/ranking/{tipo}": op("Ranking de alunos, escolas ou estados",
                                         "Mesmos critérios do site; empates dividem a posição.",
                                         [_param("tipo", "alunos, escolas ou estados", onde="path"), METODO_DOC,
                                          _param("ordem", "xp (pontos, padrão), medalhas (quadro) ou total"),
                                          *FILTROS_DOC, *PAGINA_DOC], tag="Dados completos"),
            "/api/v1/exportar": {"get": {
                "tags": ["Dados completos"], "summary": "Baixar dados em CSV ou JSON",
                "description": "Sem filtros, baixa a base inteira de premiações. Com filtros, só o que passar neles. "
                               "conjunto=alunos|escolas|estados baixa o ranking completo. CSV em UTF-8 com BOM; "
                               "separador=; para abrir direto no Excel em português. Respostas são compactadas (gzip) "
                               "quando o cliente aceita. Limite próprio por IP (ver /api/v1).",
                "parameters": [_param("formato", "csv (padrão) ou json"),
                               _param("conjunto", "premiacoes (padrão), alunos, escolas ou estados"),
                               _param("separador", "',' (padrão) ou ';'"), _param("aluno_id", "Só deste aluno"),
                               _param("escola_id", "Só desta escola"), _param("nome", "Nome do aluno"),
                               _param("escola", "Nome ou sigla da escola"), METODO_DOC, *FILTROS_DOC],
                "responses": {"200": {"description": "Arquivo", "content": {"text/csv": {}, "application/json": {}}},
                              **ERROS_DOC}}},
            "/api/v1/olimpiadas": op("Olimpíadas e valores aceitos", "Siglas, níveis, pontuação e valores dos filtros.",
                                     [], tag="Referência"),
            "/api/v1": op("Índice da API", "Rotas, exemplos e limites atuais.", [], tag="Referência"),
        },
    }
