"""
Проверка юзернеймов:
  1. Telegram Bot API (bot.get_chat) — каналы, группы, боты
  2. t.me/<username>                 — личные аккаунты (парсинг HTML)
  3. Fragment HTTP                   — не продаётся ли ник

Правило надёжности: при любой ошибке/таймауте → считаем ЗАНЯТЫМ.
Лучше пропустить свободный, чем выдать занятый.
"""

import asyncio
import logging
import aiohttp
from typing import Tuple, Optional, Dict, List
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from time import time

logger = logging.getLogger(__name__)

BATCH_SIZE = 5

# Семафор: не более 3 запросов к Fragment одновременно
_fragment_sem = asyncio.Semaphore(3)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Маркеры ЗАНЯТОГО ника на t.me (только у существующих аккаунтов)
TME_OCCUPIED = [
    "tgme_page_title",   # имя профиля — есть только у существующих
    "tgme_page_photo",   # фото профиля
    "tgme_page_extra",   # доп. блок профиля
    "view in telegram",  # кнопка открыть
    "join channel",
    "join group",
]

# Маркеры занятости на Fragment
FRAGMENT_SELLING = [
    "tm-status-unavail",       # Sold/Unavailable
    'content="buy @',          # "Buy @username"
    'content="make an offer',  # "Make an offer for @username"
    "place a bid",             # кнопка ставки
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
                timeout=aiohttp.ClientTimeout(total=12, connect=5),
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
    #  1. Telegram Bot API                                                 #
    # ------------------------------------------------------------------ #

    async def _check_bot_api(self, username: str) -> Optional[bool]:
        """
        True  → явно свободен (TG: "chat not found")
        False → занят (чат найден)
        None  → личный аккаунт или ошибка (нужна проверка t.me)
        """
        try:
            await self.bot.get_chat(f"@{username}")
            return False  # нашли — занят
        except TelegramBadRequest as e:
            err = str(e).lower()
            if any(x in err for x in (
                "chat not found", "not found",
                "username is not occupied", "peer_id_invalid",
                "username invalid",
            )):
                # TG не знает этот ник как публичный чат —
                # может быть личный аккаунт, нужна проверка t.me
                return None
            logger.debug(f"Bot API unknown error @{username}: {e}")
            return False
        except Exception as e:
            logger.debug(f"Bot API exception @{username}: {type(e).__name__}")
            return None

    # ------------------------------------------------------------------ #
    #  2. t.me — единственный способ проверить личные аккаунты            #
    # ------------------------------------------------------------------ #

    async def _check_tme(self, username: str) -> bool:
        """
        True  → ника нет на t.me (свободен)
        False → ник существует (занят) ИЛИ ошибка/таймаут

        При ошибке → False (занят). Консервативно.
        """
        try:
            session = await self._get_session()
            async with session.get(
                f"https://t.me/{username.lower()}",
                timeout=aiohttp.ClientTimeout(total=10),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    # Нестандартный статус — считаем занятым
                    return False

                chunk = await resp.content.read(32768)
                html = chunk.decode("utf-8", errors="ignore").lower()

                for marker in TME_OCCUPIED:
                    if marker in html:
                        logger.debug(f"t.me @{username}: занят ({marker})")
                        return False

                if "sorry, this username is not available" in html:
                    return False

                logger.debug(f"t.me @{username}: свободен")
                return True

        except asyncio.TimeoutError:
            logger.debug(f"t.me @{username}: таймаут → занят")
            return False
        except Exception as e:
            logger.debug(f"t.me @{username}: ошибка {e} → занят")
            return False

    # ------------------------------------------------------------------ #
    #  3. Fragment HTTP                                                    #
    # ------------------------------------------------------------------ #

    async def _check_fragment(self, username: str) -> bool:
        """
        True  → не на Fragment
        False → продаётся/продан ИЛИ ошибка/таймаут (консервативно)
        """
        async with _fragment_sem:
            try:
                session = await self._get_session()
                async with session.get(
                    f"https://fragment.com/username/{username.lower()}",
                    timeout=aiohttp.ClientTimeout(total=12),
                    allow_redirects=True,
                ) as resp:
                    if resp.status != 200:
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
        Алгоритм:
        1. Bot API → если нашёл чат: занят
        2. t.me   → всегда проверяем (ловит личные аккаунты)
        3. Fragment → проверяем если прошли 1 и 2
        """
        cached = self._from_cache(username)
        if cached is not None:
            return cached, ("Свободен" if cached else "Занят (кэш)")

        # Шаг 1: Bot API (быстро ловит каналы/группы/ботов)
        api_result = await self._check_bot_api(username)
        if api_result is False:
            self._to_cache(username, False)
            return False, "Занят в Telegram"

        # Шаг 2: t.me (ловит личные аккаунты — Bot API их не видит)
        tme_free = await self._check_tme(username)
        if not tme_free:
            self._to_cache(username, False)
            return False, "Занят в Telegram"

        # Шаг 3: Fragment
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
