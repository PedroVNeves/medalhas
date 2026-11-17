"""Critérios de ordenação e posição nos rankings (empates dividem a posição, como RANK() no SQL)."""
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

Chave = Callable[[dict], tuple]
TIPOS = ("alunos", "escolas", "estados", "cidades")

# Ordenações oferecidas. "coluna" é a coluna de pontos do método escolhido.
ORDENACOES: dict[str, Callable[[dict, str], tuple]] = {
    "xp": lambda r, coluna: (-(r[coluna] or 0), -r["ouro"], -r["prata"], -r["bronze"]),        # pontos
    "medalhas": lambda r, coluna: (-r["ouro"], -r["prata"], -r["bronze"], -(r[coluna] or 0)),  # quadro de medalhas
    "total": lambda r, coluna: (-(r["ouro"] + r["prata"] + r["bronze"]), -(r[coluna] or 0)),   # nº de medalhas
}
ORDEM_PADRAO = "xp"


def chave_de_ordenacao(ordem: str, coluna: str) -> Chave:
    """Função que ordena itens pelo critério (ORDENACOES) usando a coluna de pontos do método."""
    criterio = ORDENACOES[ordem]
    return lambda r: criterio(r, coluna)


def ordenar(itens: list[dict], ordem: str, coluna: str) -> list[dict]:
    """Ordena pelo critério; o nome desempata para a ordem ser estável entre execuções. É a definição de
    referência: os rankings do site são feitos pelo banco (adaptadores/sqlite/consultas_ranking.py), e um
    teste confere que dão o mesmo resultado.

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
class PaginaDoRanking:
    """Uma página de um ranking (ou o ranking inteiro, na exportação). Os itens são dicionários de aluno, escola,
    estado ou cidade com id, pos (posição; empates dividem), xp (pontos no método), ouro, prata, bronze, mencao e
    os campos que cada uso pediu."""
    tipo: str                    # alunos | escolas | estados | cidades
    ordem: str                   # chave de ORDENACOES
    metodo: str                  # método de pontuação
    coluna: str                  # coluna de pontos do método
    niveis: str | None           # níveis considerados (o método IMPA edital restringe)
    total: int | None            # quantos itens o ranking tem (None quando não foi contado)
    itens: Iterable[dict]


def com_pontos(item: dict, coluna: str) -> dict:
    """Acrescenta xp (pontos no método escolhido) e impa (pontuação oficial do IMPA Tech, sempre)."""
    item["xp"] = item.get(coluna) or 0
    item["impa"] = item.get("p_impa3") or 0
    return item


def preencher_posicoes(itens: list[dict], coluna: str, destino: str,
                       medalhas: tuple[str, str, str] = ("ouro", "prata", "bronze")) -> None:
    """Grava em item[destino] a posição no ranking por pontos da coluna. Usa o mesmo critério da lista do
    ranking (ORDENACOES["xp"]: pontos, depois ouros, pratas e bronzes; empate em tudo divide a posição), para
    a posição do perfil ser a mesma que a pessoa vê na lista.

    medalhas: campos com as contagens que desempatam. No método IMPA edital a lista só conta as medalhas que
    pontuam nele, então o desempate usa contagens próprias."""
    ouro, prata, bronze = medalhas

    def chave(r: dict) -> tuple:
        return -(r[coluna] or 0), -r[ouro], -r[prata], -r[bronze]
    itens.sort(key=chave)
    posicao, anterior = 0, None
    for i, item in enumerate(itens, 1):
        k = chave(item)
        if k != anterior:
            posicao, anterior = i, k
        item[destino] = posicao
