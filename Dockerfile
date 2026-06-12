FROM python:3.12-slim

# ffmpeg: necessario para converter formatos nao-nativos (.m4a, .opus, ...) -> flac
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# A porta vem de $PORT (Render injeta; default 8080 pra rodar local/Fly).
# Forma shell no CMD pra permitir a expansao da variavel.
EXPOSE 8080
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
