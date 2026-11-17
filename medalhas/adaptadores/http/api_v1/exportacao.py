"""Exportação em CSV ou JSON: premiações (base inteira ou recorte) e rankings completos.

- Base inteira sem filtros: gerada uma vez por versão da base, compactada (gzip) e reaproveitada.
- Recortes: gerados num arquivo temporário (memória até 8 MB, depois disco). A conexão com a base é
  liberada antes do envio, então um cliente lento não segura uma vaga de consulta.
"""
import csv
import gzip
import io
import json
import re
import shutil
import tempfile
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import IO, BinaryIO

from ....aplicacao.portas import Linha, SessaoDeLeitura
from ....config import PASTA_EXPORTACAO
from ....dominio.ranking import com_posicoes
from ....dominio.texto import normalizar
from ..pedido import Pedido
from . import parametros
from .apresentacao import consulta, nomes_das_olimpiadas
from .erros import ParametroInvalido

CONJUNTOS = ("premiacoes", "alunos", "escolas", "estados", "cidades")
CAMPOS_PREMIACAO = ["id", "olimpiada", "olimpiada_nome", "area", "ano", "nivel", "medalha", "premio", "nome",
                    "aluno_id", "escola", "escola_id", "municipio", "uf", "rede", "esfera", "nota",
                    "pontos_impa", "pontos_impa_n3", "pontos_nossa", "fonte"]
CAMPOS_RANKING = {
    "alunos": ["posicao", "id", "nome", "uf", "escola", "municipio"],
    "escolas": ["posicao", "id", "nome", "municipio", "uf", "rede", "alunos_premiados"],
    "estados": ["posicao", "uf", "alunos_premiados", "escolas"],
    "cidades": ["posicao", "id", "nome", "uf", "alunos_premiados", "escolas"],
}
CAMPOS_RANKING_FIM = ["ouro", "prata", "bronze", "mencao_honrosa", "total", "pontos", "pontos_impa",
                      "pontos_impa_n3", "pontos_nossa", "de", "ate"]
# Qualquer um destes faz da exportação um recorte (e não a base inteira)
FILTROS = ("uf", "municipio", "competicao", "area", "medalha", "nivel", "ano", "ano_de", "ano_ate", "rede",
           "sexo", "escola_id", "aluno_id", "nome", "escola", "busca")
# Parâmetros que entram no nome do arquivo, nesta ordem
_PARTES_DO_NOME = ("aluno_id", "escola_id", "nome", "escola", "busca", "uf", "competicao", "ano", "ano_de",
                   "ano_ate", "nivel", "medalha")
_BLOCO = 256 * 1024
_TAMANHO_EM_MEMORIA = 8 * 1024 * 1024
_gerando_base_inteira = threading.Lock()


@dataclass
class Download:
    """Resposta em arquivo: `arquivo` é o caminho de um .gz já gerado ou um arquivo temporário aberto."""
    nome: str
    tipo: str             # Content-Type
    arquivo: Path | BinaryIO
    gzipado: bool
    linhas: int

    def tamanho(self) -> int:
        if isinstance(self.arquivo, Path):
            return self.arquivo.stat().st_size
        self.arquivo.seek(0, 2)
        tamanho = self.arquivo.tell()
        self.arquivo.seek(0)
        return tamanho

    def enviar(self, saida: BinaryIO, compactado: bool) -> None:
        """Copia o arquivo para a conexão; descompacta no caminho se o cliente não aceita gzip."""
        arquivo = open(self.arquivo, "rb") if isinstance(self.arquivo, Path) else self.arquivo
        try:
            if self.gzipado and not compactado:
                with gzip.GzipFile(fileobj=arquivo, mode="rb") as gz:
                    shutil.copyfileobj(gz, saida, _BLOCO)
            else:
                shutil.copyfileobj(arquivo, saida, _BLOCO)
        finally:
            arquivo.close()


