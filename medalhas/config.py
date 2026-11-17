"""Caminhos do projeto no disco e endereço público do site."""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DADOS = RAIZ / "data"
CAMINHO_BASE = PASTA_DADOS / "medalhas.db"     # base SQLite gerada por build_db.py
PASTA_EXPORTACAO = PASTA_DADOS / "exportar"    # arquivos da base inteira, gerados sob demanda
PASTA_CACHE = RAIZ / "cache"                   # páginas oficiais baixadas (evita baixar de novo)
PASTA_WEB = RAIZ / "web"                       # site estático

# endereço oficial do site: vai no link canônico das páginas e no sitemap, venha a visita do domínio
# próprio, do endereço do Firebase (*.web.app) ou do servidor local
URL_SITE = os.environ.get("MEDALHAS_URL", "https://medalhas.online").rstrip("/")
# Domínios pelos quais o site é servido (além do de URL_SITE): atrás do proxy, o X-Forwarded-Host só vale para
# montar links se for um deles. Um nome começando com ponto vale para os subdomínios (".web.app").
HOSTS_PUBLICOS = tuple(h.strip().lower() for h in os.environ.get(
    "MEDALHAS_HOSTS", ".web.app,.firebaseapp.com,.run.app,localhost,127.0.0.1").split(",") if h.strip())
