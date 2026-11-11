"""Download das páginas oficiais, com cache em disco e novas tentativas em falhas de rede."""
import hashlib
import time
import urllib.error
import urllib.request

from ...config import PASTA_CACHE

AGENTE = "Mozilla/5.0 (medalhas-scraper)"
TENTATIVAS = 5
PAUSA_ENTRE_DOWNLOADS = 0.5   # segundos: gentileza com os servidores das olimpíadas
TEMPO_LIMITE = 60


def baixar(url: str) -> str | None:
    """Conteúdo da URL como texto, ou None se a página não existe (404).

    Cada página é baixada uma vez e guardada em PASTA_CACHE (apague a pasta para baixar de novo).
    Falhas de rede (DNS, timeout, 5xx) são tentadas de novo com espera crescente: 2, 4, 8, 16 s.
    """
    PASTA_CACHE.mkdir(exist_ok=True)
    arquivo = PASTA_CACHE / f"{hashlib.sha1(url.encode()).hexdigest()[:16]}.html"
    if arquivo.exists():
        return arquivo.read_text(encoding="utf-8")
    for tentativa in range(TENTATIVAS):
        try:
            pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE})
            with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
                bruto = resposta.read()
            try:
                texto = bruto.decode("utf-8")
            except UnicodeDecodeError:   # páginas antigas em Latin-1 / Windows-1252
                texto = bruto.decode("cp1252", errors="replace")
            arquivo.write_text(texto, encoding="utf-8")
            time.sleep(PAUSA_ENTRE_DOWNLOADS)
            return texto
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if tentativa == TENTATIVAS - 1:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if tentativa == TENTATIVAS - 1:
                raise
        time.sleep(2 ** (tentativa + 1))
    return None
