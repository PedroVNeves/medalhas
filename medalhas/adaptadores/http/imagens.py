"""Imagens de compartilhamento (og:image, 1200×630): o cartão que aparece ao mandar um link no WhatsApp,
Telegram, X, LinkedIn ou Discord.

Cada aluno e cada escola tem a sua, desenhada na hora com o nome e as medalhas; as demais páginas usam
a do site. O CDN do Firebase Hosting guarda cada imagem (como as páginas), então cada uma é desenhada
poucas vezes. Precisa do Pillow (requirements.txt); sem ele o servidor responde 404 e os cartões ficam
sem imagem, mas o resto do site funciona.
"""
import io
import threading
from functools import lru_cache
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:   # pragma: no cover - o site roda sem Pillow, só sem as imagens
    Image = None

from ...dominio.escolas import nome_de_exibicao
from ...dominio.texto import capitalizar_nome

DISPONIVEL = Image is not None
LARGURA, ALTURA = 1200, 630
MARGEM = 72
FONTES = Path(__file__).parent / "fontes"

FUNDO = (7, 10, 20)
OURO, PRATA, BRONZE = (245, 197, 66), (203, 213, 225), (205, 127, 50)
OURO_CLARO = (255, 224, 138)
TEXTO, TEXTO_2, TEXTO_3 = (241, 245, 249), (203, 213, 225), (148, 163, 184)
MENCAO = (129, 140, 248)
# a posição no ranking só entra no cartão entre os primeiros: "76.152º" não é algo que se queira mostrar
MAX_POSICAO_NO_CARTAO = 1000

_trava = threading.Lock()   # as fontes do Pillow não são seguras entre threads


# ---------------------------------------------------------------- fontes e texto

@lru_cache(maxsize=64)
def _fonte(familia: str, peso: int, tamanho: int):
    """familia: 'inter' (texto) ou 'display' (Space Grotesk, títulos e números). Fontes variáveis: o peso
    (e, na Inter, o tamanho óptico) é escolhido nos eixos da fonte."""
    arquivo = "Inter.ttf" if familia == "inter" else "SpaceGrotesk.ttf"
    fonte = ImageFont.truetype(str(FONTES / arquivo), tamanho)
    eixos = []
    for eixo in fonte.get_variation_axes():
        nome = eixo["name"].decode() if isinstance(eixo["name"], bytes) else eixo["name"]
        valor = peso if nome == "Weight" else tamanho if nome == "Optical size" else eixo["default"]
        eixos.append(max(eixo["minimum"], min(eixo["maximum"], valor)))
    fonte.set_variation_by_axes(eixos)
    return fonte


def _largura(texto: str, fonte) -> float:
    return fonte.getlength(texto)


def _cortar(texto: str, fonte, largura: float) -> str:
    """Corta com reticências para caber na largura."""
    if _largura(texto, fonte) <= largura:
        return texto
    while texto and _largura(texto + "…", fonte) > largura:
        texto = texto[:-1]
    return texto.rstrip(" ,·-") + "…"


def _quebrar(texto: str, fonte, largura: float, linhas: int) -> list[str] | None:
    """Quebra em até `linhas` linhas sem cortar palavras. None se não couber."""
    resultado, atual = [], ""
    for palavra in texto.split():
        tentativa = f"{atual} {palavra}".strip()
        if _largura(tentativa, fonte) <= largura:
            atual = tentativa
            continue
        if not atual:   # uma palavra sozinha maior que a linha
            return None
        resultado.append(atual)
        atual = palavra
    resultado.append(atual)
    return resultado if len(resultado) <= linhas else None


def _titulo(texto: str, largura: float) -> tuple[list[str], object]:
    """O maior tamanho (de 80 a 46) em que o título cabe em duas linhas; no menor, corta a segunda."""
    for tamanho in range(80, 45, -4):
        fonte = _fonte("display", 700, tamanho)
        linhas = _quebrar(texto, fonte, largura, 2)
        if linhas:
            return linhas, fonte
    fonte = _fonte("display", 700, 46)
    linhas = _quebrar(texto, fonte, largura, 99) or [texto]
    return [linhas[0], _cortar(" ".join(linhas[1:]), fonte, largura)][: len(linhas)], fonte


def numero(n: int) -> str:
    """12167 -> '12.167'"""
    return f"{n:,}".replace(",", ".")


# ---------------------------------------------------------------- desenho

