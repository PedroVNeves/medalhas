"""Gera a base data/medalhas.db a partir das listas oficiais de premiados.

Uso:
    python build_db.py            # usa as páginas já baixadas (cache/) quando existirem
    python build_db.py --refresh  # apaga o cache e baixa tudo de novo (ano novo publicado)

Ponto de montagem: liga os coletores e o repositório SQLite ao caso de uso gerar_base.
"""
import argparse
import shutil
from pathlib import Path

from medalhas import config
from medalhas.adaptadores import coletores
from medalhas.adaptadores.sqlite import RepositorioSqlite
from medalhas.aplicacao.gerar_base import gerar_base


def main(argv: list[str] | None = None, caminho: Path = config.CAMINHO_BASE) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--refresh", action="store_true", help="apaga o cache e baixa tudo de novo")
    args = parser.parse_args(argv)
    if args.refresh and config.PASTA_CACHE.exists():
        shutil.rmtree(config.PASTA_CACHE)

    relatorio = gerar_base(coletores.todos(), RepositorioSqlite(caminho))

    print(f"\n{relatorio.premiacoes} registros gravados em {caminho}")
    if relatorio.falhas:
        print("\nATENÇÃO: fontes que falharam (rode de novo para tentar baixar):")
        for falha in relatorio.falhas:
            print("  -", falha)


if __name__ == "__main__":
    main()
