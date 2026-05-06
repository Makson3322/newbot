"""
Обработчик поиска по маске (фильтр)
"""

import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from services.username_generator import generator
from services.username_checker import UsernameChecker, BATCH_SIZE
from database.db import db
from keyboards.main_kb import get_main_keyboard, get_cancel_keyboard

router = Router()
logger = logging.getLogger(__name__)


def _detect_pattern(username: str) -> str:
    """
    Определяет тип паттерна юзернейма для красивого отображения
    
    Args:
        username: Юзернейм для анализа
    
    Returns:
        Строка с описанием паттерна
    """
    length = len(username)
    unique_chars = len(set(username))
    
    # Все буквы одинаковые - ЛЕГЕНДА
    if unique_chars == 1:
        return " 🔥 (все одинаковые)"
    
    # Чередование 2 букв
    if unique_chars == 2 and length >= 4:
        if username[:2] * (length // 2) == username[:length - length % 2]:
            return " ⚡️ (чередование)"
        else:
            return " ⭐️ (2 буквы)"
    
    # Двойные буквы
    has_doubles = False
    for i in range(length - 1):
        if username[i] == username[i + 1]:
            has_doubles = True
            break
    
    if has_doubles:
        return " 💫 (двойные)"
    
    # Произносимый (чередование гласных/согласных)
    vowels = set('aeiou')
    alternating = True
    for i in range(length - 1):
        curr_vowel = username[i] in vowels
        next_vowel = username[i + 1] in vowels
        if curr_vowel == next_vowel:
            alternating = False
            break
    
    if alternating and length >= 4:
        return " ✨ (произносимый)"
    
    return ""


class FilterStates(StatesGroup):
    """Состояния FSM для фильтра"""
    waiting_for_mask = State()


@router.message(F.text == "🔍 Фильтр")
async def filter_menu_msg(message: Message, state: FSMContext):
    """
    Меню фильтра по маске (через текстовую кнопку)
    """
    await _show_filter_menu(message, state)


@router.callback_query(F.data == "search_filter")
async def filter_menu_callback(callback: CallbackQuery, state: FSMContext):
    """
    Меню фильтра по маске (через inline кнопку)
    """
    await callback.answer()
    await _show_filter_menu(callback.message, state)


async def _show_filter_menu(message: Message, state: FSMContext):
    """
    Общая логика показа меню фильтра
    """
    filter_text = (
        "🔍 <b>Фильтр по маске — функция Premium</b>\n\n"
        "• Буква <code>a-z</code> = фиксированный символ\n"
        "• Знак <code>?</code> = любая случайная буква\n\n"
        "<b>Пример:</b> <code>a?s?a</code> → amswa, azsba\n\n"
        "Введите маску для поиска:"
    )
    
    await message.answer(
        filter_text,
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    
    # Устанавливаем состояние ожидания маски
    await state.set_state(FilterStates.waiting_for_mask)


@router.message(FilterStates.waiting_for_mask, F.text == "Отмена")
async def cancel_filter(message: Message, state: FSMContext):
    """
    Отмена ввода маски
    """
    await state.clear()
    await message.answer(
        "❌ Отменено",
        reply_markup=get_main_keyboard()
    )


@router.message(FilterStates.waiting_for_mask)
async def process_mask(message: Message, state: FSMContext, bot: Bot):
    """
    Обработка введенной маски и поиск
    """
    mask = message.text.strip()
    user_id = message.from_user.id
    
    # Валидация маски
    is_valid, error_message = generator.validate_mask(mask)
    
    if not is_valid:
        await message.answer(
            f"❌ <b>Ошибка в маске:</b>\n{error_message}\n\n"
            f"Попробуйте еще раз или нажмите Отмена",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    # Очищаем состояние
    await state.clear()
    
    # Отправляем сообщение о начале поиска
    search_msg = await message.answer(
        f"🔍 <b>Начинаю поиск по маске: {mask}</b>\n\n"
        f"⚡️ Проверяю пачками по {BATCH_SIZE} ников параллельно...",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )
    
    try:
        checker = UsernameChecker(bot)
        attempts = 0
        max_attempts = 1000
        found = False

        while attempts < max_attempts:
            # Генерируем пачку по маске
            batch = [generator.generate_by_mask(mask) for _ in range(BATCH_SIZE)]
            attempts += BATCH_SIZE

            # Обновляем сообщение раз в ~50 проверок
            if (attempts // BATCH_SIZE) % 5 == 0:
                try:
                    await search_msg.edit_text(
                        f"🔍 <b>Поиск по маске: {mask}</b>\n\n"
                        f"⚡️ Проверено: <b>{attempts}</b> вариантов\n"
                        f"🔄 Последний: @{batch[-1]}",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

            results = await checker.check_batch(batch)

            for username, is_available, status in results:
                if is_available:
                    found = True
                    length = len(username)
                    liquidity_score, liquidity_level = generator.calculate_liquidity(username)

                    await db.update_search_stats(user_id)
                    await db.add_found_username(user_id, username, length, liquidity_score)

                    pattern_type = _detect_pattern(username)

                    if liquidity_score >= 9:
                        header = "🔥 <b>ЛЕГЕНДА НАЙДЕНА!</b> 🔥"
                    elif liquidity_score >= 8:
                        header = "💎 <b>ТОПЧИК НАЙДЕН!</b> 💎"
                    elif liquidity_score >= 7:
                        header = "⚡️ <b>БЛАТНОЙ НИК!</b> ⚡️"
                    elif liquidity_score >= 6:
                        header = "✨ <b>ГОДНЫЙ НИК!</b> ✨"
                    else:
                        header = "✅ <b>НИК НАЙДЕН!</b>"

                    result_text = (
                        f"{header}\n\n"
                        f"<code>@{username}</code>\n"
                        f"└ {length} букв (маска: {mask}){pattern_type}\n\n"
                        f"├ Ликвидность — <b>{liquidity_score}</b> из 10 {liquidity_level}\n"
                        f"├ Проверено вариантов: <b>{attempts}</b>\n"
                        f"└ Свободен ⚡️\n\n"
                        f"📢 @codedev_username_bot"
                    )

                    try:
                        await search_msg.delete()
                    except Exception:
                        pass

                    await message.answer(
                        result_text,
                        parse_mode="HTML",
                        reply_markup=get_main_keyboard()
                    )
                    break

            if found:
                break

        await checker.close()

        if not found:
            await search_msg.edit_text(
                f"⚠️ <b>Поиск завершён</b>\n\n"
                f"Проверено {attempts} вариантов по маске <code>{mask}</code>, "
                f"свободный ник не найден.\nПопробуйте изменить маску!",
                parse_mode="HTML"
            )
    
    except Exception as e:
        logger.error(f"Ошибка при поиске по маске: {e}")
        await message.answer(
            "❌ Произошла ошибка при поиске.\n"
            "Попробуйте еще раз позже.",
            reply_markup=get_main_keyboard()
        )
