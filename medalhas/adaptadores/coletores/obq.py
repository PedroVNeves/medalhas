"""Coletor da OBQ (Olimpíada Brasileira de Química): resultado final em PDF, um por modalidade.

A notícia "Resultado final" de cada ano em obquimica.org aponta para os PDFs das modalidades A e B. Cada PDF
é uma tabela (estado, nome, série, escola, nota, escore) dividida em faixas, com um rótulo na margem:
OURO, PRATA, BRONZE, MENÇÃO HONROSA e DEMAIS PARTICIPANTES (estes não são premiados). Os rótulos nem
sempre saem na ordem certa no texto do PDF, então a leitura usa a posição de cada trecho na página.

Resultados publicados assim: 2025 e 2026 (o arquivo de 2024 não está mais no ar). O PDF é lido com pypdf,
importado só aqui: sem ele, só a OBQ falha e as outras olimpíadas entram normalmente.
"""
import re
import time

from ...dominio.premiacao import BRONZE, MENCAO, OURO, PRATA, Premiacao
from ...dominio.texto import normalizar
from .html import texto
from .http import baixar, baixar_bytes
from .pdf import linhas, paginas

SITE = "https://obquimica.org"
NOTICIAS = (f"{SITE}/noticias/resultado-obq-{{ano}}", f"{SITE}/noticias/resultado-final-obq-{{ano}}")
PRIMEIRO_ANO = 2025
FAIXAS = {"OURO": OURO, "OIRO": OURO, "PRATA": PRATA, "BRONZE": BRONZE, "MENCAO HONROSA": MENCAO,
          "DEMAIS PARTICIPANTES": None}
UF_POR_NOME = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAZONAS": "AM", "AMAPA": "AP", "BAHIA": "BA", "CEARA": "CE",
    "DISTRITO FEDERAL": "DF", "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA", "MINAS GERAIS": "MG",
    "MATO GROSSO DO SUL": "MS", "MATO GROSSO": "MT", "PARA": "PA", "PARAIBA": "PB", "PERNAMBUCO": "PE",
    "PIAUI": "PI", "PARANA": "PR", "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN", "RONDONIA": "RO",
    "RORAIMA": "RR", "RIO GRANDE DO SUL": "RS", "SANTA CATARINA": "SC", "SERGIPE": "SE", "SAO PAULO": "SP",
    "TOCANTINS": "TO"}
_NOTA = re.compile(r"\d{1,3},\d{1,2}")
_DISTANCIA_QUEBRA = 16.0  # o resto de um nome de escola quebrado fica até isto abaixo da linha do aluno


def _limpar_nome(nome: str) -> str:
    """Tira anotações do fim do nome: "FROTA(1)" (nota de rodapé), "(PCD)", "(ANTIGO)"."""
    return re.sub(r"\s*\([^)]*\)$", "", nome).strip()


_SO_NOTAS = re.compile(r"(\d{1,3},\d{1,2}\s*)+")
_SERIE = re.compile(r"\s(\d[ºo°]\s*ANO\s+EM|\?)(\s|$)", re.I)
_ESTADOS_DO_MAIS_LONGO = sorted(UF_POR_NOME, key=len, reverse=True)   # MATO GROSSO DO SUL antes de MATO GROSSO


def _registro(linha: list[tuple[float, str]]) -> dict | None:
    """Campos de uma linha de aluno (uf, nome, série, escola, nota), ou None se a linha não é de aluno.

    Em geral cada coluna é um trecho. Quando a escola não cabe na célula, o PDF às vezes junta estado, nome,
    série e escola num trecho só (e as duas notas em outro): aí os campos saem do próprio texto.
    """
    textos = [t for _, t in linha]
    notas = [n for t in textos for n in _NOTA.findall(t)]
    uf = UF_POR_NOME.get(normalizar(textos[0]))
    if uf and len(linha) >= 3:
        meio = [t for t in textos[2:] if not _NOTA.fullmatch(t)]
        serie = next((t for t in meio if re.search(r"ano|^\?$", t, re.I)), None)
        return {"uf": uf, "nome": textos[1], "serie": serie,
                "escola": " ".join(t for t in meio if t != serie), "nota": notas[0] if notas else None}
    corrido = " ".join(t for t in textos if not _SO_NOTAS.fullmatch(t))
    normalizado = normalizar(corrido)
    estado = next((e for e in _ESTADOS_DO_MAIS_LONGO if normalizado.startswith(e + " ")), None)
    serie = _SERIE.search(corrido)
    if not estado or not serie:
        return None
    palavras_do_estado = len(estado.split())
    nome = " ".join(corrido[:serie.start()].split()[palavras_do_estado:])
    return {"uf": UF_POR_NOME[estado], "nome": nome, "serie": serie.group(1),
            "escola": corrido[serie.end():].strip(), "nota": notas[0] if notas else None}


