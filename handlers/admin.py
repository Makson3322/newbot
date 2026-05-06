"""
Админ-панель бота.
Доступна только пользователю с ADMIN_ID из .env.

Команды:
  /admin          — главное меню админки
  /give <id> <дней>  — выдать премиум на N дней (0 = бессрочно)
  /revoke <id>    — снять премиум
  /users          — список всех пользователей
"""

import logging
import os
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import db

logger = logging.getLogger(__name__)
router = Router()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def admin_only(func):
    """Декоратор — пропускает только админа."""
    async def wrapper(message: Message, *args, **kwargs):
        if not is_admin(message.from_user.id):
            return
        return await func(message, *args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


# ------------------------------------------------------------------ #
#  Клавиатура админки                                                  #
# ------------------------------------------------------------------ #

def get_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Все пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="💎 Выдать Premium", callback_data="admin_give_menu")],
        [InlineKeyboardButton(text="❌ Снять Premium",   callback_data="admin_revoke_menu")],
    ])


def get_days_keyboard(user_id: int) -> InlineKeyboardMarkup:
    days_options = [
        ("2 дня",    2),
        ("4 дня",    4),
        ("10 дней", 10),
        ("30 дней", 30),
        ("Бессрочно", 0),
    ]
    buttons = [
        [InlineKeyboardButton(
            text=label,
            callback_data=f"admin_give_{user_id}_{days}"
        )]
        for label, days in days_options
    ]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ------------------------------------------------------------------ #
#  FSM для ввода user_id                                               #
# ------------------------------------------------------------------ #

class AdminStates(StatesGroup):
    waiting_user_id_give   = State()
    waiting_user_id_revoke = State()


# ------------------------------------------------------------------ #
#  /admin                                                              #
# ------------------------------------------------------------------ #

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "🔧 <b>Админ-панель</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard(),
    )


# ------------------------------------------------------------------ #
#  Список пользователей                                                #
# ------------------------------------------------------------------ #

@router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    users = await db.get_all_users()
    if not users:
        await callback.answer("Пользователей нет", show_alert=True)
        return

    lines = []
    for u in users[:50]:  # максимум 50 чтобы не превысить лимит сообщения
        uid = u["user_id"]
        uname = f"@{u['username']}" if u["username"] else u["first_name"] or "—"
        if u["is_premium"]:
            until = u["premium_until"]
            if until:
                try:
                    dt = datetime.strptime(until, "%Y-%m-%d %H:%M:%S")
                    prem = f"💎 до {dt.strftime('%d.%m.%Y')}"
                except Exception:
                    prem = "💎"
            else:
                prem = "💎 бессрочно"
        else:
            prem = "—"
        lines.append(f"<code>{uid}</code> {uname} {prem}")

    text = f"👥 <b>Пользователи ({len(users)}):</b>\n\n" + "\n".join(lines)
    if len(users) > 50:
        text += f"\n\n<i>...и ещё {len(users) - 50}</i>"

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ]),
    )
    await callback.answer()


# ------------------------------------------------------------------ #
#  Выдать Premium                                                      #
# ------------------------------------------------------------------ #

@router.callback_query(F.data == "admin_give_menu")
async def admin_give_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "💎 <b>Выдать Premium</b>\n\n"
        "Введите Telegram ID пользователя:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_back")]
        ]),
    )
    await state.set_state(AdminStates.waiting_user_id_give)
    await callback.answer()


@router.message(AdminStates.waiting_user_id_give)
async def admin_give_get_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите числовой ID")
        return

    # Проверяем что пользователь существует
    user = await db.get_user(target_id)
    if not user:
        await message.answer(
            f"❌ Пользователь <code>{target_id}</code> не найден в БД.\n"
            "Он должен хотя бы раз запустить бота.",
            parse_mode="HTML",
        )
        await state.clear()
        return

    uname = f"@{user['username']}" if user.get("username") else user.get("first_name") or str(target_id)
    await state.clear()

    await message.answer(
        f"💎 Выдать Premium пользователю {uname} (<code>{target_id}</code>)\n\n"
        "Выберите срок:",
        parse_mode="HTML",
        reply_markup=get_days_keyboard(target_id),
    )


