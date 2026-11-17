"""Caso de uso: coletar as listas oficiais, reconhecer as pessoas e gravar a base pesquisável."""
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from ..dominio import escolas, identidade, olimpiadas, pontuacao, sexo
from ..dominio.premiacao import Premiacao
from ..dominio.texto import capitalizar_nome, limpar_escola, limpar_nome, normalizar
from .portas import Coletor, RepositorioPremiacoes

Log = Callable[[str], None]
# Uma olimpíada que volta com bem menos premiações que na base atual quase sempre é a página oficial que
# mudou ou saiu do ar pela metade; listas oficiais só crescem (ou perdem poucas linhas em correções)
QUEDA_MAXIMA = 0.10


@dataclass
class Relatorio:
    """Resultado da geração: quantas premiações foram gravadas e quais fontes falharam."""
    premiacoes: int = 0
    falhas: list[str] = field(default_factory=list)   # "SIGLA: erro" das fontes que não responderam
    gravada: bool = True                              # False: havia falhas e a base anterior foi mantida


def indexar(p: Premiacao) -> dict:
    """Premiação pronta para gravar: nome de exibição, campos de busca, chave da escola e pontos."""
    nome = capitalizar_nome(p["nome"]) if p["nome"].isupper() else p["nome"]
    termos, chave = escolas.indexar_escola(p.get("escola"), p.get("municipio"), p.get("uf"))
    return {
        **p, "nome": nome,
        "nome_busca": normalizar(nome),
        "escola_termos": termos, "escola_chave": chave, "municipio_busca": normalizar(p.get("municipio")),
        **pontuacao.pontuar(p["competicao"], p["medalha"], p.get("nivel")),
        "area": olimpiadas.area(p["competicao"]), "sexo": p.get("sexo"),
    }


def limpar(premiacoes: list[Premiacao]) -> list[Premiacao]:
    """Tira a sujeira das listas oficiais (restos de HTML, e-mail e turma no nome; ver texto.limpar_nome) e
    descarta o que não dá para atribuir a ninguém: premiação sem nome ou sem ano."""
    limpas = []
    for p in premiacoes:
        p["nome"], p["escola"] = limpar_nome(p["nome"]), limpar_escola(p.get("escola"))
        if p["nome"] and p.get("ano"):
            limpas.append(p)
    return limpas


def gerar_base(coletores: Iterable[Coletor], repositorio: RepositorioPremiacoes, log: Log = print,
               permitir_parcial: bool = False) -> Relatorio:
    """Coleta todas as fontes, aplica as regras do domínio e grava a base nova de uma vez.

    Ordem: limpeza -> correções à mão -> identidade dos alunos (UF dos que vieram sem, mesma pessoa entre
    estados) -> cidade das escolas -> filtro de meninas -> indexação (campos de busca, chave da escola, pontos).

    Uma fonte que falha (ou que não devolve nenhuma premiação, ou devolve bem menos que as da base atual: a
    página oficial mudou) entra no relatório e não
    impede a coleta das outras, mas a base só é gravada com todas as fontes, salvo permitir_parcial=True: uma
    base sem a OBMEP não pode substituir a completa por descuido.
    """
    relatorio = Relatorio()
    premiacoes: list[Premiacao] = []
    antes = repositorio.premiacoes_por_olimpiada()
    for coletor in coletores:
        try:
            coletadas = coletor.coletar(log)
            if not coletadas:
                raise LookupError("nenhuma premiação encontrada (a página oficial mudou ou está fora do ar?)")
            tinha = antes.get(coletor.sigla, 0)
            if len(coletadas) < tinha * (1 - QUEDA_MAXIMA):
                raise LookupError(f"só {len(coletadas)} premiações; a base atual tem {tinha} "
                                  f"(queda de mais de {QUEDA_MAXIMA:.0%}: a lista oficial mudou?)")
            premiacoes += coletadas
        except Exception as e:  # noqa: BLE001 — uma fonte fora do ar não pode derrubar as outras
            relatorio.falhas.append(f"{coletor.sigla}: {type(e).__name__}: {e}")
    if relatorio.falhas and not permitir_parcial:
        relatorio.gravada = False
        return relatorio

    coletadas = len(premiacoes)
    premiacoes = limpar(premiacoes)
    if coletadas != len(premiacoes):
        log(f"Limpeza: {coletadas - len(premiacoes)} premiações sem nome ou sem ano descartadas")

    corrigidas = identidade.corrigir_grafias(premiacoes)
    log(f"Identidades: {corrigidas} premiações com a grafia do nome corrigida à mão")
    exatos, abreviados = identidade.completar_identidades(premiacoes)
    log(f"Identidades: UF inferida pelo nome em {exatos} registros; {abreviados} nomes abreviados completados")
    unidos = identidade.atribuir_alunos(premiacoes)
    log(f"Identidades: {unidos} pessoas reunidas entre estados diferentes")
    # depois das identidades: quem ganhou o estado pela escola também pode ganhar a cidade
    provas = [p for p in premiacoes if not identidade.de_massa(p)]   # menções não mudam a escola de ninguém
    com_cidade = escolas.completar_municipios(premiacoes, provas)
    log(f"Escolas: {com_cidade} premiações sem cidade ganharam a da escola de mesmo nome no estado")
    meninas = sexo.marcar_meninas(premiacoes)
    log(f"Meninas: {meninas} alunas premiadas em olimpíadas ou etapas só para meninas")

    registros = [indexar(p) for p in premiacoes]
    repositorio.substituir(registros, atualizado_em=time.strftime("%Y-%m-%d %H:%M"))
    relatorio.premiacoes = len(registros)
    return relatorio
