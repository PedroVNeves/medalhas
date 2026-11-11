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


def capitalizar_nome(nome: str) -> str:
    """Nome em caixa alta para a forma de exibição.

    >>> capitalizar_nome("JOÃO DA SILVA")
    'João da Silva'
    """
    palavras = nome.lower().split()
    return " ".join(p if (i and p in _MINUSCULAS) else p[:1].upper() + p[1:] for i, p in enumerate(palavras))
