"""Endereços das páginas (/aluno/…, /escola/…, /cidade/…), lidos da base um por vez.

Calculados na geração (gravacao.gravar_enderecos, com as regras de dominio.enderecos): o oficial fica no campo
endereco de cada tabela-resumo, e a tabela enderecos guarda os outros endereços aceitos. Nada fica na memória.
"""
from ...dominio.enderecos import ALUNO, CIDADE, ESCOLA
from .conexao import Conexao

_TABELA = {ALUNO: "alunos", ESCOLA: "escolas", CIDADE: "cidades"}
# o sitemap lista só o que vale indexar: perfis só com menções da OBMEP ficam de fora (e saem com noindex)
_NO_SITEMAP = {ALUNO: "WHERE indexar", ESCOLA: "WHERE indexar", CIDADE: ""}


class EnderecosDaBase:
    """Implementa a interface de dominio.enderecos.Enderecos com uma consulta indexada por chamada."""

    def __init__(self, con: Conexao):
        self._con = con

    def de(self, tipo: str, ident: str) -> str | None:
        """Endereço oficial do aluno, escola ou cidade, ou None se o id não existe."""
        achado = self._con.execute(f"SELECT endereco FROM {_TABELA[tipo]} WHERE id = ?", (ident,)).fetchone()
        return achado[0] if achado else None

    def resolver(self, tipo: str, endereco: str) -> tuple[str, str] | None:
        """(id, endereço oficial) para um endereço aceito, ou None."""
        tabela = _TABELA[tipo]
        achado = (self._con.execute(f"SELECT id, endereco FROM {tabela} WHERE endereco = ?", (endereco,)).fetchone()
                  or self._con.execute(f"""SELECT e.id, t.endereco FROM enderecos e JOIN {tabela} t ON t.id = e.id
                                           WHERE e.tipo = ? AND e.endereco = ?""", (tipo, endereco)).fetchone())
        return (achado[0], achado[1]) if achado else None

    def contar(self, tipo: str) -> int:
        """Quantas páginas do tipo vão para o sitemap."""
        return self._con.execute(f"SELECT COUNT(*) FROM {_TABELA[tipo]} {_NO_SITEMAP[tipo]}").fetchone()[0]

    def fatia(self, tipo: str, offset: int, limite: int) -> list[str]:
        """Endereços do sitemap em ordem alfabética, de offset em diante (um arquivo de sitemap por vez)."""
        return [r[0] for r in self._con.execute(
            f"SELECT endereco FROM {_TABELA[tipo]} {_NO_SITEMAP[tipo]} ORDER BY endereco LIMIT ? OFFSET ?",
            (limite, offset))]
