"""Servidor HTTP (biblioteca padrão): site estático, API interna do site e API pública v1.

Cada requisição da API segue o mesmo caminho:
    bloqueio por abuso? -> rota -> cota do IP -> vaga de consulta -> sessão de leitura -> resposta
"""
import json
import mimetypes
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from ...aplicacao.portas import FonteDeLeitura
from ...config import PASTA_WEB
from ...dominio import pontuacao
from ...dominio.ranking import ORDENACOES, TIPOS
from . import api_v1, limites
from .pedido import Pedido
from .rotas_site import ROTAS

CABECALHOS_EXPOSTOS = ("X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Scope, Retry-After, "
                       "Content-Disposition, X-Total-Rows")
TEMPO_OCIOSO = 20   # segundos sem enviar/receber dados: derruba conexões lentas de propósito (slowloris)

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")


class Handler(BaseHTTPRequestHandler):
    server: "Servidor"
    timeout = TEMPO_OCIOSO

    # ------------------------------------------------ respostas
    def _cabecalhos(self, status: int, cabecalhos: dict) -> None:
        self.send_response(status)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")   # API pública: pode ser chamada de outros sites
        self.send_header("Access-Control-Expose-Headers", CABECALHOS_EXPOSTOS)
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in cabecalhos.items():
            self.send_header(k, v)
        self.end_headers()

    def _enviar(self, corpo: bytes, tipo: str, status: int = 200, cabecalhos: dict | None = None) -> None:
        self._cabecalhos(status, {"Content-Type": tipo, "Content-Length": str(len(corpo)), **(cabecalhos or {})})
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _json(self, dados, status: int = 200, cabecalhos: dict | None = None) -> None:
        self._enviar(json.dumps(dados, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8",
                     status, cabecalhos)

    def _recusar(self, cabecalhos: dict) -> None:
        """429 com a explicação do limite atingido."""
        espera = int(cabecalhos["Retry-After"])
        escopo = cabecalhos.get("X-RateLimit-Scope")
        if escopo == "dia":
            mensagem = "limite diário de consultas atingido; volta a liberar à meia-noite"
        elif escopo == "bloqueio":
            mensagem = f"muitas requisições depois do limite: IP bloqueado por {espera} segundo(s)"
        else:
            mensagem = f"limite de consultas atingido; tente de novo em {espera} segundo(s)"
        self._json({"erro": mensagem, "tente_em_segundos": espera}, 429, cabecalhos)

    def _enviar_download(self, download: api_v1.Download, cabecalhos: dict) -> None:
        compactado = download.gzipado and self._aceita_gzip()
        cab = {"Content-Type": download.tipo, "X-Total-Rows": str(download.linhas),
               "Content-Disposition": f'attachment; filename="{download.nome}"', **cabecalhos}
        if compactado:   # sem gzip o tamanho final só se sabe descompactando: vai sem Content-Length
            cab["Content-Encoding"] = "gzip"
            cab["Content-Length"] = str(download.tamanho())
        self._cabecalhos(200, cab)
        if self.command != "HEAD":
            download.enviar(self.wfile, compactado)

    # ------------------------------------------------ dados do cliente
    def _ip(self) -> str:
        if self.server.confiar_proxy and self.headers.get("X-Forwarded-For"):
            return self.headers["X-Forwarded-For"].split(",")[0].strip()
        return self.client_address[0]

    def _aceita_gzip(self) -> bool:
        return "gzip" in (self.headers.get("Accept-Encoding") or "")

    def _base(self) -> str:
        protocolo = (self.headers.get("X-Forwarded-Proto") if self.server.confiar_proxy else None) or "http"
        return f"{protocolo}://{self.headers.get('Host') or 'localhost'}"

    # ------------------------------------------------ API
    def _api(self, caminho: str, params: dict) -> None:
        if caminho.startswith("/api/v1"):
            rota = api_v1.rota(caminho)
            if not rota:
                self._json({"erro": f"rota inexistente: {caminho}. Veja as rotas em /api/v1"}, 404)
                return
        elif caminho in ROTAS:
            rota = ROTAS[caminho]
        else:
            self._json({"erro": f"rota inexistente: {caminho}"}, 404)
            return

        permitido, cabecalhos = limites.limitador.consumir(rota.grupo, self._ip())
        if not permitido:
            self._recusar(cabecalhos)
            return
        if not limites.consultas.acquire(timeout=limites.ESPERA_CONSULTA):
            self._json({"erro": "servidor ocupado; tente de novo em instantes", "tente_em_segundos": 5}, 503,
                       {"Retry-After": "5"})
            return
        leitura = self.server.leitura
        try:
            pedido = Pedido(params, self._base(), self._aceita_gzip(), leitura.versao())
            with leitura.sessao() as sessao:
                dados = rota.funcao(sessao, pedido)
        finally:
            limites.consultas.release()   # o envio acontece depois, sem ocupar vaga de consulta

        if isinstance(dados, api_v1.Download):
            self._enviar_download(dados, cabecalhos)
        else:
            self._json(dados, cabecalhos=cabecalhos)

    # ------------------------------------------------ site estático
    def _arquivo(self, caminho_url: str) -> None:
        relativo = "index.html" if caminho_url in ("/", "") else unquote(caminho_url.lstrip("/"))
        alvo = (PASTA_WEB / relativo).resolve()
        if PASTA_WEB.resolve() not in alvo.parents or not alvo.is_file():   # bloqueia ../ e pastas
            self._enviar(b"Not found", "text/plain", 404)
            return
        tipo = mimetypes.guess_type(alvo.name)[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo.endswith("javascript"):
            tipo += "; charset=utf-8"
        self._enviar(alvo.read_bytes(), tipo)

    # ------------------------------------------------ métodos HTTP
    def do_OPTIONS(self) -> None:   # preflight de CORS
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self) -> None:
        espera = limites.limitador.bloqueio_restante(self._ip())
        if espera:
            self._recusar({"Retry-After": str(espera), "X-RateLimit-Scope": "bloqueio"})
            return
        url = urlparse(self.path)
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        caminho = url.path.rstrip("/") or "/"
        try:
            if caminho.startswith("/api/"):
                self._api(caminho, params)
            else:
                self._arquivo(url.path)
        except api_v1.NaoEncontrado as e:
            self._json({"erro": str(e)}, 404)
        except ValueError as e:   # ParametroInvalido e conversões como ano=abc na API do site
            self._json({"erro": f"parâmetro inválido: {e}"}, 400)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass   # o cliente desistiu no meio do envio
        except Exception as e:  # noqa: BLE001 — bug do servidor: registra o traceback e responde 500
            traceback.print_exc()
            self._json({"erro": f"erro interno do servidor ({type(e).__name__})"}, 500)

    do_HEAD = do_GET

    def log_message(self, *args) -> None:   # silencia o log de cada requisição no terminal
        pass


class Servidor(ThreadingHTTPServer):
    """Uma thread por conexão, com teto de conexões (por IP e no total) verificado antes de criar a thread."""
    daemon_threads = True
    request_queue_size = 64

    def __init__(self, endereco: tuple[str, int], leitura: FonteDeLeitura, confiar_proxy: bool = False):
        self.leitura = leitura
        # atrás de um proxy reverso o IP real vem em X-Forwarded-For; sem proxy, o cabeçalho é forjável
        self.confiar_proxy = confiar_proxy
        super().__init__(endereco, Handler)

    def verify_request(self, request, client_address) -> bool:
        # atrás de um proxy todos chegam com o IP do proxy: aí só vale o teto total
        return limites.conexoes.entrar(client_address[0], por_ip=not self.confiar_proxy)

    def process_request(self, request, client_address) -> None:
        try:
            super().process_request(request, client_address)
        except Exception:
            limites.conexoes.sair(client_address[0])
            raise

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            limites.conexoes.sair(client_address[0])


def aquecer(leitura: FonteDeLeitura) -> None:
    """Pré-calcula as consultas pesadas para a primeira visita ser instantânea."""
    with leitura.sessao() as s:
        for metodo in pontuacao.METODOS:
            s.visao_geral({"metodo": metodo})
            for tipo in TIPOS:
                for ordem in ORDENACOES:
                    s.ranking({"tipo": tipo, "ordem": ordem, "metodo": metodo})
