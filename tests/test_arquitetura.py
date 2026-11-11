"""Garante a direção das dependências da arquitetura hexagonal: adaptadores -> aplicacao -> dominio."""
import ast
import unittest
from pathlib import Path

PACOTE = Path(__file__).resolve().parent.parent / "medalhas"
# Módulos da biblioteca padrão que fazem I/O: o domínio não pode usá-los
IO = {"sqlite3", "urllib", "http", "socket", "os", "shutil", "tempfile", "pathlib", "subprocess", "threading"}


def importacoes(arquivo: Path) -> set[str]:
    """Módulos importados, com imports relativos resolvidos para o nome absoluto (medalhas.x.y)."""
    pacote = ".".join(arquivo.relative_to(PACOTE.parent).with_suffix("").parts[:-1])
    nomes = set()
    for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
        if isinstance(no, ast.Import):
            nomes |= {a.name for a in no.names}
        elif isinstance(no, ast.ImportFrom):
            base = pacote.split(".")[: len(pacote.split(".")) - no.level + 1] if no.level else []
            modulo = ".".join([*base, no.module] if no.module else base)
            nomes.add(modulo)
            nomes |= {f"{modulo}.{a.name}" for a in no.names}
    return nomes


def modulos(camada: str) -> list[Path]:
    return sorted((PACOTE / camada).rglob("*.py"))


class TestDependencias(unittest.TestCase):
    def assert_nao_importa(self, camada: str, proibidos: tuple[str, ...]) -> None:
        for arquivo in modulos(camada):
            for nome in importacoes(arquivo):
                with self.subTest(arquivo=arquivo.name, importa=nome):
                    self.assertFalse(nome.startswith(proibidos), f"{arquivo} não pode importar {nome}")

    def test_dominio_e_puro(self):
        self.assert_nao_importa("dominio", ("medalhas.aplicacao", "medalhas.adaptadores", "medalhas.config"))
        for arquivo in modulos("dominio"):
            for nome in importacoes(arquivo):
                with self.subTest(arquivo=arquivo.name, importa=nome):
                    self.assertNotIn(nome.split(".")[0], IO, f"{arquivo.name} faz I/O via {nome}")

    def test_aplicacao_nao_conhece_adaptadores(self):
        self.assert_nao_importa("aplicacao", ("medalhas.adaptadores", "medalhas.config", "sqlite3", "urllib", "http"))

    def test_adaptadores_nao_se_conhecem(self):
        """HTTP não fala com o SQLite direto (usa a porta de leitura) e vice-versa."""
        self.assert_nao_importa("adaptadores/http", ("medalhas.adaptadores.sqlite", "medalhas.adaptadores.coletores",
                                                     "sqlite3"))
        self.assert_nao_importa("adaptadores/sqlite", ("medalhas.adaptadores.http", "medalhas.adaptadores.coletores"))
        self.assert_nao_importa("adaptadores/coletores", ("medalhas.adaptadores.http", "medalhas.adaptadores.sqlite"))


if __name__ == "__main__":
    unittest.main()
