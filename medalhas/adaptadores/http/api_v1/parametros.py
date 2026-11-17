"""Validação dos parâmetros da URL. Valor inválido gera ParametroInvalido com uma mensagem útil;
o resto da API só recebe valores já conferidos."""
import re

from ....aplicacao.portas import Criterios, SessaoDeLeitura
from ....dominio import pontuacao
from ....dominio.escolas import Expansao, palavras_da_busca
from ....dominio.premiacao import PREMIOS, UFS
from ....dominio.ranking import ORDEM_PADRAO, ORDENACOES, TIPOS
from ....dominio.texto import normalizar
from .erros import NaoEncontrado, ParametroInvalido

LIMITE_PADRAO = 20
LIMITE_MAXIMO = {"alunos": 100, "escolas": 100, "medalhistas": 500, "premiacoes": 1000, "ranking": 500}
MAX_CARACTERES = 100   # buscas por texto: protege a base de consultas caras
MAX_PALAVRAS = 8
_VERDADEIRO = ("1", "true", "sim", "s", "yes")
_REDES = {"publica": "Pública", "privada": "Privada"}
_SEXOS = {"F": "F", "FEMININO": "F", "MENINAS": "F"}
# Campos de texto que cada rota aceita: parâmetro da URL -> campo pesquisado
TEXTO_PREMIACOES = (("nome", "nome"), ("escola", "escola"), ("busca", "tudo"))


def booleano(params: dict, chave: str, padrao: bool) -> bool:
    v = (params.get(chave) or "").strip().lower()
    return padrao if not v else v in _VERDADEIRO


def inteiro(params: dict, chave: str, padrao: int | None = None, minimo: int | None = None,
            maximo: int | None = None) -> int | None:
    """Número inteiro, ajustado ao intervalo [minimo, maximo] em vez de recusado."""
    v = (params.get(chave) or "").strip()
    if not v:
        return padrao
    if not re.fullmatch(r"-?\d+", v):
        raise ParametroInvalido(f"'{chave}' deve ser um número inteiro (recebido: {v[:20]!r})")
    n = int(v)
    if minimo is not None:
        n = max(n, minimo)
    if maximo is not None:
        n = min(n, maximo)
    return n


def paginacao(params: dict, rota: str) -> tuple[int, int]:
    """(limite, offset) da página, com o tamanho máximo da rota."""
    return inteiro(params, "limite", LIMITE_PADRAO, 1, LIMITE_MAXIMO[rota]), inteiro(params, "offset", 0, 0)


def texto(params: dict, chave: str, obrigatorio: bool = False) -> Expansao:
    """Palavras de busca (acentos e ordem ignorados)."""
    v = (params.get(chave) or "").strip()
    if len(v) > MAX_CARACTERES:
        raise ParametroInvalido(f"'{chave}' pode ter no máximo {MAX_CARACTERES} caracteres")
    palavras = palavras_da_busca(v)
    if obrigatorio and not palavras:
        raise ParametroInvalido(f"informe o parâmetro '{chave}' (ex.: ?{chave}=maria silva)")
    if len(palavras) > MAX_PALAVRAS:
        raise ParametroInvalido(f"'{chave}' pode ter no máximo {MAX_PALAVRAS} palavras")
    return palavras


def metodo(params: dict) -> tuple[str, str]:
    """(método, coluna de pontos). Valor desconhecido usa o método padrão."""
    return pontuacao.resolver_metodo(params.get("metodo"))


def _lista(params: dict, chave: str, validos: set[str], nome: str) -> str | None:
    """Valores separados por vírgula, todos conferidos contra o catálogo."""
    v = (params.get(chave) or "").strip()
    if not v:
        return None
    itens = [x.strip() for x in v.split(",") if x.strip()]
    errados = [x for x in itens if x not in validos]
    if errados:
        raise ParametroInvalido(f"valor desconhecido em '{chave}' ({nome}): {', '.join(errados)[:80]}. "
                                "Valores aceitos em GET /api/v1/olimpiadas")
    return ",".join(itens)


def filtros(params: dict, sessao: SessaoDeLeitura) -> dict:
    """Filtros comuns a todas as rotas, validados e no vocabulário da base."""
    catalogo = pontuacao.catalogo()
    f: dict = {}
    if params.get("uf"):
        uf = params["uf"].upper().strip()
        if uf not in UFS:
            raise ParametroInvalido(f"UF inválida: {params['uf'][:10]!r} (use a sigla, ex.: SP)")
        f["uf"] = uf
    if params.get("medalha"):
        medalha = {normalizar(m): m for m in PREMIOS}.get(normalizar(params["medalha"]))
        if not medalha:
            raise ParametroInvalido(f"medalha inválida: {params['medalha'][:20]!r} (use {', '.join(PREMIOS)})")
        f["medalha"] = medalha
    for chave, validos, nome in (("competicao", {o["sigla"] for o in catalogo}, "olimpíada"),
                                 ("area", {o["area"] for o in catalogo}, "área"),
                                 ("nivel", sessao.niveis(), "nível")):
        valor = _lista(params, chave, validos, nome)
        if valor:
            f[chave] = valor
    for chave in ("ano", "ano_de", "ano_ate"):
        n = inteiro(params, chave)
        if n is not None:
            f[chave] = n
    if params.get("rede"):
        rede = _REDES.get(normalizar(params["rede"]).lower())
        if not rede:
            raise ParametroInvalido("rede deve ser 'publica' ou 'privada'")
        f["rede"] = rede
    if params.get("sexo"):
        sexo = _SEXOS.get(normalizar(params["sexo"]))
        if not sexo:
            raise ParametroInvalido("sexo aceita só 'F': alunas premiadas em olimpíadas só para meninas "
                                    "(EGMO, PAGMO, EGOI); as listas oficiais não informam o sexo dos demais")
        f["sexo"] = sexo
    if params.get("municipio"):
        f["municipio"] = params["municipio"][:MAX_CARACTERES]
    if params.get("escola_id"):
        f["escola_chave"] = params["escola_id"]
    return f


def ranking(params: dict, tipo: str, sessao: SessaoDeLeitura) -> dict:
    """Parâmetros do ranking no formato das consultas do site (todos os valores como texto)."""
    if tipo not in TIPOS:
        raise NaoEncontrado("ranking inexistente: use /api/v1/ranking/alunos, /escolas, /estados ou /cidades")
    p = {**filtros(params, sessao), "tipo": tipo, "metodo": params.get("metodo", ""),
         "ordem": params.get("ordem", ORDEM_PADRAO)}
    if p["ordem"] not in ORDENACOES:
        raise ParametroInvalido("ordem deve ser xp (pontos), medalhas (quadro de medalhas) ou total")
    return {k: str(v) for k, v in p.items() if v not in (None, "")}


def criterios(params: dict, sessao: SessaoDeLeitura, textos=TEXTO_PREMIACOES) -> Criterios:
    """Recorte de premiações: filtros comuns + aluno_id + buscas por texto aceitas pela rota."""
    return Criterios(filtros=filtros(params, sessao),
                     textos=tuple((campo, texto(params, chave)) for chave, campo in textos),
                     aluno_id=params.get("aluno_id") or None)
