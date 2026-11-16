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


def _baixar(url: str, extensao: str) -> bytes | None:
    """Conteúdo bruto da URL, ou None se a página não existe (404).

    Cada endereço é baixado uma vez e guardado em PASTA_CACHE (apague a pasta, ou rode build_db.py --refresh,
    para baixar de novo). Falhas de rede (DNS, timeout, 5xx) são tentadas de novo com espera crescente:
    2, 4, 8, 16 s.
    """
    PASTA_CACHE.mkdir(exist_ok=True)
    arquivo = PASTA_CACHE / f"{hashlib.sha1(url.encode()).hexdigest()[:16]}.{extensao}"
    if arquivo.exists():
        return arquivo.read_bytes()
    for tentativa in range(TENTATIVAS):
        try:
            pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE})
            with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
                bruto = resposta.read()
            arquivo.write_bytes(bruto)
            time.sleep(PAUSA_ENTRE_DOWNLOADS)
            return bruto
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


def baixar(url: str) -> str | None:
    """Página como texto (UTF-8; páginas antigas em Latin-1/Windows-1252), ou None se não existe."""
    bruto = _baixar(url, "html")
    if bruto is None:
        return None
    try:
        return bruto.decode("utf-8")
    except UnicodeDecodeError:
        return bruto.decode("cp1252", errors="replace")


def baixar_bytes(url: str) -> bytes | None:
    """Arquivo sem decodificar (PDFs), ou None se não existe. Cache com extensão .bin."""
    return _baixar(url, "bin")
