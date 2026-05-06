"""
Модуль для проверки доступности юзернеймов в Telegram.
Проверяет через:
  1. Telegram Bot API  — каналы / группы / боты
  2. t.me/<username>   — личные аккаунты (парсинг HTML)
  3. fragment.com      — не продаётся ли ник на аукционе

Ключевая оптимизация: пачечная параллельная проверка (BATCH_SIZE ников за раз).
"""

import asyncio
import logging
import aiohttp
from typing import Tuple, Optional, Dict, List
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from time import time

logger = logging.getLogger(__name__)

# Сколько ников проверяем одновременно
BATCH_SIZE = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Маркеры занятости на t.me (присутствуют ТОЛЬКО на занятых никах, проверено)
TME_OCCUPIED = [
    "tgme_page_title",   # заголовок профиля — только у занятых
    "tgme_page_photo",   # фото профиля — только у занятых
    "view in telegram",  # кнопка открыть — только у занятых
    "join channel",      # вступить в канал
    "join group",        # вступить в группу
]

# Маркеры того что ник ЗАНЯТ на Fragment (продаётся или уже продан)
# Проверено на реальных страницах fragment.com
FRAGMENT_SELLING = [
    "tm-status-unavail",        # статус Sold/Unavailable
    'content="buy @',           # og:title = "Buy @username" — выставлен на продажу
    "place a bid",              # кнопка ставки
]

# Маркер СВОБОДНОГО ника на Fragment — страница поиска, не страница конкретного ника
FRAGMENT_FREE_MARKER = "auctions for usernames"


