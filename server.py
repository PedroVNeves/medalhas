"""Servidor: interface web, API do site e API pública (v1).

Uso:
    python server.py                 # abre em http://localhost:8000
    python server.py --port 9000 --no-browser
    python server.py --host 0.0.0.0  # aceita conexões de outras máquinas (API pública)
    python server.py --rate-limit 30 --daily-limit 500 --export-limit 10   # limites por IP (limites.py)
"""
import json
import mimetypes
import sys
import threading
import traceback
import webbrowser
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import api_v1
import limites
import olimpiadas as olp
from consultas import DB_PATH, ROOT, SORT_KEYS, connect, overview, perfil_aluno, perfil_escola, ranking, search

WEB_DIR = ROOT / "web"
CONFIAR_PROXY = False  # usa X-Forwarded-For (só ligue atrás de um proxy reverso seu, como nginx)

# API interna, usada pelas páginas do site (pode mudar sem aviso; integrações devem usar /api/v1)
ROUTES = {
    "/api/busca": lambda con, p: search(con, p),
    "/api/ranking": lambda con, p: ranking(con, p),
    "/api/aluno": lambda con, p: perfil_aluno(con, p.get("id", ""), p),
    "/api/escola": lambda con, p: perfil_escola(con, p.get("id", ""), p),
    "/api/overview": lambda con, p: overview(con, p),
}
EXPOE = "X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Scope, Retry-After, Content-Disposition, X-Total-Rows"


class Handler(BaseHTTPRequestHandler):
    timeout = 20  # segundos sem receber/enviar dados: derruba conexões lentas de propósito (slowloris)

    # ------------------------------------------------ respostas
    def _cabecalhos(self, status: int, headers: dict) -> None:
        self.send_response(status)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")  # API pública: pode ser chamada de outros sites
        self.send_header("Access-Control-Expose-Headers", EXPOE)
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()

    def _send(self, body: bytes, ctype: str, status: int = 200, headers: dict | None = None) -> None:
        self._cabecalhos(status, {"Content-Type": ctype, "Content-Length": str(len(body)), **(headers or {})})
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data, status=200, headers: dict | None = None) -> None:
        self._send(json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8",
                   status, headers)

    def _ip(self) -> str:
        if CONFIAR_PROXY and self.headers.get("X-Forwarded-For"):
            return self.headers["X-Forwarded-For"].split(",")[0].strip()
        return self.client_address[0]

    def _aceita_gzip(self) -> bool:
        return "gzip" in (self.headers.get("Accept-Encoding") or "")

    def _recusar(self, cab: dict) -> None:
        espera = int(cab["Retry-After"])
        escopo = cab.get("X-RateLimit-Scope")
        if escopo == "dia":
            msg = "limite diário de consultas atingido; volta a liberar à meia-noite"
        elif escopo == "bloqueio":
            msg = f"muitas requisições depois do limite: IP bloqueado por {espera} segundo(s)"
        else:
            msg = f"limite de consultas atingido; tente de novo em {espera} segundo(s)"
        self._json({"erro": msg, "tente_em_segundos": espera}, 429, cab)

    # ------------------------------------------------ API
    def _api(self, path: str, params: dict) -> None:
        if path.startswith("/api/v1"):
            achou = api_v1.rota(path)
            if not achou:
                self._json({"erro": f"rota inexistente: {path}. Veja as rotas em /api/v1"}, 404)
                return
            fn, grupo = achou
        elif path in ROUTES:
            fn, grupo = ROUTES[path], "site"
        else:
            self._json({"erro": f"rota inexistente: {path}"}, 404)
            return

        ok, cab = limites.limitador.consumir(grupo, self._ip())
        if not ok:
            self._recusar(cab)
            return
        if not limites.consultas.acquire(timeout=limites.ESPERA_CONSULTA):
            self._json({"erro": "servidor ocupado; tente de novo em instantes", "tente_em_segundos": 5}, 503,
                       {"Retry-After": "5"})
            return
        try:
            with closing(connect()) as con:
                data = api_v1.exportar(con, params, self._aceita_gzip()) if fn == "exportar" else fn(con, params)
        finally:
            limites.consultas.release()  # o envio do arquivo acontece já sem ocupar a base

        if isinstance(data, api_v1.Download):
            self._enviar_download(data, cab)
        else:
            self._json(data, headers=cab)

    def _enviar_download(self, dl: "api_v1.Download", cab: dict) -> None:
        gz = dl.gzipado and self._aceita_gzip()
        headers = {"Content-Type": dl.ctype, "X-Total-Rows": str(dl.linhas),
                   "Content-Disposition": f'attachment; filename="{dl.nome}"', **cab}
        if gz:
            headers["Content-Encoding"] = "gzip"
            arq = dl.arquivo
            if hasattr(arq, "stat"):
                tamanho = arq.stat().st_size
            else:
                arq.seek(0, 2)
                tamanho = arq.tell()
                arq.seek(0)
            headers["Content-Length"] = str(tamanho)
        self._cabecalhos(200, headers)
        if self.command == "HEAD":
            return
        api_v1.enviar_arquivo(dl, self.wfile, gz)

    # ------------------------------------------------ HTTP
    def do_OPTIONS(self) -> None:  # preflight CORS
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self) -> None:
        ip = self._ip()
        espera = limites.limitador.bloqueio_restante(ip)
        if espera:
            self._recusar({"Retry-After": str(espera), "X-RateLimit-Scope": "bloqueio"})
            return
        url = urlparse(self.path)
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        proto = (self.headers.get("X-Forwarded-Proto") if CONFIAR_PROXY else None) or "http"
        params["_base"] = f"{proto}://{self.headers.get('Host') or 'localhost'}"
        path = url.path.rstrip("/") or "/"
        try:
            if path.startswith("/api/"):
                self._api(path, params)
                return
            rel = "index.html" if url.path in ("/", "") else unquote(url.path.lstrip("/"))
            target = (WEB_DIR / rel).resolve()
            if WEB_DIR.resolve() in target.parents and target.is_file():
                ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype.endswith("javascript"):
                    ctype += "; charset=utf-8"
                self._send(target.read_bytes(), ctype)
            else:
                self._send(b"Not found", "text/plain", 404)
        except api_v1.NaoEncontrado as e:
            self._json({"erro": str(e)}, 404)
        except ValueError as e:  # ex.: ano=abc, offset=xyz
            self._json({"erro": f"parâmetro inválido: {e}"}, 400)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass  # o cliente desistiu no meio do envio
        except Exception as e:  # noqa: BLE001 — bug do servidor: registra no terminal com o traceback
            traceback.print_exc()
            self._json({"erro": f"erro interno do servidor ({type(e).__name__})"}, 500)

    do_HEAD = do_GET

    def log_message(self, *args) -> None:
        pass


