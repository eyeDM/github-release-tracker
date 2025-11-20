#!/usr/bin/env python3

import sys
import json
import asyncio
from datetime import datetime
from typing import List, Tuple, Optional

import aiohttp
from telegram import Bot

from release_db import init_db, get_seen_releases, save_seen_release

# --- constants ---
RETRY_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 300  # 5 minutes
REQUEST_TIMEOUT = 10
GITHUB_PER_PAGE = 10


# --- config loading ---
if len(sys.argv) < 2:
    print("Usage: python bot.py <config.json>")
    sys.exit(1)

config_path = sys.argv[1]
with open(config_path, "r") as f:
    config = json.load(f)

BOT_TOKEN = config["BOT_TOKEN"]
CHAT_ID = config["CHAT_ID"]
REPOS = config["REPOS"]


# --- helpers ---
def parse_published_at(s: str) -> str:
    """Normalize timestamp from GitHub into consistent ISO8601."""
    if s.endswith("Z"):
        return s[:-1] + "+00:00"
    return s


async def fetch_releases_for_repo(session: aiohttp.ClientSession, repo: str) -> List[dict]:
    """Single HTTP request to GitHub API."""
    url = f"https://api.github.com/repos/{repo}/releases?per_page={GITHUB_PER_PAGE}"

    async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
        if resp.status >= 500:
            raise aiohttp.ClientResponseError(
                resp.request_info, resp.history,
                status=resp.status, message=f"Server error {resp.status}"
            )
        if resp.status != 200:
            raise ValueError(f"HTTP {resp.status} for repo {repo}")
        return await resp.json()


def newest_non_prerelease(releases: List[dict]) -> Optional[Tuple[str, str, str]]:
    """Find newest non-draft, non-prerelease release."""
    for r in releases:
        if r.get("draft") or r.get("prerelease"):
            continue
        published_at = r.get("published_at")
        if not published_at:
            continue
        name = r.get("tag_name") or r.get("name") or ""
        url = r.get("html_url", "")
        return name, published_at, url
    return None


async def process_repos_once(bot: Bot):
    """
    Process all repos:
    - do up to RETRY_ATTEMPTS per repo
    - sleep between retries
    - update release_db
    - send telegram messages
    - collect problematic repos
    """
    init_db()
    seen = get_seen_releases() or {}
    problematic = []

    timeout_cfg = aiohttp.ClientTimeout(total=None)
    async with aiohttp.ClientSession(timeout=timeout_cfg) as session:

        for repo in REPOS:
            attempt = 0
            last_exc = None

            while attempt < RETRY_ATTEMPTS:
                try:
                    releases = await fetch_releases_for_repo(session, repo)
                    nr = newest_non_prerelease(releases)

                    if nr is None:
                        # no releases
                        break

                    name, published_at, url = nr
                    published_at_norm = parse_published_at(published_at)

                    if seen.get(repo) is None or seen[repo] < published_at_norm:
                        save_seen_release(repo, published_at_norm)
                        seen[repo] = published_at_norm

                        try:
                            ts = datetime.fromisoformat(published_at_norm)
                            human = ts.strftime("%Y-%m-%d %H:%M:%S")
                        except Exception:
                            human = published_at_norm

                        text = (
                            f"<b>{repo}</b>\n"
                            f"Релиз <i>{name}</i>\n"
                            f"Дата публикации: {human}\n"
                            f"{url}"
                        )
                        await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML")

                    break  # success

                except ValueError as ve:
                    last_exc = ve
                    problematic.append((repo, str(ve)))
                    break

                except aiohttp.ClientResponseError as rexc:
                    # retryable only for 5xx
                    if 500 <= rexc.status <= 599:
                        last_exc = rexc
                        attempt += 1
                        if attempt >= RETRY_ATTEMPTS:
                            problematic.append((repo, f"network/server errors after {RETRY_ATTEMPTS} attempts: {rexc}"))
                            break
                        await asyncio.sleep(RETRY_DELAY_SECONDS)
                        continue
                    else:
                        # non-retryable
                        problematic.append((repo, f"HTTP {rexc.status}: {rexc.message}"))
                        break

                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    # network / timeout — retry
                    last_exc = exc
                    attempt += 1
                    if attempt >= RETRY_ATTEMPTS:
                        problematic.append((repo, f"network timeout/error after {RETRY_ATTEMPTS} attempts: {exc}"))
                        break
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                    continue

                except Exception as exc:
                    problematic.append((repo, f"unexpected error: {exc}"))
                    break

    return problematic


async def send_aggregate_problem_report(bot: Bot, problems):
    if not problems:
        return
    lines = ["Не удалось получить данные по следующим репозиториям:"]
    for repo, reason in problems:
        lines.append(f"- {repo}: {reason}")
    text = "\n".join(lines)
    await bot.send_message(chat_id=CHAT_ID, text=text)


async def main():
    bot = Bot(token=BOT_TOKEN)

    problems = await process_repos_once(bot)

    if problems:
        await send_aggregate_problem_report(bot, problems)


if __name__ == "__main__":
    asyncio.run(main())
