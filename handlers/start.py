"""
Обработчик команды /start и главного меню
"""

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards.main_kb import get_main_keyboard, get_documents_keyboard, get_premium_plans_keyboard
from database.db import db

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """
    Обработчик команды /start
    Регистрирует пользователя и показывает главное меню
    """
    # Очищаем состояние FSM
    await state.clear()
    
    # Регистрируем пользователя в базе данных
    await db.add_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )
    
    # Получаем статистику пользователя для отображения попыток
    stats = await db.get_user_stats(message.from_user.id)
    attempts_left = 3 - stats.get('today_searches', 0)
    if attempts_left < 0:
        attempts_left = 0
    
    # Проверяем премиум статус
    has_premium = await db.check_premium(message.from_user.id)
    
    # Текст приветствия
    username = message.from_user.username or "username"
    welcome_text = (
        f"⚡️codedev || {username} — поиск свободных ников\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"🎯 Попытки: {attempts_left if not has_premium else '∞'}/{'∞' if has_premium else '3'}\n"
        "💎 Premium открывает:\n"
        "• Поиск редких 5-буквенных ников\n"
        "• Фильтр по маске (a?b?c → любые буквы)\n"
        "• Безлимитный поиск без ограничений\n\n"
        "Выберите действие ниже 👇"
    )
    
    # Отправляем приветствие с клавиатурой
    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )
    
    # Отправляем документы
    documents_text = "📋 Документы бота:"
    await message.answer(
        documents_text,
        reply_markup=get_documents_keyboard(),
        parse_mode="HTML"
    )


@router.message(F.text == "💎 Премиум")
async def show_premium(message: Message):
    """
    Показ информации о премиум подписке
    """
    user_id = message.from_user.id
    has_premium = await db.check_premium(user_id)

    if has_premium:
        await message.answer(
            "💎 <b>У вас уже есть Premium!</b>\n\n"
            "• Безлимитный поиск ✅\n"
            "• Поиск 5-буквенных ников ✅\n"
            "• Фильтр по маске ✅",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
        return

    premium_text = (
        "💎 <b>Premium подписка</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "Что открывает Premium:\n"
        "• 🔍 Поиск редких 5-буквенных ников\n"
        "• 🎭 Фильтр по маске (a?b?c → любые буквы)\n"
        "• ♾️ Безлимитный поиск без ограничений\n\n"
        "Выберите тариф:"
    )

    await message.answer(
        premium_text,
        parse_mode="HTML",
        reply_markup=get_premium_plans_keyboard()
    )


@router.callback_query(F.data.startswith("plan_"))
async def handle_premium_plan(callback: CallbackQuery):
    """
    Обработка выбора тарифного плана
    """
    from keyboards.main_kb import get_payment_keyboard

    plans = {
        "plan_2_100": ("2 дня", 100),
        "plan_4_175": ("4 дня", 175),
        "plan_10_300": ("10 дней", 300),
        "plan_30_650": ("30 дней", 650),
    }

    plan = plans.get(callback.data)
    if not plan:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return

    days, amount = plan
    await callback.message.edit_text(
        f"💳 <b>Оплата Premium — {days}</b>\n\n"
        f"Сумма: <b>{amount}₽</b>\n\n"
        f"Нажмите кнопку ниже для оплаты через СБП:",
        parse_mode="HTML",
        reply_markup=get_payment_keyboard(amount)
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: CallbackQuery):
    """
    Отмена оплаты
    """
    await callback.message.edit_text(
        "❌ Оплата отменена.",
        parse_mode="HTML"
    )
    await callback.answer()
