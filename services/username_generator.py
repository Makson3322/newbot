"""
Модуль для генерации юзернеймов и оценки их ликвидности
"""

import random
import string
import re
from typing import Tuple


class UsernameGenerator:
    """Класс для генерации и оценки юзернеймов"""
    
    def __init__(self):
        # Только латинские буквы в нижнем регистре
        self.letters = string.ascii_lowercase
        
        # Популярные гласные и согласные для блатных ников
        self.vowels = 'aeiou'
        self.consonants = 'bcdfghjklmnpqrstvwxyz'
        
        # Топовые согласные (часто используются в крутых никах)
        self.top_consonants = 'bcdklmnprstvxz'
        
        # Популярные двухбуквенные комбинации
        self.cool_pairs = ['ab', 'ad', 'ak', 'al', 'am', 'an', 'ar', 'as', 'at', 'ax',
                          'ba', 'be', 'bo', 'by',
                          'ca', 'co', 'da', 'de', 'do',
                          'ed', 'el', 'em', 'en', 'er', 'ex',
                          'go', 'ha', 'he', 'hi', 'ho',
                          'id', 'in', 'is', 'it',
                          'ja', 'jo', 'ka', 'ke', 'ki', 'ko',
                          'la', 'le', 'li', 'lo',
                          'ma', 'me', 'mi', 'mo', 'my',
                          'na', 'ne', 'ni', 'no',
                          'od', 'ok', 'on', 'or', 'ox',
                          'pa', 'pe', 'pi', 'po',
                          'ra', 're', 'ri', 'ro',
                          'sa', 'se', 'si', 'so',
                          'ta', 'te', 'ti', 'to',
                          'up', 'us',
                          'va', 've', 'vi', 'vo',
                          'we', 'wi', 'wo',
                          'xa', 'xe', 'xi',
                          'ya', 'ye', 'yo',
                          'za', 'ze', 'zo']
    
    def is_valid_telegram_username(self, username: str) -> bool:
        """
        Проверка юзернейма на соответствие правилам Telegram
        
        Правила Telegram:
        - Длина от 5 до 32 символов
        - Только латинские буквы (a-z, A-Z), цифры (0-9) и подчеркивания (_)
        - Должен начинаться с буквы
        - Не может заканчиваться на "bot"
        - Не может содержать два подчеркивания подряд
        - Не может начинаться или заканчиваться подчеркиванием
        
        Args:
            username: Юзернейм для проверки
        
        Returns:
            True если юзернейм валиден, False если нет
        """
        if not username:
            return False
        
        # Проверка длины
        if len(username) < 5 or len(username) > 32:
            return False
        
        # Должен начинаться с буквы
        if not username[0].isalpha():
            return False
        
        # Не может заканчиваться на "bot" (регистронезависимо)
        if username.lower().endswith('bot'):
            return False
        
        # Проверка допустимых символов (только буквы, цифры и подчеркивания)
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', username):
            return False
        
        # Не может содержать два подчеркивания подряд
        if '__' in username:
            return False
        
        # Не может заканчиваться подчеркиванием
        if username.endswith('_'):
            return False
        
        return True
    
    def generate_random(self, length: int) -> str:
        """
        Генерация РЕАЛЬНО блатного юзернейма
        
        Фокус на простые, запоминающиеся, произносимые ники
        
        Args:
            length: Длина юзернейма (5 или 6 букв)
        
        Returns:
            Сгенерированный юзернейм
        """
        # 90% шанс генерации блатного юзернейма
        if random.random() < 0.9:
            return self.generate_premium(length)
        
        # 10% обычная генерация
        return ''.join(random.choice(self.letters) for _ in range(length))
    
    def generate_by_mask(self, mask: str) -> str:
        """
        Генерация юзернейма по маске
        
        Args:
            mask: Маска (например: "a?s?a" где ? - случайная буква)
        
        Returns:
            Сгенерированный юзернейм
        """
        result = []
        for char in mask.lower():
            if char == '?':
                result.append(random.choice(self.letters))
            elif char in self.letters:
                result.append(char)
            else:
                # Игнорируем недопустимые символы
                continue
        
        return ''.join(result)
    
    def validate_mask(self, mask: str) -> Tuple[bool, str]:
        """
        Проверка корректности маски
        
        Args:
            mask: Маска для проверки
        
        Returns:
            Tuple[bool, str]: (валидна ли маска, сообщение об ошибке)
        """
        if not mask:
            return False, "Маска не может быть пустой"
        
        # Убираем пробелы
        mask = mask.strip()
        
        # Проверяем длину (от 4 до 32 символов для Telegram)
        if len(mask) < 4:
            return False, "Маска слишком короткая (минимум 4 символа)"
        
        if len(mask) > 32:
            return False, "Маска слишком длинная (максимум 32 символа)"
        
        # Проверяем допустимые символы (только a-z и ?)
        if not re.match(r'^[a-z?]+$', mask.lower()):
            return False, "Маска может содержать только буквы a-z и символ ?"
        
        return True, "OK"
    
    def calculate_liquidity(self, username: str) -> Tuple[int, str]:
        """
        Расчет ликвидности РЕАЛЬНО блатных юзернеймов от 1 до 10
        
        Критерии:
        - Простота и запоминаемость
        - Произносимость
        - Короткие = лучше
        - Повторы = круто
        
        Args:
            username: Юзернейм для оценки
        
        Returns:
            Tuple[int, str]: (оценка от 1 до 10, описание уровня)
        """
        score = 2  # Базовая оценка
        length = len(username)
        unique_chars = len(set(username))
        vowels = set('aeiou')
        
        # 1. ДЛИНА - чем короче, тем блатнее
        if length <= 3:
            score += 6  # ТОПЧИК
        elif length == 4:
            score += 5
        elif length == 5:
            score += 4
        elif length == 6:
            score += 3
        else:
            score += 1
        
        # 2. ВСЕ ОДИНАКОВЫЕ БУКВЫ - ЛЕГЕНДА
        if unique_chars == 1:
            score += 6  # aaaaa, bbbbb - ЭТО ОГОНЬ
        
        # 3. ЧЕРЕДОВАНИЕ 2 БУКВ - БЛАТНО
        elif unique_chars == 2:
            # Проверяем чередование (ababa, kakak)
            if length >= 4 and username[:2] * (length // 2) == username[:length - length % 2]:
                score += 5  # Идеальное чередование
            else:
                score += 3  # Просто 2 буквы
        
        # 4. ПРОИЗНОСИМОСТЬ - ВАЖНО
        # Считаем чередование гласных/согласных
        alternating_count = 0
        for i in range(length - 1):
            curr_vowel = username[i] in vowels
            next_vowel = username[i + 1] in vowels
            if curr_vowel != next_vowel:
                alternating_count += 1
        
        # Если почти всё чередуется - ГОДНОТА
        if alternating_count >= length - 2:
            score += 3  # Легко произносится
        elif alternating_count >= length // 2:
            score += 1
        
        # 5. ДВОЙНЫЕ БУКВЫ - КРАСИВО
        has_doubles = False
        for i in range(length - 1):
            if username[i] == username[i + 1]:
                has_doubles = True
                score += 1
                break
        
        # 6. ПОПУЛЯРНЫЕ КОМБИНАЦИИ
        cool_starts = ['al', 'an', 'ar', 'be', 'bo', 'da', 'el', 'ja', 'jo', 'ka', 'le', 'ma', 'mi', 'na', 'ra', 're', 'sa', 'ta', 've', 'za']
        if length >= 2 and username[:2] in cool_starts:
            score += 1
        
        # 7. ШТРАФ ЗА МНОГО СОГЛАСНЫХ ПОДРЯД
        max_consonants = 0
        consonants_in_row = 0
        for char in username:
            if char not in vowels:
                consonants_in_row += 1
                max_consonants = max(max_consonants, consonants_in_row)
            else:
                consonants_in_row = 0
        
        if max_consonants >= 4:
            score -= 3  # Хрень непроизносимая
        elif max_consonants >= 3:
            score -= 1
        
        # 8. ШТРАФ ЗА МНОГО УНИКАЛЬНЫХ БУКВ
        if unique_chars >= length - 1:
            score -= 1  # Слишком сложно
        
        # Ограничиваем от 1 до 10
        score = max(1, min(10, score))
        
        # Определяем уровень
        if score >= 9:
            level = "🔥 ЛЕГЕНДА"
        elif score >= 8:
            level = "💎 ТОПЧИК"
        elif score >= 7:
            level = "⚡️ БЛАТНОЙ"
        elif score >= 6:
            level = "✨ ГОДНЫЙ"
        elif score >= 4:
            level = "👌 НОРМ"
        else:
            level = "📉 СЛАБО"
        
        return score, level
    
    def generate_premium(self, length: int) -> str:
        """
        Генерация РЕАЛЬНО блатного юзернейма
        Простые, запоминающиеся, произносимые ники
        
        Args:
            length: Длина юзернейма
        
        Returns:
            Сгенерированный юзернейм
        """
        patterns = [
            # Все одинаковые буквы (aaaaa) - ТОПЧИК
            (lambda l: random.choice(self.letters) * l, 5),
            
            # Чередование 2 букв (ababa, kakak) - БЛАТНО
            (lambda l: self._generate_alternating(l), 15),
            
            # Простые произносимые (kakao, bebop, lemon) - ГОДНОТА
            (lambda l: self._generate_pronounceable(l), 30),
            
            # Двойные буквы (aabbcc, llama) - КРАСИВО
            (lambda l: self._generate_doubles(l), 10),
            
            # Популярные комбинации (based, toxic, venom) - КРУТЫЕ
            (lambda l: self._generate_cool_combo(l), 25),
            
            # Короткие слова-основы + буква (alex, mark, john) - ИМЕНА
            (lambda l: self._generate_name_like(l), 15),
        ]
        
        # Выбираем паттерн с учётом весов
        total_weight = sum(weight for _, weight in patterns)
        rand = random.uniform(0, total_weight)
        
        current = 0
        for pattern_func, weight in patterns:
            current += weight
            if rand <= current:
                try:
                    result = pattern_func(length)
                    # Проверяем что длина правильная
                    if len(result) == length:
                        return result
                except:
                    pass
        
        # Запасной вариант - произносимый ник
        return self._generate_pronounceable(length)
    
    def _generate_palindrome(self, length: int) -> str:
        """Генерация палиндрома"""
        half = length // 2
        first_half = ''.join(random.choice(self.letters) for _ in range(half))
        
        if length % 2 == 0:
            return first_half + first_half[::-1]
        else:
            middle = random.choice(self.letters)
            return first_half + middle + first_half[::-1]
    
    def _generate_palindrome(self, length: int) -> str:
        """Генерация палиндрома"""
        half = length // 2
        first_half = ''.join(random.choice(self.letters) for _ in range(half))
        
        if length % 2 == 0:
            return first_half + first_half[::-1]
        else:
            middle = random.choice(self.letters)
            return first_half + middle + first_half[::-1]
    
    def _generate_alternating(self, length: int) -> str:
        """Генерация чередующихся букв (ababa, kakak)"""
        char1 = random.choice(self.top_consonants)
        char2 = random.choice(self.vowels)
        
        result = []
        for i in range(length):
            result.append(char1 if i % 2 == 0 else char2)
        
        return ''.join(result)
    
    def _generate_pronounceable(self, length: int) -> str:
        """Генерация произносимого ника (чередование согласных и гласных)"""
        result = []
        
        for i in range(length):
            if i % 2 == 0:
                # Согласная
                result.append(random.choice(self.top_consonants))
            else:
                # Гласная
                result.append(random.choice(self.vowels))
        
        return ''.join(result)
    
    def _generate_cool_combo(self, length: int) -> str:
        """Генерация из популярных комбинаций"""
        if length < 4:
            return self._generate_pronounceable(length)
        
        # Начинаем с крутой пары
        result = random.choice(self.cool_pairs)
        
        # Добавляем оставшиеся буквы чередуя согласные/гласные
        while len(result) < length:
            if len(result) % 2 == 0:
                result += random.choice(self.vowels)
            else:
                result += random.choice(self.top_consonants)
        
        return result[:length]
    
    def _generate_name_like(self, length: int) -> str:
        """Генерация похожего на имя (alex, mark, john)"""
        # Популярные начала имён
        name_starts = ['al', 'an', 'ar', 'be', 'bo', 'ca', 'ch', 'da', 'de', 'el', 
                      'er', 'ja', 'jo', 'ka', 'ke', 'ki', 'le', 'li', 'lu', 'ma', 
                      'mi', 'mo', 'na', 'ni', 'ol', 'pa', 'pe', 'ra', 're', 'ri', 
                      'ro', 'sa', 'se', 'si', 'ta', 'te', 'ti', 'to', 've', 'vi', 
                      'za', 'ze']
        
        result = random.choice(name_starts)
        
        # Добавляем буквы чередуя
        while len(result) < length:
            if len(result) % 2 == 0:
                result += random.choice(self.top_consonants)
            else:
                result += random.choice(self.vowels)
        
        return result[:length]
    
    def _generate_with_vowels(self, length: int) -> str:
        """Генерация с чередованием гласных и согласных"""
        vowels = 'aeiou'
        consonants = ''.join(c for c in self.letters if c not in vowels)
        
        result = []
        for i in range(length):
            if i % 2 == 0:
                result.append(random.choice(consonants))
            else:
                result.append(random.choice(vowels))
        
        return ''.join(result)
    
    def _generate_sequence(self, length: int) -> str:
        """Генерация последовательности (abc, xyz)"""
        # Выбираем случайную начальную букву так, чтобы хватило места для последовательности
        max_start = ord('z') - length + 1
        start_char = chr(random.randint(ord('a'), max_start))
        
        result = []
        for i in range(length):
            result.append(chr(ord(start_char) + i))
        
        return ''.join(result)
    
    def _generate_reverse_sequence(self, length: int) -> str:
        """Генерация обратной последовательности (cba, zyx)"""
        # Выбираем случайную начальную букву
        min_start = ord('a') + length - 1
        start_char = chr(random.randint(min_start, ord('z')))
        
        result = []
        for i in range(length):
            result.append(chr(ord(start_char) - i))
        
        return ''.join(result)
    
    def _generate_doubles(self, length: int) -> str:
        """Генерация с двойными буквами (aabbcc)"""
        result = []
        chars_needed = (length + 1) // 2
        
        for i in range(chars_needed):
            # Чередуем согласные и гласные для произносимости
            if i % 2 == 0:
                char = random.choice(self.top_consonants)
            else:
                char = random.choice(self.vowels)
            
            result.append(char)
            if len(result) < length:
                result.append(char)
        
        return ''.join(result[:length])
    
    def _generate_mirror(self, length: int) -> str:
        """Генерация зеркальных паттернов (abcba, xyzyx)"""
        if length <= 2:
            return random.choice(self.letters) * length
        
        # Для нечётной длины
        if length % 2 == 1:
            half = length // 2
            first_half = ''.join(random.choice(self.letters) for _ in range(half))
            middle = random.choice(self.letters)
            return first_half + middle + first_half[::-1]
        else:
            # Для чётной длины
            half = length // 2
            first_half = ''.join(random.choice(self.letters) for _ in range(half))
            return first_half + first_half[::-1]


# Глобальный экземпляр генератора
generator = UsernameGenerator()
