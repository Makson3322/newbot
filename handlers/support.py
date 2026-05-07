"""
Обработчик раздела поддержки
"""

from aiogram import Router, F
from aiogram.types import Message
from keyboards.main_kb import get_main_keyboard

router = Router()

E = {
    "support": '<tg-emoji emoji-id="6039422865189638057">📣</tg-emoji>',
    "msg":     '<tg-emoji emoji-id="5870676941614354370">✍</tg-emoji>',
    "clock":   '<tg-emoji emoji-id="5983150113483134607">⏰</tg-emoji>',
    "info":    '<tg-emoji emoji-id="6028435952299413210">ℹ</tg-emoji>',
    "ok":      '<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji>',
}


@router.message(F.text == "🆘 Поддержка")
async def show_support(message: Message):
    support_text = (
        f"{E['support']} <b>Поддержка codedev | UserName</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "Если у вас возникли вопросы, проблемы с ботом\n"
        "или предложения по улучшению — мы всегда на связи!\n\n"
        f"{E['msg']} Написать: @vwibx\n\n"
        f"{E['clock']} Среднее время ответа: до 24 часов\n\n"
        f"{E['info']} Опишите проблему подробно:\n"
        "укажите ваш ID, что не работает и как воспроизвести."
    )

    await message.answer(
        support_text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )
