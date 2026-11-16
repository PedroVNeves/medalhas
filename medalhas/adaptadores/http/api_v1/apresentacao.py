"""Formato das respostas JSON da API v1: o contrato público. Mudar um campo aqui quebra clientes;
campos novos podem entrar, os existentes só mudam numa /api/v2."""
from collections.abc import Iterable
from urllib.parse import quote

from ....aplicacao.portas import Linha
from ....dominio import pontuacao
from ....dominio.enderecos import slug
from ....dominio.premiacao import BRONZE, MENCAO, OURO, PRATA
from ....dominio.texto import normalizar


class Links:
    """URLs absolutas da API e do site, a partir do endereço pelo qual o cliente chegou."""

    def __init__(self, base: str):
        self.base = base

    def api(self, rota: str, ident: str, sufixo: str = "") -> str:
        return f"{self.base}/api/v1/{rota}/{quote(ident, safe='')}{sufixo}"

    def site(self, pagina: str, ident: str) -> str:
        """Página do aluno ou da escola. Escolas: o servidor redireciona do slug do id para o endereço oficial."""
        return f"{self.base}/{pagina}/{slug(ident)}"


def consulta(params: dict) -> dict:
    """Parâmetros recebidos, devolvidos para o cliente conferir o que foi aplicado."""
    return {k: v for k, v in params.items() if not k.startswith("_")}


def nomes_das_olimpiadas() -> dict[str, str]:
    return {o["sigla"]: o["nome"] for o in pontuacao.catalogo()}


def pontos(linha: Linha) -> dict:
    """Pontos nos três métodos: {"impa": …, "impa3": …, "site": …}."""
    return {m: linha[i["coluna"]] or 0 for m, i in pontuacao.METODOS.items()}


def medalhas(linha: Linha) -> dict:
    return {"ouro": linha["ouro"], "prata": linha["prata"], "bronze": linha["bronze"],
            "mencao_honrosa": linha["mencao"], "total": linha["total"]}


def contar_medalhas(premiacoes: list[Linha]) -> dict:
    def quantas(medalha: str) -> int:
        return sum(r["medalha"] == medalha for r in premiacoes)
    return {"ouro": quantas(OURO), "prata": quantas(PRATA), "bronze": quantas(BRONZE),
            "mencao_honrosa": quantas(MENCAO), "total": len(premiacoes)}


def posicoes(resumo: Linha) -> dict:
    """Posição nacional e estadual em cada método (None quando não pontua no método)."""
    return {m: ({"nacional": resumo[f"{i['coluna']}_pos"], "estadual": resumo[f"{i['coluna']}_pos_uf"]}
                if resumo[i["coluna"]] else None) for m, i in pontuacao.METODOS.items()}


def sem_repetir(valores: Iterable[str | None]) -> list[str]:
    """Une grafias do mesmo valor ("SAO PAULO", "São Paulo"), ficando com a mais legível
    (a que tem mais minúsculas e acentos)."""
    grupos: dict[str, list[str]] = {}
    for v in valores:
        if v:
            grupos.setdefault(normalizar(v), []).append(v)
    return [max(vs, key=lambda v: (sum(c.islower() for c in v), sum(not c.isascii() for c in v)))
            for vs in grupos.values()]


def premiacao(r: Linha, nomes: dict[str, str]) -> dict:
    return {
        "id": r["id"], "olimpiada": r["competicao"], "olimpiada_nome": nomes.get(r["competicao"], r["competicao"]),
        "area": r["area"], "ano": r["ano"], "nivel": r["nivel"], "medalha": r["medalha"], "premio": r["premio"],
        "nome_na_lista": r["nome"], "aluno_id": r["aluno_id"], "escola": r["escola"], "escola_id": r["escola_chave"],
        "municipio": r["municipio"], "uf": r["uf"], "rede": r["rede"], "nota": r["pontos"],
        "pontos": pontos(r), "fonte": r["fonte"],
    }


