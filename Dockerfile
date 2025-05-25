FROM python:3.13-slim

WORKDIR /app

RUN addgroup --gid 1001 --system app && \
    adduser --no-create-home --shell /bin/false --disabled-password --uid 1001 --system --group app

COPY ./requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

USER app

CMD ["python", "bot.py", "config.json"]