def _fundo() -> "Image.Image":
    img = Image.new("RGB", (LARGURA, ALTURA), FUNDO)
    brilho = Image.new("RGBA", (LARGURA, ALTURA), (0, 0, 0, 0))
    d = ImageDraw.Draw(brilho)
    d.ellipse((760, -260, 1460, 360), fill=(*OURO, 70))          # dourado no canto de cima
    d.ellipse((-300, 330, 420, 900), fill=(99, 102, 241, 60))    # índigo no canto de baixo
    brilho = brilho.filter(ImageFilter.GaussianBlur(130))
    img.paste(brilho, (0, 0), brilho)
    grade = ImageDraw.Draw(img, "RGBA")   # a grade discreta do fundo do site
    for x in range(0, LARGURA, 60):
        grade.line((x, 0, x, ALTURA), fill=(255, 255, 255, 7))
    for y in range(0, ALTURA, 60):
        grade.line((0, y, LARGURA, y), fill=(255, 255, 255, 7))
    return img


def _estrela(d: "ImageDraw.ImageDraw", cx: float, cy: float, raio: float, cor) -> None:
    import math
    pontos = []
    for i in range(10):
        r = raio if i % 2 == 0 else raio * 0.45
        a = -math.pi / 2 + i * math.pi / 5
        pontos.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pontos, fill=cor)


def _medalha(d: "ImageDraw.ImageDraw", x: int, y: int, tamanho: int) -> None:
    """O ícone do site (web/favicon.svg) em tamanho × tamanho."""
    k = tamanho / 64
    d.polygon([(x + 18 * k, y + 2 * k), (x + 30 * k, y + 2 * k), (x + 36 * k, y + 24 * k), (x + 24 * k, y + 24 * k)],
              fill=(79, 107, 216))
    d.polygon([(x + 46 * k, y + 2 * k), (x + 34 * k, y + 2 * k), (x + 28 * k, y + 24 * k), (x + 40 * k, y + 24 * k)],
              fill=(224, 71, 91))
    d.ellipse((x + 11 * k, y + 19 * k, x + 53 * k, y + 61 * k), fill=(184, 134, 11))
    d.ellipse((x + 15 * k, y + 23 * k, x + 49 * k, y + 57 * k), fill=OURO)
    _estrela(d, x + 32 * k, y + 40 * k, 11 * k, (255, 243, 196))


def _cabecalho(d: "ImageDraw.ImageDraw") -> None:
    _medalha(d, MARGEM - 6, 50, 64)
    d.text((MARGEM + 70, 82), "Medalhas", font=_fonte("display", 700, 36), fill=OURO_CLARO, anchor="lm")
    site = _fonte("inter", 500, 24)
    d.text((LARGURA - MARGEM, 82), "medalhas.online", font=site, fill=TEXTO_3, anchor="rm")


def _tipos(m: dict) -> list[tuple]:
    """As medalhas que existem (sem "0 ouros"); só menções honrosas quando não há medalha."""
    tipos = [(m.get("ouro") or 0, OURO, "ouro", "ouros"), (m.get("prata") or 0, PRATA, "prata", "pratas"),
             (m.get("bronze") or 0, BRONZE, "bronze", "bronzes")]
    tipos = [t for t in tipos if t[0]]
    if not tipos and m.get("mencao"):
        tipos = [(m["mencao"], MENCAO, "menção honrosa", "menções honrosas")]
    return tipos


def _moedas(d: "ImageDraw.ImageDraw", y: int, tipos: list[tuple]) -> None:
    """Medalhas lado a lado: moeda, número e nome."""
    x = MARGEM
    num, rotulo = _fonte("display", 700, 52), _fonte("inter", 500, 26)
    for qtd, cor, um, varios in tipos:
        escura = tuple(int(c * 0.7) for c in cor)
        d.ellipse((x, y - 26, x + 52, y + 26), fill=escura)
        d.ellipse((x + 5, y - 21, x + 47, y + 21), fill=cor)
        _estrela(d, x + 26, y, 11, tuple(min(255, int(c * 1.15) + 25) for c in cor))
        x += 68
        texto = numero(qtd)
        d.text((x, y + 2), texto, font=num, fill=TEXTO, anchor="lm")
        x += _largura(texto, num) + 12
        palavra = um if qtd == 1 else varios
        d.text((x, y + 8), palavra, font=rotulo, fill=TEXTO_3, anchor="lm")
        x += _largura(palavra, rotulo) + 48


