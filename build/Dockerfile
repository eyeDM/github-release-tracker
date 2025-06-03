FROM python:3.13-slim

RUN addgroup --gid 1001 --system app && \
    adduser --no-create-home --shell /bin/false --disabled-password --uid 1001 --system --group app

RUN pip install --no-cache-dir requests python-telegram-bot

USER app

WORKDIR /app

CMD ["python", "bot.py", "config.json"]