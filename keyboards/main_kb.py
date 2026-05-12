"""
Клавиатуры бота с премиум эмодзи
"""

from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)


def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔍 ПОИСК"),
                KeyboardButton(text="💎 Премиум"),
            ],
            [
                KeyboardButton(text="👤 Профиль"),
                KeyboardButton(text="🆘 Поддержка"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие...",
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Отмена", icon_custom_emoji_id="5870657884844462243")],
        ],
        resize_keyboard=True,
    )


def get_search_control_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="Остановить поиск",
                callback_data="stop_search",
                icon_custom_emoji_id="5870657884844462243",
            )],
        ]
    )


def get_documents_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Польз. соглашение",
                    url="https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19",
                    icon_custom_emoji_id="5769289093221454192",
                ),
                InlineKeyboardButton(
                    text="Конфиденциальность",
                    url="https://telegra.ph/Politika-konfidencialnosti-04-01-26",
                    icon_custom_emoji_id="6037249452824072506",
                ),
            ]
        ]
    )


def get_search_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="5 букв", callback_data="search_5", icon_custom_emoji_id="5870676941614354370"),
                InlineKeyboardButton(text="6 букв", callback_data="search_6", icon_custom_emoji_id="5870676941614354370"),
            ],
            [
                InlineKeyboardButton(text="Фильтр", callback_data="search_filter", icon_custom_emoji_id="5870982283724328568"),
            ],
        ]
    )


def get_premium_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="Купить Premium",
                callback_data="buy_premium",
                icon_custom_emoji_id="6032644646587338669",
            )],
        ]
    )


def get_premium_plans_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="3 часа — 1₽",    callback_data="plan_3_1",    icon_custom_emoji_id="5904462880941545555")],
            [InlineKeyboardButton(text="2 дня — 100₽",   callback_data="plan_2_100",  icon_custom_emoji_id="5904462880941545555")],
            [InlineKeyboardButton(text="4 дня — 175₽",   callback_data="plan_4_175",  icon_custom_emoji_id="5904462880941545555")],
            [InlineKeyboardButton(text="10 дней — 300₽", callback_data="plan_10_300", icon_custom_emoji_id="5904462880941545555")],
            [InlineKeyboardButton(text="30 дней — 650₽", callback_data="plan_30_650", icon_custom_emoji_id="5904462880941545555")],
        ]
    )


def get_payment_keyboard(amount: int, days: int = 30) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="Оплатить СБП",
                callback_data=f"pay_sbp_{amount}_{days}",
                icon_custom_emoji_id="5879814368572478751",
            )],
            [InlineKeyboardButton(
                text="Проверить оплату",
                callback_data=f"check_payment_{amount}_{days}",
                icon_custom_emoji_id="5870633910337015697",
            )],
            [InlineKeyboardButton(
                text="Отмена",
                callback_data="cancel_payment",
                icon_custom_emoji_id="5870657884844462243",
            )],
        ]
    )
