"""Caminhos do projeto no disco. Único módulo que sabe onde ficam os arquivos."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DADOS = RAIZ / "data"
CAMINHO_BASE = PASTA_DADOS / "medalhas.db"     # base SQLite gerada por build_db.py
PASTA_EXPORTACAO = PASTA_DADOS / "exportar"    # arquivos da base inteira, gerados sob demanda
PASTA_CACHE = RAIZ / "cache"                   # páginas oficiais baixadas (evita baixar de novo)
PASTA_WEB = RAIZ / "web"                       # site estático
