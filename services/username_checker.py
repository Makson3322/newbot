"""
Проверка юзернеймов:
  1. Telegram Bot API — bot.get_chat (каналы/группы/боты)
  2. t.me парсинг    — личные аккаунты (через прокси)
  3. Fragment        — python-fragment (через прокси, ротация)

Прокси берутся из PROXIES в .env, ротируются по кругу.
"""

import asyncio
import logging
import os
import random
import aiohttp
import fragment as frag
from fragment.errors import ParserError, FragmentHTTPError
from aiohttp_socks import ProxyConnector
from typing import Tuple, Optional, Dict, List
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from time import time

logger = logging.getLogger(__name__)

BATCH_SIZE = 8  # с прокси можно больше

# Семафор: не более 4 одновременных запросов к Fragment
_fragment_sem = asyncio.Semaphore(4)

# Прокси используем ТОЛЬКО для Fragment

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

TME_OCCUPIED = [
    "tgme_page_title",
    "tgme_page_photo",
    "tgme_page_extra",
    "view in telegram",
    "join channel",
    "join group",
]

# Загружаем список прокси из .env
def _load_proxies() -> List[str]:
    raw = os.getenv("PROXIES", "")
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]

_PROXIES = _load_proxies()
_proxy_idx = 0

def _next_proxy() -> Optional[str]:
    """Возвращает следующий прокси по кругу."""
    global _proxy_idx
    if not _PROXIES:
        return None
    proxy = _PROXIES[_proxy_idx % len(_PROXIES)]
    _proxy_idx += 1
    return proxy


class UsernameChecker:

    def __init__(self, bot: Bot):
        self.bot = bot
        self._cache: Dict[str, Tuple[bool, float]] = {}
        self._cache_ttl = 300

    async def close(self):
        pass  # сессии создаются per-request

    def _from_cache(self, username: str) -> Optional[bool]:
        entry = self._cache.get(username)
        if entry and (time() - entry[1]) < self._cache_ttl:
            return entry[0]
        return None

    def _to_cache(self, username: str, available: bool):
        self._cache[username] = (available, time())

    # ------------------------------------------------------------------ #
    #  1. Telegram Bot API                                                 #
    # ------------------------------------------------------------------ #

    async def _check_bot_api(self, username: str) -> Optional[bool]:
        """
        True  → явно свободен (chat not found)
        False → занят (чат найден)
        None  → личный аккаунт, нужна проверка t.me
        """
        try:
            await self.bot.get_chat(f"@{username}")
            return False
        except TelegramBadRequest as e:
            err = str(e).lower()
            if any(x in err for x in (
                "chat not found", "not found",
                "username is not occupied", "peer_id_invalid",
                "username invalid",
            )):
                return None
            return False
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    #  2. t.me — без прокси                                               #
    # ------------------------------------------------------------------ #

    async def _check_tme(self, username: str) -> bool:
        """True → свободен, False → занят или ошибка."""
        try:
            async with aiohttp.ClientSession(
                headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as session:
                async with session.get(
                    f"https://t.me/{username.lower()}",
                    allow_redirects=True,
                ) as resp:
                    if resp.status != 200:
                        return False
                    chunk = await resp.content.read(32768)
                    html = chunk.decode("utf-8", errors="ignore").lower()
                    for marker in TME_OCCUPIED:
                        if marker in html:
                            return False
                    if "sorry, this username is not available" in html:
                        return False
                    return True
        except Exception as e:
            logger.debug(f"t.me @{username}: {type(e).__name__}")
            return False

    # ------------------------------------------------------------------ #
    #  3. Fragment — через прокси                                         #
    # ------------------------------------------------------------------ #

    async def _check_fragment(self, username: str) -> bool:
        """
        sold / auction / available → продаётся → False
        taken / ParserError / ошибка → доверяем TG → True
        """
        async with _fragment_sem:
            proxy = _next_proxy()
            try:
                async with frag.AsyncClient(proxy=proxy) as client:
                    info = await client.username_info(username.lower())
                    status = info.get("status", "")
                    logger.debug(f"Fragment @{username}: {status!r} proxy={proxy}")

                    if status in ("sold", "auction", "available"):
                        return False
                    return True

            except ParserError:
                logger.debug(f"Fragment @{username}: не найден → ок")
                return True
            except FragmentHTTPError as e:
                logger.debug(f"Fragment @{username}: HTTP {e}")
                return True
            except Exception as e:
                logger.debug(f"Fragment @{username}: {type(e).__name__}: {e}")
                return True

    # ------------------------------------------------------------------ #
    #  Основная проверка                                                   #
    # ------------------------------------------------------------------ #

    async def check_username(self, username: str) -> Tuple[bool, str]:
        cached = self._from_cache(username)
        if cached is not None:
            return cached, ("Свободен" if cached else "Занят (кэш)")

        # Шаг 1: Bot API
        api_result = await self._check_bot_api(username)
        if api_result is False:
            self._to_cache(username, False)
            return False, "Занят в Telegram"

        # Шаг 2: t.me + Fragment параллельно
        tme_result, fr_result = await asyncio.gather(
            self._check_tme(username),
            self._check_fragment(username),
            return_exceptions=True,
        )

        if isinstance(tme_result, BaseException):
            tme_result = True
        if isinstance(fr_result, BaseException):
            fr_result = True

        if not tme_result:
            self._to_cache(username, False)
            return False, "Занят в Telegram"

        if not fr_result:
            self._to_cache(username, False)
            return False, "Продаётся на Fragment"

        self._to_cache(username, True)
        return True, "Свободен"

    async def check_username_safe(self, username: str) -> Tuple[bool, str]:
        try:
            result = await self.check_username(username)
            logger.info(f"CHECK @{username} → {result[1]}")
            return result
        except Exception as e:
            logger.error(f"Критическая ошибка @{username}: {e}")
            return False, "Ошибка проверки"

    # ------------------------------------------------------------------ #
    #  Пачечная проверка                                                   #
    # ------------------------------------------------------------------ #

    async def check_batch(self, usernames: List[str]) -> List[Tuple[str, bool, str]]:
        tasks = [asyncio.create_task(self.check_username_safe(u)) for u in usernames]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        output = []
        for username, result in zip(usernames, results):
            if isinstance(result, BaseException):
                output.append((username, False, "Ошибка"))
            else:
                is_avail, status = result
                output.append((username, is_avail, status))
        return output