class UsernameChecker:
    """Проверяет доступность юзернеймов параллельными пачками."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Tuple[bool, float]] = {}
        self._cache_ttl = 300  # 5 минут

    # ------------------------------------------------------------------ #
    #  HTTP-сессия                                                         #
    # ------------------------------------------------------------------ #

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,           # до 100 одновременных соединений
                limit_per_host=30,
                ttl_dns_cache=300,
                force_close=False,   # keep-alive
            )
            self._session = aiohttp.ClientSession(
                headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=6, connect=3),
                connector=connector,
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------ #
    #  Кэш                                                                 #
    # ------------------------------------------------------------------ #

    def _from_cache(self, username: str) -> Optional[bool]:
        entry = self._cache.get(username)
        if entry and (time() - entry[1]) < self._cache_ttl:
            return entry[0]
        return None

    def _to_cache(self, username: str, available: bool):
        self._cache[username] = (available, time())

    # ------------------------------------------------------------------ #
    #  Одиночные проверки                                                  #
    # ------------------------------------------------------------------ #

    async def _check_bot_api(self, username: str) -> Optional[bool]:
        """
        Bot API через getChat.
        None  → неопределённо (личный аккаунт или ошибка сети)
        False → точно занят (чат найден)
        True  → явно свободен (TG вернул "chat not found")
        """
        try:
            await self.bot.get_chat(f"@{username}")
            return False  # чат найден — занят
        except TelegramBadRequest as e:
            err = str(e).lower()
            if any(x in err for x in (
                "chat not found",
                "not found",
                "username is not occupied",
                "peer_id_invalid",
            )):
                return True  # явно свободен
            # Другая ошибка — неопределённо
            logger.debug(f"Bot API неизвестная ошибка @{username}: {e}")
            return None
        except Exception as e:
            logger.debug(f"Bot API exception @{username}: {type(e).__name__}: {e}")
            return None

    async def _check_tme(self, username: str) -> bool:
        """
        t.me/<username>: работает для ВСЕХ типов аккаунтов.
        True  → свободен
        False → занят / зарезервирован
        """
        try:
            session = await self._get_session()
            async with session.get(
                f"https://t.me/{username.lower()}",
                timeout=aiohttp.ClientTimeout(total=6),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return True
                # Читаем 16 КБ — маркеры занятых ников появляются глубже
                chunk = await resp.content.read(16384)
                html = chunk.decode("utf-8", errors="ignore").lower()

                for marker in TME_OCCUPIED:
                    if marker in html:
                        return False

                # Зарезервирован Telegram
                if "sorry, this username is not available" in html:
                    return False

                return True
        except Exception as e:
            logger.debug(f"t.me check error @{username}: {e}")
            return True  # при ошибке считаем свободным, не блокируем

    async def _check_fragment(self, username: str) -> bool:
        """
        fragment.com: True → ник свободен (не на аукционе), False → продаётся/продан.

        Логика:
        - Если страница содержит маркеры продажи → False (занят)
        - Если og:title = "Auctions for Usernames" → Fragment не знает этот ник → True (свободен)
        - Иначе → True (на всякий случай не блокируем)
        """
        try:
            session = await self._get_session()
            async with session.get(
                f"https://fragment.com/username/{username.lower()}",
                timeout=aiohttp.ClientTimeout(total=8),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return True
                chunk = await resp.content.read(16384)
                html = chunk.decode("utf-8", errors="ignore").lower()

                # Ник продаётся или уже продан
                for marker in FRAGMENT_SELLING:
                    if marker in html:
                        logger.debug(f"Fragment @{username}: занят (маркер: {marker})")
                        return False

                return True
        except Exception as e:
            logger.debug(f"Fragment error @{username}: {e}")
            return True

    # ------------------------------------------------------------------ #
    #  Проверка одного ника                                                #
    # ------------------------------------------------------------------ #

    async def check_username(self, username: str) -> Tuple[bool, str]:
        """
        Проверка одного ника:
        1. Bot API  — если явно занят/свободен, сразу возвращаем
        2. t.me     — если Bot API не дал ответа (личный аккаунт)
        3. Fragment — только если прошли оба предыдущих
        """
        cached = self._from_cache(username)
        if cached is not None:
            return cached, ("Свободен" if cached else "Занят (кэш)")

        # --- Шаг 1: Bot API (самый надёжный источник) ---
        api_result = await self._check_bot_api(username)
        logger.debug(f"@{username} bot_api={api_result}")

        if api_result is False:
            self._to_cache(username, False)
            return False, "Занят в Telegram"

        if api_result is True:
            # Bot API явно сказал "нет такого" — проверяем только Fragment
            fr_free = await self._check_fragment(username)
            logger.debug(f"@{username} api=True fragment={fr_free}")
            if not fr_free:
                self._to_cache(username, False)
                return False, "Продаётся на Fragment"
            self._to_cache(username, True)
            return True, "Свободен"

        # --- Шаг 2: api_result is None — личный аккаунт или сеть недоступна ---
        # Запускаем t.me и Fragment параллельно
        tme_result, fr_result = await asyncio.gather(
            self._check_tme(username),
            self._check_fragment(username),
            return_exceptions=True,
        )

        if isinstance(tme_result, BaseException):
            tme_result = True   # ошибка = не блокируем
        if isinstance(fr_result, BaseException):
            fr_result = True    # ошибка = не блокируем

        logger.debug(f"@{username} api=None tme={tme_result} fragment={fr_result}")

        if not tme_result:
            self._to_cache(username, False)
            return False, "Занят в Telegram"

        if not fr_result:
            self._to_cache(username, False)
            return False, "Продаётся на Fragment"

        self._to_cache(username, True)
        return True, "Свободен"

    async def check_username_safe(self, username: str) -> Tuple[bool, str]:
        """Обёртка с защитой от исключений."""
        try:
            result = await self.check_username(username)
            logger.info(f"CHECK @{username} → {result[1]}")
            return result
        except Exception as e:
            logger.error(f"Критическая ошибка при проверке @{username}: {e}")
            return False, "Ошибка проверки"

    # ------------------------------------------------------------------ #
    #  Пачечная проверка (главная оптимизация)                            #
    # ------------------------------------------------------------------ #

    async def check_batch(
        self, usernames: List[str]
    ) -> List[Tuple[str, bool, str]]:
        """
        Проверяет список ников параллельно.
        Возвращает [(username, is_available, status), ...]
        """
        tasks = [
            asyncio.create_task(self.check_username_safe(u))
            for u in usernames
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = []
        for username, result in zip(usernames, results):
            if isinstance(result, Exception):
                output.append((username, False, "Ошибка"))
            else:
                is_avail, status = result
                output.append((username, is_avail, status))
        return output