def aluno(resumo: Linha, premiacoes: list[Linha], links: Links, incluir_premiacoes: bool) -> dict:
    escolas: dict[str, list[str]] = {}
    for r in premiacoes:   # mais recente primeiro; grafias da mesma escola (mesma chave) viram um item só
        if r["escola_chave"]:
            escolas.setdefault(r["escola_chave"], []).append(r["escola"])
    item = {
        "id": resumo["id"], "nome": resumo["nome"], "uf": resumo["uf"],
        "escolas": [{"id": k, "nome": sem_repetir(v)[0], "api": links.api("escolas", k),
                     "perfil": links.site("escola", k)} for k, v in escolas.items()],
        "municipios": sorted(sem_repetir(r["municipio"] for r in premiacoes), key=normalizar),
        "olimpiadas": sorted({r["competicao"] for r in premiacoes}),
        "anos": {"de": resumo["de"], "ate": resumo["ate"]},
        "medalhas": medalhas(resumo), "pontos": pontos(resumo), "posicao": posicoes(resumo),
        "premiacoes_encontradas": len(premiacoes),
        "api": links.api("alunos", resumo["id"]), "perfil": links.site("aluno", resumo["id"]),
    }
    if incluir_premiacoes:
        nomes = nomes_das_olimpiadas()
        item["premiacoes"] = [premiacao(r, nomes) for r in premiacoes]
    return item


def escola(resumo: Linha, links: Links) -> dict:
    return {
        "id": resumo["id"], "nome": resumo["nome"], "municipio": resumo["municipio"], "uf": resumo["uf"],
        "rede": resumo["rede"], "esfera": resumo["esfera"], "alunos_premiados": resumo["alunos"],
        "anos": {"de": resumo["de"], "ate": resumo["ate"]},
        "medalhas": medalhas(resumo), "pontos": pontos(resumo), "posicao": posicoes(resumo),
        "api": links.api("escolas", resumo["id"]),
        "medalhistas": links.api("escolas", resumo["id"], "/medalhistas"),
        "perfil": links.site("escola", resumo["id"]),
    }


def medalhista(aluno_id: str, info: Linha | None, premiacoes: list[Linha], links: Links, nomes: dict) -> dict:
    """Aluno na lista de medalhistas de uma escola: só as premiações por essa escola."""
    return {
        "id": aluno_id, "nome": premiacoes[0]["nome"] if info is None else info["nome"],
        "uf": None if info is None else info["uf"],
        "anos": sorted({r["ano"] for r in premiacoes}),
        "medalhas_nesta_escola": contar_medalhas(premiacoes),
        "pontos_nesta_escola": {m: sum(r[c["coluna"]] or 0 for r in premiacoes) for m, c in pontuacao.METODOS.items()},
        "api": links.api("alunos", aluno_id), "perfil": links.site("aluno", aluno_id),
        "premiacoes": [premiacao(r, nomes) for r in premiacoes],
    }


def item_ranking(r: dict, tipo: str, links: Links) -> dict:
    item = {"posicao": r["pos"], "id": r["id"], "nome": r["nome"]}
    if tipo == "alunos":
        item.update({"uf": r.get("uf"), "escola": r.get("escola"), "municipio": r.get("municipio")})
    elif tipo == "escolas":
        item.update({"municipio": r.get("municipio"), "uf": r.get("uf"), "rede": r.get("rede"),
                     "alunos_premiados": r.get("alunos")})
    else:
        item.update({"alunos_premiados": r.get("alunos"), "escolas": r.get("escolas")})
    item.update({"medalhas": medalhas(r), "pontos": r["xp"], "pontos_metodos": pontos(r),
                 "anos": {"de": r.get("de"), "ate": r.get("ate")}})
    if tipo != "estados":
        item["api"] = links.api(tipo, r["id"])
    return item
