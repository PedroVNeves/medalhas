"""Frequência de cada nome por sexo no Censo 2010, pela API de nomes do IBGE.

GET servicodados.ibge.gov.br/api/v2/censos/nomes/MARIA|JOAO?sexo=F devolve, para cada nome encontrado,
quantas mulheres nasceram com ele em cada década. Somando as décadas e fazendo o mesmo com sexo=M, sai a
fração de mulheres com o nome. As respostas ficam no cache em disco, como as páginas das olimpíadas.
"""
import json
import re

from .http import baixar

URL = "https://servicodados.ibge.gov.br/api/v2/censos/nomes/{nomes}?sexo={sexo}"
POR_PEDIDO = 40   # nomes por consulta (separados por |): URL curta e poucas consultas


def _frequencias(nomes: list[str], sexo: str) -> dict[str, int]:
    resposta = baixar(URL.format(nomes="|".join(nomes), sexo=sexo))
    if not resposta:
        return {}
    return {item["nome"]: sum(r["frequencia"] for r in item.get("res", [])) for item in json.loads(resposta)}


class NomesIbge:
    """Implementa aplicacao.portas.NomesPorSexo."""

    def fracao_feminina(self, nomes: set[str], log=print) -> dict[str, float]:
        validos = sorted(n for n in nomes if re.fullmatch(r"[A-Z]{2,}", n))   # a API só aceita letras
        fracao: dict[str, float] = {}
        for i in range(0, len(validos), POR_PEDIDO):
            lote = validos[i:i + POR_PEDIDO]
            mulheres, homens = _frequencias(lote, "F"), _frequencias(lote, "M")
            for nome in lote:
                f, m = mulheres.get(nome, 0), homens.get(nome, 0)
                if f + m:
                    fracao[nome] = f / (f + m)
        log(f"Nomes: {len(fracao)} de {len(validos)} primeiros nomes encontrados no Censo 2010 (IBGE)")
        return fracao
