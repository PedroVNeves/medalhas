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
                 cidades: Iterable[tuple[str, str]] = (), antigos_alunos: Iterable[tuple[str, str]] = ()):
        """alunos, escolas e cidades: pares (id, texto de onde sai o endereço). A ordem dos pares decide quem
        fica com o endereço montado a partir do id quando dois ids dão o mesmo (o primeiro): passe primeiro
        os mais procurados.

        antigos_alunos: pares (endereço antigo, id) de perfis que deixaram de existir porque a grafia errada
        do nome foi corrigida (identidade.GRAFIAS_CORRIGIDAS). Continuam aceitos e levam ao perfil certo, mas
        nunca tomam o endereço de outra pessoa.
        """
        self._oficial: dict[str, dict[str, str]] = {}
        self._ids: dict[str, dict[str, str]] = {}
        for tipo, pares in ((ALUNO, alunos), (ESCOLA, escolas), (CIDADE, cidades)):
            oficial, ids = self._oficial.setdefault(tipo, {}), self._ids.setdefault(tipo, {})
            pares = list(pares)
            # endereço montado a partir de cada id (é o que o site põe nos links): do primeiro que o tiver
            pelo_id: dict[str, str] = {}
            for ident, _ in pares:
                pelo_id.setdefault(slug(ident), ident)
            # ordem fixa: quando dois textos dão o mesmo slug, o id menor fica com ele e o outro ganha -2.
            # Um endereço que já é o do id de outro também está ocupado: senão o link desse outro cairia aqui
            for ident, texto in sorted(pares):
                base = slug(texto) or slug(ident) or "sem-nome"
                endereco, n = base, 1
                while endereco in ids or pelo_id.get(endereco, ident) != ident:
                    n += 1
                    endereco = f"{base}-{n}"
                oficial[ident] = endereco
                ids[endereco] = ident
            # endereço montado pelo site a partir do id, quando não coincide com o oficial
            for endereco, ident in pelo_id.items():
                ids.setdefault(endereco, ident)
        for endereco, ident in antigos_alunos:
            if ident in self._oficial[ALUNO]:
                self._ids[ALUNO].setdefault(endereco, ident)

    def de(self, tipo: str, ident: str) -> str | None:
        """Endereço oficial do aluno/escola, ou None se o id não existe."""
        return self._oficial[tipo].get(ident)

    def resolver(self, tipo: str, endereco: str) -> tuple[str, str] | None:
        """(id, endereço oficial) para um endereço aceito, ou None."""
        ident = self._ids[tipo].get(endereco)
        return (ident, self._oficial[tipo][ident]) if ident else None

    def contar(self, tipo: str) -> int:
        """Quantas páginas do tipo existem (uma por endereço oficial)."""
        return len(self._oficial[tipo])

    def fatia(self, tipo: str, offset: int, limite: int) -> list[str]:
        """Endereços oficiais em ordem alfabética, de offset em diante (os sitemaps saem um arquivo por vez)."""
        return sorted(self._oficial[tipo].values())[offset:offset + limite]

    def aceitos(self, tipo: str) -> Iterable[tuple[str, str]]:
        """(endereço, id) de todo endereço aceito: o oficial, o montado pelo id e os antigos (para gravar)."""
        return self._ids[tipo].items()