# ---------------------------------------------------------------- linhas

def _linha_premiacao(r: Linha, nomes: dict) -> dict:
    return {"id": r["id"], "olimpiada": r["competicao"], "olimpiada_nome": nomes.get(r["competicao"], r["competicao"]),
            "area": r["area"], "ano": r["ano"], "nivel": r["nivel"], "medalha": r["medalha"], "premio": r["premio"],
            "nome": r["nome"], "aluno_id": r["aluno_id"], "escola": r["escola"], "escola_id": r["escola_chave"],
            "municipio": r["municipio"], "uf": r["uf"], "rede": r["rede"], "esfera": r["esfera"], "nota": r["pontos"],
            "pontos_impa": r["p_impa"], "pontos_impa_n3": r["p_impa3"], "pontos_nossa": r["p_site"],
            "fonte": r["fonte"]}


def _linha_ranking(r: dict, tipo: str, ultima_escola: dict) -> dict:
    d = {"posicao": r["pos"], "id": r["id"], "nome": r["nome"], "uf": r.get("uf") if tipo != "estados" else r["id"],
         "escola": r.get("escola"), "municipio": r.get("municipio"), "rede": r.get("rede"),
         "alunos_premiados": r.get("alunos"), "escolas": r.get("escolas"),
         "ouro": r["ouro"], "prata": r["prata"], "bronze": r["bronze"], "mencao_honrosa": r["mencao"],
         "total": r["total"], "pontos": r["xp"], "pontos_impa": r["p_impa"], "pontos_impa_n3": r["p_impa3"],
         "pontos_nossa": r["p_site"], "de": r.get("de"), "ate": r.get("ate")}
    if tipo == "alunos" and not d["escola"]:
        d["escola"], d["municipio"] = ultima_escola.get(r["id"], (None, None))
    return d


# ---------------------------------------------------------------- escrita em fluxo

def _escrever(saida: IO[bytes], linhas: Iterable[dict], campos: list[str], formato: str, separador: str,
              meta: dict) -> int:
    """CSV (com BOM, para o Excel reconhecer UTF-8) ou JSON, linha a linha. Devolve o nº de linhas."""
    texto = io.TextIOWrapper(saida, encoding="utf-8", newline="", write_through=False)
    n = 0
    if formato == "csv":
        texto.write("﻿")
        escritor = csv.DictWriter(texto, fieldnames=campos, delimiter=separador, extrasaction="ignore")
        escritor.writeheader()
        for d in linhas:
            escritor.writerow(d)
            n += 1
    else:   # {"fonte": …, "dados": [ {…}, … ], "total": n}, sem montar a lista inteira na memória
        texto.write(json.dumps(meta, ensure_ascii=False)[:-1] + ', "dados": [\n')
        for d in linhas:
            texto.write(("," if n else "") + json.dumps({k: d.get(k) for k in campos}, ensure_ascii=False) + "\n")
            n += 1
        texto.write(f'], "total": {n}}}\n')
    texto.flush()
    texto.detach()   # devolve a saída ao chamador sem fechá-la
    return n


def _gerar(s: SessaoDeLeitura, params: dict, conjunto: str, formato: str, separador: str, saida: IO[bytes]) -> int:
    meta = {"fonte": "Medalhas", "gerado_em": time.strftime("%Y-%m-%d %H:%M"), "conjunto": conjunto,
            "filtros": consulta(params)}
    if conjunto == "premiacoes":
        nomes = nomes_das_olimpiadas()
        linhas = (_linha_premiacao(r, nomes) for r in s.iterar_premiacoes(parametros.criterios(params, s)))
        campos = CAMPOS_PREMIACAO
    else:
        ranking = s.ranking_ordenado(parametros.ranking(params, conjunto, s))
        meta.update({"metodo": ranking.metodo, "ordem": ranking.ordem})
        ultima_escola = s.ultima_escola_dos_alunos() if conjunto == "alunos" else {}
        linhas = (_linha_ranking(r, conjunto, ultima_escola) for r in com_posicoes(ranking))
        campos = CAMPOS_RANKING[conjunto] + CAMPOS_RANKING_FIM
    return _escrever(saida, linhas, campos, formato, separador, meta)


