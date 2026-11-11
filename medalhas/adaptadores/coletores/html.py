"""Leitura simples de HTML: as páginas oficiais são tabelas sem estrutura semântica confiável,
então expressões regulares toleram melhor as variações de cada ano que um parser estrito."""
import html
import re


def texto(fragmento: str) -> str:
    """Texto visível de um trecho de HTML: sem tags, com entidades decodificadas e espaços normalizados."""
    t = re.sub(r"<[^>]+>", " ", fragmento)
    t = html.unescape(t).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def corpo_do_artigo(pagina: str) -> str:
    """Conteúdo principal de uma página WordPress da OBM, sem comentários e scripts."""
    inicio = pagina.find("post-body")
    corpo = pagina[inicio:] if inicio >= 0 else pagina
    fim = corpo.find("</main>")
    corpo = corpo[:fim] if fim >= 0 else corpo
    return re.sub(r"<!--.*?-->|<script\b.*?</script>", " ", corpo, flags=re.S | re.I)


def nota(valor: str | None) -> str | None:
    """Nota da prova só quando for número ("32", "27,5"); qualquer outro texto vira None."""
    return valor if valor and re.fullmatch(r"[\d.,]+", valor) else None
