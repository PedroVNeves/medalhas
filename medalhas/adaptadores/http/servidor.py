"""Servidor HTTP (biblioteca padrão): site estático, API interna do site e API pública v1.

Cada requisição da API segue o mesmo caminho:
    bloqueio por abuso? -> rota -> cota do IP -> vaga de consulta -> sessão de leitura -> resposta
"""
import gzip
import html
import json
import mimetypes
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from ...aplicacao.portas import FonteDeLeitura
from ...config import HOSTS_PUBLICOS, PASTA_WEB, URL_SITE
from ...dominio import pontuacao
from ...dominio.enderecos import ALUNO, ESCOLA
from ...dominio.enderecos import TIPOS as TIPOS_DE_PAGINA
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

# Páginas de erro (web/erro.html) para quem abre um endereço do site; a API responde com JSON
ERROS_DE_PAGINA = {
    429: ("Muitas visitas seguidas", "Recebemos muitas visitas seguidas do seu endereço. Espere alguns segundos e "
                                     "tente de novo."),
    503: ("Servidor ocupado", "O Medalhas está atendendo muita gente agora. Tente de novo em alguns segundos."),
    500: ("Algo deu errado", "Tivemos um problema ao montar esta página. Tente de novo; se continuar, avise."),
}

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")


class Handler(BaseHTTPRequestHandler):
    """Atende uma requisição GET/HEAD/OPTIONS. Para onde vai cada caminho (do_GET):

        /api/v1/…, /api/…            API pública e API interna do site (JSON)
        /og/…                        imagens de compartilhamento (PNG)
        /ranking/…, /sobre…          telas do site com título e resumo próprios (paginas.TELAS)
        /aluno|escola|cidade/{end.}  páginas de perfil
        /sitemap.xml, /sitemaps/…    sitemaps
        qualquer outro               arquivo estático de web/ (404 se não existe)
    """
    server: "Servidor"
    timeout = TEMPO_OCIOSO

    # ------------------------------------------------ respostas
    def _cabecalhos(self, status: int, cabecalhos: dict) -> None:
        """Status e cabeçalhos comuns a toda resposta: sem cache (salvo se pedido), CORS aberto e nosniff."""
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
        """Envia o corpo inteiro, compactado em gzip se for texto acima de COMPACTAR_A_PARTIR e o cliente aceitar.
        Em HEAD, só os cabeçalhos."""
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
        """Envia `dados` como JSON em UTF-8 (acentos sem escape)."""
        self._enviar(json.dumps(dados, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8",
                     status, cabecalhos)

    def _recusar(self, cabecalhos: dict) -> None:
        """429 com a explicação do limite atingido."""
        espera = int(cabecalhos["Retry-After"])
        escopo = cabecalhos.get("X-RateLimit-Scope")
        if escopo == "dia":
            mensagem = "limite diário de consultas atingido; volta a liberar à meia-noite (horário de Brasília)"
        elif escopo == "bloqueio":
            mensagem = f"muitas requisições depois do limite: IP bloqueado por {espera} segundo(s)"
        else:
            mensagem = f"limite de consultas atingido; tente de novo em {espera} segundo(s)"
        self._json({"erro": mensagem, "tente_em_segundos": espera}, 429, cabecalhos)

    def _enviar_download(self, download: api_v1.Download, cabecalhos: dict) -> None:
        """Envia um arquivo de exportação como anexo, com o nº de linhas em X-Total-Rows. Um .gz é enviado
        compactado ou descompactado no caminho, conforme o cliente aceite gzip."""
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
        """IP do cliente: atrás do proxy (confiar_proxy), o de X-Forwarded-For; senão, o da conexão.

        Cada proxy acrescenta à direita o IP de quem falou com ele, e o que vem à esquerda é o que o cliente
        mandou (forjável). Por isso o IP é contado da direita: o último valor com um proxy (saltos_proxy=1), o
        penúltimo com dois. Com menos valores que saltos, vale o primeiro."""
        if self.server.confiar_proxy:
            repassados = ",".join(self.headers.get_all("X-Forwarded-For") or [])
            ips = [ip.strip() for ip in repassados.split(",") if ip.strip()]
            if ips:
                return ips[max(len(ips) - self.server.saltos_proxy, 0)]
        return self.client_address[0]

    def _aceita_gzip(self) -> bool:
        """O cliente aceita resposta compactada (Accept-Encoding: gzip)."""
        return "gzip" in (self.headers.get("Accept-Encoding") or "")

    def _base(self) -> str:
        """URL pública do site, para os links da API. Atrás de um proxy (Firebase Hosting), o Host que chega
        é o do servidor interno (Cloud Run); o domínio que o usuário digitou vem em X-Forwarded-Host.

        O cabeçalho também pode ser forjado por quem chama o servidor direto: só vale se for um dos domínios
        do site (URL_SITE e config.HOSTS_PUBLICOS). Outro valor cai no endereço oficial."""
        if not self.server.confiar_proxy:
            return f"http://{self.headers.get('Host') or 'localhost'}"
        host = (self.headers.get("X-Forwarded-Host") or "").split(",")[0].strip().lower()
        nome = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        aceitos = self.server.hosts_publicos
        if not host or not any(nome == h or (h.startswith(".") and nome.endswith(h)) for h in aceitos):
            return URL_SITE
        protocolo = (self.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
        return f"{protocolo if protocolo in ('http', 'https') else 'https'}://{host}"

    # ------------------------------------------------ API
    def _api(self, caminho: str, params: dict) -> None:
        """Uma requisição de API: rota -> cota do IP (429) -> vaga de consulta (503) -> sessão -> resposta.

        A vaga de consulta é liberada antes do envio. Rotas com cache_cdn saem com Cache-Control público e sem
        os X-RateLimit-* (que valem para um IP só)."""
        if caminho == "/api/v1" or caminho.startswith("/api/v1/"):
            rota = api_v1.rota(caminho)
            if not rota:
                self._json({"erro": f"rota inexistente: {caminho}. Veja as rotas em /api/v1"}, 404)
                return
        elif caminho in ROTAS:
            rota = ROTAS[caminho]
        else:
            self._json({"erro": f"rota inexistente: {caminho}"}, 404)
            return

        ip = self._ip()
        permitido, cabecalhos = limites.limitador.consumir(rota.grupo, ip)
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
        except (api_v1.ParametroInvalido, api_v1.NaoEncontrado):
            limites.limitador.devolver(rota.grupo, ip)   # pedido recusado antes de consultar: não gasta a cota
            raise
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
    def _com_sessao(self, funcao, pagina: bool = False):
        """Roda funcao(sessao) com as mesmas proteções da API do site. None se a consulta foi recusada.

        pagina=True: a recusa vai como página de erro (quem pediu foi uma pessoa abrindo o endereço)."""
        permitido, cabecalhos = limites.limitador.consumir("site", self._ip())
        if not permitido:
            self._pagina_de_erro(429, cabecalhos) if pagina else self._recusar(cabecalhos)
            return None
        if not limites.consultas.acquire(timeout=limites.ESPERA_CONSULTA):
            if pagina:
                self._pagina_de_erro(503, {"Retry-After": "5"})
            else:
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
        """Página de perfil (aluno, escola, cidade): 200, 404, ou 301 para o endereço oficial."""
        pagina = self._com_sessao(lambda s: paginas.perfil(s, tipo, endereco, URL_SITE), pagina=True)
        if pagina is None:
            return
        if pagina.destino:
            self._enviar(b"", "text/plain", 301, {"Location": pagina.destino, **self._CACHE_PAGINA})
        else:
            self._enviar(pagina.corpo, "text/html; charset=utf-8", pagina.status,
                         self._CACHE_PAGINA if pagina.status == 200 else None)

    def _tela(self, caminho: str) -> None:
        """Tela do site com endereço próprio (ranking, estados, dados, sobre…); /ranking redireciona para
        /ranking/alunos."""
        pagina = self._com_sessao(lambda s: paginas.tela(s, caminho, URL_SITE), pagina=True)
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

    def _pagina_de_erro(self, status: int, cabecalhos: dict | None = None) -> None:
        """web/erro.html preenchida com o código, o título e a mensagem do erro (ERROS_DE_PAGINA)."""
        titulo, mensagem = ERROS_DE_PAGINA[status]
        corpo = ((PASTA_WEB / "erro.html").read_text(encoding="utf-8")
                 .replace("{{codigo}}", str(status)).replace("{{titulo}}", html.escape(titulo))
                 .replace("{{mensagem}}", html.escape(mensagem)))
        self._enviar(corpo.encode("utf-8"), "text/html; charset=utf-8", status, cabecalhos)

    def _sitemap(self, nome: str) -> None:
        """sitemap.xml ou um dos arquivos de /sitemaps/, montados quando pedidos; 404 se não existe."""
        resultado = self._com_sessao(lambda s: [paginas.sitemap(s, nome, URL_SITE)])
        if resultado is None:   # recusado: a resposta já foi enviada
            return
        if resultado[0] is None:
            self._enviar(b"Not found", "text/plain", 404)
        else:
            self._enviar(resultado[0], "application/xml; charset=utf-8", cabecalhos=self._CACHE_PAGINA)

    # ------------------------------------------------ site estático
    def _arquivo(self, caminho_url: str) -> None:
        """Arquivo estático de web/ (/ é o index.html). Fora de web/, pasta ou erro.html: a página 404."""
        relativo = "index.html" if caminho_url in ("/", "") else unquote(caminho_url.lstrip("/"))
        try:
            alvo = (PASTA_WEB / relativo).resolve()
            existe = alvo.is_file()
        except (ValueError, OSError):   # %00 ou outro caractere que o sistema de arquivos não aceita
            existe = False
        # bloqueia ../, pastas e o modelo das páginas de erro (sem os marcadores preenchidos)
        if not existe or PASTA_WEB.resolve() not in alvo.parents or alvo.name == "erro.html":
            self._nao_encontrado()
            return
        tipo = mimetypes.guess_type(alvo.name)[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo.endswith("javascript"):
            tipo += "; charset=utf-8"
        self._enviar(alvo.read_bytes(), tipo)

    # ------------------------------------------------ métodos HTTP
    def do_OPTIONS(self) -> None:   # preflight de CORS
        """Responde ao preflight de CORS: qualquer origem pode fazer GET e HEAD."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self) -> None:
        """Encaminha pelo caminho (ver a classe) e traduz erros: IP bloqueado -> 429, NaoEncontrado -> 404,
        parâmetro inválido -> 400, bug -> 500 com o traceback no log. A API recebe JSON; quem abriu o endereço
        no navegador recebe uma página de erro."""
        url = urlparse(self.path)
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        caminho = url.path.rstrip("/") or "/"
        eh_api = caminho.startswith("/api/")
        espera = limites.limitador.bloqueio_restante(self._ip())
        if espera:
            cabecalhos = {"Retry-After": str(espera), "X-RateLimit-Scope": "bloqueio"}
            self._recusar(cabecalhos) if eh_api else self._pagina_de_erro(429, cabecalhos)
            return
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
        except api_v1.ParametroInvalido as e:
            self._json({"erro": f"parâmetro inválido: {e}"}, 400)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass   # o cliente desistiu no meio do envio
        except Exception as e:  # noqa: BLE001 — bug do servidor: registra o traceback e responde 500
            if isinstance(e, ValueError) and eh_api and not caminho.startswith("/api/v1"):
                # API do site: conversões como ano=abc (sqlite.filtros.inteiro) chegam como ValueError
                self._json({"erro": f"parâmetro inválido: {e}"}, 400)
                return
            traceback.print_exc()
            if eh_api:
                self._json({"erro": f"erro interno do servidor ({type(e).__name__})"}, 500)
            else:
                self._pagina_de_erro(500)

    do_HEAD = do_GET

    def log_message(self, *args) -> None:   # silencia o log de cada requisição no terminal
        pass


class Servidor(ThreadingHTTPServer):
    """Uma thread por conexão, com teto de conexões (por IP e no total) verificado antes de criar a thread."""
    daemon_threads = True
    request_queue_size = 64

    def __init__(self, endereco: tuple[str, int], leitura: FonteDeLeitura, confiar_proxy: bool = False,
                 saltos_proxy: int = 1):
        self.leitura = leitura
        # atrás de um proxy reverso o IP real vem em X-Forwarded-For; sem proxy, o cabeçalho é forjável
        self.confiar_proxy = confiar_proxy
        # quantos proxies seus há na frente do servidor: o IP do visitante é o N-ésimo de X-Forwarded-For,
        # contado da direita (Handler._ip)
        self.saltos_proxy = max(saltos_proxy, 1)
        # domínios aceitos em X-Forwarded-Host (Handler._base)
        self.hosts_publicos = (URL_SITE.split("://", 1)[-1].lower(), *HOSTS_PUBLICOS)
        super().__init__(endereco, Handler)

    def verify_request(self, request, client_address) -> bool:
        """Aceita a conexão só se houver vaga (limites.conexoes); recusada, ela é fechada sem criar thread."""
        # atrás de um proxy todos chegam com o IP do proxy: aí só vale o teto total
        return limites.conexoes.entrar(client_address[0], por_ip=not self.confiar_proxy)

    def process_request(self, request, client_address) -> None:
        """Se a thread nem chegar a ser criada, devolve aqui a vaga ocupada em verify_request."""
        try:
            super().process_request(request, client_address)
        except Exception:
            limites.conexoes.sair(client_address[0])
            raise

    def process_request_thread(self, request, client_address) -> None:
        """Atende a conexão na thread e devolve a vaga ao terminar, mesmo com erro."""
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