def _base_inteira(s: SessaoDeLeitura, versao: int, formato: str, separador: str) -> tuple[Path, int]:
    """Arquivo .gz da base inteira, gerado uma vez por versão da base. Versões antigas são apagadas."""
    caminho = PASTA_EXPORTACAO / f"premiacoes-{versao}-{'pv' if separador == ';' else 'v'}.{formato}.gz"
    contagem = caminho.with_suffix(".linhas")
    with _gerando_base_inteira:
        if not caminho.exists():
            PASTA_EXPORTACAO.mkdir(parents=True, exist_ok=True)
            for antigo in PASTA_EXPORTACAO.glob("premiacoes-*"):
                if f"-{versao}-" not in antigo.name:
                    antigo.unlink(missing_ok=True)
            temporario = caminho.with_suffix(".tmp")
            with open(temporario, "wb") as bruto, gzip.GzipFile(fileobj=bruto, mode="wb", compresslevel=6,
                                                                 mtime=0) as gz:
                n = _gerar(s, {}, "premiacoes", formato, separador, gz)
            temporario.replace(caminho)
            contagem.write_text(str(n))
    return caminho, int(contagem.read_text() or 0) if contagem.exists() else 0


def _nome_do_arquivo(params: dict, conjunto: str, formato: str) -> str:
    """Ex.: medalhas-premiacoes-erick-akira-koga-sp.csv, medalhas-ranking-escolas-al-impa3.json"""
    partes = [conjunto if conjunto == "premiacoes" else f"ranking-{conjunto}"]
    for chave in _PARTES_DO_NOME:
        if params.get(chave):
            partes.append(re.sub(r"[^a-z0-9]+", "-", normalizar(params[chave]).lower())[:40].strip("-"))
    if params.get("sexo"):   # só existe sexo=F (validado antes)
        partes.append("meninas")
    if conjunto != "premiacoes":
        partes.append(parametros.metodo(params)[0])
    return "medalhas-" + "-".join(p for p in partes if p) + f".{formato}"


def exportar(s: SessaoDeLeitura, pedido: Pedido) -> Download:
    params = pedido.params
    formato = (params.get("formato") or "csv").lower()
    if formato not in ("csv", "json"):
        raise ParametroInvalido("formato deve ser csv ou json")
    separador = ";" if params.get("separador") in (";", "ponto-e-virgula", "excel") else ","
    conjunto = (params.get("conjunto") or "premiacoes").lower()
    if conjunto not in CONJUNTOS:
        raise ParametroInvalido("conjunto deve ser premiacoes, alunos, escolas, estados ou cidades")
    parametros.criterios(params, s)   # valida tudo antes de começar a gerar o arquivo

    nome = _nome_do_arquivo(params, conjunto, formato)
    tipo = "text/csv; charset=utf-8" if formato == "csv" else "application/json; charset=utf-8"
    if conjunto == "premiacoes" and not any(params.get(k) for k in FILTROS):
        caminho, linhas = _base_inteira(s, pedido.versao_base, formato, separador)
        return Download(nome, tipo, caminho, True, linhas)

    temporario = tempfile.SpooledTemporaryFile(max_size=_TAMANHO_EM_MEMORIA)
    if pedido.aceita_gzip:
        with gzip.GzipFile(fileobj=temporario, mode="wb", compresslevel=5, mtime=0) as gz:
            linhas = _gerar(s, params, conjunto, formato, separador, gz)
    else:
        linhas = _gerar(s, params, conjunto, formato, separador, temporario)
    temporario.seek(0)
    return Download(nome, tipo, temporario, pedido.aceita_gzip, linhas)
