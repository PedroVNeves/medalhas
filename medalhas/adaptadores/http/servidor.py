"""Servidor HTTP (biblioteca padrão): site estático, API interna do site e API pública v1.

Cada requisição da API segue o mesmo caminho:
    bloqueio por abuso? -> rota -> cota do IP -> vaga de consulta -> sessão de leitura -> resposta
"""
import gzip
import json
import mimetypes
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from ...aplicacao.portas import FonteDeLeitura
from ...config import PASTA_WEB, URL_SITE
from ...dominio.enderecos import ALUNO, ESCOLA, TIPOS as TIPOS_DE_PAGINA
from ...dominio import pontuacao
from ...dominio.ranking import ORDENACOES, TIPOS
from . import api_v1, imagens, limites, paginas
from .pedido import Pedido
from .rotas_site import ROTAS

CABECALHOS_EXPOSTOS = ("X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Scope, Retry-After, "
                       "Content-Disposition, X-Total-Rows")
TEMPO_OCIOSO = 20   # segundos sem enviar/receber dados: derruba conexões lentas de propósito (slowloris)
COMPACTAR_A_PARTIR = 1024   # bytes; abaixo disso o gzip quase não ganha nada
TIPOS_COMPACTAVEIS = ("application/json", "text/", "application/javascript", "application/xml")
CACHE_NAVEGADOR = 300   # segundos que o navegador reaproveita respostas marcadas com cache_cdn

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")


