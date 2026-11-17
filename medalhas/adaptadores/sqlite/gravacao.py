"""Repositório de escrita: grava as premiações e pré-calcula as tabelas-resumo de alunos e escolas."""
import sqlite3
from pathlib import Path

from ...dominio.escolas import ESCOLAS_RENOMEADAS
from ...dominio.premiacao import BRONZE, MENCAO, OURO, PRATA
from ...dominio.ranking import preencher_posicoes
from .esquema import (CAMPOS_ALUNO, CAMPOS_ESCOLA, CAMPOS_PREMIACAO, PONTOS, PREMIACOES, RESUMOS, insert)

_CAMPO_MEDALHA = {OURO: "ouro", PRATA: "prata", BRONZE: "bronze", MENCAO: "mencao"}


class RepositorioSqlite:
    """Implementa aplicacao.portas.RepositorioPremiacoes.

    A base nova é montada num arquivo temporário e só substitui a atual no fim: quem estiver lendo
    nunca vê uma base pela metade.
    """

    def __init__(self, caminho: Path):
        self.caminho = caminho

    def substituir(self, registros: list[dict], atualizado_em: str) -> None:
        self.caminho.parent.mkdir(exist_ok=True)
        temporario = self.caminho.with_suffix(".tmp")
        temporario.unlink(missing_ok=True)
        con = sqlite3.connect(temporario)
        try:
            con.executescript(PREMIACOES)
            con.executemany(insert("medalhas", CAMPOS_PREMIACAO),
                            ([r[c] for c in CAMPOS_PREMIACAO] for r in registros))
            con.execute("INSERT INTO meta VALUES ('atualizado_em', ?)", (atualizado_em,))
            gravar_resumos(con)
            con.commit()
        finally:
            con.close()
        temporario.replace(self.caminho)   # troca atômica: nunca há um instante sem base


def _zerado(base: dict) -> dict:
    return {**base, "ouro": 0, "prata": 0, "bronze": 0, "mencao": 0, "total": 0, **{c: 0 for c in PONTOS}}


def gravar_resumos(con: sqlite3.Connection) -> None:
    """Tabelas alunos e escolas: totais, pontos e posição nacional/estadual em cada método.

    Lê as premiações da mais recente para a mais antiga, então o "primeiro valor não vazio" de
    nome, UF, escola e município é sempre o mais recente.
    """
    con.executescript(RESUMOS)
    alunos: dict[str, dict] = {}
    escolas: dict[str, dict] = {}
    cursor = con.execute(f"""SELECT aluno_id, nome, uf, competicao, ano, medalha, escola, escola_chave, municipio,
                                    rede, esfera, {", ".join(PONTOS)}
                             FROM medalhas ORDER BY ano DESC, competicao DESC""")
    for linha in cursor:
        aluno_id, nome, uf, competicao, ano, medalha, escola, chave, municipio, rede, esfera = linha[:11]
        pontos = dict(zip(PONTOS, linha[11:]))
        a = alunos.get(aluno_id)
        if a is None:
            a = alunos[aluno_id] = _zerado({"id": aluno_id, "nome": nome, "uf": uf, "comps": set(), "escola": None,
                                            "escola_chave": None, "municipio": None, "de": ano, "ate": ano})
        if competicao == "OBM" and a["nome"] != nome and "OBM" not in a["comps"]:
            a["nome"] = nome   # a OBM publica nomes com acento e caixa mista: é a grafia mais fiel
        a["comps"].add(competicao)
        a["uf"] = a["uf"] or uf
        a["escola"] = a["escola"] or escola
        a["escola_chave"] = a["escola_chave"] or (chave or None)
        a["municipio"] = a["municipio"] or municipio
        acumular = [a]
        if chave:
            e = escolas.get(chave)
            if e is None:
                e = escolas[chave] = _zerado({"id": chave, "nomes": {}, "municipio": municipio, "uf": uf,
                                              "rede": rede, "esfera": esfera, "alunos_set": set(),
                                              "de": ano, "ate": ano})
            e["nomes"][escola] = e["nomes"].get(escola, 0) + 1
            e["alunos_set"].add(aluno_id)
            acumular.append(e)
        for x in acumular:
            x["total"] += 1
            for c in PONTOS:
                x[c] += pontos[c]
            x["de"], x["ate"] = min(x["de"], ano), max(x["ate"], ano)
            if medalha in _CAMPO_MEDALHA:
                x[_CAMPO_MEDALHA[medalha]] += 1

    for grupo in (alunos, escolas):
        itens = list(grupo.values())
        por_uf: dict[str, list[dict]] = {}
        for item in itens:
            if item["uf"]:   # sem estado (listas que não informam a UF) não há posição estadual
                por_uf.setdefault(item["uf"], []).append(item)
        for c in PONTOS:
            preencher_posicoes(itens, c, f"{c}_pos")
            for item in itens:
                item[f"{c}_pos_uf"] = None
            for da_uf in por_uf.values():
                preencher_posicoes(da_uf, c, f"{c}_pos_uf")

    for a in alunos.values():
        a["competicoes"] = ",".join(sorted(a["comps"], reverse=True))
    for e in escolas.values():
        # a grafia mais frequente; na escola que mudou de nome, a mais recente (as premiações vêm da mais nova
        # para a mais antiga): o nome antigo pode ser mais frequente, mas a página mostra o atual
        renomeada = e["id"] in ESCOLAS_RENOMEADAS.values()
        e["nome"] = next(iter(e["nomes"])) if renomeada else max(e["nomes"], key=e["nomes"].get)
        e["alunos"] = len(e["alunos_set"])
    con.executemany(insert("alunos", CAMPOS_ALUNO), ([a[c] for c in CAMPOS_ALUNO] for a in alunos.values()))
    con.executemany(insert("escolas", CAMPOS_ESCOLA), ([e[c] for c in CAMPOS_ESCOLA] for e in escolas.values()))
