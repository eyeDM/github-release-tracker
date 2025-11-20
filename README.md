# GitHub Release Tracker Bot

Telegram-бот, отслеживающий выход новых релизов на GitHub в указанных репозиториях и отправляющий уведомления в чат.

## Возможности

- Отправка сообщений в Telegram.
- Поддержка нескольких репозиториев GitHub.
- Отсеивание черновых и предрелизных версий.
- Хранение состояния в SQLite — бот не присылает одни и те же релизы повторно.
- Лёгкий деплой через Docker Compose.

## Установка

### 1. Получение исходного кода

```console
git clone <репозиторий>
cd github-release-tracker
```

### 2. Подготовка к запуску

Создайте файл `.env` на основе `.env.example`. Если нужно, измените к нём значения по умолчанию:
```
IMAGE_VERSION="25.11.21" # версия создаваемого Docker-образа
PYTHON_VERSION="3.13" # используемая версия Python
UID=10001 # UID пользователя, от имени которого будет выполняться python-код
```

Создайте файл `app/config.json` на основе `app/config.json.example`:
```json
{
  "BOT_TOKEN": "your_bot_token",
  "CHAT_ID": "your_chat_id",
  "REPOS": [
    "owner1/repo1",
    "owner2/repo2"
  ]
}
```

* `BOT_TOKEN` — токен вашего бота, полученный от @BotFather.
* `CHAT_ID` — идентификатор tg-чата, в который будут отправляться уведомления. Если это личный чат, нужно начать диалог с ботом.
* `REPOS` — список опрашиваемых репозиториев.

Директория `./storage` должна быть доступна на запись пользователю, который был указан в файле `.env`:
```console
chown 10001:10001 ./storage
```

### 3. Запуск контейнера

```console
docker compose up --build --abort-on-container-exit
```
В случае отсутствия ошибок вывод команды `docker compose logs` будет пустым.

## Структура проекта

* `app/bot.py` — основной код бота.
* `app/release_db.py` — работа с SQLite.
* `app/config.json.example` — пример конфигурации.
* `build/Dockerfile` — сценарий сборки Docker-образа.
* `docker-compose.yml` — конфигурационный файл для Docker Compose.
* `systemd/github-tracker.service` — пример systemd-юнита, запускающего контейнер.
* `systemd/github-tracker.timer` — пример systemd-таймера для запуска контейнера по расписанию.

## Хранение данных

Информация о последних обработанных релизах хранится в SQLite-файле `./storage/releases.db`. Внутрь Docker-контейнера этот файл монтируется как `/var/lib/app/releases.db`.

## Лицензия

MIT License — свободно используйте и дорабатывайте под свои задачи.
