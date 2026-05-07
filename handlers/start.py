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

PLANS = {
    "plan_2_100":  ("2 дня",    2,  100),
    "plan_4_175":  ("4 дня",    4,  175),
    "plan_10_300": ("10 дней", 10,  300),
    "plan_30_650": ("30 дней", 30,  650),
}

E = {
    "search":  '<tg-emoji emoji-id="5870676941614354370">🔍</tg-emoji>',
    "diamond": '<tg-emoji emoji-id="6032644646587338669">🎁</tg-emoji>',
    "ok":      '<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji>',
    "no":      '<tg-emoji emoji-id="5870657884844462243">✖️</tg-emoji>',
    "clock":   '<tg-emoji emoji-id="5983150113483134607">⏰</tg-emoji>',
    "money":   '<tg-emoji emoji-id="5904462880941545555">🪙</tg-emoji>',
    "person":  '<tg-emoji emoji-id="5870994129244131212">👤</tg-emoji>',
    "gift":    '<tg-emoji emoji-id="6032644646587338669">🎁</tg-emoji>',
    "star":    '<tg-emoji emoji-id="6041731551845159060">🎉</tg-emoji>',
    "info":    '<tg-emoji emoji-id="6028435952299413210">ℹ</tg-emoji>',
    "wallet":  '<tg-emoji emoji-id="5769126056262898415">👛</tg-emoji>',
}


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
        f"<b>⚡️ codedev || {username}</b>\n"
        f"<i>поиск свободных ников в Telegram</i>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"{E['search']} Попытки: <b>{'∞' if has_premium else attempts_left}/{'∞' if has_premium else '3'}</b>\n"
        f"{E['diamond']} Premium открывает:\n"
        f"  • {E['search']} Поиск редких 5-буквенных ников\n"
        f"  • {E['ok']} Фильтр по маске (a?b?c)\n"
        f"  • {E['ok']} Безлимитный поиск\n\n"
        "Выберите действие ниже 👇"
    )

    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")
    await message.answer(
        f"{E['info']} <b>Документы бота:</b>",
        reply_markup=get_documents_keyboard(),
        parse_mode="HTML",
    )


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
            expire_line = f"\n{E['clock']} Действует до: <b>{until_str}</b>"
        else:
            expire_line = f"\n{E['clock']} Срок: <b>бессрочно</b>"

        await message.answer(
            f"{E['diamond']} <b>У вас уже есть Premium!</b>{expire_line}\n\n"
            f"{E['ok']} Безлимитный поиск\n"
            f"{E['ok']} Поиск 5-буквенных ников\n"
            f"{E['ok']} Фильтр по маске",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
        return

    await message.answer(
        f"{E['diamond']} <b>Premium подписка</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "<b>Что открывает Premium:</b>\n"
        f"  {E['search']} Поиск редких 5-буквенных ников\n"
        f"  {E['ok']} Фильтр по маске (a?b?c → любые буквы)\n"
        f"  {E['ok']} Безлимитный поиск без ограничений\n\n"
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
        f"{E['wallet']} <b>Оплата Premium — {name}</b>\n\n"
        f"{E['money']} Сумма: <b>{amount}₽</b>\n\n"
        f"Нажмите кнопку ниже для оплаты через СБП:",
        parse_mode="HTML",
        reply_markup=get_payment_keyboard(amount, days),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_sbp_"))
async def pay_sbp(callback: CallbackQuery):
    await callback.answer(
        "Оплата временно недоступна.\n"
        "Нажмите «Проверить оплату» для получения Premium.",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment(callback: CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.split("_")
    try:
        days = int(parts[-1])
    except (ValueError, IndexError):
        days = 30

    await db.set_premium(user_id, days=days)

    from datetime import datetime, timedelta
    until = datetime.now() + timedelta(days=days)
    until_str = until.strftime("%d.%m.%Y %H:%M")

    await callback.message.edit_text(
        f"{E['star']} <b>Premium активирован!</b>\n\n"
        f"{E['clock']} Действует до: <b>{until_str}</b>\n\n"
        "<b>Теперь вам доступны:</b>\n"
        f"  {E['ok']} Безлимитный поиск\n"
        f"  {E['search']} Поиск 5-буквенных ников\n"
        f"  {E['ok']} Фильтр по маске",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )
    await callback.answer("Premium активирован!", show_alert=False)


@router.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: CallbackQuery):
    await callback.message.edit_text(
        f"{E['no']} Оплата отменена.",
        parse_mode="HTML",
    )
    await callback.answer()
