"""Leitura de tabelas em PDF pela posição de cada trecho de texto na página (OBQ, OMIF).

O texto extraído de um PDF nem sempre sai na ordem visual: rótulos de faixa (OURO, PRATA…) e colunas podem
vir fora de lugar. Aqui cada trecho vem com a posição real, e as linhas são montadas pela altura.
"""
import io

_TOLERANCIA_Y = 2.0   # trechos da mesma linha podem variar alguns décimos na altura


def paginas(conteudo: bytes):
    """Páginas do PDF. pypdf é importado só aqui: só quem gera a base precisa dele (pip install pypdf)."""
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        raise RuntimeError("falta o pypdf para ler PDFs (pip install pypdf)") from None
    return PdfReader(io.BytesIO(conteudo)).pages


def trechos(pagina) -> list[tuple[float, float, str]]:
    """(y de cima para baixo, x, texto) de cada trecho da página, já na posição real (matriz de texto × CTM)."""
    altura = float(pagina.mediabox.height)
    achados = []

    def visitar(t, cm, tm, _fonte, _tamanho):
        t = t.replace("\x00", "ti").strip()   # alguns PDFs perdem a ligadura "ti" (Mar\x00nez = Martinez)
        if t:
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            achados.append((round(altura - y, 1), round(x, 1), t))
    pagina.extract_text(visitor_text=visitar)
    return sorted(achados)


def linhas(pagina) -> list[tuple[float, list[tuple[float, str]]]]:
    """(y, [(x, texto) da esquerda para a direita]) de cada linha da página, de cima para baixo."""
    resultado: list[tuple[float, list[tuple[float, str]]]] = []
    for y, x, t in trechos(pagina):
        if not resultado or y - resultado[-1][0] > _TOLERANCIA_Y:
            resultado.append((y, []))
        resultado[-1][1].append((x, t))
    return [(y, sorted(itens)) for y, itens in resultado]
