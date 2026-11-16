"""Rotas da API pública v1.

Cada rota recebe a sessão de leitura e o pedido, valida os parâmetros (parametros), consulta a base
pela porta SessaoDeLeitura e monta a resposta (apresentacao).
"""
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote, unquote

from ....aplicacao.portas import Criterios, SessaoDeLeitura
from ....dominio import pontuacao
from ....dominio.premiacao import PREMIOS, UFS
from ....dominio.ranking import com_posicoes
from .. import limites
from ..pedido import Pedido
from . import apresentacao as ap
from . import parametros
from .erros import NaoEncontrado
from .exportacao import exportar
from .openapi import VERSAO, especificacao

Funcao = Callable[[SessaoDeLeitura, Pedido], object]


@dataclass(frozen=True)
class Rota:
    funcao: Funcao
    grupo: str   # grupo de limite por IP (limites.GRUPOS)
    # segundos que o CDN do Firebase Hosting pode guardar a resposta (0 = não guarda). Só para respostas
    # que mudam apenas quando a base muda: cada `firebase deploy` limpa o CDN.
    cache_cdn: int = 0


# ---------------------------------------------------------------- referência

def indice(s: SessaoDeLeitura, pedido: Pedido) -> dict:
    b = pedido.base
    base = s.resumo_base()
    return {
        "nome": "Medalhas API", "versao": VERSAO, "atualizado_em": base["atualizado_em"],
        "premiacoes": base["premiacoes"],
        "documentacao": f"{b}/dados", "openapi": f"{b}/api/v1/openapi.json",
        "rotas": {
            "GET /api/v1/alunos?nome=": "busca alunos pelo nome",
            "GET /api/v1/alunos/{id}": "um aluno e todas as premiações dele",
            "GET /api/v1/escolas?nome=": "busca escolas pelo nome ou sigla",
            "GET /api/v1/escolas/{id}": "resumo de uma escola",
            "GET /api/v1/escolas/{id}/medalhistas": "todos os alunos premiados de uma escola",
            "GET /api/v1/premiacoes": "todas as premiações, com filtros e paginação",
            "GET /api/v1/ranking/{alunos|escolas|estados|cidades}": "rankings com filtros",
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


def olimpiadas(s: SessaoDeLeitura, pedido: Pedido) -> dict:
    estatisticas = s.estatisticas_olimpiadas()
    catalogo = pontuacao.catalogo()

    def olimpiada(o: dict) -> dict:
        total, de, ate = estatisticas["premiacoes"].get(o["sigla"], (0, None, None))
        return {
            "sigla": o["sigla"], "nome": o["nome"], "area": o["area"], "internacional": o["internacional"],
            "premiacoes": total, "anos": {"de": de, "ate": ate},
            "niveis": estatisticas["niveis"].get(o["sigla"], []), "site_oficial": o["site"],
            "pontos": {"impa": o["pontos"], "impa3_niveis": o["impa_niveis"], "site": o["pontos_site"]},
        }

    return {"olimpiadas": [olimpiada(o) for o in catalogo], "medalhas": list(PREMIOS), "ufs": sorted(UFS),
            "areas": sorted({o["area"] for o in catalogo}), "redes": ["publica", "privada"],
            "metodos": pontuacao.metodos()}


# ---------------------------------------------------------------- alunos

def buscar_alunos(s: SessaoDeLeitura, pedido: Pedido) -> dict:
    params = pedido.params
    parametros.texto(params, "nome", obrigatorio=True)
    limite, offset = parametros.paginacao(params, "alunos")
    metodo, coluna = parametros.metodo(params)
    criterios = parametros.criterios(params, s, (("nome", "nome"), ("escola", "escola")))
    total, encontrados = s.buscar_alunos(criterios, params["nome"], coluna, offset, limite)
    links, incluir = ap.Links(pedido.base), parametros.booleano(params, "premiacoes", True)
    return {"consulta": ap.consulta(params), "metodo": metodo, "total": total, "offset": offset, "limite": limite,
            "alunos": [ap.aluno(resumo, premiacoes, links, incluir) for resumo, premiacoes in encontrados]}


def aluno(s: SessaoDeLeitura, pedido: Pedido, aluno_id: str) -> dict:
    achado = s.aluno(aluno_id, parametros.criterios(pedido.params, s, ()))
    if not achado:
        raise NaoEncontrado(f"aluno não encontrado: {aluno_id!r}. Busque o id em GET /api/v1/alunos?nome=")
    resumo, premiacoes = achado
    return {"aluno": ap.aluno(resumo, premiacoes, ap.Links(pedido.base), True)}


# ---------------------------------------------------------------- escolas

def buscar_escolas(s: SessaoDeLeitura, pedido: Pedido) -> dict:
    params = pedido.params
    palavras = parametros.texto(params, "nome", obrigatorio=True)
    limite, offset = parametros.paginacao(params, "escolas")
    metodo, coluna = parametros.metodo(params)
    criterios = Criterios(parametros.filtros(params, s), (("escola", palavras),))
    total, resumos = s.buscar_escolas(criterios, coluna, offset, limite)
    links = ap.Links(pedido.base)
    return {"consulta": ap.consulta(params), "metodo": metodo, "total": total, "offset": offset,
            "limite": limite, "escolas": [ap.escola(r, links) for r in resumos]}


def escola(s: SessaoDeLeitura, pedido: Pedido, escola_id: str) -> dict:
    achado = s.escola(escola_id)
    if not achado:
        raise NaoEncontrado(f"escola não encontrada: {escola_id!r}. Busque o id em GET /api/v1/escolas?nome=")
    resumo, grafias = achado
    return {"escola": {**ap.escola(resumo, ap.Links(pedido.base)), "grafias": grafias}}


def medalhistas(s: SessaoDeLeitura, pedido: Pedido, escola_id: str) -> dict:
    params = pedido.params
    limite, offset = parametros.paginacao(params, "medalhistas")
    metodo, coluna = parametros.metodo(params)
    criterios = parametros.criterios(params, s, (("nome", "nome"),))
    achado = s.medalhistas(escola_id, criterios, params.get("ordem", ""), coluna, offset, limite)
    if not achado:
        raise NaoEncontrado(f"escola não encontrada: {escola_id!r}. Busque o id em GET /api/v1/escolas?nome=")
    resumo, total, alunos = achado
    links, nomes = ap.Links(pedido.base), ap.nomes_das_olimpiadas()
    return {"escola": {"id": resumo["id"], "nome": resumo["nome"], "municipio": resumo["municipio"],
                       "uf": resumo["uf"], "api": links.api("escolas", escola_id)},
            "consulta": ap.consulta(params), "metodo": metodo, "total": total, "offset": offset, "limite": limite,
            "medalhistas": [ap.medalhista(i, info, premiacoes, links, nomes) for i, info, premiacoes in alunos]}


# ---------------------------------------------------------------- dados completos

def premiacoes(s: SessaoDeLeitura, pedido: Pedido) -> dict:
    params = pedido.params
    limite, offset = parametros.paginacao(params, "premiacoes")
    total, linhas = s.premiacoes(parametros.criterios(params, s), offset, limite)
    proxima = None
    if offset + limite < total:
        q = {**{k: v for k, v in ap.consulta(params).items() if k != "offset"}, "offset": offset + limite}
        proxima = f"{pedido.base}/api/v1/premiacoes?" + "&".join(f"{k}={quote(str(v))}" for k, v in q.items())
    nomes = ap.nomes_das_olimpiadas()
    return {"consulta": ap.consulta(params), "total": total, "offset": offset, "limite": limite,
            "proxima_pagina": proxima, "premiacoes": [ap.premiacao(r, nomes) for r in linhas]}


def ranking(s: SessaoDeLeitura, pedido: Pedido, tipo: str) -> dict:
    params = pedido.params
    limite, offset = parametros.paginacao(params, "ranking")
    r = s.ranking_ordenado(parametros.ranking(params, tipo, s))
    itens = list(com_posicoes(r, offset, limite))
    if tipo == "alunos":   # rankings filtrados não trazem a escola: completa com a mais recente
        ultima_escola = s.ultima_escola_dos_alunos()
        for item in itens:
            if not item.get("escola"):
                item["escola"], item["municipio"] = ultima_escola.get(item["id"], (None, None))
    links = ap.Links(pedido.base)
    return {"consulta": ap.consulta(params), "tipo": tipo, "metodo": r.metodo, "ordem": r.ordem,
            "niveis_considerados": r.niveis, "total": len(r.itens), "offset": offset, "limite": limite,
            "itens": [ap.item_ranking(item, tipo, links) for item in itens]}


# ---------------------------------------------------------------- roteamento

_FIXAS = {
    (): Rota(indice, "v1"),
    ("olimpiadas",): Rota(olimpiadas, "v1"),
    ("openapi.json",): Rota(lambda s, pedido: especificacao(pedido.base), "v1"),
    ("alunos",): Rota(buscar_alunos, "v1"),
    ("escolas",): Rota(buscar_escolas, "v1"),
    ("premiacoes",): Rota(premiacoes, "v1"),
    ("exportar",): Rota(exportar, "exportar"),
}
# (tamanho do caminho, primeira parte, última parte ou None) -> função que recebe o id
_COM_ID: dict[tuple, Callable] = {
    (2, "alunos", None): aluno,
    (2, "escolas", None): escola,
    (3, "escolas", "medalhistas"): medalhistas,
    (2, "ranking", None): ranking,
}


def rota(caminho: str) -> Rota | None:
    """Rota para um caminho /api/v1/..., ou None. Ids chegam codificados (%7C para |)."""
    partes = tuple(unquote(p) for p in caminho.split("/")[3:] if p)   # depois de /api/v1/
    if partes in _FIXAS:
        return _FIXAS[partes]
    if len(partes) in (2, 3):
        funcao = _COM_ID.get((len(partes), partes[0], partes[2] if len(partes) == 3 else None))
        if funcao:
            ident = partes[1]
            return Rota(lambda s, pedido: funcao(s, pedido, ident), "v1")
    return None
