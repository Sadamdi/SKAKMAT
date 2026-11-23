FROM python:3.12-slim

# Stockfish dari repo Debian (dipasang di /usr/games/stockfish); opsional tapi disarankan.
RUN apt-get update && apt-get install -y --no-install-recommends stockfish \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py gdss.py mesin.py ./
COPY static ./static

# Basis data SQLite disimpan di volume /data supaya selamat dari penggantian container.
RUN useradd --system --uid 10001 skakmat && mkdir /data && chown skakmat /data
USER skakmat
ENV SKAKMAT_DB=/data/skakmat.db \
    SKAKMAT_STOCKFISH=/usr/games/stockfish \
    SKAKMAT_HOST=0.0.0.0 \
    SKAKMAT_PORT=8000
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/me')" || exit 1
CMD ["python", "app.py"]
