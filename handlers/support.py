"""
Обработчик раздела поддержки
"""

from aiogram import Router, F
from aiogram.types import Message

from keyboards.main_kb import get_main_keyboard

router = Router()


@router.message(F.text == "🆘 Поддержка")
async def show_support(message: Message):
    """
    Показ информации о поддержке
    """
    support_text = (
        "🆘 <b>Поддержка codedev | UserName</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "Если у вас возникли вопросы, проблемы с ботом\n"
        "или предложения по улучшению — мы всегда на связи!\n\n"
        "📩 Бот поддержки: @vwibx\n\n"
        "⏱️ Среднее время ответа: до 24 часов\n\n"
        "💡 Опишите проблему подробно:\n"
        "укажите ваш ID, что не работает и как воспроизвести."
    )
    
    await message.answer(
        support_text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )
