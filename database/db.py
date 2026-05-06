"""
Модуль для работы с базой данных SQLite
Хранит информацию о пользователях и их статистике
"""

import aiosqlite
import logging
from datetime import datetime
from typing import Optional, Dict

logger = logging.getLogger(__name__)

DB_PATH = "bot_database.db"


class Database:
    """Класс для работы с базой данных"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
    
    async def init_db(self):
        """Инициализация базы данных и создание таблиц"""
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица пользователей
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    registration_date TEXT,
                    total_searches INTEGER DEFAULT 0,
                    found_usernames INTEGER DEFAULT 0,
                    last_search_date TEXT,
                    is_premium INTEGER DEFAULT 0
                )
            """)
            
            # Добавляем колонку is_premium если её нет (для существующих БД)
            try:
                await db.execute("ALTER TABLE users ADD COLUMN is_premium INTEGER DEFAULT 0")
                await db.commit()
            except Exception:
                pass  # Колонка уже существует
            
            # Таблица статистики по дням
            await db.execute("""
                CREATE TABLE IF NOT EXISTS daily_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    date TEXT,
                    searches_count INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    UNIQUE(user_id, date)
                )
            """)
            
            # Таблица найденных юзернеймов
            await db.execute("""
                CREATE TABLE IF NOT EXISTS found_usernames (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    length INTEGER,
                    liquidity_score INTEGER,
                    found_date TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            await db.commit()
            logger.info("База данных инициализирована")
    
    async def add_user(self, user_id: int, username: Optional[str] = None, 
                      first_name: Optional[str] = None):
        """Добавление нового пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("""
                    INSERT INTO users (user_id, username, first_name, registration_date)
                    VALUES (?, ?, ?, ?)
                """, (user_id, username, first_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                await db.commit()
                logger.info(f"Добавлен новый пользователь: {user_id}")
            except aiosqlite.IntegrityError:
                # Пользователь уже существует
                pass
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Получение информации о пользователе"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM users WHERE user_id = ?
            """, (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                return None
    
    async def update_search_stats(self, user_id: int):
        """Обновление статистики поисков"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        async with aiosqlite.connect(self.db_path) as db:
            # Обновляем общую статистику
            await db.execute("""
                UPDATE users 
                SET total_searches = total_searches + 1,
                    last_search_date = ?
                WHERE user_id = ?
            """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
            
            # Обновляем дневную статистику
            await db.execute("""
                INSERT INTO daily_stats (user_id, date, searches_count)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, date) 
                DO UPDATE SET searches_count = searches_count + 1
            """, (user_id, today))
            
            await db.commit()
    
    async def add_found_username(self, user_id: int, username: str, 
                                 length: int, liquidity_score: int):
        """Добавление найденного юзернейма"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO found_usernames (user_id, username, length, liquidity_score, found_date)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, username, length, liquidity_score, 
                  datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            
            # Увеличиваем счетчик найденных юзернеймов
            await db.execute("""
                UPDATE users 
                SET found_usernames = found_usernames + 1
                WHERE user_id = ?
            """, (user_id,))
            
            await db.commit()
    
    async def get_today_searches(self, user_id: int) -> int:
        """Получение количества поисков за сегодня"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT searches_count FROM daily_stats
                WHERE user_id = ? AND date = ?
            """, (user_id, today)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
    
    async def get_user_stats(self, user_id: int) -> Dict:
        """Получение полной статистики пользователя"""
        user = await self.get_user(user_id)
        if not user:
            return {}
        
        today_searches = await self.get_today_searches(user_id)
        
        return {
            "user_id": user["user_id"],
            "username": user["username"],
            "registration_date": user["registration_date"],
            "total_searches": user["total_searches"],
            "found_usernames": user["found_usernames"],
            "today_searches": today_searches
        }


    async def check_premium(self, user_id: int) -> bool:
        """Проверка премиум статуса пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT is_premium FROM users WHERE user_id = ?
            """, (user_id,)) as cursor:
                row = await cursor.fetchone()
                return bool(row[0]) if row else False

    async def set_premium(self, user_id: int, status: bool = True):
        """Установка премиум статуса пользователю"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users SET is_premium = ? WHERE user_id = ?
            """, (int(status), user_id))
            await db.commit()


# Глобальный экземпляр базы данных
db = Database()
