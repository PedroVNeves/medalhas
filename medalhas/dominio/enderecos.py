"""Endereços legíveis das páginas de aluno, escola e cidade, como /aluno/maria-souza-lima-al.

Cada página tem um endereço oficial (o que vai para o Google e para o sitemap):
- aluno: o próprio id (NOME|UF) em forma de slug, então o site monta o link sozinho a partir do id;
- escola: nome de exibição + município + UF. O id da escola tem as palavras em ordem alfabética
  ("BENEDITA BRAGA COBRA ESCOLA MUNICIPAL|...") e daria endereços embaralhados;
- cidade: o id (MUNICIPIO|UF, sem acento) em forma de slug, como o aluno: /cidade/sao-paulo-sp.

O slug do id (slug(id)) também é aceito para escolas: é o que o site usa nos links, porque nem toda tela
tem o nome de exibição. O servidor redireciona esse endereço para o oficial.
"""
import re
import unicodedata
from collections.abc import Iterable

ALUNO, ESCOLA, CIDADE = "aluno", "escola", "cidade"
TIPOS = (ALUNO, ESCOLA, CIDADE)


def slug(texto: str | None) -> str:
    """Letras minúsculas sem acento, números e hífens. Tem uma cópia em web/js/util.js (slug): as duas
    precisam dar o mesmo resultado.

    >>> slug("MARIA SOUZA LIMA|AL")
    'maria-souza-lima-al'
    >>> slug("Colégio  São Luís (SP)")
    'colegio-sao-luis-sp'
    """
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "-", texto).strip("-")


def texto_escola(nome: str | None, municipio: str | None, uf: str | None) -> str:
    """Texto de onde sai o endereço da escola: nome + município + UF (o mesmo nome em outra cidade é outra
    página)."""
    return " ".join(p for p in (nome, municipio, uf) if p)


class Enderecos:
    """Endereços oficiais de todas as páginas, nos dois sentidos (id -> endereço e endereço -> id)."""

    def __init__(self, alunos: Iterable[tuple[str, str]], escolas: Iterable[tuple[str, str]],
                 cidades: Iterable[tuple[str, str]] = ()):
        """alunos, escolas e cidades: pares (id, texto de onde sai o endereço)."""
        self._oficial: dict[str, dict[str, str]] = {}
        self._ids: dict[str, dict[str, str]] = {}
        for tipo, pares in ((ALUNO, alunos), (ESCOLA, escolas), (CIDADE, cidades)):
            oficial, ids = self._oficial.setdefault(tipo, {}), self._ids.setdefault(tipo, {})
            # ordem fixa: quando dois textos dão o mesmo slug, o id menor fica com ele e o outro ganha -2
            for ident, texto in sorted(pares):
                base = slug(texto) or slug(ident) or "sem-nome"
                endereco, n = base, 1
                while endereco in ids:
                    n += 1
                    endereco = f"{base}-{n}"
                oficial[ident] = endereco
                ids[endereco] = ident
            # endereço montado pelo site a partir do id, quando não coincide com o oficial
            for ident in oficial:
                ids.setdefault(slug(ident), ident)

    def de(self, tipo: str, ident: str) -> str | None:
        """Endereço oficial do aluno/escola, ou None se o id não existe."""
        return self._oficial[tipo].get(ident)

    def resolver(self, tipo: str, endereco: str) -> tuple[str, str] | None:
        """(id, endereço oficial) para um endereço aceito, ou None."""
        ident = self._ids[tipo].get(endereco)
        return (ident, self._oficial[tipo][ident]) if ident else None

    def todos(self, tipo: str) -> list[str]:
        """Endereços oficiais, em ordem alfabética (para o sitemap)."""
        return sorted(self._oficial[tipo].values())
