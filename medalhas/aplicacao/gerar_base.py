"""Caso de uso: coletar as listas oficiais, reconhecer as pessoas e gravar a base pesquisável."""
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from ..dominio import escolas, identidade, olimpiadas, pontuacao
from ..dominio.premiacao import Premiacao
from ..dominio.texto import capitalizar_nome, normalizar
from .portas import Coletor, RepositorioPremiacoes

Log = Callable[[str], None]


@dataclass
class Relatorio:
    premiacoes: int = 0
    falhas: list[str] = field(default_factory=list)   # "SIGLA: erro" das fontes que não responderam


def indexar(p: Premiacao) -> dict:
    """Premiação pronta para gravar: nome de exibição, campos de busca, chave da escola e pontos."""
    nome = capitalizar_nome(p["nome"]) if p["nome"].isupper() else p["nome"]
    termos, chave = escolas.indexar_escola(p.get("escola"), p.get("municipio"), p.get("uf"))
    return {
        **p, "nome": nome,
        "nome_busca": normalizar(nome), "escola_busca": normalizar(p.get("escola")),
        "escola_termos": termos, "escola_chave": chave, "municipio_busca": normalizar(p.get("municipio")),
        **pontuacao.pontuar(p["competicao"], p["medalha"], p.get("nivel")),
        "area": olimpiadas.area(p["competicao"]),
    }


def gerar_base(coletores: Iterable[Coletor], repositorio: RepositorioPremiacoes, log: Log = print) -> Relatorio:
    relatorio = Relatorio()
    premiacoes: list[Premiacao] = []
    for coletor in coletores:
        try:
            premiacoes += coletor.coletar(log)
        except Exception as e:  # noqa: BLE001 — uma fonte fora do ar não pode derrubar as outras
            relatorio.falhas.append(f"{coletor.sigla}: {type(e).__name__}: {e}")

    corrigidas = identidade.corrigir_grafias(premiacoes)
    log(f"Identidades: {corrigidas} premiações com a grafia do nome corrigida à mão")
    exatos, abreviados = identidade.completar_identidades(premiacoes)
    log(f"Identidades: UF inferida pelo nome em {exatos} registros; {abreviados} nomes abreviados completados")
    unidos = identidade.atribuir_alunos(premiacoes)
    log(f"Identidades: {unidos} pessoas reunidas entre estados diferentes")

    registros = [indexar(p) for p in premiacoes]
    repositorio.substituir(registros, atualizado_em=time.strftime("%Y-%m-%d %H:%M"))
    relatorio.premiacoes = len(registros)
    return relatorio
