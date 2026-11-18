"""Coletores: leem as listas oficiais de premiados e devolvem premiações no formato do domínio.

Cada olimpíada do catálogo (dominio.olimpiadas.CATALOGO) precisa de um coletor registrado aqui.
"""
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from ...dominio.olimpiadas import CATALOGO
from ...dominio.premiacao import Premiacao
from . import egoi, imo, ioai, itabirana, obi, obm, obm_internacional, obmep, obq, omif

Log = Callable[[str], None]

_ESPECIFICOS: dict[str, Callable[[Log], list[Premiacao]]] = {
    "OBMEP": obmep.coletar, "OBM": obm.coletar, "OBI": obi.coletar, "IMO": imo.coletar,
    "EGOI": egoi.coletar, "IOAI": ioai.coletar, "OBQ": obq.coletar, "OMIF": omif.coletar,
    "OITM": itabirana.coletar,
}


@dataclass(frozen=True)
class ColetorDeFuncao:
    """Implementa aplicacao.portas.Coletor a partir de uma função coletar(log)."""
    sigla: str
    funcao: Callable[[Log], list[Premiacao]]

    def coletar(self, log: Log) -> list[Premiacao]:
        return self.funcao(log)


def todos(mencoes_obmep: bool = False) -> list[ColetorDeFuncao]:
    """Um coletor por olimpíada, na ordem do catálogo. mencoes_obmep: inclui as menções honrosas da OBMEP
    (cerca de 50 mil por edição)."""
    coletores = []
    for sigla in CATALOGO:
        if sigla == "OBMEP" and mencoes_obmep:
            funcao = partial(obmep.coletar, mencoes=True)
        elif sigla in _ESPECIFICOS:
            funcao = _ESPECIFICOS[sigla]
        elif sigla in obm_internacional.SIGLAS:
            funcao = partial(obm_internacional.coletar, sigla)
        else:
            raise LookupError(f"olimpíada {sigla} está no catálogo mas não tem coletor registrado")
        coletores.append(ColetorDeFuncao(sigla, funcao))
    return coletores
