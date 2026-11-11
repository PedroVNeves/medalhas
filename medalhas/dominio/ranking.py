"""Critérios de ordenação e posição nos rankings (empates dividem a posição, como RANK() no SQL)."""
from collections.abc import Callable, Iterator
from dataclasses import dataclass

Chave = Callable[[dict], tuple]
TIPOS = ("alunos", "escolas", "estados")

# Ordenações oferecidas. "coluna" é a coluna de pontos do método escolhido.
ORDENACOES: dict[str, Callable[[dict, str], tuple]] = {
    "xp": lambda r, coluna: (-(r[coluna] or 0), -r["ouro"], -r["prata"], -r["bronze"]),        # pontos
    "medalhas": lambda r, coluna: (-r["ouro"], -r["prata"], -r["bronze"], -(r[coluna] or 0)),  # quadro de medalhas
    "total": lambda r, coluna: (-(r["ouro"] + r["prata"] + r["bronze"]), -(r[coluna] or 0)),   # nº de medalhas
}
ORDEM_PADRAO = "xp"


def chave_de_ordenacao(ordem: str, coluna: str) -> Chave:
    criterio = ORDENACOES[ordem]
    return lambda r: criterio(r, coluna)


def ordenar(itens: list[dict], ordem: str, coluna: str) -> list[dict]:
    """Ordena pelo critério; o nome desempata para a ordem ser estável entre execuções.

    No ranking por pontos, quem não pontua no método fica de fora.
    """
    chave = chave_de_ordenacao(ordem, coluna)
    if ordem == "xp":
        itens = [r for r in itens if r[coluna]]
    return sorted(itens, key=lambda r: (chave(r), r["nome"] or ""))


def posicionar(ordenados: list[dict], chave: Chave, offset: int = 0,
               limite: int | None = None) -> Iterator[tuple[int, dict]]:
    """(posição, item) de uma lista já ordenada, da posição offset+1 em diante."""
    fim = len(ordenados) if limite is None else offset + limite
    posicao, anterior = 0, None
    for i, item in enumerate(ordenados[:fim], 1):
        k = chave(item)
        if k != anterior:
            posicao, anterior = i, k
        if i > offset:
            yield posicao, item


@dataclass(frozen=True)
class RankingOrdenado:
    """Ranking completo de um recorte, já ordenado. Os itens são agregados de aluno, escola ou estado."""
    tipo: str               # alunos | escolas | estados
    ordem: str              # chave de ORDENACOES
    metodo: str             # método de pontuação
    coluna: str             # coluna de pontos do método
    niveis: str | None      # níveis considerados (o método IMPA N3 restringe)
    itens: list[dict]

    @property
    def chave(self) -> Chave:
        return chave_de_ordenacao(self.ordem, self.coluna)


def com_pontos(item: dict, coluna: str) -> dict:
    """Acrescenta xp (pontos no método escolhido) e impa (pontuação oficial do IMPA Tech, sempre)."""
    item["xp"] = item.get(coluna) or 0
    item["impa"] = item.get("p_impa3") or 0
    return item


def com_posicoes(ranking: RankingOrdenado, offset: int = 0, limite: int | None = None) -> Iterator[dict]:
    """Cópias dos itens com posição e pontos, prontas para exibir ou exportar."""
    for posicao, item in posicionar(ranking.itens, ranking.chave, offset, limite):
        yield com_pontos(dict(item, pos=posicao), ranking.coluna)


def preencher_posicoes(itens: list[dict], coluna: str, destino: str) -> None:
    """Grava em item[destino] a posição pela coluna de pontos (maior primeiro; empates dividem)."""
    itens.sort(key=lambda a: -a[coluna])
    posicao, anterior = 0, None
    for i, item in enumerate(itens, 1):
        if item[coluna] != anterior:
            posicao, anterior = i, item[coluna]
        item[destino] = posicao
