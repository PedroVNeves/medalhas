"""Especificação OpenAPI 3.1 da API v1 (GET /api/v1/openapi.json), para Postman, Insomnia ou Swagger."""
import json

from .. import limites

VERSAO = "1.1.0"


def _parametro(nome: str, descricao: str, tipo: str = "string", onde: str = "query", obrigatorio: bool = False,
               exemplo=None) -> dict:
    """Um parâmetro no formato OpenAPI. Parâmetros de caminho (onde="path") são sempre obrigatórios."""
    p = {"name": nome, "in": onde, "required": obrigatorio or onde == "path", "description": descricao,
         "schema": {"type": tipo}}
    if exemplo is not None:
        p["example"] = exemplo
    return p


def _resposta(descricao: str, exemplo=None) -> dict:
    """Uma resposta JSON no formato OpenAPI, com exemplo opcional."""
    r = {"description": descricao, "content": {"application/json": {"schema": {"type": "object"}}}}
    if exemplo:
        r["content"]["application/json"]["example"] = exemplo
    return r


FILTROS = [
    _parametro("uf", "Sigla do estado (ex.: SP)", exemplo="SP"),
    _parametro("municipio", "Município (acentos ignorados)"),
    _parametro("competicao", "Uma ou mais olimpíadas separadas por vírgula (siglas em /olimpiadas)",
               exemplo="OBMEP,OBM"),
    _parametro("area", "Área (Matemática, Informática…)"),
    _parametro("medalha", "Ouro, Prata, Bronze ou Menção Honrosa"),
    _parametro("nivel", "Um ou mais níveis separados por vírgula (ex.: 3 ou 1,2,3,Universitário)", exemplo="3"),
    _parametro("ano", "Ano exato", "integer"),
    _parametro("ano_de", "A partir do ano", "integer"),
    _parametro("ano_ate", "Até o ano", "integer"),
    _parametro("rede", "publica ou privada"),
    _parametro("sexo", "F: só alunas premiadas em olimpíadas só para meninas (EGMO, PAGMO, EGOI), com todas as "
                       "premiações delas"),
]
PAGINA = [_parametro("limite", "Itens por página", "integer"),
          _parametro("offset", "Quantos itens pular", "integer")]
METODO = _parametro("metodo", "Método de pontuação que ordena os resultados: impa (padrão), impa3 ou site")
ID_ALUNO = _parametro("id", "Id do aluno (campo `id` da busca), codificado na URL", onde="path",
                      exemplo="ERICK AKIRA KOGA|SP")
ID_ESCOLA = _parametro("id", "Id da escola (campo `id` da busca), codificado na URL", onde="path")
ALUNO_ID = _parametro("aluno_id", "Só deste aluno")
ESCOLA_ID = _parametro("escola_id", "Só desta escola")
ERROS = {
    "400": _resposta("Parâmetro inválido", {"erro": "parâmetro inválido: informe o parâmetro 'nome'"}),
    "404": _resposta("Aluno, escola ou rota não encontrados", {"erro": "aluno não encontrado"}),
    "429": {"description": "Limite de consultas atingido; veja o cabeçalho Retry-After (segundos)",
            "headers": {"Retry-After": {"schema": {"type": "integer"}}}},
    "503": {"description": "Servidor ocupado; tente de novo em alguns segundos"},
}


def _get(resumo: str, descricao: str, parametros: list, tag: str = "Consulta", respostas: dict | None = None) -> dict:
    """Uma operação GET; sem `respostas`, documenta o 200 e os erros comuns (400, 404, 429, 503)."""
    return {"get": {"tags": [tag], "summary": resumo, "description": descricao, "parameters": parametros,
                    "responses": respostas or {"200": _resposta("OK"), **ERROS}}}


