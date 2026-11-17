"""Conexão somente leitura com a base e cache em memória das consultas pesadas."""
import sqlite3
import threading
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")
_MAX_ITENS_CACHE = 200
# O que limita o cache é o tamanho, não a quantidade: um ranking de alunos filtrado tem ~80 mil linhas
# (~65 MB). Os rankings sem filtro, que todo mundo usa, ficam fora do limite (Cache.fixo; com eles o processo
# tem ~280 MB). O teto cobre os do método IMPA edital (~35 mil linhas) mais um recorte grande; com outro
# sendo calculado ao mesmo tempo, o processo fica perto de 420 MB.
_MAX_LINHAS_CACHE = 150_000
_FATOR_LEVE = 8   # uma lista que só reordena linhas já guardadas pesa 1/8 das linhas


def _linhas(valor: Any) -> int:
    """Tamanho de um valor do cache, em linhas (1 para o que não é coleção)."""
    return max(len(valor), 1) if isinstance(valor, (list, dict, set, frozenset, tuple)) else 1


class Cache:
    """Resultados de consultas, invalidados sozinhos quando a base é regerada (muda a data do arquivo).

    A versão de cada valor é a da base que a conexão abriu (Conexao.versao), não a do instante em que ele é
    guardado: uma requisição que atravessa a troca da base não grava dado antigo como se fosse novo."""

    def __init__(self, caminho: Path):
        self._caminho = caminho
        self._itens: OrderedDict[Any, tuple[float, Any, int]] = OrderedDict()   # do menos ao mais usado
        self._peso = 0
        self._fixos: dict[Any, tuple[float, Any]] = {}
        self._travas_dos_fixos: dict[Any, threading.Lock] = {}
        self._trava = threading.Lock()

    def versao(self) -> float:
        """Versão atual da base (data de modificação do arquivo)."""
        return self._caminho.stat().st_mtime

    def fixo(self, chave: Any, calcular: Callable[[], T], versao: float | None = None) -> T:
        """Como obter, mas fora dos limites: para tabelas usadas em toda requisição (endereços).

        As threads da primeira visita esperam um único cálculo, numa trava só daquela chave: o resto do cache
        continua respondendo enquanto isso."""
        versao = self.versao() if versao is None else versao
        with self._trava:
            achado = self._fixos.get(chave)
            if achado and achado[0] == versao:
                return achado[1]
            trava = self._travas_dos_fixos.setdefault(chave, threading.Lock())
        with trava:
            with self._trava:
                achado = self._fixos.get(chave)
                if achado and achado[0] == versao:
                    return achado[1]
            valor = calcular()
            with self._trava:
                self._fixos[chave] = (versao, valor)
            return valor

    def obter(self, chave: Any, calcular: Callable[[], T], versao: float | None = None, leve: bool = False) -> T:
        """Valor guardado para a chave nesta versão da base, ou calcular() guardado agora.

        Quando passa de _MAX_LINHAS_CACHE linhas (ou _MAX_ITENS_CACHE itens), sai primeiro o que está há mais
        tempo sem uso. leve=True: o valor só reordena linhas de outro item (pesa 1/_FATOR_LEVE). Duas
        requisições com a mesma chave ao mesmo tempo podem calcular as duas: é raro e só custa tempo."""
        versao = self.versao() if versao is None else versao
        with self._trava:
            achado = self._itens.get(chave)
            if achado and achado[0] == versao:
                self._itens.move_to_end(chave)
                return achado[1]
        valor = calcular()   # fora da trava: consultas diferentes calculam em paralelo
        peso = max(_linhas(valor) // _FATOR_LEVE, 1) if leve else _linhas(valor)
        with self._trava:
            antigo = self._itens.pop(chave, None)
            if antigo:
                self._peso -= antigo[2]
            self._itens[chave] = (versao, valor, peso)
            self._peso += peso
            while len(self._itens) > 1 and (len(self._itens) > _MAX_ITENS_CACHE or self._peso > _MAX_LINHAS_CACHE):
                _, (_, _, peso_do_antigo) = self._itens.popitem(last=False)
                self._peso -= peso_do_antigo
        return valor


class Conexao:
    """sqlite3.Connection somente leitura com acesso ao cache compartilhado.

    execute devolve as linhas como sqlite3.Row (acesso por nome de coluna); linhas já as converte em dict,
    para quem vai alterá-las ou serializá-las. em_cache e fixo repassam para Cache.obter e Cache.fixo, com a
    versão da base lida ao abrir a conexão."""

    def __init__(self, caminho: Path, cache: Cache):
        self.versao = cache.versao()   # antes de abrir: na dúvida, o valor é guardado como da versão antiga
        self._con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
        self._con.row_factory = sqlite3.Row
        self._cache = cache

    def execute(self, sql: str, args=()) -> sqlite3.Cursor:
        return self._con.execute(sql, args)

    def linhas(self, sql: str, args=()) -> list[dict]:
        return [dict(r) for r in self._con.execute(sql, args).fetchall()]

    def em_cache(self, chave: Any, calcular: Callable[[], T], leve: bool = False) -> T:
        return self._cache.obter(chave, calcular, self.versao, leve)

    def fixo(self, chave: Any, calcular: Callable[[], T]) -> T:
        return self._cache.fixo(chave, calcular, self.versao)

    def close(self) -> None:
        self._con.close()


def marcadores(n: int) -> str:
    """'?,?,?' para cláusulas IN com n valores."""
    return ",".join("?" * n)
