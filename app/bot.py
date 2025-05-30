import os
import sys
import json
import requests
import asyncio
from telegram import Bot
from time import sleep
from datetime import datetime
from release_db import init_db, get_seen_releases, save_seen_release

if len(sys.argv) < 2:
    print("Usage: python bot.py <config.json>")
    sys.exit(1)

config_path = sys.argv[1]

with open(config_path, 'r') as f:
    config = json.load(f)

BOT_TOKEN = config['BOT_TOKEN']
CHAT_ID = config['CHAT_ID']
CHECK_TIMEOUT = int(config['CHECK_TIMEOUT'])
REPOS = config['REPOS']

bot = Bot(token=BOT_TOKEN)

def check_releases(seen_releases):
    for repo in REPOS:
        response = requests.get(f'https://api.github.com/repos/{repo}/releases?per_page=10')
        releases = response.json()

        for release in releases:
            if release.get("draft", False) or release.get("prerelease", False):
                continue

            release_date = release["published_at"]
            release_name = release.get("tag_name", release.get("name", ""))
            release_url = release["html_url"]

            if repo not in seen_releases or seen_releases[repo] < release_date:
                yield (repo, release_name, release_date, release_url)
                save_seen_release(repo, release_date)
                seen_releases[repo] = release_date
            break

async def main():
    init_db()
    seen_releases = get_seen_releases()

    while True:
        for message in check_releases(seen_releases):
            repo, name, date, url = message
            notification_text = (
                f'<b>{repo}</b>\n'
                f'Релиз <i>{name}</i>\n'
                f'Дата публикации: {datetime.fromisoformat(date[:-1]).strftime("%Y-%m-%d %H:%M:%S")}\n'
                f'{url}'
            )
            await bot.send_message(chat_id=CHAT_ID, text=notification_text, parse_mode='HTML')

        await asyncio.sleep(CHECK_TIMEOUT)

if __name__ == '__main__':
    asyncio.run(main())
