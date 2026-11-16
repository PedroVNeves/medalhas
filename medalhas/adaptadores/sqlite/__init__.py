"""Adaptador SQLite: gravação da base (RepositorioSqlite) e leitura (LeituraSqlite)."""
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ...aplicacao.portas import Criterios
from . import consultas_api as api
from . import consultas_site as site
from .conexao import Cache, Conexao
from .gravacao import RepositorioSqlite

__all__ = ["LeituraSqlite", "RepositorioSqlite", "SessaoSqlite"]


class SessaoSqlite:
    """Implementa aplicacao.portas.SessaoDeLeitura sobre uma conexão somente leitura."""

    def __init__(self, con: Conexao):
        self._con = con

    # páginas do site
    def busca(self, params: dict) -> dict:
        return site.busca(self._con, params)

    def sugestoes(self, params: dict) -> dict:
        return site.sugestoes(self._con, params)

    def ranking(self, params: dict) -> dict:
        return site.ranking(self._con, params)

    def perfil_aluno(self, aluno_id: str, params: dict) -> dict:
        return site.perfil_aluno(self._con, aluno_id, params)

    def perfil_escola(self, escola_id: str, params: dict) -> dict:
        return site.perfil_escola(self._con, escola_id, params)

    def perfil_cidade(self, cidade_id: str, params: dict) -> dict:
        return site.perfil_cidade(self._con, cidade_id, params)

    def visao_geral(self, params: dict) -> dict:
        return site.visao_geral(self._con, params)

    def enderecos(self):
        return site.enderecos(self._con)

    def ranking_ordenado(self, params: dict):
        return site.ranking_ordenado(self._con, params)

    # API pública
    def resumo_base(self) -> dict:
        return api.resumo_base(self._con)

    def estatisticas_olimpiadas(self) -> dict:
        return api.estatisticas_olimpiadas(self._con)

    def niveis(self) -> set[str]:
        return api.niveis(self._con)

    def ultima_escola_dos_alunos(self) -> dict:
        return api.ultima_escola_dos_alunos(self._con)

    def buscar_alunos(self, criterios: Criterios, nome: str, coluna: str, offset: int, limite: int):
        return api.buscar_alunos(self._con, criterios, nome, coluna, offset, limite)

    def aluno(self, aluno_id: str, criterios: Criterios):
        return api.aluno(self._con, aluno_id, criterios)

    def buscar_escolas(self, criterios: Criterios, coluna: str, offset: int, limite: int):
        return api.buscar_escolas(self._con, criterios, coluna, offset, limite)

    def escola(self, escola_id: str):
        return api.escola(self._con, escola_id)

    def medalhistas(self, escola_id: str, criterios: Criterios, ordem: str, coluna: str, offset: int, limite: int):
        return api.medalhistas(self._con, escola_id, criterios, ordem, coluna, offset, limite)

    def premiacoes(self, criterios: Criterios, offset: int, limite: int):
        return api.premiacoes(self._con, criterios, offset, limite)

    def iterar_premiacoes(self, criterios: Criterios):
        return api.iterar_premiacoes(self._con, criterios)


class LeituraSqlite:
    """Implementa aplicacao.portas.FonteDeLeitura. Uma conexão por sessão; o cache é compartilhado."""

    def __init__(self, caminho: Path):
        self.caminho = caminho
        self._cache = Cache(caminho)

    @contextmanager
    def sessao(self) -> Iterator[SessaoSqlite]:
        con = Conexao(self.caminho, self._cache)
        try:
            yield SessaoSqlite(con)
        finally:
            con.close()

    def versao(self) -> int:
        return int(self.caminho.stat().st_mtime)
