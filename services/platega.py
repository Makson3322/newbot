"""
Сервис для работы с Platega.io API.

Создание платежа:
  POST https://app.platega.io/transaction/process

Проверка статуса:
  GET https://app.platega.io/transaction/{transaction_id}
  ИЛИ через свою БД (PHP API): GET https://yoursite.ru/api/payment-status?txn=...

Вебхук принимает PHP-скрипт codersdev/webhook_platega.php,
который сохраняет результат в MySQL.
Бот опрашивает статус через свой PHP API.
"""

import os
import logging
import aiohttp
from typing import Optional, Dict

logger = logging.getLogger(__name__)

PLATEGA_API  = "https://app.platega.io"
MERCHANT_ID  = os.getenv("PLATEGA_MERCHANT_ID", "")
SECRET       = os.getenv("PLATEGA_SECRET", "")
SITE_URL     = os.getenv("SITE_URL", "https://yoursite.ru")

# СБП QR = 2
PAYMENT_METHOD_SBP = 2


def _headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-MerchantId": MERCHANT_ID,
        "X-Secret": SECRET,
    }


async def create_payment(amount: int, days: int, user_id: int) -> Optional[Dict]:
    """
    Создаёт платёж через Platega.
    Возвращает dict: { transactionId, redirect, status, expiresIn }
    или None при ошибке.
    payload = "user_id:days" — используется при обработке вебхука.
    """
    body = {
        "paymentMethod": PAYMENT_METHOD_SBP,
        "paymentDetails": {
            "amount": float(amount),
            "currency": "RUB",
        },
        "description": f"Premium {days} дн. | @codedev_username_bot",
        "return": f"https://t.me/codedev_username_bot",
        "failedUrl": f"https://t.me/codedev_username_bot",
        "payload": f"{user_id}:{days}",
    }

    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{PLATEGA_API}/transaction/process",
                json=body,
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                logger.info(f"Platega create_payment: {data}")
                if resp.status == 200 and "transactionId" in data:
                    return data
                logger.error(f"Platega error {resp.status}: {data}")
                return None
    except Exception as e:
        logger.error(f"Platega create_payment exception: {e}")
        return None


async def get_payment_status_from_platega(transaction_id: str) -> Optional[str]:
    """
    Прямой запрос к Platega API для проверки статуса.
    Возвращает: PENDING | CONFIRMED | CANCELED | CHARGEBACK | None
    """
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{PLATEGA_API}/transaction/{transaction_id}",
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                logger.info(f"Platega status {transaction_id}: {data}")
                return data.get("status")
    except Exception as e:
        logger.error(f"Platega get_status exception: {e}")
        return None


async def get_payment_status_from_db(transaction_id: str) -> Optional[str]:
    """
    Проверяет статус платежа через PHP API сайта (читает из MySQL).
    Возвращает: PENDING | CONFIRMED | CANCELED | CHARGEBACK | None
    """
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{SITE_URL}/api/payment-status",
                params={"txn": transaction_id},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("status")
                return None
    except Exception as e:
        logger.error(f"DB status check exception: {e}")
        return None


async def get_payment_status(transaction_id: str) -> Optional[str]:
    """
    Сначала пробует получить статус из своей БД (через PHP),
    если не получилось — спрашивает напрямую у Platega.
    """
    status = await get_payment_status_from_db(transaction_id)
    if status:
        return status
    return await get_payment_status_from_platega(transaction_id)
