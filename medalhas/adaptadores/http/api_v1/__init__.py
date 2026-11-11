"""API pública v1: alunos, escolas, premiações, rankings e exportação (CSV/JSON).

Rotas estáveis para outros sistemas: só mudam numa nova versão (/api/v2). A API interna do site
(rotas_site.py) pode mudar sem aviso. Documentação: página "API & Dados" do site, GET /api/v1 e
GET /api/v1/openapi.json.

    parametros.py    validação da URL
    rotas.py         uma função por rota + roteamento
    apresentacao.py  formato JSON das respostas (o contrato público)
    exportacao.py    arquivos CSV/JSON
    openapi.py       especificação OpenAPI 3.1
"""
from .erros import NaoEncontrado, ParametroInvalido
from .exportacao import Download
from .rotas import Rota, rota

__all__ = ["Download", "NaoEncontrado", "ParametroInvalido", "Rota", "rota"]
