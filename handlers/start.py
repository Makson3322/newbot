"""
Обработчик команды /start, главного меню и оплаты через Platega.io
"""

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from keyboards.main_kb import (
    get_main_keyboard, get_documents_keyboard,
    get_premium_plans_keyboard,
)
from database.db import db
from services.platega import create_payment, get_payment_status

logger = logging.getLogger(__name__)
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
    "star":    '<tg-emoji emoji-id="6041731551845159060">🎉</tg-emoji>',
    "info":    '<tg-emoji emoji-id="6028435952299413210">ℹ</tg-emoji>',
    "wallet":  '<tg-emoji emoji-id="5769126056262898415">👛</tg-emoji>',
    "refresh": '<tg-emoji emoji-id="5345906554510012647">🔄</tg-emoji>',
}


def get_pay_keyboard(pay_url: str, transaction_id: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой оплаты и проверки."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Оплатить СБП",
            url=pay_url,
            icon_custom_emoji_id="5879814368572478751",
        )],
        [InlineKeyboardButton(
            text="Проверить оплату",
            callback_data=f"check_pay_{transaction_id}",
            icon_custom_emoji_id="5870633910337015697",
        )],
        [InlineKeyboardButton(
            text="Отмена",
            callback_data="cancel_payment",
            icon_custom_emoji_id="5870657884844462243",
        )],
    ])


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


# ------------------------------------------------------------------ #
#  Премиум — показ тарифов                                             #
# ------------------------------------------------------------------ #

@router.message(F.text == "💎 Премиум")
async def show_premium(message: Message):
    user_id = message.from_user.id
    has_premium = await db.check_premium(user_id)

    if has_premium:
        until = await db.get_premium_until(user_id)
        if until:
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


# ------------------------------------------------------------------ #
#  Выбор тарифа → создание платежа Platega                            #
# ------------------------------------------------------------------ #

@router.callback_query(F.data.startswith("plan_"))
async def handle_premium_plan(callback: CallbackQuery):
    plan = PLANS.get(callback.data)
    if not plan:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return

    name, days, amount = plan
    user_id = callback.from_user.id

    await callback.answer()
    await callback.message.edit_text(
        f"{E['refresh']} <b>Создаю платёж...</b>",
        parse_mode="HTML",
    )

    # Создаём платёж через Platega API
    result = await create_payment(amount=amount, days=days, user_id=user_id)

    if not result:
        await callback.message.edit_text(
            f"{E['no']} <b>Ошибка создания платежа.</b>\n\n"
            "Попробуйте позже или обратитесь в поддержку @vwibx",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Назад", callback_data="back_to_plans",
                                      icon_custom_emoji_id="5893057118545646106")]
            ]),
        )
        return

    transaction_id = result["transactionId"]
    pay_url = result["redirect"]
    expires = result.get("expiresIn", "30:00")

    # Сохраняем платёж в БД
    await db.create_payment(
        transaction_id=transaction_id,
        user_id=user_id,
        amount=amount,
        days=days,
    )

    await callback.message.edit_text(
        f"{E['wallet']} <b>Оплата Premium — {name}</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"{E['money']} Сумма: <b>{amount}₽</b>\n"
        f"{E['clock']} Действует: <b>{expires}</b>\n\n"
        "1. Нажмите <b>«Оплатить СБП»</b>\n"
        "2. Оплатите по QR-коду\n"
        "3. Нажмите <b>«Проверить оплату»</b>",
        parse_mode="HTML",
        reply_markup=get_pay_keyboard(pay_url, transaction_id),
    )


@router.callback_query(F.data == "back_to_plans")
async def back_to_plans(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        f"{E['diamond']} <b>Premium подписка</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "<b>Что открывает Premium:</b>\n"
        f"  {E['search']} Поиск редких 5-буквенных ников\n"
        f"  {E['ok']} Фильтр по маске\n"
        f"  {E['ok']} Безлимитный поиск\n\n"
        "Выберите тариф:",
        parse_mode="HTML",
        reply_markup=get_premium_plans_keyboard(),
    )


# ------------------------------------------------------------------ #
#  Проверка оплаты                                                     #
# ------------------------------------------------------------------ #

@router.callback_query(F.data.startswith("check_pay_"))
async def check_payment(callback: CallbackQuery, bot: Bot):
    transaction_id = callback.data.replace("check_pay_", "")
    user_id = callback.from_user.id

    await callback.answer()

    # Сначала проверяем в своей БД
    payment = await db.get_payment(transaction_id)

    # Если в своей БД ещё PENDING — спрашиваем у Platega напрямую
    if not payment or payment.get("status") == "PENDING":
        status = await get_payment_status(transaction_id)
        if status == "CONFIRMED" and payment:
            await db.confirm_payment(transaction_id)
            payment["status"] = "CONFIRMED"
        elif status in ("CANCELED", "CHARGEBACK") and payment:
            await db.cancel_payment(transaction_id)
            payment["status"] = status
    else:
        status = payment.get("status", "PENDING")

    if not payment:
        await callback.message.edit_text(
            f"{E['no']} Платёж не найден. Попробуйте создать новый.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Назад к тарифам", callback_data="back_to_plans",
                                      icon_custom_emoji_id="5893057118545646106")]
            ]),
        )
        return

    current_status = payment.get("status", "PENDING")

    if current_status == "CONFIRMED":
        days = payment.get("days", 30)

        # Проверяем не выдан ли уже (защита от дублей)
        already = await db.check_premium(user_id)
        if not already:
            await db.set_premium(user_id, days=days)

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

    elif current_status in ("CANCELED", "CHARGEBACK"):
        await callback.message.edit_text(
            f"{E['no']} <b>Платёж отменён.</b>\n\n"
            "Попробуйте оплатить снова.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Попробовать снова", callback_data="back_to_plans",
                                      icon_custom_emoji_id="5893057118545646106")]
            ]),
        )

    else:
        # Всё ещё PENDING
        await callback.message.answer(
            f"{E['clock']} <b>Оплата ещё не поступила.</b>\n\n"
            "Оплатите по ссылке выше и нажмите «Проверить оплату» снова.\n"
            "Обычно оплата подтверждается за 1-2 минуты.",
            parse_mode="HTML",
        )


@router.callback_query(F.data == "cancel_payment")
async def cancel_payment_cb(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        f"{E['no']} Оплата отменена.",
        parse_mode="HTML",
    )
