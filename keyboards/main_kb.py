"""
Модуль с клавиатурами для бота
"""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """
    Главная клавиатура бота
    
    Returns:
        ReplyKeyboardMarkup с основными кнопками
    """
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔍 ПОИСК"),
                KeyboardButton(text="💎 Премиум")
            ],
            [
                KeyboardButton(text="👤 Профиль"),
                KeyboardButton(text="🆘 Поддержка")
            ]
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )
    return keyboard


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """
    Клавиатура с кнопкой отмены
    
    Returns:
        ReplyKeyboardMarkup с кнопкой отмены
    """
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Отмена")]
        ],
        resize_keyboard=True
    )
    return keyboard


def get_search_control_keyboard() -> InlineKeyboardMarkup:
    """
    Inline клавиатура для управления поиском
    
    Returns:
        InlineKeyboardMarkup с кнопкой остановки поиска
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏹ Остановить поиск", callback_data="stop_search")]
        ]
    )
    return keyboard


def get_documents_keyboard() -> InlineKeyboardMarkup:
    """
    Inline клавиатура с документами бота
    
    Returns:
        InlineKeyboardMarkup с кнопками документов
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📜 Польз. соглашение", url="https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19"),
                InlineKeyboardButton(text="🔒 Конфиденциальность", url="https://telegra.ph/Politika-konfidencialnosti-04-01-26")
            ]
        ]
    )
    return keyboard


def get_search_type_keyboard() -> InlineKeyboardMarkup:
    """
    Inline клавиатура для выбора типа поиска
    
    Returns:
        InlineKeyboardMarkup с кнопками типов поиска
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="5 букв", callback_data="search_5"),
                InlineKeyboardButton(text="6 букв", callback_data="search_6")
            ],
            [
                InlineKeyboardButton(text="Фильтр", callback_data="search_filter")
            ]
        ]
    )
    return keyboard


def get_premium_keyboard() -> InlineKeyboardMarkup:
    """
    Inline клавиатура для покупки премиума
    
    Returns:
        InlineKeyboardMarkup с кнопкой покупки
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купить Premium", callback_data="buy_premium")]
        ]
    )
    return keyboard


def get_premium_plans_keyboard() -> InlineKeyboardMarkup:
    """
    Inline клавиатура с тарифами премиума
    
    Returns:
        InlineKeyboardMarkup с тарифными планами
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="2 дня — 100₽", callback_data="plan_2_100")],
            [InlineKeyboardButton(text="4 дня — 175₽", callback_data="plan_4_175")],
            [InlineKeyboardButton(text="10 дней — 300₽", callback_data="plan_10_300")],
            [InlineKeyboardButton(text="30 дней — 650₽", callback_data="plan_30_650")]
        ]
    )
    return keyboard


def get_payment_keyboard(amount: int, days: int = 30) -> InlineKeyboardMarkup:
    """
    Inline клавиатура для оплаты.
    days передаётся в check_payment чтобы знать на сколько выдавать премиум.
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить СБП", callback_data=f"pay_sbp_{amount}_{days}")],
            [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_payment_{amount}_{days}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_payment")],
        ]
    )
    return keyboard