class Servidor(ThreadingHTTPServer):
    """Recusa conexões além do teto (por IP e no total) antes de criar uma thread para elas."""
    daemon_threads = True
    request_queue_size = 64

    def verify_request(self, request, client_address) -> bool:
        # atrás de um proxy todo mundo chega com o IP do proxy: aí só vale o teto total
        return limites.conexoes.entrar(client_address[0], por_ip=not CONFIAR_PROXY)

    def process_request(self, request, client_address):
        try:
            super().process_request(request, client_address)
        except Exception:
            limites.conexoes.sair(client_address[0])
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            limites.conexoes.sair(client_address[0])


def warm_up() -> None:
    """Pré-calcula as consultas pesadas para a primeira visita ser instantânea."""
    with closing(connect()) as con:
        for metodo in olp.METODOS:
            overview(con, {"metodo": metodo})
            for tipo in ("alunos", "escolas", "estados"):
                for ordem in SORT_KEYS:
                    ranking(con, {"tipo": tipo, "ordem": ordem, "metodo": metodo})


def main() -> None:
    if not DB_PATH.exists():
        sys.exit("Base não encontrada. Rode primeiro: python build_db.py")
    mimetypes.add_type("text/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8000
    # --host 0.0.0.0 deixa a API acessível para outras máquinas da rede
    host = sys.argv[sys.argv.index("--host") + 1] if "--host" in sys.argv else "127.0.0.1"
    global CONFIAR_PROXY
    CONFIAR_PROXY = "--trust-proxy" in sys.argv
    limites.configurar(sys.argv)
    server = Servidor((host, port), Handler)
    threading.Thread(target=warm_up, daemon=True).start()
    url = f"http://localhost:{port}"
    print(f"Medalhas rodando em {url}  (Ctrl+C para sair)")
    v1, exp = limites.GRUPOS["v1"], limites.GRUPOS["exportar"]
    print(f"Limites por IP: API {v1['quantidade']}/min e {v1['por_dia'] or 'sem teto'}/dia; "
          f"exportação {exp['quantidade']}/h e {exp['por_dia'] or 'sem teto'}/dia; "
          f"{limites.MAX_CONEXOES_IP} conexões simultâneas")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