ROTAS = {
    "/api/v1/alunos": _get(
        "Buscar alunos pelo nome",
        "Todas as palavras precisam aparecer no nome (em qualquer ordem; acentos ignorados). "
        "Quem tem exatamente o nome pesquisado vem primeiro.",
        [_parametro("nome", "Nome ou parte do nome", obrigatorio=True, exemplo="erick akira koga"),
         _parametro("escola", "Só premiações por esta escola (aceita siglas)"),
         _parametro("premiacoes", "1 (padrão) inclui a lista de premiações; 0 só o resumo"),
         METODO, *FILTROS, *PAGINA]),
    "/api/v1/alunos/{id}": _get(
        "Um aluno e todas as premiações dele",
        "Use o `id` devolvido pela busca. Aceita os mesmos filtros para restringir as premiações.",
        [ID_ALUNO, *FILTROS]),
    "/api/v1/escolas": _get(
        "Buscar escolas pelo nome",
        "Aceita siglas (IFAL, ETEC, EEEFM…) e ignora acentos e ordem das palavras.",
        [_parametro("nome", "Nome ou sigla da escola", obrigatorio=True, exemplo="ifal"), METODO, *FILTROS, *PAGINA]),
    "/api/v1/escolas/{id}": _get(
        "Resumo de uma escola", "Medalhas, pontos, posições e grafias do nome.", [ID_ESCOLA]),
    "/api/v1/escolas/{id}/medalhistas": _get(
        "Todos os medalhistas de uma escola",
        "Cada aluno premiado pela escola com as premiações por ela. Pagine com limite/offset (até 500).",
        [ID_ESCOLA, _parametro("nome", "Filtra alunos pelo nome"),
         _parametro("ordem", "pontos (padrão), nome ou recentes"), METODO, *FILTROS, *PAGINA]),
    "/api/v1/premiacoes": _get(
        "Todas as premiações (paginado)",
        "Base inteira ou filtrada, uma premiação por item, em ordem estável. Até 1000 por "
        "página; siga `proxima_pagina`. Para baixar tudo de uma vez, use /exportar.",
        [_parametro("nome", "Nome do aluno"), _parametro("escola", "Nome ou sigla da escola"),
         _parametro("busca", "Texto em nome, escola ou município"), ALUNO_ID, ESCOLA_ID, *FILTROS, *PAGINA],
        tag="Dados completos"),
    "/api/v1/ranking/{tipo}": _get(
        "Ranking de alunos, escolas, estados ou cidades",
        "Mesmos critérios do site; empates dividem a posição.",
        [_parametro("tipo", "alunos, escolas, estados ou cidades", onde="path"), METODO,
         _parametro("ordem", "xp (pontos, padrão), medalhas (quadro) ou total"), *FILTROS, *PAGINA],
        tag="Dados completos"),
    "/api/v1/exportar": _get(
        "Baixar dados em CSV ou JSON",
        "Sem filtros, baixa a base inteira de premiações. Com filtros, só o que passar neles. "
        "conjunto=alunos|escolas|estados|cidades baixa o ranking completo. CSV em UTF-8 com BOM; "
        "separador=; para abrir direto no Excel em português. Respostas são compactadas (gzip) "
        "quando o cliente aceita. Limite próprio por IP (ver /api/v1).",
        [_parametro("formato", "csv (padrão) ou json"),
         _parametro("conjunto", "premiacoes (padrão), alunos, escolas, estados ou cidades"),
         _parametro("separador", "',' (padrão) ou ';'"), ALUNO_ID, ESCOLA_ID, _parametro("nome", "Nome do aluno"),
         _parametro("escola", "Nome ou sigla da escola"), METODO, *FILTROS],
        tag="Dados completos",
        respostas={"200": {"description": "Arquivo", "content": {"text/csv": {}, "application/json": {}}}, **ERROS}),
    "/api/v1/olimpiadas": _get(
        "Olimpíadas e valores aceitos", "Siglas, níveis, pontuação e valores dos filtros.", [], tag="Referência"),
    "/api/v1": _get("Índice da API", "Rotas, exemplos e limites atuais.", [], tag="Referência"),
}


def especificacao(base: str) -> dict:
    """Documento OpenAPI 3.1 com o endereço do servidor e os limites em vigor."""
    return {
        "openapi": "3.1.0",
        "info": {"title": "Medalhas API", "version": VERSAO,
                 "description": "Medalhistas brasileiros em olimpíadas científicas (OBMEP, OBM, OBI, IMO, Ibero…). "
                                "Sem autenticação. Limite por IP: "
                                + json.dumps(limites.resumo(), ensure_ascii=False)},
        "servers": [{"url": base or "/"}],
        "tags": [{"name": "Consulta"}, {"name": "Dados completos"}, {"name": "Referência"}],
        "paths": ROTAS,
    }
