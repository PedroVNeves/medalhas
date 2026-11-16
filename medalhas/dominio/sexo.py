"""Sexo estimado de cada aluno, para o filtro "meninas" / "meninos".

As listas oficiais não informam sexo. A estimativa usa o primeiro nome e a proporção de mulheres com esse
nome no Censo 2010 do IBGE, de forma conservadora: só classifica nomes usados quase só por um sexo
(LIMITE). Nomes ambíguos (Ariel, Andrea, Darcy) ou desconhecidos ficam sem classificação e não entram em
nenhum dos dois filtros. Quem tem premiação em olimpíada só para meninas conta como menina.
"""
from .premiacao import Premiacao

FEMININO, MASCULINO = "F", "M"
SEXOS = (FEMININO, MASCULINO)
LIMITE = 0.9                                     # fração mínima de um sexo entre as pessoas com o nome
COMPETICOES_SO_MENINAS = frozenset({"EGMO", "PAGMO", "EGOI"})


def primeiro_nome(aluno_id: str) -> str:
    """'MARIA CLARA SOUZA|SP' -> 'MARIA'."""
    nome = aluno_id.split("|")[0].split()
    return nome[0] if nome else ""


def classificar(fracao_feminina: float | None) -> str | None:
    if fracao_feminina is None:
        return None
    if fracao_feminina >= LIMITE:
        return FEMININO
    if fracao_feminina <= 1 - LIMITE:
        return MASCULINO
    return None


def estimar(premiacoes: list[Premiacao], fracao_feminina: dict[str, float]) -> dict[str | None, int]:
    """Preenche `sexo` (F, M ou None) em cada premiação, igual para todas as de um mesmo aluno.

    fracao_feminina: primeiro nome (normalizado) -> fração de mulheres entre as pessoas com esse nome.
    Devolve quantos alunos ficaram em cada classe.
    """
    so_meninas = {p["aluno_id"] for p in premiacoes if p["competicao"] in COMPETICOES_SO_MENINAS}
    por_aluno: dict[str, str | None] = {}
    for p in premiacoes:
        ident = p["aluno_id"]
        if ident not in por_aluno:
            por_aluno[ident] = FEMININO if ident in so_meninas else \
                classificar(fracao_feminina.get(primeiro_nome(ident)))
        p["sexo"] = por_aluno[ident]
    contagem: dict[str | None, int] = {}
    for s in por_aluno.values():
        contagem[s] = contagem.get(s, 0) + 1
    return contagem
