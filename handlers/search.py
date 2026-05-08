"""
Обработчик поиска юзернеймов с анимированным прогресс-баром.
"""

import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from services.username_generator import generator
from services.username_checker import UsernameChecker, BATCH_SIZE
from database.db import db
from keyboards.main_kb import get_main_keyboard, get_search_type_keyboard

router = Router()
logger = logging.getLogger(__name__)

active_searches: dict = {}

E = {
    "search": '<tg-emoji emoji-id="5870676941614354370">🔍</tg-emoji>',
    "ok":     '<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji>',
    "no":     '<tg-emoji emoji-id="5870657884844462243">✖️</tg-emoji>',
    "diamond":'<tg-emoji emoji-id="6032644646587338669">🎁</tg-emoji>',
    "warn":   '<tg-emoji emoji-id="5983150113483134607">⏰</tg-emoji>',
    "stop":   '<tg-emoji emoji-id="5870657884844462243">✖️</tg-emoji>',
}

# Анимация прогресс-бара — кадры
BAR_LEN = 20
BAR_FILL = "▰"
BAR_EMPTY = "▱"

# Спиннер-символы для заголовка
SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def _progress_bar(attempts: int, max_attempts: int) -> str:
    """Возвращает строку прогресс-бара."""
    pct = min(attempts / max_attempts, 1.0)
    filled = int(BAR_LEN * pct)
    bar = BAR_FILL * filled + BAR_EMPTY * (BAR_LEN - filled)
    return f"[{bar}]"


def _search_frame(attempts: int, max_attempts: int, last_nick: str, spin_idx: int, label: str) -> str:
    """Один кадр анимации поиска."""
    spin = SPINNER[spin_idx % len(SPINNER)]
    bar = _progress_bar(attempts, max_attempts)
    pct = min(int(attempts / max_attempts * 100), 100)
    return (
        f"{spin} <b>Поиск {label}...</b>\n\n"
        f"<code>{bar}</code> {pct}%\n\n"    
    )


