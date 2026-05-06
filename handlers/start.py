"""
Обработчик команды /start, главного меню и премиума
"""

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards.main_kb import (
    get_main_keyboard, get_documents_keyboard,
    get_premium_plans_keyboard, get_payment_keyboard,
)
from database.db import db

router = Router()

# Тарифы: callback_data → (название, дней, сумма)
PLANS = {
    "plan_2_100":  ("2 дня",    2,  100),
    "plan_4_175":  ("4 дня",    4,  175),
    "plan_10_300": ("10 дней", 10,  300),
    "plan_30_650": ("30 дней", 30,  650),
}


# ------------------------------------------------------------------ #
#  /start                                                              #
# ------------------------------------------------------------------ #

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    await db.add_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    stats = await db.get_user_stats(message.from_user.id)
    has_premium = await db.check_premium(message.from_user.id)

    attempts_left = max(0, 3 - stats.get("today_searches", 0))
    username = message.from_user.username or "username"

    welcome_text = (
        f"⚡️codedev || {username} — поиск свободных ников\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"🎯 Попытки: {'∞' if has_premium else attempts_left}/{'∞' if has_premium else '3'}\n"
        "💎 Premium открывает:\n"
        "• Поиск редких 5-буквенных ников\n"
        "• Фильтр по маске (a?b?c → любые буквы)\n"
        "• Безлимитный поиск без ограничений\n\n"
        "Выберите действие ниже 👇"
    )

    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")
    await message.answer("📋 Документы бота:", reply_markup=get_documents_keyboard(), parse_mode="HTML")


# ------------------------------------------------------------------ #
#  Премиум                                                             #
# ------------------------------------------------------------------ #

@router.message(F.text == "💎 Премиум")
async def show_premium(message: Message):
    user_id = message.from_user.id
    has_premium = await db.check_premium(user_id)

    if has_premium:
        until = await db.get_premium_until(user_id)
        if until:
            from datetime import datetime
            try:
                dt = datetime.strptime(until, "%Y-%m-%d %H:%M:%S")
                until_str = dt.strftime("%d.%m.%Y %H:%M")
            except Exception:
                until_str = until
            expire_line = f"\n⏳ Действует до: <b>{until_str}</b>"
        else:
            expire_line = "\n⏳ Срок: <b>бессрочно</b>"

        await message.answer(
            f"💎 <b>У вас уже есть Premium!</b>{expire_line}\n\n"
            "• Безлимитный поиск ✅\n"
            "• Поиск 5-буквенных ников ✅\n"
            "• Фильтр по маске ✅",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
        return

    await message.answer(
        "💎 <b>Premium подписка</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "Что открывает Premium:\n"
        "• 🔍 Поиск редких 5-буквенных ников\n"
        "• 🎭 Фильтр по маске (a?b?c → любые буквы)\n"
        "• ♾️ Безлимитный поиск без ограничений\n\n"
        "Выберите тариф:",
        parse_mode="HTML",
        reply_markup=get_premium_plans_keyboard(),
    )


@router.callback_query(F.data.startswith("plan_"))
async def handle_premium_plan(callback: CallbackQuery):
    plan = PLANS.get(callback.data)
    if not plan:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return

    name, days, amount = plan
    await callback.message.edit_text(
        f"💳 <b>Оплата Premium — {name}</b>\n\n"
        f"Сумма: <b>{amount}₽</b>\n\n"
        f"Нажмите кнопку ниже для оплаты через СБП:",
        parse_mode="HTML",
        reply_markup=get_payment_keyboard(amount, days),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_sbp_"))
async def pay_sbp(callback: CallbackQuery):
    """Кнопка 'Оплатить СБП' — временно недоступно"""
    await callback.answer(
        "⚠️ Оплата временно недоступна.\n"
        "Нажмите «✅ Проверить оплату» для получения Premium.",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment(callback: CallbackQuery):
    """
    Временная логика: при нажатии 'Проверить оплату' сразу выдаём премиум.
    Формат callback: check_payment_{amount}_{days}
    """
    user_id = callback.from_user.id

    # Парсим days из callback_data
    parts = callback.data.split("_")
    # check_payment_{amount}_{days}
    try:
        days = int(parts[-1])
    except (ValueError, IndexError):
        days = 30  # fallback

    await db.set_premium(user_id, days=days)

    from datetime import datetime, timedelta
    until = datetime.now() + timedelta(days=days)
    until_str = until.strftime("%d.%m.%Y %H:%M")

    await callback.message.edit_text(
        f"✅ <b>Premium активирован!</b>\n\n"
        f"⏳ Действует до: <b>{until_str}</b>\n\n"
        f"Теперь вам доступны:\n"
        f"• ♾️ Безлимитный поиск\n"
        f"• 🔍 Поиск 5-буквенных ников\n"
        f"• 🎭 Фильтр по маске",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )
    await callback.answer("💎 Premium активирован!", show_alert=False)


@router.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: CallbackQuery):
    await callback.message.edit_text("❌ Оплата отменена.")
    await callback.answer()
