"""Utilitários compartilhados: download com cache e parsing simples de tabelas HTML."""
import hashlib
import html
import re
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache"
USER_AGENT = "Mozilla/5.0 (medalhas-scraper)"


def fetch(url: str, retries: int = 5, delay: float = 0.5) -> str | None:
    """Baixa uma URL (com cache em disco). Retorna None se 404.

    Falhas de rede (DNS, timeout, 5xx) são tentadas de novo com espera crescente (2, 4, 8, 16 s)."""
    CACHE_DIR.mkdir(exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    path = CACHE_DIR / f"{key}.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:  # páginas antigas em Latin-1/Windows-1252
                text = raw.decode("cp1252", errors="replace")
            path.write_text(text, encoding="utf-8")
            time.sleep(delay)  # gentileza com o servidor
            return text
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == retries - 1:
                raise
        time.sleep(2 ** (attempt + 1))
    return None


def clean(fragment: str) -> str:
    """Remove tags, decodifica entidades e normaliza espaços."""
    text = re.sub(r"<[^>]+>", " ", fragment)
    text = html.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def normalize(text: str) -> str:
    """Versão para busca: sem acentos, maiúscula, só letras/números/espaço."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9 ]+", " ", text).upper()
    return re.sub(r"\s+", " ", text).strip()


def title_case(name: str) -> str:
    """'JOÃO DA SILVA' -> 'João da Silva'."""
    small = {"da", "de", "do", "das", "dos", "e", "di", "du", "del", "van", "von"}
    words = name.lower().split()
    return " ".join(w if (i and w in small) else w[:1].upper() + w[1:] for i, w in enumerate(words))
