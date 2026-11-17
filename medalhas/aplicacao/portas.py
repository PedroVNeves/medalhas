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
from ..dominio.ranking import PaginaDoRanking

Linha = Mapping[str, Any]   # registro lido da base, indexável pelo nome da coluna


# ---------------------------------------------------------------- escrita

class Coletor(Protocol):
    """Lê as premiações de uma fonte oficial."""
    sigla: str

    def coletar(self, log: Callable[[str], None]) -> list[Premiacao]:
        """Todas as premiações publicadas pela fonte, já no vocabulário do domínio. Pode lançar exceção se a
        fonte estiver fora do ar: gerar_base registra a falha e segue com as outras."""


class RepositorioPremiacoes(Protocol):
    """Guarda a base pesquisável."""

    def substituir(self, registros: list[dict], atualizado_em: str) -> None:
        """Troca a base inteira pelos registros (premiações indexadas por gerar_base.indexar)."""

    def premiacoes_por_olimpiada(self) -> dict[str, int]:
        """Quantas premiações de cada olimpíada (sigla) a base atual tem; vazio se ainda não há base."""


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

    # ------------------------------------------------ páginas do site
    # Recebem os parâmetros crus da URL; valor desconhecido vira o padrão (a validação é tolerante).
    def busca(self, params: dict) -> dict:
        """Alunos (ou escolas, no campo escola) que mais pontuam entre as premiações que casam com o texto
        (q, campo nome|escola|tudo) e os filtros: as contagens de cada um e as premiações que a tela mostra."""

    def sugestoes(self, params: dict) -> dict:
        """Até 8 alunos e escolas mais premiados que casam com o texto digitado (lista enquanto digita)."""

    def ranking(self, params: dict) -> dict:
        """Uma página do ranking (tipo alunos|escolas|estados|cidades), com posição e nível de cada item."""

    def perfil_aluno(self, aluno_id: str, params: dict) -> dict:
        """Perfil completo do aluno, ou {"erro": ...} se o id não existe."""

    def perfil_escola(self, escola_id: str, params: dict) -> dict:
        """Perfil completo da escola, ou {"erro": ...} se o id não existe."""

    def premiacoes_recentes_da_escola(self, escola_id: str, limite: int) -> list[Linha]:
        """As premiações mais recentes da escola (ano, competicao, premio, medalha, nivel, nome do aluno)."""

    def perfil_cidade(self, cidade_id: str, params: dict) -> dict:
        """Resumo da cidade (id MUNICIPIO|UF), ou {"erro": ...} se ela não tem premiações."""

    def visao_geral(self, params: dict) -> dict:
        """Tudo o que a página inicial mostra: totais, séries, destaques, catálogo e métodos."""

    def enderecos(self) -> Enderecos:
        """Endereços legíveis de todas as páginas de aluno, escola e cidade (/aluno/maria-souza-lima-al)."""

    # ------------------------------------------------ API pública
    # Recebem critérios já validados pelo adaptador HTTP (api_v1.parametros).
    def resumo_base(self) -> dict:
        """Data da última geração e total de premiações."""

    def estatisticas_olimpiadas(self) -> dict:
        """Por olimpíada: total de premiações, primeiro e último ano, e premiações por nível."""

    def niveis(self) -> set[str]:
        """Todos os níveis que aparecem na base (para validar o filtro nivel)."""

    def ranking_pagina(self, params: dict, offset: int, limite: int) -> PaginaDoRanking:
        """Uma página do ranking do recorte com todos os campos públicos (posição, nome, lugar, medalhas, pontos
        nos três métodos, anos). Só as linhas da página saem da base."""

    def iterar_ranking(self, params: dict) -> tuple[PaginaDoRanking, Iterator[Linha]]:
        """O ranking inteiro do recorte em fluxo, com os mesmos campos (exportação): (informações, linhas)."""

    def buscar_alunos(self, criterios: Criterios, nome: str, coluna: str, offset: int,
                      limite: int) -> tuple[int, list[tuple[Linha, list[Linha]]]]:
        """(total, [(resumo do aluno, premiações no recorte)]) da página; nome exato primeiro."""

    def aluno(self, aluno_id: str, criterios: Criterios) -> tuple[Linha, list[Linha]] | None:
        """(resumo, premiações no recorte) do aluno, ou None se o id não existe."""

    def buscar_escolas(self, criterios: Criterios, coluna: str, offset: int,
                       limite: int) -> tuple[int, list[Linha]]:
        """(total, resumos) das escolas com premiações no recorte, das que mais pontuam para as que menos."""

    def escola(self, escola_id: str) -> tuple[Linha, list[str]] | None:
        """(resumo, grafias do nome nas listas oficiais) da escola, ou None se o id não existe."""

    def medalhistas(self, escola_id: str, criterios: Criterios, ordem: str, coluna: str, offset: int,
                    limite: int) -> tuple[Linha, int, list[tuple[str, Linha | None, list[Linha]]]] | None:
        """(resumo da escola, total, [(aluno_id, resumo do aluno, premiações pela escola)]), ou None."""

    def premiacoes(self, criterios: Criterios, offset: int, limite: int) -> tuple[int, list[Linha]]:
        """(total, uma página de premiações) do recorte, em ordem estável (id)."""

    def iterar_premiacoes(self, criterios: Criterios) -> Iterator[Linha]:
        """Todas as premiações do recorte, em fluxo (exportação sem carregar tudo na memória)."""


class FonteDeLeitura(Protocol):
    """A base de leitura: abre sessões e diz a versão atual."""

    def sessao(self) -> AbstractContextManager[SessaoDeLeitura]:
        """Uma sessão (conexão) para uma requisição; fechada ao sair do bloco with."""

    def versao(self) -> int:
        """Muda sempre que a base é regerada (serve para invalidar arquivos derivados)."""
