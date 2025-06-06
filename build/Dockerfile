FROM python:3.13-slim

ARG UID=1001

RUN addgroup --gid $UID --system app && \
    adduser --no-create-home --shell /bin/false --disabled-password --uid $UID --system --group app

RUN pip install --no-cache-dir requests python-telegram-bot

USER app

WORKDIR /app

CMD ["python", "bot.py", "config.json"]
