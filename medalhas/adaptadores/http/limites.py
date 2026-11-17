"""Proteção do servidor contra excesso de requisições, por IP.

Três camadas:
  1. Cota por IP e por grupo de rotas (balde de fichas: permite rajadas curtas e recarrega aos poucos,
     mais um teto diário). Quem passa recebe HTTP 429 com Retry-After.
  2. Bloqueio temporário: um IP que continua insistindo depois de bloqueado (muitos 429 seguidos)
     fica suspenso por alguns minutos em todas as rotas.
  3. Conexões: teto de conexões abertas por IP e no total; o excesso é recusado antes de ocupar
     uma thread. Consultas à base também têm teto de simultaneidade.

Os contadores ficam na memória: zeram quando o servidor reinicia.
"""
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

# grupo -> {"quantidade": fichas por janela, "janela": segundos, "por_dia": teto diário ou None}
GRUPOS = {
    "v1": {"quantidade": 60, "janela": 60, "por_dia": 2000},        # API pública
    # downloads de arquivos: a base inteira tem ~7 MB compactada, e 10 GB/mês é a cota grátis do Hosting
    "exportar": {"quantidade": 5, "janela": 3600, "por_dia": 10},
    "site": {"quantidade": 600, "janela": 60, "por_dia": None},      # API usada pelas páginas do site
}

ABUSO_REJEICOES = 30      # recusas (429) dentro de ABUSO_JANELA segundos...
ABUSO_JANELA = 60
ABUSO_BLOQUEIO = 10 * 60  # ...deixam o IP bloqueado por 10 minutos

MAX_CONEXOES = 64         # conexões abertas ao mesmo tempo (todos os IPs)
MAX_CONEXOES_IP = 12      # conexões abertas ao mesmo tempo por IP
MAX_CONSULTAS = 8         # consultas à base rodando ao mesmo tempo
ESPERA_CONSULTA = 10      # segundos esperando vaga antes de responder 503
SEM_LIMITE = 10**9        # cota "infinita" (limite desligado com 0 na linha de comando)
# O teto diário vira à meia-noite de Brasília, não à do servidor (o Cloud Run roda em UTC, que daria 21h).
# Horário fixo: o Brasil não tem horário de verão desde 2019.
BRASILIA = timezone(timedelta(hours=-3))


def _hoje() -> str:
    """Data de hoje em Brasília: muda quando o teto diário volta a zero."""
    return datetime.now(BRASILIA).strftime("%Y-%m-%d")


