"""Tradução de filtros e buscas por texto para cláusulas WHERE.

Valores do usuário sempre vão como parâmetros (?), nunca interpolados no SQL.
"""
from ...aplicacao.portas import Criterios
from ...dominio.escolas import Expansao
from ...dominio.texto import normalizar

# Agregados de premiações usados em rankings e resumos
AGREGADOS = """SUM(medalha='Ouro') AS ouro, SUM(medalha='Prata') AS prata, SUM(medalha='Bronze') AS bronze,
         SUM(medalha='Menção Honrosa') AS mencao, COUNT(*) AS total,
         SUM(p_impa) AS p_impa, SUM(p_impa3) AS p_impa3, SUM(p_site) AS p_site,
         MIN(ano) AS de, MAX(ano) AS ate"""

# Chaves de filtro reconhecidas (as demais chaves da URL são ignoradas)
CHAVES_FILTRO = ("competicao", "area", "medalha", "uf", "rede", "nivel", "escola_chave", "esfera", "sexo", "ano", "ano_de",
                 "ano_ate", "municipio", "sem_mencao")

# Campos pesquisáveis por texto. Os espaços à esquerda fazem "% PALAVRA%" casar no início de palavra.
_NOME = "(' ' || nome_busca)"
_MUNICIPIO = "(' ' || municipio_busca)"
_ESCOLA = "escola_termos"   # já gravado entre espaços
_CAMPOS_TEXTO = {"nome": [_NOME], "escola": [_ESCOLA], "tudo": [_NOME, _ESCOLA, _MUNICIPIO]}


def condicoes(filtros: dict) -> tuple[list[str], list]:
    """Cláusulas (unidas por AND) e argumentos dos filtros."""
    where: list[str] = []
    args: list = []
    # múltipla escolha: valores separados por vírgula ("OBMEP,OBM", "1,2,3,Universitário")
    for chave in ("competicao", "nivel", "area"):
        valores = [v.strip() for v in (filtros.get(chave) or "").split(",") if v.strip()]
        if valores:
            where.append(f"{chave} IN ({','.join('?' * len(valores))})")
            args += valores
    for chave in ("medalha", "uf", "rede", "escola_chave", "esfera", "sexo"):
        if filtros.get(chave):
            where.append(f"{chave} = ?")
            args.append(filtros[chave])
    for chave, operador in (("ano", "="), ("ano_de", ">="), ("ano_ate", "<=")):
        if filtros.get(chave):
            where.append(f"ano {operador} ?")
            args.append(int(filtros[chave]))
    if filtros.get("municipio"):
        where.append("municipio_busca = ?")
        args.append(normalizar(filtros["municipio"]))
    if filtros.get("sem_mencao") == "1":
        where.append("medalha != 'Menção Honrosa'")
    return where, args


def condicao_de_palavra(campo: str, palavra: str, expansao: list[str]) -> tuple[str, list[str]]:
    """Uma palavra digitada casa no início de uma palavra do campo. Em escolas, também casa pela
    expansão da sigla (IFAL -> INSTITUTO FEDERAL ALAGOAS)."""
    campos = _CAMPOS_TEXTO[campo]
    partes = [f"{c} LIKE ?" for c in campos]
    args = [f"% {palavra}%"] * len(campos)
    if campo in ("escola", "tudo") and expansao != [palavra]:
        partes.append("(" + " AND ".join(f"{_ESCOLA} LIKE ?" for _ in expansao) + ")")
        args += [f"% {e}%" for e in expansao]
    return "(" + " OR ".join(partes) + ")", args


def condicoes_de_texto(campo: str, palavras: Expansao) -> tuple[list[str], list]:
    where: list[str] = []
    args: list = []
    for palavra, expansao in palavras:
        cond, cond_args = condicao_de_palavra(campo, palavra, expansao)
        where.append(cond)
        args += cond_args
    return where, args


def where_de(criterios: Criterios) -> tuple[str, list]:
    """WHERE completo de um recorte (filtros + aluno + textos). "1" quando não há restrição."""
    where, args = condicoes(criterios.filtros)
    if criterios.aluno_id:
        where.append("aluno_id = ?")
        args.append(criterios.aluno_id)
    for campo, palavras in criterios.textos:
        w, a = condicoes_de_texto(campo, palavras)
        where += w
        args += a
    return " AND ".join(where) or "1", args
