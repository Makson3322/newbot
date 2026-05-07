"""
Модуль для проверки доступности юзернеймов в Telegram.
Проверяет через:
  1. Telegram Bot API  — каналы / группы / боты
  2. t.me/<username>   — личные аккаунты (парсинг HTML)
  3. fragment.com      — не продаётся ли ник на аукционе

Ключевые правила надёжности:
  - Fragment: при любой ошибке/таймауте считаем ник ЗАНЯТЫМ (не выдаём мусор)
  - Семафор на Fragment: не более 3 одновременных запросов (иначе Fragment банит)
  - BATCH_SIZE уменьшен до 5 чтобы не перегружать Fragment
"""

import asyncio
import logging
import aiohttp
from typing import Tuple, Optional, Dict, List
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from time import time

logger = logging.getLogger(__name__)

# Пачка: 5 ников одновременно — баланс скорости и надёжности Fragment
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Маркеры занятости на t.me (только у занятых, проверено)
TME_OCCUPIED = [
    "tgme_page_title",
    "tgme_page_photo",
    "view in telegram",
    "join channel",
    "join group",
]

# Маркеры того что ник ЗАНЯТ на Fragment (проверено на реальных страницах)
FRAGMENT_SELLING = [
    "tm-status-unavail",   # статус Sold/Unavailable — есть у ВСЕХ занятых ников
    'content="buy @',      # og:title = "Buy @username"
    "place a bid",         # кнопка ставки
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
                force_close=False,
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
    #  Bot API                                                             #
    # ------------------------------------------------------------------ #

    async def _check_bot_api(self, username: str) -> Optional[bool]:
        """
        None  → неопределённо (личный аккаунт)
        False → занят (чат найден)
        True  → явно свободен ("chat not found")
        """
        try:
            await self.bot.get_chat(f"@{username}")
            return False
        except TelegramBadRequest as e:
            err = str(e).lower()
            if any(x in err for x in (
                "chat not found", "not found",
                "username is not occupied", "peer_id_invalid",
            )):
                return True
            logger.debug(f"Bot API unknown error @{username}: {e}")
            return None
        except Exception as e:
            logger.debug(f"Bot API exception @{username}: {type(e).__name__}")
            return None

    # ------------------------------------------------------------------ #
    #  t.me                                                                #
    # ------------------------------------------------------------------ #

    async def _check_tme(self, username: str) -> bool:
        """True → свободен, False → занят. При ошибке → True (не блокируем)."""
        try:
            session = await self._get_session()
            async with session.get(
                f"https://t.me/{username.lower()}",
                timeout=aiohttp.ClientTimeout(total=8),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return True
                chunk = await resp.content.read(16384)
                html = chunk.decode("utf-8", errors="ignore").lower()
                for marker in TME_OCCUPIED:
                    if marker in html:
                        return False
                if "sorry, this username is not available" in html:
                    return False
                return True
        except Exception as e:
            logger.debug(f"t.me error @{username}: {e}")
            return True

    # ------------------------------------------------------------------ #
    #  Fragment                                                            #
    # ------------------------------------------------------------------ #

    async def _check_fragment(self, username: str) -> bool:
        """
        True  → не на Fragment (свободен со стороны Fragment)
        False → продаётся / продан

        ВАЖНО: при любой ошибке или таймауте возвращаем FALSE (занят).
        Лучше пропустить свободный ник, чем выдать занятый.
        """
        async with _fragment_sem:  # не более 3 одновременных запросов
            try:
                session = await self._get_session()
                async with session.get(
                    f"https://fragment.com/username/{username.lower()}",
                    timeout=aiohttp.ClientTimeout(total=12),
                    allow_redirects=True,
                ) as resp:
                    if resp.status != 200:
                        # Нестандартный статус — не знаем, считаем занятым
                        logger.debug(f"Fragment @{username}: status {resp.status} → занят")
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
                # Таймаут = Fragment не ответил = не знаем = считаем занятым
                logger.debug(f"Fragment @{username}: таймаут → занят")
                return False
            except Exception as e:
                logger.debug(f"Fragment @{username}: ошибка {e} → занят")
                return False

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

        if api_result is True:
            # TG явно свободен — проверяем Fragment
            fr_free = await self._check_fragment(username)
            if not fr_free:
                self._to_cache(username, False)
                return False, "Продаётся на Fragment"
            self._to_cache(username, True)
            return True, "Свободен"

        # Шаг 2: api=None (личный аккаунт) — t.me + Fragment параллельно
        tme_result, fr_result = await asyncio.gather(
            self._check_tme(username),
            self._check_fragment(username),
            return_exceptions=True,
        )

        # t.me: ошибка = не блокируем (True)
        if isinstance(tme_result, BaseException):
            tme_result = True
        # Fragment: ошибка = блокируем (False) — уже обработано внутри метода,
        # но на случай если gather поймал BaseException
        if isinstance(fr_result, BaseException):
            fr_result = False

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
