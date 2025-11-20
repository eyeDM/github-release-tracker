ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

# Create a non-privileged user that the app will run under.
# See https://docs.docker.com/go/dockerfile-user-best-practices/
ARG UID=10001
RUN adduser \
        --disabled-password \
        --shell /bin/false \
        --gecos "" \
        --home "/nonexistent" \
        --no-create-home \
        --uid ${UID} \
        appuser

# Install system packages needed for aiohttp
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir aiohttp python-telegram-bot

# Application
USER appuser

WORKDIR /app

CMD ["python3", "bot.py", "config.json"]