class Handler(BaseHTTPRequestHandler):
    server: "Servidor"
    timeout = TEMPO_OCIOSO

    # ------------------------------------------------ respostas
    def _cabecalhos(self, status: int, cabecalhos: dict) -> None:
        self.send_response(status)
        if "Cache-Control" not in cabecalhos:
            self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")   # API pública: pode ser chamada de outros sites
        self.send_header("Access-Control-Expose-Headers", CABECALHOS_EXPOSTOS)
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in cabecalhos.items():
            self.send_header(k, v)
        self.end_headers()

    def _enviar(self, corpo: bytes, tipo: str, status: int = 200, cabecalhos: dict | None = None) -> None:
        cab = {"Content-Type": tipo, **(cabecalhos or {})}
        # JSON e texto compactam ~85% (a visão geral cai de 67 KB para 10 KB): menos espera no celular e
        # menos transferência na cota do Firebase Hosting
        if len(corpo) >= COMPACTAR_A_PARTIR and tipo.startswith(TIPOS_COMPACTAVEIS):
            cab["Vary"] = "Accept-Encoding"
            if self._aceita_gzip():
                corpo = gzip.compress(corpo, compresslevel=6, mtime=0)
                cab["Content-Encoding"] = "gzip"
        cab["Content-Length"] = str(len(corpo))
        self._cabecalhos(status, cab)
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
        """URL pública do site, para os links da API. Atrás de um proxy (Firebase Hosting), o Host que chega
        é o do servidor interno (Cloud Run); o domínio que o usuário digitou vem em X-Forwarded-Host."""
        def repassado(nome: str) -> str | None:
            valor = self.headers.get(nome) if self.server.confiar_proxy else None
            return valor.split(",")[0].strip() if valor else None
        protocolo = repassado("X-Forwarded-Proto") or "http"
        host = repassado("X-Forwarded-Host") or self.headers.get("Host") or "localhost"
        return f"{protocolo}://{host}"

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
        elif rota.cache_cdn:
            # resposta igual para todos até a próxima publicação: o CDN do Firebase Hosting guarda a cópia
            # (e a apaga a cada `firebase deploy`). Sem os X-RateLimit-*, que são de um IP só.
            self._json(dados, cabecalhos={"Cache-Control": f"public, max-age={CACHE_NAVEGADOR}, "
                                                           f"s-maxage={rota.cache_cdn}"})
        else:
            self._json(dados, cabecalhos=cabecalhos)

    # ------------------------------------------------ páginas de aluno/escola, telas do site e sitemap
    def _com_sessao(self, funcao):
        """Roda funcao(sessao) com as mesmas proteções da API do site. None se a consulta foi recusada."""
        permitido, cabecalhos = limites.limitador.consumir("site", self._ip())
        if not permitido:
            self._recusar(cabecalhos)
            return None
        if not limites.consultas.acquire(timeout=limites.ESPERA_CONSULTA):
            self._enviar(b"Servidor ocupado; tente de novo em instantes", "text/plain; charset=utf-8", 503,
                         {"Retry-After": "5"})
            return None
        try:
            with self.server.leitura.sessao() as sessao:
                return funcao(sessao)
        finally:
            limites.consultas.release()

    # como /api/overview: só muda com a base, então o CDN do Firebase guarda (e cada deploy limpa)
    _CACHE_PAGINA = {"Cache-Control": f"public, max-age={CACHE_NAVEGADOR}, s-maxage=86400"}

    def _pagina(self, tipo: str, endereco: str) -> None:
        pagina = self._com_sessao(lambda s: paginas.perfil(s, tipo, endereco, URL_SITE))
        if pagina is None:
            return
        if pagina.destino:
            self._enviar(b"", "text/plain", 301, {"Location": pagina.destino, **self._CACHE_PAGINA})
        else:
            self._enviar(pagina.corpo, "text/html; charset=utf-8", pagina.status,
                         self._CACHE_PAGINA if pagina.status == 200 else None)

    def _tela(self, caminho: str) -> None:
        pagina = self._com_sessao(lambda s: paginas.tela(s, caminho, URL_SITE))
        if pagina is None:
            return
        if pagina.destino:
            self._enviar(b"", "text/plain", 301, {"Location": pagina.destino, **self._CACHE_PAGINA})
        else:
            self._enviar(pagina.corpo, "text/html; charset=utf-8", cabecalhos=self._CACHE_PAGINA)

    def _imagem(self, partes: list[str]) -> None:
        """/og/site.png, /og/{aluno|escola}/{endereço}.png (cartão do link) e /og/story/{aluno|escola}/{endereço}.png
        (story do Instagram)."""
        if not imagens.DISPONIVEL:   # Pillow não instalado (só no computador; a imagem do Docker tem)
            self._nao_encontrado()
            return

        def desenhar(sessao):
            if partes == ["og", "site.png"]:
                return imagens.site(sessao.visao_geral({}))
            story = len(partes) == 4 and partes[1] == "story"   # /og/story/aluno/x.png: vertical, para o Instagram
            tipo, arquivo = partes[-2:] if story or len(partes) == 3 else (None, "")
            if tipo not in (ALUNO, ESCOLA) or not arquivo.endswith(".png"):   # cidades usam a imagem do site
                return None
            achado = sessao.enderecos().resolver(tipo, unquote(arquivo[:-4]))
            if not achado:
                return None
            if tipo == ALUNO:
                dados = sessao.perfil_aluno(achado[0], {})
                return imagens.story_aluno(dados) if story else imagens.aluno(dados)
            dados = sessao.perfil_escola(achado[0], {})
            return imagens.story_escola(dados) if story else imagens.escola(dados)

        resultado = self._com_sessao(lambda s: [desenhar(s)])
        if resultado is None:   # recusado: a resposta já foi enviada
            return
        if resultado[0] is None:
            self._nao_encontrado()
        else:
            self._enviar(resultado[0], "image/png", cabecalhos=self._CACHE_PAGINA)

    def _nao_encontrado(self) -> None:
        """A mesma página 404 que o Firebase Hosting mostra para endereços que não existem."""
        self._enviar((PASTA_WEB / "404.html").read_bytes(), "text/html; charset=utf-8", 404)

    def _sitemap(self, nome: str) -> None:
        versao = self.server.leitura.versao()
        resultado = self._com_sessao(lambda s: [paginas.sitemap(s, nome, URL_SITE, versao)])
        if resultado is None:   # recusado: a resposta já foi enviada
            return
        if resultado[0] is None:
            self._enviar(b"Not found", "text/plain", 404)
        else:
            self._enviar(resultado[0], "application/xml; charset=utf-8", cabecalhos=self._CACHE_PAGINA)

    # ------------------------------------------------ site estático
    def _arquivo(self, caminho_url: str) -> None:
        relativo = "index.html" if caminho_url in ("/", "") else unquote(caminho_url.lstrip("/"))
        alvo = (PASTA_WEB / relativo).resolve()
        if PASTA_WEB.resolve() not in alvo.parents or not alvo.is_file():   # bloqueia ../ e pastas
            self._nao_encontrado()
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
            partes = caminho.strip("/").split("/")
            if caminho.startswith("/api/"):
                self._api(caminho, params)
            elif partes[0] == "og":
                self._imagem(partes)
            elif caminho in paginas.TELAS or caminho == "/ranking":
                self._tela(caminho)
            elif len(partes) == 2 and partes[0] in TIPOS_DE_PAGINA:
                self._pagina(partes[0], unquote(partes[1]))
            elif caminho == "/sitemap.xml" or (len(partes) == 2 and partes[0] == "sitemaps"):
                self._sitemap(caminho.lstrip("/"))
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
        s.enderecos()
        s.sugestoes({"q": "aquecer"})   # monta o índice das sugestões da busca
        for metodo in pontuacao.METODOS:
            s.visao_geral({"metodo": metodo})
            for tipo in TIPOS:
                for ordem in ORDENACOES:
                    s.ranking({"tipo": tipo, "ordem": ordem, "metodo": metodo})
