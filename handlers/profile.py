"""
Обработчик профиля пользователя
"""

from aiogram import Router, F
from aiogram.types import Message
from datetime import datetime

from database.db import db
from keyboards.main_kb import get_main_keyboard

router = Router()


@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "не указан"

    # Убеждаемся что пользователь зарегистрирован
    await db.add_user(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    stats = await db.get_user_stats(user_id)

    # get_user_stats возвращает {} если пользователь не найден —
    # после add_user выше это не должно случиться, но на всякий случай
    if not stats or "user_id" not in stats:
        await message.answer(
            "❌ Не удалось загрузить профиль. Попробуйте ещё раз.",
            reply_markup=get_main_keyboard(),
        )
        return

    # Премиум статус
    has_premium = await db.check_premium(user_id)
    premium_line = "💎 Premium: <b>активен</b>" if has_premium else "💎 Premium: <b>нет</b>"

    # Дата регистрации
    try:
        reg_date = datetime.strptime(stats["registration_date"], "%Y-%m-%d %H:%M:%S")
        formatted_date = reg_date.strftime("%d.%m.%Y")
    except Exception:
        formatted_date = "Неизвестно"

    # Лимит поисков
    today = stats.get("today_searches", 0)
    if has_premium:
        limit_line = f"🔘 Сегодня: <b>{today}</b> / ∞"
    else:
        left = max(0, 3 - today)
        limit_line = f"🔘 Сегодня: <b>{today}</b> / 3 (осталось: {left})"

    profile_text = (
        "👤 <b>ПРОФИЛЬ</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"🪪 ID: <code>{stats['user_id']}</code>\n"
        f"✏️ Юзернейм: @{username}\n"
        f"📅 Регистрация: {formatted_date}\n\n"
        f"{premium_line}\n\n"
        f"{limit_line}\n"
        f"🔍 Всего поисков: <b>{stats['total_searches']}</b>\n"
        f"✅ Найдено ников: <b>{stats['found_usernames']}</b>"
    )

    await message.answer(
        profile_text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )
