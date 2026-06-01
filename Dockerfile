# syntax=docker/dockerfile:1

# --- Synthea Django/Channels backend ---
# Served with Daphne (ASGI) so both HTTP REST and the websocket consumers work.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=core.settings

WORKDIR /app

# Minimal build/runtime libs. Most wheels are prebuilt, but a few packages
# (cffi/cryptography fallbacks, etc.) may need a compiler + libffi headers.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        curl \
        portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better layer caching.
COPY requirements-docker.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements-docker.txt

# --- Voice transcription (WhisperFlow) ---
# The backend imports whisperflow in-process (ide/consumers.py VoiceConsumer),
# so it runs as part of THIS image rather than a separate service. Fetched
# directly from PyPI. CPU-only torch keeps the image off the multi-GB CUDA
# wheels. Toggle off with `--build-arg INCLUDE_VOICE=false` for a lean build.
ARG INCLUDE_VOICE=true
RUN if [ "$INCLUDE_VOICE" = "true" ]; then \
        pip install --index-url https://download.pytorch.org/whl/cpu torch \
        && pip install openai-whisper pyaudio ; \
    fi

# App source.
COPY . .

# Entrypoint applies DB migrations then launches Daphne.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "core.asgi:application"]
