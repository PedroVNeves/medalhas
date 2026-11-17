"""Download das páginas oficiais, com cache em disco e novas tentativas em falhas de rede."""
import hashlib
import time
import urllib.error
import urllib.request
from collections.abc import Callable

from ...config import PASTA_CACHE

AGENTE = "Mozilla/5.0 (medalhas-scraper)"
TENTATIVAS = 5
PAUSA_ENTRE_DOWNLOADS = 0.5   # segundos: gentileza com os servidores das olimpíadas
TEMPO_LIMITE = 60


class RespostaInesperada(RuntimeError):
    """O servidor respondeu 200, mas sem o conteúdo esperado (página de manutenção, de erro ou de bloqueio)."""


def _baixar(url: str, extensao: str, valida: Callable[[bytes], bool] | None = None) -> bytes | None:
    """Conteúdo bruto da URL, ou None se a página não existe (404).

    valida: confere o conteúdo antes de guardá-lo. Uma resposta reprovada não entra no cache (e a que já
    estiver nele é apagada e baixada de novo) e levanta RespostaInesperada: uma página de manutenção não pode
    ficar guardada como se fosse a lista oficial até o próximo --refresh.

    Cada endereço é baixado uma vez e guardado em PASTA_CACHE (apague a pasta, ou rode build_db.py --refresh,
    para baixar de novo). Falhas de rede (DNS, timeout, 5xx) são tentadas de novo com espera crescente:
    2, 4, 8, 16 s.
    """
    PASTA_CACHE.mkdir(exist_ok=True)
    arquivo = PASTA_CACHE / f"{hashlib.sha1(url.encode()).hexdigest()[:16]}.{extensao}"
    if arquivo.exists():
        guardado = arquivo.read_bytes()
        if valida is None or valida(guardado):
            return guardado
        arquivo.unlink()   # cache de uma resposta ruim: baixa de novo
    for tentativa in range(TENTATIVAS):
        try:
            pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE})
            with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
                bruto = resposta.read()
            if valida is not None and not valida(bruto):
                raise RespostaInesperada(f"{url}: a resposta não tem o conteúdo esperado")
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


def baixar(url: str, esperado: str | None = None) -> str | None:
    """Página como texto (UTF-8; páginas antigas em Latin-1/Windows-1252), ou None se não existe.

    esperado: trecho que a página precisa ter (use nos índices, de onde saem os endereços das listas); sem
    ele, levanta RespostaInesperada e nada é guardado."""
    bruto = _baixar(url, "html", (lambda b: esperado.encode() in b) if esperado else None)
    if bruto is None:
        return None
    try:
        return bruto.decode("utf-8")
    except UnicodeDecodeError:
        return bruto.decode("cp1252", errors="replace")


def baixar_bytes(url: str) -> bytes | None:
    """PDF sem decodificar, ou None se não existe. Cache com extensão .bin. Uma resposta que não é PDF
    (página de erro no lugar do arquivo) levanta RespostaInesperada e não é guardada."""
    return _baixar(url, "bin", lambda b: b.lstrip()[:5] == b"%PDF-")