def _meia_noite() -> float:
    """Instante (time.time) da próxima meia-noite de Brasília, quando o teto diário volta a zero."""
    agora = datetime.now(BRASILIA)
    return (agora + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


class Limitador:
    """Cotas por (grupo de rotas, IP) e bloqueio de quem insiste depois de recusado. Seguro entre threads."""

    def __init__(self):
        self._lock = threading.Lock()
        self._baldes: dict = {}      # (grupo, ip) -> [fichas, instante]
        self._dia: dict = {}         # (grupo, ip) -> [data, usadas]
        self._recusas: dict = {}     # ip -> [instantes das últimas recusas]
        self._bloqueados: dict = {}  # ip -> instante em que o bloqueio acaba
        self._chamadas = 0

    # ------------------------------------------------ bloqueio por abuso
    def bloqueio_restante(self, ip: str) -> int:
        """Segundos de bloqueio que faltam para o IP (0 = livre)."""
        with self._lock:
            fim = self._bloqueados.get(ip)
            if fim is None:
                return 0
            falta = fim - time.monotonic()
            if falta <= 0:
                del self._bloqueados[ip]
                return 0
            return max(1, int(falta))

    def _registrar_recusa(self, ip: str, agora: float) -> None:
        recentes = [t for t in self._recusas.get(ip, []) if agora - t < ABUSO_JANELA] + [agora]
        self._recusas[ip] = recentes
        if len(recentes) >= ABUSO_REJEICOES:
            self._bloqueados[ip] = agora + ABUSO_BLOQUEIO
            self._recusas.pop(ip, None)

    # ------------------------------------------------ cota por grupo
    def consumir(self, grupo: str, ip: str) -> tuple[bool, dict]:
        """Gasta uma ficha. Devolve (permitido, cabeçalhos X-RateLimit-* / Retry-After)."""
        g = GRUPOS[grupo]
        qtd, janela, por_dia = g["quantidade"], g["janela"], g["por_dia"]
        agora, hoje, chave = time.monotonic(), _hoje(), (grupo, ip)
        por = "min" if janela == 60 else "h" if janela == 3600 else f"{janela}s"
        cab = {"X-RateLimit-Limit": f"{qtd}/{por}" + (f", {por_dia}/dia" if por_dia else "")}
        with self._lock:
            self._chamadas += 1
            if self._chamadas % 1000 == 0:
                self._limpar(agora, hoje)
            fichas, antes = self._baldes.get(chave, [qtd, agora])
            fichas = min(qtd, fichas + (agora - antes) * qtd / janela)
            dia = self._dia.get(chave)
            usadas = dia[1] if dia and dia[0] == hoje else 0
            if por_dia and usadas >= por_dia:
                cab.update({"Retry-After": str(max(1, int(_meia_noite() - time.time()))),
                            "X-RateLimit-Remaining": "0", "X-RateLimit-Scope": "dia"})
                self._registrar_recusa(ip, agora)
                return False, cab
            if fichas < 1:
                self._baldes[chave] = [fichas, agora]
                cab.update({"Retry-After": str(max(1, round((1 - fichas) * janela / qtd))),
                            "X-RateLimit-Remaining": "0", "X-RateLimit-Scope": por})
                self._registrar_recusa(ip, agora)
                return False, cab
            self._baldes[chave] = [fichas - 1, agora]
            self._dia[chave] = [hoje, usadas + 1]
            restantes = int(fichas - 1)
            if por_dia:
                restantes = min(restantes, por_dia - usadas - 1)
            cab["X-RateLimit-Remaining"] = str(restantes)
            return True, cab

    def _limpar(self, agora: float, hoje: str) -> None:
        """Esquece IPs inativos para a memória não crescer sem limite."""
        maior_janela = max(g["janela"] for g in GRUPOS.values())
        self._baldes = {k: v for k, v in self._baldes.items() if agora - v[1] < maior_janela}
        self._dia = {k: v for k, v in self._dia.items() if v[0] == hoje}
        self._recusas = {ip: ts for ip, ts in self._recusas.items() if ts and agora - ts[-1] < ABUSO_JANELA}
        self._bloqueados = {ip: fim for ip, fim in self._bloqueados.items() if fim > agora}


class Conexoes:
    """Conta conexões abertas por IP e no total."""

    def __init__(self):
        self._lock = threading.Lock()
        self._por_ip: Counter = Counter()
        self._total = 0

    def entrar(self, ip: str, por_ip: bool = True) -> bool:
        """Registra a conexão se houver vaga. por_ip=False ignora o teto por IP (atrás de proxy)."""
        with self._lock:
            if self._total >= MAX_CONEXOES or (por_ip and self._por_ip[ip] >= MAX_CONEXOES_IP):
                return False
            self._total += 1
            self._por_ip[ip] += 1
            return True

    def sair(self, ip: str) -> None:
        with self._lock:
            self._total -= 1
            self._por_ip[ip] -= 1
            if self._por_ip[ip] <= 0:
                del self._por_ip[ip]


def configurar(api_por_minuto: int | None = None, api_por_dia: int | None = None,
               exportacoes_por_hora: int | None = None, site_por_minuto: int | None = None,
               consultas_simultaneas: int | None = None, conexoes_por_ip: int | None = None) -> None:
    """Ajusta os limites (None mantém o padrão; 0 remove o limite de cota)."""
    global MAX_CONSULTAS, MAX_CONEXOES_IP, consultas
    for valor, grupo, campo in ((api_por_minuto, "v1", "quantidade"), (api_por_dia, "v1", "por_dia"),
                                (exportacoes_por_hora, "exportar", "quantidade"),
                                (site_por_minuto, "site", "quantidade")):
        if valor is not None:
            GRUPOS[grupo][campo] = valor if valor > 0 else (None if campo == "por_dia" else SEM_LIMITE)
    if consultas_simultaneas:
        MAX_CONSULTAS = consultas_simultaneas
        consultas = threading.BoundedSemaphore(MAX_CONSULTAS)
    if conexoes_por_ip:
        MAX_CONEXOES_IP = conexoes_por_ip


def resumo() -> dict:
    """Limites atuais, para a documentação da API."""
    def fmt(g):
        return {"consultas": g["quantidade"], "a_cada_segundos": g["janela"], "por_dia": g["por_dia"]}
    return {"api_publica": fmt(GRUPOS["v1"]), "exportacao": fmt(GRUPOS["exportar"]),
            "conexoes_simultaneas_por_ip": MAX_CONEXOES_IP,
            "bloqueio_por_abuso": {"recusas": ABUSO_REJEICOES, "em_segundos": ABUSO_JANELA,
                                   "bloqueio_segundos": ABUSO_BLOQUEIO}}


limitador = Limitador()
conexoes = Conexoes()
consultas = threading.BoundedSemaphore(MAX_CONSULTAS)
