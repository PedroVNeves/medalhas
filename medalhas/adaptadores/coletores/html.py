"""Leitura simples de HTML: as páginas oficiais são tabelas sem estrutura semântica confiável,
então expressões regulares toleram melhor as variações de cada ano que um parser estrito."""
import html
import re
from collections.abc import Iterator


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


def registrar_periodo(log, sigla: str, premiacoes: list[dict]) -> None:
    """Linha de resumo de um coletor: "OBI: 4812 premiações, 1999–2025"."""
    anos = sorted({p["ano"] for p in premiacoes})
    log(f"{sigla}: {len(premiacoes)} premiações, {anos[0] if anos else '-'}–{anos[-1] if anos else '-'}")


def celulas_das_linhas(tabela: str) -> Iterator[list[str]]:
    """Texto das células (td ou th) de cada linha de uma <table>, pulando as linhas vazias."""
    for trecho in re.split(r"<tr\b", tabela, flags=re.I)[1:]:
        trecho = re.split(r"</tr>", trecho, flags=re.I)[0]
        celulas = [texto(c) for c in re.split(r"<t[dh]\b[^>]*>", trecho, flags=re.I)[1:]]
        if any(celulas):
            yield celulas
