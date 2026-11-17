"""Filtro "meninas": alunas reconhecidas por ter premiação em uma olimpíada (ou etapa) só para meninas.

As listas oficiais não informam o sexo, e estimá-lo pelo nome erra (nomes usados pelos dois sexos, grafias
raras). Por isso o filtro só inclui quem tem certeza de ser menina: quem foi premiada na EGMO, na PAGMO, na
EGOI ou na etapa "Elas em Destaque" da Olimpíada Itabirana (medalha ou menção honrosa da etapa). Para essas
alunas, todas as premiações contam (OBMEP, OBM, OBI…), não só as das olimpíadas femininas.
"""
from .premiacao import Premiacao

FEMININO = "F"
COMPETICOES_SO_MENINAS = frozenset({"EGMO", "PAGMO", "EGOI"})
# etapa feminina da Olimpíada Itabirana: a medalha e a menção honrosa dela
MENCAO_ELAS = "Menção Honrosa (Elas em Destaque)"
PREMIOS_SO_MENINAS = frozenset({"Elas em Destaque", MENCAO_ELAS})
# Alunas que pediram para entrar no filtro (pelo contato do site): ids "NOME|UF", como em dominio.identidade
MENINAS_CONFIRMADAS: frozenset[str] = frozenset()


def marcar_meninas(premiacoes: list[Premiacao]) -> int:
    """Preenche `sexo` ("F" ou None) em cada premiação, igual para todas as de um mesmo aluno.

    Devolve quantas alunas foram reconhecidas.
    """
    meninas = {p["aluno_id"] for p in premiacoes
               if p["competicao"] in COMPETICOES_SO_MENINAS or p.get("premio") in PREMIOS_SO_MENINAS
               or p["aluno_id"] in MENINAS_CONFIRMADAS}
    for p in premiacoes:
        p["sexo"] = FEMININO if p["aluno_id"] in meninas else None
    return len(meninas)