@router.callback_query(F.data.startswith("admin_give_"))
async def admin_give_confirm(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    # admin_give_{user_id}_{days}
    parts = callback.data.split("_")
    try:
        target_id = int(parts[2])
        days = int(parts[3])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    await db.set_premium(target_id, days=days if days > 0 else None)

    if days == 0:
        label = "бессрочно"
    else:
        from datetime import timedelta
        until = datetime.now() + timedelta(days=days)
        label = f"до {until.strftime('%d.%m.%Y %H:%M')}"

    user = await db.get_user(target_id)
    uname = f"@{user['username']}" if user and user.get("username") else str(target_id)

    await callback.message.edit_text(
        f"✅ <b>Premium выдан!</b>\n\n"
        f"👤 Пользователь: {uname} (<code>{target_id}</code>)\n"
        f"⏳ Срок: <b>{label}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В меню", callback_data="admin_back")]
        ]),
    )
    await callback.answer("✅ Готово!")

    # Уведомляем пользователя
    try:
        from aiogram import Bot
        bot: Bot = callback.bot
        if days == 0:
            expire_text = "бессрочно"
        else:
            from datetime import timedelta
            until = datetime.now() + timedelta(days=days)
            expire_text = f"до {until.strftime('%d.%m.%Y %H:%M')}"

        await bot.send_message(
            target_id,
            f"🎉 <b>Вам выдан Premium!</b>\n\n"
            f"⏳ Действует: <b>{expire_text}</b>\n\n"
            f"Теперь вам доступны:\n"
            f"• ♾️ Безлимитный поиск\n"
            f"• 🔍 Поиск 5-буквенных ников\n"
            f"• 🎭 Фильтр по маске",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Не удалось уведомить {target_id}: {e}")


# ------------------------------------------------------------------ #
#  Снять Premium                                                       #
# ------------------------------------------------------------------ #

@router.callback_query(F.data == "admin_revoke_menu")
async def admin_revoke_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "❌ <b>Снять Premium</b>\n\n"
        "Введите Telegram ID пользователя:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_back")]
        ]),
    )
    await state.set_state(AdminStates.waiting_user_id_revoke)
    await callback.answer()


@router.message(AdminStates.waiting_user_id_revoke)
async def admin_revoke_get_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите числовой ID")
        return

    await db.set_premium(target_id, status=False)
    await state.clear()

    await message.answer(
        f"✅ Premium снят с пользователя <code>{target_id}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В меню", callback_data="admin_back")]
        ]),
    )


# ------------------------------------------------------------------ #
#  Назад                                                               #
# ------------------------------------------------------------------ #

@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await state.clear()
    await callback.message.edit_text(
        "🔧 <b>Админ-панель</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard(),
    )
    await callback.answer()


# ------------------------------------------------------------------ #
#  Быстрые команды                                                     #
# ------------------------------------------------------------------ #

@router.message(Command("give"))
async def cmd_give(message: Message):
    """
    /give <user_id> <days>
    days=0 → бессрочно
    """
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Использование: /give <user_id> <days>\ndays=0 → бессрочно")
        return

    try:
        target_id = int(parts[1])
        days = int(parts[2])
    except ValueError:
        await message.answer("❌ Неверный формат. Пример: /give 123456789 30")
        return

    await db.set_premium(target_id, days=days if days > 0 else None)

    label = "бессрочно" if days == 0 else f"{days} дн."
    await message.answer(
        f"✅ Premium выдан пользователю <code>{target_id}</code> на {label}",
        parse_mode="HTML",
    )


@router.message(Command("revoke"))
async def cmd_revoke(message: Message):
    """/revoke <user_id>"""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Использование: /revoke <user_id>")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ Неверный ID")
        return

    await db.set_premium(target_id, status=False)
    await message.answer(
        f"✅ Premium снят с <code>{target_id}</code>",
        parse_mode="HTML",
    )
