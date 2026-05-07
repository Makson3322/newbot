"""
Обработчик профиля пользователя
"""

from aiogram import Router, F
from aiogram.types import Message
from datetime import datetime

from database.db import db
from keyboards.main_kb import get_main_keyboard

router = Router()

E = {
    "person":  '<tg-emoji emoji-id="5870994129244131212">👤</tg-emoji>',
    "id":      '<tg-emoji emoji-id="5870982283724328568">⚙️</tg-emoji>',
    "pen":     '<tg-emoji emoji-id="5870676941614354370">🖋</tg-emoji>',
    "cal":     '<tg-emoji emoji-id="5890937706803894250">📅</tg-emoji>',
    "diamond": '<tg-emoji emoji-id="6032644646587338669">🎁</tg-emoji>',
    "search":  '<tg-emoji emoji-id="5870676941614354370">🔍</tg-emoji>',
    "ok":      '<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji>',
    "no":      '<tg-emoji emoji-id="5870657884844462243">✖️</tg-emoji>',
    "chart":   '<tg-emoji emoji-id="5870921681735781843">📊</tg-emoji>',
    "clock":   '<tg-emoji emoji-id="5983150113483134607">⏰</tg-emoji>',
}


@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "не указан"

    await db.add_user(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    stats = await db.get_user_stats(user_id)

    if not stats or "user_id" not in stats:
        await message.answer(
            f"{E['no']} Не удалось загрузить профиль. Попробуйте ещё раз.",
            reply_markup=get_main_keyboard(),
            parse_mode="HTML",
        )
        return

    has_premium = await db.check_premium(user_id)

    if has_premium:
        until = await db.get_premium_until(user_id)
        if until:
            try:
                dt = datetime.strptime(until, "%Y-%m-%d %H:%M:%S")
                prem_str = f"активен до {dt.strftime('%d.%m.%Y')}"
            except Exception:
                prem_str = "активен"
        else:
            prem_str = "активен (бессрочно)"
        premium_line = f"{E['diamond']} Premium: <b>{prem_str}</b>"
    else:
        premium_line = f"{E['diamond']} Premium: <b>нет</b>"

    try:
        reg_date = datetime.strptime(stats["registration_date"], "%Y-%m-%d %H:%M:%S")
        formatted_date = reg_date.strftime("%d.%m.%Y")
    except Exception:
        formatted_date = "Неизвестно"

    today = stats.get("today_searches", 0)
    if has_premium:
        limit_line = f"{E['search']} Сегодня: <b>{today}</b> / ∞"
    else:
        left = max(0, 3 - today)
        limit_line = f"{E['search']} Сегодня: <b>{today}</b> / 3 (осталось: {left})"

    profile_text = (
        f"{E['person']} <b>ПРОФИЛЬ</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"{E['id']} ID: <code>{stats['user_id']}</code>\n"
        f"{E['pen']} Юзернейм: @{username}\n"
        f"{E['cal']} Регистрация: {formatted_date}\n\n"
        f"{premium_line}\n\n"
        f"{limit_line}\n"
        f"{E['chart']} Всего поисков: <b>{stats['total_searches']}</b>\n"
        f"{E['ok']} Найдено ников: <b>{stats['found_usernames']}</b>"
    )

    await message.answer(
        profile_text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )
