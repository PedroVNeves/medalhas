"""Servidor do site e da API.

Uso:
    python server.py                 # abre em http://localhost:8000
    python server.py --port 9000 --no-browser
    python server.py --host 0.0.0.0  # aceita conexões de outras máquinas (API pública)
    python server.py --rate-limit 30 --daily-limit 500 --export-limit 3    # limites por IP
    python server.py --trust-proxy --proxy-hops 2   # atrás de dois proxies (CDN + balanceador)

Ponto de montagem: liga a leitura SQLite ao servidor HTTP e aplica os limites da linha de comando.
"""
import argparse
import sys
import threading
import webbrowser

from medalhas import config
from medalhas.adaptadores.http import limites
from medalhas.adaptadores.http.servidor import Servidor, aquecer
from medalhas.adaptadores.sqlite import LeituraSqlite


def argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    """Opções da linha de comando; os limites ausentes mantêm o padrão de limites.GRUPOS."""
    p = argparse.ArgumentParser(description="Site e API dos medalhistas brasileiros.")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1", help="0.0.0.0 aceita conexões de outras máquinas")
    p.add_argument("--no-browser", action="store_true", help="não abre o navegador")
    p.add_argument("--trust-proxy", action="store_true",
                   help="usa o IP de X-Forwarded-For (só atrás de um proxy reverso seu, como nginx)")
    p.add_argument("--proxy-hops", type=int, default=1,
                   help="quantos proxies seus há na frente (padrão 1): o IP do visitante é o N-ésimo de "
                        "X-Forwarded-For contado da direita; o resto do cabeçalho é forjável")
    limite = p.add_argument_group("limites por IP (0 remove o limite)")
    limite.add_argument("--rate-limit", type=int, help="consultas por minuto à API pública (padrão 60)")
    limite.add_argument("--daily-limit", type=int, help="consultas por dia à API pública (padrão 2000)")
    limite.add_argument("--export-limit", type=int, help="exportações por hora (padrão 5; teto de 10 por dia)")
    limite.add_argument("--site-rate-limit", type=int, help="requisições por minuto da API do site (padrão 600)")
    limite.add_argument("--max-concurrent", type=int, help="consultas simultâneas à base (padrão 8)")
    limite.add_argument("--max-connections-per-ip", type=int, help="conexões abertas por IP (padrão 12)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Aplica os limites, sobe o servidor, aquece o cache em segundo plano e abre o navegador (salvo
    --no-browser). Sai com mensagem se a base ainda não foi gerada."""
    args = argumentos(argv)
    if not config.CAMINHO_BASE.exists():
        sys.exit("Base não encontrada. Rode primeiro: python build_db.py")
    limites.configurar(api_por_minuto=args.rate_limit, api_por_dia=args.daily_limit,
                       exportacoes_por_hora=args.export_limit, site_por_minuto=args.site_rate_limit,
                       consultas_simultaneas=args.max_concurrent, conexoes_por_ip=args.max_connections_per_ip)

    leitura = LeituraSqlite(config.CAMINHO_BASE)
    servidor = Servidor((args.host, args.port), leitura, confiar_proxy=args.trust_proxy,
                        saltos_proxy=args.proxy_hops)
    threading.Thread(target=aquecer, args=(leitura,), daemon=True).start()

    url = f"http://localhost:{args.port}"
    v1, exportar = limites.GRUPOS["v1"], limites.GRUPOS["exportar"]
    print(f"Medalhas rodando em {url}  (Ctrl+C para sair)")
    print(f"Limites por IP: API {v1['quantidade']}/min e {v1['por_dia'] or 'sem teto'}/dia; "
          f"exportação {exportar['quantidade']}/h e {exportar['por_dia'] or 'sem teto'}/dia; "
          f"{limites.MAX_CONEXOES_IP} conexões simultâneas")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
