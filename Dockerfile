# Imagem do servidor para o Cloud Run. A base SQLite vai dentro da imagem (é só leitura):
# para atualizar os dados, rode `python build_db.py` localmente e publique de novo.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY medalhas ./medalhas
COPY web ./web
COPY server.py ./
COPY data/medalhas.db ./data/medalhas.db

# usuário sem privilégios; data/ precisa ser gravável para os arquivos de exportação (data/exportar/)
RUN useradd --create-home app && chown -R app /app/data
USER app

# O Cloud Run informa a porta em $PORT. --trust-proxy: o IP real do visitante chega em X-Forwarded-For.
# --proxy-hops 2: Firebase Hosting + Cloud Run acrescentam um IP cada; o do visitante é o penúltimo. Chamando
# o Cloud Run direto (um salto só), vale o primeiro valor do cabeçalho, como antes.
CMD exec python server.py --host 0.0.0.0 --port ${PORT:-8080} --no-browser --trust-proxy --proxy-hops 2
