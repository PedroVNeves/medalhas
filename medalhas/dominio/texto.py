"""Normalização de texto usada para comparar nomes de pessoas, escolas e municípios."""
import re
import unicodedata

# Palavras que ficam minúsculas no meio de um nome próprio ("João da Silva")
_MINUSCULAS = {"da", "de", "do", "das", "dos", "e", "di", "du", "del", "van", "von"}


def normalizar(texto: str | None) -> str:
    """Forma canônica para busca e comparação: sem acentos, maiúscula, só letras, números e espaço.

    >>> normalizar("  São  Paulo-SP ")
    'SAO PAULO SP'
    """
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^A-Za-z0-9 ]+", " ", texto).upper()
    return re.sub(r"\s+", " ", texto).strip()


# Sujeira que as listas oficiais deixam no fim do nome e que faria da mesma pessoa dois perfis
_RESTO_DE_TAG = re.compile(r"\s*</?\s*\w*\s*/?>|\s*/\w+>")            # "Júnior/td>", "Junior</B>"
_EMAIL = re.compile(r"\s*\S+@\S+\.\S+")                               # e-mail colado ao nome
_TURMA = re.compile(r"\s+\d{1,2}\s?[ºª°]?\s?[A-Za-z]$")                # "7ºB", "8b", "9º D"
_DIGITOS_NO_FIM = re.compile(r"(?<=[^\W\d_])\d+$")                     # "Pereira3" (nota de rodapé)


def limpar_nome(nome: str) -> str:
    """Nome de pessoa sem restos de HTML, e-mail, turma, nota de rodapé e pontuação solta no fim.

    >>> limpar_nome("Adenilson Arcanjo de Moura Júnior/td>")
    'Adenilson Arcanjo de Moura Júnior'
    >>> limpar_nome("Sofia Nunes Pinto de Oliveira 7ºB")
    'Sofia Nunes Pinto de Oliveira'
    >>> limpar_nome("Marianny Rocha Marques ;")
    'Marianny Rocha Marques'
    """
    nome = _EMAIL.sub("", _RESTO_DE_TAG.sub("", nome or ""))
    nome = re.sub(r"\s+", " ", nome).strip(" ;,:-*")
    nome = _DIGITOS_NO_FIM.sub("", _TURMA.sub("", nome))
    return nome.strip(" ;,:-*")


def limpar_escola(escola: str | None) -> str | None:
    """Nome de escola sem restos de tag ("EMEF> JOAO JAIME GADELHA"); None se não sobra nada."""
    if not escola:
        return None
    return re.sub(r"\s+", " ", re.sub(r"[<>]+", " ", escola)).strip() or None


def capitalizar_nome(nome: str) -> str:
    """Nome em caixa alta para a forma de exibição.

    >>> capitalizar_nome("JOÃO DA SILVA")
    'João da Silva'
    """
    palavras = nome.lower().split()
    return " ".join(p if (i and p in _MINUSCULAS) else p[:1].upper() + p[1:] for i, p in enumerate(palavras))


def nome_da_cidade(grafias: dict[str, int]) -> str:
    """Nome de exibição a partir das grafias vistas nas listas e quantas vezes cada uma apareceu.

    Prefere a grafia com acento mais comum ("São Paulo", não "SAO PAULO"), tira pontuação solta ('São Paulo"')
    e padroniza as maiúsculas ("Rio de janeiro" -> "Rio de Janeiro").

    >>> nome_da_cidade({"SAO PAULO": 90, 'São Paulo"': 3, "São Paulo": 2})
    'São Paulo'
    >>> nome_da_cidade({'SANTA BÁRBARA D"OESTE': 4})
    "Santa Bárbara d'Oeste"
    """
    limpas: dict[str, int] = {}
    for g, n in grafias.items():
        g = re.sub(r"[\"´`’]", "'", g or "")   # aspas e acentos soltos no lugar do apóstrofo
        g = re.sub(r"\s+", " ", re.sub(r"^[^\w]+|[^\w]+$", "", g)).strip()
        if g:
            limpas[g.upper()] = limpas.get(g.upper(), 0) + n
    if not limpas:
        return ""
    com_acento = {g: n for g, n in limpas.items() if not g.isascii()} or limpas
    nome = capitalizar_nome(max(com_acento, key=lambda g: (com_acento[g], g)))
    return re.sub(r"\bD'(\w)", lambda m: "d'" + m.group(1).upper(), nome)   # Santa Bárbara d'Oeste