def _detect_pattern(username: str) -> str:
    length = len(username)
    unique_chars = len(set(username))
    if unique_chars == 1:
        return " 🔥 (все одинаковые)"
    if unique_chars == 2 and length >= 4:
        if username[:2] * (length // 2) == username[:length - length % 2]:
            return " ⚡️ (чередование)"
        return " ⭐️ (2 буквы)"
    for i in range(length - 1):
        if username[i] == username[i + 1]:
            return " 💫 (двойные)"
    vowels = set("aeiou")
    if all(
        (username[i] in vowels) != (username[i + 1] in vowels)
        for i in range(length - 1)
    ) and length >= 4:
        return " ✨ (произносимый)"
    return ""


def _build_result_text(username: str, length: int, attempts: int, extra: str = "") -> tuple:
    liquidity_score, liquidity_level = generator.calculate_liquidity(username)
    pattern_type = _detect_pattern(username)

    if liquidity_score >= 9:
        header = "🔥 <b>ЛЕГЕНДА НАЙДЕНА!</b> 🔥"
    elif liquidity_score >= 8:
        header = f"{E['diamond']} <b>ТОПЧИК НАЙДЕН!</b>"
    elif liquidity_score >= 7:
        header = "⚡️ <b>БЛАТНОЙ НИК!</b> ⚡️"
    elif liquidity_score >= 6:
        header = "✨ <b>ГОДНЫЙ НИК!</b> ✨"
    else:
        header = f"{E['ok']} <b>НИК НАЙДЕН!</b>"

    text = (
        f"{header}\n\n"
        f"<code>@{username}</code>\n"
        f"└ {length} букв{extra}{pattern_type}\n\n"
        f"├ Ликвидность — <b>{liquidity_score}</b> из 10 {liquidity_level}\n"
        f"├ Проверено вариантов: <b>{attempts}</b>\n"
        f"└ Свободен ⚡️\n\n"
        f"📢 @codedev_username_bot"
    )
    return text, liquidity_score


async def _run_search(bot: Bot, user_id: int, length: int,
                      reply_to: Message, search_msg: Message, mask: str = None):
    checker = UsernameChecker(bot)
    attempts = 0
    max_attempts = 2000
    found = False
    spin_idx = 0
    label = f"маска: {mask}" if mask else f"{length} букв"

    # Обновляем анимацию каждые N батчей
    UPDATE_EVERY = 2  # каждые 2 батча = каждые ~10 проверок

    try:
        while active_searches.get(user_id, False) and attempts < max_attempts:
            batch = [
                generator.generate_by_mask(mask) if mask else generator.generate_random(length)
                for _ in range(BATCH_SIZE)
            ]
            attempts += BATCH_SIZE
            spin_idx += 1

            # Обновляем анимацию
            if spin_idx % UPDATE_EVERY == 0:
                try:
                    frame = _search_frame(attempts, max_attempts, batch[-1], spin_idx, label)
                    await search_msg.edit_text(frame, parse_mode="HTML")
                except Exception:
                    pass

            # Параллельная проверка пачки
            results = await checker.check_batch(batch)

            for username, is_available, status in results:
                if not active_searches.get(user_id, False):
                    break
                if is_available:
                    found = True
                    await db.update_search_stats(user_id)
                    await db.add_found_username(
                        user_id, username, len(username),
                        generator.calculate_liquidity(username)[0],
                    )
                    extra = f" (маска: {mask})" if mask else ""
                    result_text, _ = _build_result_text(username, len(username), attempts, extra)

                    # Удаляем сообщение с анимацией
                    try:
                        await search_msg.delete()
                    except Exception:
                        pass

                    await reply_to.answer(result_text, parse_mode="HTML", reply_markup=get_main_keyboard())
                    active_searches[user_id] = False
                    return

        if not found and active_searches.get(user_id, False):
            lbl = f"маске <code>{mask}</code>" if mask else f"{length}-буквенный"
            await search_msg.edit_text(
                f"{E['warn']} <b>Поиск завершён</b>\n\n"
                f"Проверено {attempts} вариантов по {lbl}, "
                f"свободный ник не найден.\nПопробуйте ещё раз!",
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error(f"Ошибка поиска user {user_id}: {e}")
        try:
            await reply_to.answer(
                f"{E['no']} Произошла ошибка при поиске.\nПопробуйте ещё раз позже.",
                reply_markup=get_main_keyboard(),
                parse_mode="HTML",
            )
        except Exception:
            pass
    finally:
        active_searches.pop(user_id, None)
        await checker.close()


# ------------------------------------------------------------------ #
#  Хендлеры                                                           #
# ------------------------------------------------------------------ #

@router.message(F.text == "🔍 ПОИСК")
async def show_search_menu(message: Message):
    await message.answer(
        f"{E['search']} <b>ВЫБЕРИТЕ ТИП ПОИСКА</b>\n\nВыберите длину юзернейма или используйте фильтр:",
        reply_markup=get_search_type_keyboard(),
        parse_mode="HTML",
    )


async def _start_search(bot: Bot, user_id: int, length: int,
                        reply_to: Message, answer_target: Message):
    """Общая логика запуска поиска."""
    if active_searches.get(user_id):
        return "already"

    has_premium = await db.check_premium(user_id)
    if not has_premium:
        stats = await db.get_user_stats(user_id)
        if stats.get("today_searches", 0) >= 3:
            return "limit"

    # Первый кадр анимации
    bar = _progress_bar(0, 2000)
    search_msg = await answer_target.answer(
        f"⠋ <b>Поиск {length} букв...</b>\n\n"
        f"<code>{bar}</code> 0%\n\n"
        f"🔄 Проверено: <b>0</b>\n"
        f"📍 Запускаю...",
        parse_mode="HTML",
    )

    active_searches[user_id] = True
    asyncio.create_task(_run_search(bot, user_id, length, reply_to, search_msg))
    return "ok"


@router.callback_query(F.data.in_(["search_5", "search_6"]))
async def start_search_callback(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    length = 5 if callback.data == "search_5" else 6

    result = await _start_search(bot, user_id, length, callback.message, callback.message)

    if result == "already":
        await callback.answer("Поиск уже запущен!", show_alert=True)
    elif result == "limit":
        await callback.answer(
            "Дневной лимит (3/3) исчерпан.\nКупите Premium для безлимитного поиска!",
            show_alert=True,
        )
    else:
        await callback.answer()


@router.message(F.text.in_(["5 букв", "6 букв"]))
async def start_search_message(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    length = 5 if message.text == "5 букв" else 6

    result = await _start_search(bot, user_id, length, message, message)

    if result == "already":
        await message.answer("Поиск уже запущен!", reply_markup=get_main_keyboard())
    elif result == "limit":
        await message.answer(
            f"{E['no']} Дневной лимит (3/3) исчерпан.\nКупите Premium для безлимитного поиска!",
            reply_markup=get_main_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "stop_search")
async def stop_search(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id in active_searches:
        active_searches[user_id] = False
        await callback.answer("Поиск остановлен", show_alert=True)
        try:
            await callback.message.edit_text(
                f"{E['stop']} <b>Поиск остановлен</b>", parse_mode="HTML"
            )
        except Exception:
            pass
    else:
        await callback.answer("Поиск уже завершён")
