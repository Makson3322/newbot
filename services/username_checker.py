"""
Проверка юзернеймов:
  1. Telegram — bot.get_chat(@username): если "chat not found" → свободен в TG
  2. Fragment  — GET https://fragment.com/username/<nick>: ищем маркеры продажи в HTML
"""

import asyncio
import logging
import aiohttp
from typing import Tuple, Optional, Dict, List
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from time import time

logger = logging.getLogger(__name__)

BATCH_SIZE = 8

# Семафор: не более 4 запросов к Fragment одновременно
_fragment_sem = asyncio.Semaphore(4)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Маркеры занятости на Fragment (проверено на реальных страницах)
FRAGMENT_SELLING = [
    "tm-status-unavail",        # статус Sold/Unavailable
    'content="buy @',           # og:title = "Buy @username"
    'content="make an offer',   # og:title = "Make an offer for @username" — выставлен на продажу
    "place a bid",              # кнопка ставки
]


class UsernameChecker:

    def __init__(self, bot: Bot):
        self.bot = bot
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Tuple[bool, float]] = {}
        self._cache_ttl = 300

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=50,
                limit_per_host=10,
                ttl_dns_cache=300,
            )
            self._session = aiohttp.ClientSession(
                headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=8, connect=3),
                connector=connector,
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _from_cache(self, username: str) -> Optional[bool]:
        entry = self._cache.get(username)
        if entry and (time() - entry[1]) < self._cache_ttl:
            return entry[0]
        return None

    def _to_cache(self, username: str, available: bool):
        self._cache[username] = (available, time())

    # ------------------------------------------------------------------ #
    #  Telegram: bot.get_chat                                              #
    # ------------------------------------------------------------------ #

    async def _check_telegram(self, username: str) -> bool:
        """
        Пытается открыть чат через Bot API.
        True  → ник свободен ("chat not found")
        False → ник занят (чат найден или неизвестная ошибка)
        """
        try:
            await self.bot.get_chat(f"@{username}")
            # Чат открылся — ник занят
            return False
        except TelegramBadRequest as e:
            err = str(e).lower()
            if any(x in err for x in (
                "chat not found",
                "not found",
                "username is not occupied",
                "peer_id_invalid",
                "username invalid",
            )):
                # TG явно говорит что такого нет — свободен
                return True
            # Другая ошибка — неизвестно, считаем занятым
            logger.debug(f"TG unknown error @{username}: {e}")
            return False
        except Exception as e:
            logger.debug(f"TG exception @{username}: {type(e).__name__}: {e}")
            # Сетевая ошибка — неизвестно, считаем занятым
            return False

    # ------------------------------------------------------------------ #
    #  Fragment: HTTP GET                                                  #
    # ------------------------------------------------------------------ #

    async def _check_fragment(self, username: str) -> bool:
        """
        GET https://fragment.com/username/<nick>
        True  → ника нет на Fragment
        False → ник продаётся / продан

        При любой ошибке или таймауте → False (занят).
        Лучше пропустить свободный, чем выдать занятый.
        """
        async with _fragment_sem:
            try:
                session = await self._get_session()
                async with session.get(
                    f"https://fragment.com/username/{username.lower()}",
                    timeout=aiohttp.ClientTimeout(total=8),
                    allow_redirects=True,
                ) as resp:
                    if resp.status != 200:
                        logger.debug(f"Fragment @{username}: HTTP {resp.status} → занят")
                        return False

                    chunk = await resp.content.read(16384)
                    html = chunk.decode("utf-8", errors="ignore").lower()

                    for marker in FRAGMENT_SELLING:
                        if marker in html:
                            logger.debug(f"Fragment @{username}: занят ({marker})")
                            return False

                    logger.debug(f"Fragment @{username}: свободен")
                    return True

            except asyncio.TimeoutError:
                logger.debug(f"Fragment @{username}: таймаут → занят")
                return False
            except Exception as e:
                logger.debug(f"Fragment @{username}: ошибка {e} → занят")
                return False

    # ------------------------------------------------------------------ #
    #  Основная проверка                                                   #
    # ------------------------------------------------------------------ #

    async def check_username(self, username: str) -> Tuple[bool, str]:
        """
        1. Проверяем Telegram через bot.get_chat
        2. Если свободен в TG — проверяем Fragment через HTTP
        Оба должны сказать "свободен" чтобы вернуть True.
        """
        cached = self._from_cache(username)
        if cached is not None:
            return cached, ("Свободен" if cached else "Занят (кэш)")

        # Шаг 1: Telegram
        tg_free = await self._check_telegram(username)
        if not tg_free:
            self._to_cache(username, False)
            return False, "Занят в Telegram"

        # Шаг 2: Fragment
        fr_free = await self._check_fragment(username)
        if not fr_free:
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
