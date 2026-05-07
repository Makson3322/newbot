"""
Обработчик поиска юзернеймов.
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
    "fire":   '<tg-emoji emoji-id="5870930636742595124">📊</tg-emoji>',
    "diamond":'<tg-emoji emoji-id="6032644646587338669">🎁</tg-emoji>',
    "bolt":   '<tg-emoji emoji-id="5870676941614354370">🔗</tg-emoji>',
    "warn":   '<tg-emoji emoji-id="5983150113483134607">⏰</tg-emoji>',
    "stop":   '<tg-emoji emoji-id="5870657884844462243">✖️</tg-emoji>',
}


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


async def _run_search(bot, user_id, length, reply_to, search_msg, mask=None):
    checker = UsernameChecker(bot)
    attempts = 0
    max_attempts = 2000
    found = False

    try:
        while active_searches.get(user_id, False) and attempts < max_attempts:
            batch = [
                generator.generate_by_mask(mask) if mask else generator.generate_random(length)
                for _ in range(BATCH_SIZE)
            ]
            attempts += BATCH_SIZE

            if (attempts // BATCH_SIZE) % 5 == 0:
                try:
                    label = f"маска: {mask}" if mask else f"{length} букв"
                    await search_msg.edit_text(
                        f"{E['search']} <b>Поиск ({label})...</b>\n\n"
                        f"⚡️ Проверено: <b>{attempts}</b> вариантов\n"
                        f"🔄 Последний: @{batch[-1]}",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

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
                    try:
                        await search_msg.delete()
                    except Exception:
                        pass
                    await reply_to.answer(result_text, parse_mode="HTML", reply_markup=get_main_keyboard())
                    active_searches[user_id] = False
                    return

        if not found and active_searches.get(user_id, False):
            label = f"маске <code>{mask}</code>" if mask else f"{length}-буквенный"
            await search_msg.edit_text(
                f"{E['warn']} <b>Поиск завершён</b>\n\n"
                f"Проверено {attempts} вариантов по {label}, "
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


@router.message(F.text == "🔍 ПОИСК")
async def show_search_menu(message: Message):
    await message.answer(
        f"{E['search']} <b>ВЫБЕРИТЕ ТИП ПОИСКА</b>\n\nВыберите длину юзернейма или используйте фильтр:",
        reply_markup=get_search_type_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.in_(["search_5", "search_6"]))
async def start_search_callback(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    length = 5 if callback.data == "search_5" else 6

    if active_searches.get(user_id):
        await callback.answer("Поиск уже запущен!", show_alert=True)
        return

    has_premium = await db.check_premium(user_id)
    if not has_premium:
        stats = await db.get_user_stats(user_id)
        if stats.get("today_searches", 0) >= 3:
            await callback.answer(
                "Дневной лимит (3/3) исчерпан.\nКупите Premium для безлимитного поиска!",
                show_alert=True,
            )
            return

    await callback.answer()

    search_msg = await callback.message.answer(
        f"{E['search']} <b>Поиск юзернейма ({length} букв)...</b>\n\n"
        f"⚡️ Проверяю пачками по {BATCH_SIZE} ников параллельно...",
        parse_mode="HTML",
    )
    active_searches[user_id] = True
    asyncio.create_task(_run_search(bot, user_id, length, callback.message, search_msg))


@router.message(F.text.in_(["5 букв", "6 букв"]))
async def start_search_message(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    length = 5 if message.text == "5 букв" else 6

    if active_searches.get(user_id):
        await message.answer("Поиск уже запущен!", reply_markup=get_main_keyboard())
        return

    has_premium = await db.check_premium(user_id)
    if not has_premium:
        stats = await db.get_user_stats(user_id)
        if stats.get("today_searches", 0) >= 3:
            await message.answer(
                f"{E['no']} Дневной лимит (3/3) исчерпан.\nКупите Premium для безлимитного поиска!",
                reply_markup=get_main_keyboard(),
                parse_mode="HTML",
            )
            return

    search_msg = await message.answer(
        f"{E['search']} <b>Поиск юзернейма ({length} букв)...</b>\n\n"
        f"⚡️ Проверяю пачками по {BATCH_SIZE} ников параллельно...",
        parse_mode="HTML",
    )
    active_searches[user_id] = True
    asyncio.create_task(_run_search(bot, user_id, length, message, search_msg))


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
