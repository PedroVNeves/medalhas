"""A premiação: a unidade de dado do sistema (uma pessoa, uma olimpíada, um ano, um prêmio)."""
from typing import NotRequired, TypedDict

OURO, PRATA, BRONZE, MENCAO = "Ouro", "Prata", "Bronze", "Menção Honrosa"
MEDALHAS = (OURO, PRATA, BRONZE)             # medalhas propriamente ditas
PREMIOS = (OURO, PRATA, BRONZE, MENCAO)      # categorias aceitas nos filtros

UFS = ("AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI",
       "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO")


class Premiacao(TypedDict):
    """Registro como sai de um coletor, já no vocabulário do sistema.

    `medalha` é a categoria normalizada (Ouro, Prata, Bronze, Menção Honrosa ou outro prêmio);
    `premio` é o texto original publicado; `pontos` é a nota na prova, quando divulgada.
    """
    competicao: str
    ano: int | None
    nivel: str | None
    nome: str
    escola: str | None
    rede: str | None         # Pública / Privada (só a OBMEP publica)
    esfera: str | None       # Estadual, Municipal, Federal, Privada (só a OBMEP publica)
    municipio: str | None
    uf: str | None
    premio: str | None
    medalha: str
    pontos: str | None
    fonte: str               # página oficial onde o resultado foi publicado
    aluno_id: NotRequired[str]   # preenchido pela regra de identidade (dominio.identidade)
