"""Portas: o que o núcleo espera dos adaptadores, descrito como interfaces (typing.Protocol).

Escrita (gerar a base):  Coletor -> gerar_base -> RepositorioPremiacoes
Leitura (site e API):    adaptador HTTP -> FonteDeLeitura.sessao() -> SessaoDeLeitura

A leitura não passa por um caso de uso intermediário de propósito: as consultas são relatórios
(agregações, rankings, paginação) e cada camada extra só repetiria a assinatura. As regras de negócio
que elas usam (pontuação, ranking, tiers, conquistas) continuam no domínio.
"""
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..dominio.enderecos import Enderecos
from ..dominio.escolas import Expansao
from ..dominio.premiacao import Premiacao
from ..dominio.ranking import RankingOrdenado

Linha = Mapping[str, Any]   # registro lido da base, indexável pelo nome da coluna


# ---------------------------------------------------------------- escrita

class Coletor(Protocol):
    """Lê as premiações de uma fonte oficial."""
    sigla: str

    def coletar(self, log: Callable[[str], None]) -> list[Premiacao]: ...


class RepositorioPremiacoes(Protocol):
    """Guarda a base pesquisável."""

    def substituir(self, registros: list[dict], atualizado_em: str) -> None:
        """Troca a base inteira pelos registros (premiações indexadas por gerar_base.indexar)."""


# ---------------------------------------------------------------- leitura

@dataclass(frozen=True)
class Criterios:
    """Recorte de premiações pedido por um cliente, já validado.

    filtros: campo -> valor ("uf", "competicao" (lista separada por vírgula), "ano", "escola_chave"…)
    textos:  (campo, palavras) com campo em nome | escola | tudo; todas as palavras precisam casar
    """
    filtros: dict = field(default_factory=dict)
    textos: tuple[tuple[str, Expansao], ...] = ()
    aluno_id: str | None = None


class SessaoDeLeitura(Protocol):
    """Consultas feitas durante uma requisição (uma conexão com a base)."""

    # páginas do site (parâmetros crus da URL; a validação é tolerante)
    def busca(self, params: dict) -> dict: ...
    def sugestoes(self, params: dict) -> dict: ...
    def ranking(self, params: dict) -> dict: ...
    def perfil_aluno(self, aluno_id: str, params: dict) -> dict: ...
    def perfil_escola(self, escola_id: str, params: dict) -> dict: ...
    def perfil_cidade(self, cidade_id: str, params: dict) -> dict: ...
    def visao_geral(self, params: dict) -> dict: ...
    def enderecos(self) -> Enderecos:
        """Endereços legíveis de todas as páginas de aluno e escola (/aluno/maria-souza-lima-al)."""

    # API pública (critérios já validados pelo adaptador HTTP)
    def resumo_base(self) -> dict: ...
    def estatisticas_olimpiadas(self) -> dict: ...
    def niveis(self) -> set[str]: ...
    def ranking_ordenado(self, params: dict) -> RankingOrdenado: ...
    def ultima_escola_dos_alunos(self) -> dict[str, tuple[str | None, str | None]]: ...
    def buscar_alunos(self, criterios: Criterios, nome: str, coluna: str, offset: int,
                      limite: int) -> tuple[int, list[tuple[Linha, list[Linha]]]]: ...
    def aluno(self, aluno_id: str, criterios: Criterios) -> tuple[Linha, list[Linha]] | None: ...
    def buscar_escolas(self, criterios: Criterios, coluna: str, offset: int,
                       limite: int) -> tuple[int, list[Linha]]: ...
    def escola(self, escola_id: str) -> tuple[Linha, list[str]] | None: ...
    def medalhistas(self, escola_id: str, criterios: Criterios, ordem: str, coluna: str, offset: int,
                    limite: int) -> tuple[Linha, int, list[tuple[str, Linha | None, list[Linha]]]] | None: ...
    def premiacoes(self, criterios: Criterios, offset: int, limite: int) -> tuple[int, list[Linha]]: ...
    def iterar_premiacoes(self, criterios: Criterios) -> Iterator[Linha]: ...


class FonteDeLeitura(Protocol):
    def sessao(self) -> AbstractContextManager[SessaoDeLeitura]: ...

    def versao(self) -> int:
        """Muda sempre que a base é regerada (serve para invalidar arquivos derivados)."""
