"""Gera a base data/medalhas.db a partir das listas oficiais de premiados.

Uso:
    python build_db.py            # usa as páginas já baixadas (cache/) quando existirem
    python build_db.py --refresh  # apaga o cache e baixa tudo de novo (ano novo publicado)
    python build_db.py --permitir-parcial  # grava mesmo se alguma fonte falhar (a base fica sem ela)

Ponto de montagem: liga os coletores e o repositório SQLite ao caso de uso gerar_base.
"""
import argparse
import shutil
import sys
from pathlib import Path

from medalhas import config
from medalhas.adaptadores import coletores
from medalhas.adaptadores.sqlite import RepositorioSqlite
from medalhas.aplicacao.gerar_base import gerar_base


def main(argv: list[str] | None = None, caminho: Path = config.CAMINHO_BASE) -> None:
    """Gera a base em `caminho` e mostra quantas premiações foram gravadas e quais fontes falharam."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--refresh", action="store_true", help="apaga o cache e baixa tudo de novo")
    parser.add_argument("--permitir-parcial", action="store_true",
                        help="grava a base mesmo se alguma fonte falhar (ela fica sem as premiações dessa fonte)")
    parser.add_argument("--mencoes-obmep", action="store_true",
                        help="inclui as menções honrosas da OBMEP (cerca de 50 mil por edição; em avaliação)")
    args = parser.parse_args(argv)
    if args.refresh and config.PASTA_CACHE.exists():
        shutil.rmtree(config.PASTA_CACHE)

    relatorio = gerar_base(coletores.todos(args.mencoes_obmep), RepositorioSqlite(caminho),
                           permitir_parcial=args.permitir_parcial)

    if relatorio.gravada:
        print(f"\n{relatorio.premiacoes} registros gravados em {caminho}")
    if relatorio.falhas:
        print("\nATENÇÃO: fontes que falharam (rode de novo para tentar baixar):")
        for falha in relatorio.falhas:
            print("  -", falha)
    if not relatorio.gravada:
        sys.exit("\nA base NÃO foi gravada: a anterior continua valendo. Rode de novo, ou use --permitir-parcial "
                 "para gravar sem as fontes que falharam.")


if __name__ == "__main__":
    main()