def ler_pdf(paginas) -> list[dict]:
    """Premiados de um PDF (lista de páginas do pypdf), na ordem do arquivo.

    Quando o nome da escola não cabe na célula, o resto vem numa linha solta logo abaixo da linha do aluno:
    cada pedaço solto vai para a linha de aluno imediatamente acima dele, na mesma página.
    """
    registros: list[dict] = []
    faixa = "?"
    for pagina in paginas:
        da_pagina: list[tuple[float, dict]] = []
        soltos: list[tuple[float, str]] = []
        for y, linha in linhas(pagina):
            rotulo = normalizar(" ".join(t for _, t in linha))
            if rotulo in FAIXAS:
                faixa = FAIXAS[rotulo]
                continue
            r = _registro(linha)
            if r:
                r.update(nome=_limpar_nome(r["nome"]), faixa=faixa, partes=[(y, r.pop("escola"))])
                da_pagina.append((y, r))
            else:
                soltos.append((y, " ".join(t for _, t in linha)))
        for y, texto_solto in soltos:
            acima = [(y_aluno, r) for y_aluno, r in da_pagina if 0 < y - y_aluno <= _DISTANCIA_QUEBRA]
            if acima and not re.match(r"p[aá]gina \d", texto_solto, re.I):   # cabeçalho/rodapé ficam longe
                max(acima, key=lambda item: item[0])[1]["partes"].append((y, texto_solto))
        for _, r in da_pagina:
            r["escola"] = " ".join(t for _, t in sorted(r.pop("partes")) if t) or None
            registros.append(r)
    return registros


def _pdfs_do_ano(ano: int) -> list[tuple[str, str]]:
    """(modalidade, url do PDF) da notícia de resultado final do ano."""
    for modelo in NOTICIAS:
        pagina = baixar(modelo.format(ano=ano))
        if not pagina:
            continue
        achados = []
        for href, rotulo in re.findall(r'<a\b[^>]*href="([^"]+\.pdf)"[^>]*>(.*?)</a>', pagina, re.S | re.I):
            m = re.search(r"modalidade\s+([AB])\b", texto(rotulo), re.I)
            if m:
                achados.append((m.group(1).upper(), href if href.startswith("http") else SITE + href))
        if achados:
            return achados
    return []


def coletar(log=print) -> list[Premiacao]:
    """Premiações das modalidades A e B de cada ano desde 2025. Demais participantes e linhas antes do
    primeiro rótulo de faixa não entram."""
    premiacoes: list[Premiacao] = []
    for ano in range(PRIMEIRO_ANO, time.localtime().tm_year + 1):
        for modalidade, url in _pdfs_do_ano(ano):
            conteudo = baixar_bytes(url)
            if not conteudo:
                continue
            for r in ler_pdf(paginas(conteudo)):
                if r["faixa"] in (None, "?"):
                    continue   # demais participantes (ou linha antes do primeiro rótulo)
                premiacoes.append({
                    "competicao": "OBQ", "ano": ano, "nivel": f"Modalidade {modalidade}", "nome": r["nome"],
                    "escola": r["escola"], "rede": None, "esfera": None, "municipio": None, "uf": r["uf"],
                    "premio": r["faixa"], "medalha": r["faixa"], "pontos": r["nota"], "fonte": url,
                })
    anos = sorted({p["ano"] for p in premiacoes})
    log(f"OBQ: {len(premiacoes)} premiações, {anos[0] if anos else '-'}–{anos[-1] if anos else '-'}")
    return premiacoes
