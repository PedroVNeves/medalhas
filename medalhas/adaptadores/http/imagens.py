"""Imagens de compartilhamento:
- og:image (1200×630): o cartão que aparece ao mandar um link no WhatsApp, Telegram, X, LinkedIn ou Discord;
- story (1080×1920): imagem vertical para postar no story do Instagram (botão "Compartilhar no story" dos
  perfis), com espaço embaixo para o adesivo de link.

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
    """Largura do texto em pixels nesta fonte."""
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

def _fundo(largura: int = LARGURA, altura: int = ALTURA) -> "Image.Image":
    """Fundo escuro do site com um brilho dourado em cima, um índigo embaixo e a grade discreta."""
    img = Image.new("RGB", (largura, altura), FUNDO)
    brilho = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    d = ImageDraw.Draw(brilho)
    d.ellipse((largura - 440, -260, largura + 260, 360), fill=(*OURO, 70))     # dourado no canto de cima
    d.ellipse((-300, altura - 300, 420, altura + 270), fill=(99, 102, 241, 60))   # índigo no canto de baixo
    brilho = brilho.filter(ImageFilter.GaussianBlur(130))
    img.paste(brilho, (0, 0), brilho)
    grade = ImageDraw.Draw(img, "RGBA")   # a grade discreta do fundo do site
    for x in range(0, largura, 60):
        grade.line((x, 0, x, altura), fill=(255, 255, 255, 7))
    for y in range(0, altura, 60):
        grade.line((0, y, largura, y), fill=(255, 255, 255, 7))
    return img


def _estrela(d: "ImageDraw.ImageDraw", cx: float, cy: float, raio: float, cor) -> None:
    """Estrela de cinco pontas centrada em (cx, cy)."""
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
    def fita(x0, x1, x2, x3, cor):   # topo de x0 a x1, base de x2 a x3 (em 1/64 do tamanho)
        d.polygon([(x + x0 * k, y + 2 * k), (x + x1 * k, y + 2 * k), (x + x3 * k, y + 24 * k), (x + x2 * k, y + 24 * k)],
                  fill=cor)
    fita(18, 30, 24, 36, (79, 107, 216))
    fita(22.5, 25.5, 28.5, 31.5, (140, 160, 240))
    fita(34, 46, 28, 40, (224, 71, 91))
    fita(38.5, 41.5, 32.5, 35.5, (240, 140, 155))
    d.ellipse((x + 11 * k, y + 19 * k, x + 53 * k, y + 61 * k), fill=(154, 107, 5))
    d.ellipse((x + 14.5 * k, y + 22.5 * k, x + 49.5 * k, y + 57.5 * k), fill=OURO)
    _estrela(d, x + 32 * k, y + 40 * k, 11 * k, (255, 243, 196))


def _cabecalho(d: "ImageDraw.ImageDraw") -> None:
    """Faixa de cima do cartão: ícone e nome à esquerda, endereço do site à direita."""
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
    """Siglas das olimpíadas, da que mais premiou para a que menos."""
    contagem: dict[str, int] = {}
    for r in premiacoes:
        contagem[r["competicao"]] = contagem.get(r["competicao"], 0) + 1
    return sorted(contagem, key=lambda s: (-contagem[s], s))


def _posicao(rank: int | None, sufixo: str) -> str | None:
    """'12º no ranking nacional', ou None fora dos MAX_POSICAO_NO_CARTAO primeiros."""
    return f"{numero(rank)}{sufixo}" if rank and rank <= MAX_POSICAO_NO_CARTAO else None


def aluno(d: dict) -> bytes:
    """Cartão (PNG 1200×630) do aluno, a partir do perfil (SessaoDeLeitura.perfil_aluno): nome, escola mais
    recente, medalhas, período, olimpíadas e a posição nacional se estiver entre os primeiros."""
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
    """Cartão (PNG 1200×630) da escola, a partir do perfil (SessaoDeLeitura.perfil_escola)."""
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
    """Cartão (PNG 1200×630) do site, com os totais da visão geral; usado pelas páginas sem cartão próprio."""
    t = visao["totais"]
    rodape = [f"{numero(t['total'])} premiações", f"{numero(t['alunos'])} alunos", f"{numero(t['escolas'])} escolas",
              f"{t['de']}–{t['ate']}"]
    outras = len(visao.get("olimpiadas") or []) - 4
    subtitulo = f"OBMEP, OBM, OBI, IMO e mais {outras} olimpíadas em um só lugar" if outras > 0 else None
    with _trava:
        return _cartao("Olimpíadas de conhecimento · Brasil", "Quem brilhou nas olimpíadas do Brasil", subtitulo,
                       t, rodape, None)


# ---------------------------------------------------------------- story do Instagram (1080×1920)

STORY_L, STORY_A = 1080, 1920
# o Instagram cobre ~250 px no topo (barra de progresso, perfil) e ~300 px embaixo (resposta): o conteúdo
# fica no meio, e a faixa de baixo é o lugar do adesivo de link
_STORY_M = 96


def _etiquetas_numa_linha(etiquetas: list[str], fonte, largura: float) -> list[str]:
    """As etiquetas que cabem numa linha, na ordem (as do fim saem)."""
    fila: list[str] = []
    for et in etiquetas:
        if sum(_largura(e, fonte) + 56 for e in fila + [et]) - 16 > largura:
            break
        fila.append(et)
    return fila


def _story(rotulo: str, titulo: str, subtitulo: str | None, medalhas: dict, etiquetas: list[str],
           destaque: str | None) -> bytes:
    """Desenha um story (PNG 1080×1920): marca em cima, o bloco do meio centralizado na área que o Instagram
    não cobre e, embaixo, o endereço do site e o espaço para o adesivo de link.

    O título tenta do maior tamanho para o menor (até 3 linhas) e, se preciso, as moedas encolhem para 80%;
    um nome que não cabe nem assim sai no menor tamanho, cortado com reticências."""
    img = _fundo(STORY_L, STORY_A)
    d = ImageDraw.Draw(img)
    largura = STORY_L - 2 * _STORY_M
    centro = STORY_L // 2

    _medalha(d, centro - 56, 236, 112)
    d.text((centro, 400), "Medalhas", font=_fonte("display", 700, 50), fill=OURO_CLARO, anchor="mm")

    # o conteúdo do meio é medido antes de desenhar: o maior título (e as maiores moedas) que caibam na
    # área visível, e o bloco centralizado nela
    topo, base = 500, 1530
    tipos = _tipos(medalhas)
    sub = _fonte("inter", 500, 40)
    linhas_sub = (_quebrar(subtitulo, sub, largura, 2) or [_cortar(subtitulo, sub, largura)]) if subtitulo else []
    fonte_et = _fonte("inter", 600, 34)
    fila = _etiquetas_numa_linha(etiquetas, fonte_et, largura)

    def altura(linhas_titulo: int, tam_titulo: int, escala: float) -> float:
        return (50 + linhas_titulo * tam_titulo * 1.08 + (24 + 52 * len(linhas_sub) if linhas_sub else 0)
                + 80 + len(tipos) * 150 * escala + (40 + 60 if fila else 0) + (110 if destaque else 0))

    opcoes = [(tam, 1.0) for tam in range(112, 87, -6)] + [(tam, 0.8) for tam in range(112, 57, -6)]
    escolha = None
    for tam, escala in opcoes:
        linhas = _quebrar(titulo, _fonte("display", 700, tam), largura, 3)
        if linhas and altura(len(linhas), tam, escala) <= base - topo:
            escolha = (tam, escala, linhas)
            break
    if not escolha:   # nome enorme: o menor tamanho, cortado
        tam, escala = 58, 0.8
        fonte = _fonte("display", 700, tam)
        todas = _quebrar(titulo, fonte, largura, 99) or [titulo]
        escolha = (tam, escala, [*todas[:2], _cortar(" ".join(todas[2:]), fonte, largura)][: len(todas)])
    tam, escala, linhas = escolha
    fonte = _fonte("display", 700, tam)
    y = topo + (base - topo - altura(len(linhas), tam, escala)) / 2

    d.text((centro, y + 18), rotulo.upper(), font=_fonte("inter", 700, 32), fill=OURO, anchor="mm")
    y += 50
    for linha in linhas:
        d.text((centro, y), linha, font=fonte, fill=TEXTO, anchor="ma")
        y += tam * 1.08
    if linhas_sub:
        y += 24
        for linha in linhas_sub:
            d.text((centro, y), linha, font=sub, fill=TEXTO_2, anchor="ma")
            y += 52
    y += 80

    # medalhas: uma por linha, moeda + número + nome, o bloco centralizado
    num, rot = _fonte("display", 700, int(120 * escala)), _fonte("inter", 500, int(46 * escala))
    raio, passo = 60 * escala, 150 * escala
    larguras = [2 * raio + 30 + _largura(numero(q), num) + 24 + _largura(um if q == 1 else varios, rot)
                for q, _, um, varios in tipos]
    x0 = centro - max(larguras, default=0) / 2
    y += passo / 2
    for qtd, cor, um, varios in tipos:
        escura = tuple(int(c * 0.7) for c in cor)
        d.ellipse((x0, y - raio, x0 + 2 * raio, y + raio), fill=escura)
        d.ellipse((x0 + raio * 0.18, y - raio * 0.82, x0 + raio * 1.82, y + raio * 0.82), fill=cor)
        _estrela(d, x0 + raio, y, raio * 0.43, tuple(min(255, int(c * 1.15) + 25) for c in cor))
        texto = numero(qtd)
        xt = x0 + 2 * raio + 30
        d.text((xt, y + 4 * escala), texto, font=num, fill=TEXTO, anchor="lm")
        d.text((xt + _largura(texto, num) + 24, y + 22 * escala), um if qtd == 1 else varios, font=rot,
               fill=TEXTO_3, anchor="lm")
        y += passo
    y -= passo / 2

    if fila:   # olimpíadas e período, em etiquetas
        y += 40 + 30
        total = sum(_largura(e, fonte_et) + 56 for e in fila) - 16
        x = centro - total / 2
        for e in fila:
            w = _largura(e, fonte_et) + 40
            d.rounded_rectangle((x, y - 30, x + w, y + 30), radius=30, fill=(21, 27, 47), outline=(45, 52, 75), width=2)
            d.text((x + w / 2, y), e, font=fonte_et, fill=TEXTO_2, anchor="mm")
            x += w + 16
        y += 30

    if destaque:   # posição no ranking
        forte = _fonte("inter", 700, 40)
        w = _largura(destaque, forte) + 64
        y += 34 + 38
        d.rounded_rectangle((centro - w / 2, y - 38, centro + w / 2, y + 38), radius=38, fill=(58, 46, 12),
                            outline=OURO, width=2)
        d.text((centro, y), destaque, font=forte, fill=OURO_CLARO, anchor="mm")

    # embaixo fica o adesivo de link (o Instagram não deixa pôr link clicável na imagem)
    d.text((centro, 1610), "Veja todas as premiações em", font=_fonte("inter", 500, 36), fill=TEXTO_3, anchor="mm")
    d.text((centro, 1662), "medalhas.online", font=_fonte("display", 700, 48), fill=OURO_CLARO, anchor="mm")

    saida = io.BytesIO()
    img.save(saida, "PNG", optimize=True)
    return saida.getvalue()


def story_aluno(d: dict) -> bytes:
    """Story do aluno, a partir do perfil: período e olimpíadas viram etiquetas."""
    m = d["medalhas"]
    anos = d.get("anos") or []
    periodo = (str(anos[0]) if len(anos) == 1 else f"{anos[0]}–{anos[-1]}") if anos else None
    escola = d["escolas"][0] if d.get("escolas") else None
    subtitulo = None
    if escola:
        lugar = capitalizar_nome(escola["municipio"]) if escola.get("municipio") else None
        subtitulo = nome_de_exibicao(escola["escola"]) + (f" · {lugar}" if lugar else "")
    etiquetas = [*([periodo] if periodo else []), *_siglas(d.get("premiacoes") or [])]
    rotulo = "Medalhista" + (f" · {d['uf']}" if d.get("uf") else "")
    with _trava:
        return _story(rotulo, d["nome"], subtitulo, m, etiquetas, _posicao(d.get("rank"), "º no ranking nacional"))


def story_escola(d: dict) -> bytes:
    """Story da escola, a partir do perfil: alunos premiados e as olimpíadas."""
    lugar = ", ".join(p for p in (capitalizar_nome(d["municipio"]) if d.get("municipio") else None, d.get("uf")) if p)
    plural = "aluno premiado" if d["alunos"] == 1 else "alunos premiados"
    etiquetas = _siglas(d.get("recentes") or [])
    with _trava:
        return _story("Escola" + (f" · {lugar}" if lugar else ""), nome_de_exibicao(d["nome"]),
                      f"{numero(d['alunos'])} {plural}", d["medalhas"], etiquetas,
                      _posicao(d.get("rank"), "ª no ranking de escolas"))
