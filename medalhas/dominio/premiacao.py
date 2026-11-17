"""A premiação: a unidade de dado do sistema (uma pessoa, uma olimpíada, um ano, um prêmio)."""
from typing import NotRequired, TypedDict

OURO, PRATA, BRONZE, MENCAO = "Ouro", "Prata", "Bronze", "Menção Honrosa"
MEDALHAS = (OURO, PRATA, BRONZE)             # medalhas propriamente ditas
PREMIOS = (OURO, PRATA, BRONZE, MENCAO)      # categorias aceitas nos filtros

# Sigla -> nome do estado. A única tabela de estados do sistema: as outras (nomes sem acento para ler PDFs,
# expansão de siglas de escola) são derivadas dela.
NOMES_UF = {
    "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MG": "Minas Gerais",
    "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco",
    "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RO": "Rondônia",
    "RR": "Roraima", "RS": "Rio Grande do Sul", "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo",
    "TO": "Tocantins"}
UFS = tuple(NOMES_UF)


class Premiacao(TypedDict):
    """Registro como sai de um coletor, já no vocabulário do sistema.

    `medalha` é a categoria normalizada (Ouro, Prata, Bronze, Menção Honrosa ou outro prêmio);
    `premio` é o texto original publicado; `pontos` é a nota na prova, quando divulgada.
    """
    competicao: str
    ano: int                 # premiação sem ano é descartada ao gerar a base (aplicacao.gerar_base)
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