def _cartao(rotulo: str, titulo: str, subtitulo: str | None, medalhas: dict, rodape: list[str],
            destaque: str | None) -> bytes:
    """rodape: partes separadas por " · "; as do fim saem inteiras quando não cabem."""
    img = _fundo()
    d = ImageDraw.Draw(img)
    _cabecalho(d)
    largura = LARGURA - 2 * MARGEM

    d.text((MARGEM, 178), rotulo.upper(), font=_fonte("inter", 700, 22), fill=OURO, anchor="ls")
    linhas, fonte = _titulo(titulo, largura)
    y = 196
    altura_linha = int(fonte.size * 1.08)
    for linha in linhas:
        d.text((MARGEM, y), linha, font=fonte, fill=TEXTO, anchor="la")
        y += altura_linha
    if subtitulo:
        sub = _fonte("inter", 500, 30)
        d.text((MARGEM, y + 14), _cortar(subtitulo, sub, largura), font=sub, fill=TEXTO_2, anchor="la")

    _moedas(d, 486, _tipos(medalhas))

    d.line((MARGEM, 540, LARGURA - MARGEM, 540), fill=(34, 39, 54), width=2)
    base = _fonte("inter", 500, 24)
    x_fim = LARGURA - MARGEM
    if destaque:   # posição no ranking, à direita, em dourado
        forte = _fonte("inter", 700, 24)
        d.text((x_fim, 578), destaque, font=forte, fill=OURO_CLARO, anchor="rm")
        x_fim -= _largura(destaque, forte) + 32
    partes = [p for p in rodape if p]
    while len(partes) > 1 and _largura(" · ".join(partes), base) > x_fim - MARGEM:
        partes.pop()
    d.text((MARGEM, 578), _cortar(" · ".join(partes), base, x_fim - MARGEM), font=base, fill=TEXTO_3, anchor="lm")

    saida = io.BytesIO()
    img.save(saida, "PNG", optimize=True)
    return saida.getvalue()


# ---------------------------------------------------------------- cartões

def _siglas(premiacoes: list[dict]) -> list[str]:
    contagem: dict[str, int] = {}
    for r in premiacoes:
        contagem[r["competicao"]] = contagem.get(r["competicao"], 0) + 1
    return sorted(contagem, key=lambda s: (-contagem[s], s))


def _posicao(rank: int | None, sufixo: str) -> str | None:
    return f"{numero(rank)}{sufixo}" if rank and rank <= MAX_POSICAO_NO_CARTAO else None


def aluno(d: dict) -> bytes:
    m = d["medalhas"]
    anos = d.get("anos") or []
    periodo = (str(anos[0]) if len(anos) == 1 else f"{anos[0]}–{anos[-1]}") if anos else ""
    escola = d["escolas"][0] if d.get("escolas") else None
    subtitulo = None
    if escola:
        lugar = capitalizar_nome(escola["municipio"]) if escola.get("municipio") else None
        subtitulo = nome_de_exibicao(escola["escola"]) + (f" · {lugar}" if lugar else "")
    siglas = _siglas(d.get("premiacoes") or [])
    mencoes = (f"{m['mencao']} {'menção honrosa' if m['mencao'] == 1 else 'menções honrosas'}"
               if m.get("mencao") else None)
    if not (m.get("ouro") or m.get("prata") or m.get("bronze")):
        mencoes = None   # já estão nas moedas
    rodape = [periodo, *siglas[:5], mencoes]   # o período primeiro: é o que não pode faltar
    destaque = _posicao(d.get("rank"), "º no ranking nacional")
    rotulo = "Medalhista" + (f" · {d['uf']}" if d.get("uf") else "")
    with _trava:
        return _cartao(rotulo, d["nome"], subtitulo, m, rodape, destaque)


def escola(d: dict) -> bytes:
    m = d["medalhas"]
    lugar = ", ".join(p for p in (capitalizar_nome(d["municipio"]) if d.get("municipio") else None, d.get("uf")) if p)
    plural = "aluno premiado" if d["alunos"] == 1 else "alunos premiados"
    siglas = _siglas(d.get("recentes") or [])
    rodape = [f"{numero(d['alunos'])} {plural}", *siglas[:4]]
    destaque = _posicao(d.get("rank"), "ª no ranking de escolas")
    rotulo = "Escola" + (f" · {lugar}" if lugar else "")
    with _trava:
        return _cartao(rotulo, nome_de_exibicao(d["nome"]), None, m, rodape, destaque)


def site(visao: dict) -> bytes:
    t = visao["totais"]
    rodape = [f"{numero(t['total'])} premiações", f"{numero(t['alunos'])} alunos", f"{numero(t['escolas'])} escolas",
              f"{t['de']}–{t['ate']}"]
    outras = len(visao.get("olimpiadas") or []) - 4
    subtitulo = f"OBMEP, OBM, OBI, IMO e mais {outras} olimpíadas em um só lugar" if outras > 0 else None
    with _trava:
        return _cartao("Olimpíadas de conhecimento · Brasil", "Quem brilhou nas olimpíadas do Brasil", subtitulo,
                       t, rodape, None)
