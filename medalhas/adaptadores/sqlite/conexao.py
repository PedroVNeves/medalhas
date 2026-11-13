"""Conexão somente leitura com a base e cache em memória das consultas pesadas."""
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")
_MAX_ITENS_CACHE = 60   # cada agregado pode ter ~76 mil itens: guarda só os mais recentes


class Cache:
    """Resultados de consultas, invalidados sozinhos quando a base é regerada (muda a data do arquivo)."""

    def __init__(self, caminho: Path):
        self._caminho = caminho
        self._itens: dict[Any, tuple[float, Any]] = {}
        self._fixos: dict[Any, tuple[float, Any]] = {}
        self._trava = threading.Lock()

    def fixo(self, chave: Any, calcular: Callable[[], T]) -> T:
        """Como obter, mas fora do limite de itens: para tabelas usadas em toda requisição (endereços)."""
        versao = self._caminho.stat().st_mtime
        with self._trava:
            achado = self._fixos.get(chave)
            if achado and achado[0] == versao:
                return achado[1]
            valor = calcular()   # dentro da trava: as threads da primeira visita esperam um único cálculo
            self._fixos[chave] = (versao, valor)
            return valor

    def obter(self, chave: Any, calcular: Callable[[], T]) -> T:
        versao = self._caminho.stat().st_mtime
        with self._trava:
            achado = self._itens.get(chave)
            if achado and achado[0] == versao:
                return achado[1]
        valor = calcular()   # fora da trava: consultas diferentes calculam em paralelo
        with self._trava:
            self._itens.pop(chave, None)
            self._itens[chave] = (versao, valor)
            while len(self._itens) > _MAX_ITENS_CACHE:
                self._itens.pop(next(iter(self._itens)))
        return valor


class Conexao:
    """sqlite3.Connection somente leitura com acesso ao cache compartilhado."""

    def __init__(self, caminho: Path, cache: Cache):
        self._con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
        self._con.row_factory = sqlite3.Row
        self._cache = cache

    def execute(self, sql: str, args=()) -> sqlite3.Cursor:
        return self._con.execute(sql, args)

    def linhas(self, sql: str, args=()) -> list[dict]:
        return [dict(r) for r in self._con.execute(sql, args).fetchall()]

    def em_cache(self, chave: Any, calcular: Callable[[], T]) -> T:
        return self._cache.obter(chave, calcular)

    def fixo(self, chave: Any, calcular: Callable[[], T]) -> T:
        return self._cache.fixo(chave, calcular)

    def close(self) -> None:
        self._con.close()


def marcadores(n: int) -> str:
    """'?,?,?' para cláusulas IN com n valores."""
    return ",".join("?" * n)
