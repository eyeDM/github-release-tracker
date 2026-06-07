#!/usr/bin/env python3

import sys
import json
import asyncio
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any
import re
import html

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

# Normalize repo config entries into dicts: {"repo": str, "asset_regex": Optional[Pattern]}
REPO_CONFIGS: List[Dict[str, Any]] = []
for entry in REPOS:
    if isinstance(entry, str):
        REPO_CONFIGS.append({"repo": entry, "asset_regex": None, "asset_regex_raw": None})
    elif isinstance(entry, dict):
        repo_name = entry.get("repo")
        raw = entry.get("asset_regex")
        if not repo_name:
            print(f"Skipping invalid REPO entry (missing 'repo'): {entry}")
            continue
        compiled = None
        if raw:
            try:
                compiled = re.compile(raw)
            except re.error as rexc:
                print(f"Invalid asset_regex for {repo_name}: {rexc}; ignoring regex")
                compiled = None
        REPO_CONFIGS.append({"repo": repo_name, "asset_regex": compiled, "asset_regex_raw": raw})
    else:
        print(f"Ignoring REPOS entry of unsupported type: {entry}")



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


def newest_non_prerelease(releases: List[dict]) -> Optional[Tuple[str, str, str, dict]]:
    """Find newest non-draft, non-prerelease release and return release dict."""
    for r in releases:
        if r.get("draft") or r.get("prerelease"):
            continue
        published_at = r.get("published_at")
        if not published_at:
            continue
        name = r.get("tag_name") or r.get("name") or ""
        url = r.get("html_url", "")
        return name, published_at, url, r
    return None


def select_asset(assets: List[dict], regex: Optional[re.Pattern]) -> Tuple[Optional[str], Optional[str]]:
    """Select an asset matching compiled `regex` (first match). Returns (name, browser_download_url) or (None, None)."""
    if not regex or not assets:
        return None, None
    for a in assets:
        name = a.get("name")
        url = a.get("browser_download_url")
        if not name or not url:
            continue
        try:
            if regex.search(name):
                return name, url
        except re.error:
            # Shouldn't happen because regexes are compiled at startup, but guard anyway
            continue
    return None, None


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

        for entry in REPO_CONFIGS:
            repo = entry["repo"]
            asset_regex = entry.get("asset_regex")
            attempt = 0
            last_exc = None

            while attempt < RETRY_ATTEMPTS:
                try:
                    releases = await fetch_releases_for_repo(session, repo)
                    nr = newest_non_prerelease(releases)

                    if nr is None:
                        # no releases
                        break

                    name, published_at, url, release_obj = nr
                    asset_name, asset_url = select_asset(release_obj.get("assets", []), asset_regex)
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
                            f"Release <i>{name}</i>\n"
                            f"Published at {human}\n"
                            f"{url}"
                        )
                        if asset_url:
                            link = html.escape(asset_url, quote=True)
                            display = html.escape(asset_name or asset_url)
                            text = text + f"\nDownload: <a href=\"{link}\">{display}</a>"
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
    lines = ["Failed to retrieve data for the following repositories:"]
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
