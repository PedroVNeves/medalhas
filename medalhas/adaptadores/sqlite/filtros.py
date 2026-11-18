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
CHAVES_FILTRO = ("competicao", "area", "medalha", "uf", "rede", "nivel", "escola_chave", "esfera", "sexo", "ano",
                 "ano_de", "ano_ate", "municipio", "sem_mencao", "so_edital")
_ANO_MAXIMO = 9999   # acima disso o SQLite nem aceita o número; nenhum ano de verdade chega perto

# Campos pesquisáveis por texto. Os espaços à esquerda fazem "% PALAVRA%" casar no início de palavra.
_NOME = "(' ' || nome_busca)"
_MUNICIPIO = "(' ' || municipio_busca)"
_ESCOLA = "escola_termos"   # já gravado entre espaços
_CAMPOS_TEXTO = {"nome": [_NOME], "escola": [_ESCOLA], "tudo": [_NOME, _ESCOLA, _MUNICIPIO]}


def inteiro(valor, nome: str, minimo: int = 0, maximo: int = _ANO_MAXIMO) -> int:
    """Número inteiro vindo da URL, ajustado ao intervalo. ValueError (com o nome do parâmetro) se não é número."""
    try:
        return max(minimo, min(int(valor), maximo))
    except (TypeError, ValueError):
        raise ValueError(f"'{nome}' deve ser um número inteiro") from None


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
            args.append(inteiro(filtros[chave], chave))
    if filtros.get("municipio"):
        where.append("municipio_busca = ?")
        args.append(normalizar(filtros["municipio"]))
    if filtros.get("sem_mencao") == "1":
        where.append("medalha != 'Menção Honrosa'")
    if filtros.get("so_edital") == "1":   # método IMPA edital: só o que pontua nele (olimpíada e nível aceitos)
        where.append("p_impa3 > 0")
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
    """Uma condição por palavra digitada (unidas por AND): todas as palavras precisam casar."""
    where: list[str] = []
    args: list = []
    for palavra, expansao in palavras:
        cond, cond_args = condicao_de_palavra(campo, palavra, expansao)
        where.append(cond)
        args += cond_args
    return where, args


def prefiltro_de_texto(campo: str, palavras: Expansao, consulta_fts: str | None = None) -> tuple[list[str], list]:
    """Condições indexadas que reduzem as premiações às candidatas antes das de condicoes_de_texto, que continuam
    valendo: o resultado é o mesmo, sem o LIKE percorrer a base inteira.

    Nome (consulta_fts: a consulta do índice de texto): os alunos que o índice das sugestões acha (busca_alunos,
    com todas as grafias de cada um). Os nomes da base só têm A-Z, 0-9 e espaços, então toda premiação que o
    LIKE aceita é de um aluno achado aqui. Escola: as grafias (tabela pequena) que casam, pela mesma condição.
    No campo tudo não há prefiltro: juntar três caminhos saiu mais lento que percorrer a base."""
    if campo == "nome" and palavras and consulta_fts:
        return ["aluno_n IN (SELECT rowid FROM busca_alunos WHERE busca_alunos MATCH ?)"], [consulta_fts]
    if campo == "escola" and palavras:
        where, args = condicoes_de_texto("escola", palavras)
        return [f"grafia_n IN (SELECT n FROM grafias WHERE {' AND '.join(where)})"], args
    return [], []


def where_de(criterios: Criterios) -> tuple[str, list]:
    """WHERE completo de um recorte (filtros + aluno + textos). "1" quando não há restrição."""
    where, args = condicoes(criterios.filtros)
    if criterios.aluno_id:
        where.append("aluno_n = (SELECT n FROM alunos WHERE id = ?)")
        args.append(criterios.aluno_id)
    for campo, palavras in criterios.textos:
        w, a = condicoes_de_texto(campo, palavras)
        where += w
        args += a
    return " AND ".join(where) or "1", args
