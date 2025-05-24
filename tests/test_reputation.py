# tests/test_reputation.py
import unittest
import asyncio # Для запуска асинхронных методов, если они есть в тестируемом классе
from collections import defaultdict

# Импортируем тестируемый класс
# Добавляем путь к корневой директории проекта, чтобы можно было импортировать 'reputation'
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from reputation import ReputationSystem

# --- Мок-объекты для Discord ---
class MockUser:
    """
    Упрощенный мок-объект для discord.User.
    Содержит только необходимые для тестов атрибуты.
    """
    def __init__(self, id: int, name: str, mention_override: str = None):
        self.id = id
        self.name = name
        self._mention = mention_override if mention_override else f"<@{id}>" # Имитация упоминания

    @property
    def mention(self) -> str:
        return self._mention

    # Для сравнения объектов в тестах (если потребуется)
    def __eq__(self, other):
        if isinstance(other, MockUser):
            return self.id == other.id
        return False

    def __hash__(self):
        return hash(self.id)

class TestReputationSystem(unittest.TestCase):
    """
    Набор тестов для класса ReputationSystem.
    """

    def setUp(self):
        """
        Настройка перед каждым тестом.
        Создает новый экземпляр ReputationSystem и мок-пользователей.
        """
        self.rep_system = ReputationSystem()
        self.user1 = MockUser(1, "Тестер1")
        self.user2 = MockUser(2, "Тестер2")
        self.user3 = MockUser(3, "Тестер3")
        self.user4 = MockUser(4, "Тестер4")

    # Обертка для запуска асинхронных тестов, если add_rating останется async
    # В текущей реализации reputation.py, add_rating - async.
    def async_test_wrapper(self, coro):
        """Обертка для выполнения асинхронного теста."""
        return asyncio.run(coro)

    def test_add_rating_self_rating(self):
        """
        Тест: Запрет на оценку самого себя.
        """
        async def test_logic():
            success, message = await self.rep_system.add_rating(self.user1, self.user1, 1, "Самооценка")
            self.assertFalse(success, "Самооценка должна быть запрещена.")
            self.assertEqual(self.rep_system.get_reputation(self.user1.id), 0, "Репутация не должна измениться при самооценке.")
            self.assertIn("не можете оценивать самого себя", message.lower(), "Сообщение об ошибке должно содержать информацию о запрете самооценки.")
        self.async_test_wrapper(test_logic())

    def test_add_rating_others_positive(self):
        """
        Тест: Успешная положительная оценка другого пользователя.
        """
        async def test_logic():
            success, message = await self.rep_system.add_rating(self.user1, self.user2, 1, "Хороший игрок")
            self.assertTrue(success, "Оценка должна быть успешной.")
            self.assertEqual(self.rep_system.get_reputation(self.user2.id), 1, "Репутация user2 должна увеличиться на 1.")
            self.assertIn("успешно повысили репутацию", message.lower())
        self.async_test_wrapper(test_logic())

    def test_add_rating_others_negative(self):
        """
        Тест: Успешная отрицательная оценка другого пользователя.
        """
        async def test_logic():
            success, message = await self.rep_system.add_rating(self.user1, self.user2, -1, "Плохое поведение")
            self.assertTrue(success, "Оценка должна быть успешной.")
            self.assertEqual(self.rep_system.get_reputation(self.user2.id), -1, "Репутация user2 должна уменьшиться на 1.")
            self.assertIn("успешно понизили репутацию", message.lower())
        self.async_test_wrapper(test_logic())

    def test_add_rating_multiple_changes(self):
        """
        Тест: Несколько оценок для одного пользователя.
        """
        async def test_logic():
            await self.rep_system.add_rating(self.user1, self.user3, 1, "Помог")
            await self.rep_system.add_rating(self.user2, self.user3, 1, "Дружелюбный")
            await self.rep_system.add_rating(self.user4, self.user3, -1, "Нарушил правила")
            self.assertEqual(self.rep_system.get_reputation(self.user3.id), 1, "Итоговая репутация user3 должна быть 1 (1+1-1).")
        self.async_test_wrapper(test_logic())
        
    def test_add_rating_invalid_change_value(self):
        """
        Тест: Попытка изменения репутации на некорректное значение (не +1 или -1).
        """
        async def test_logic():
            success, message = await self.rep_system.add_rating(self.user1, self.user2, 0, "Нулевое изменение")
            self.assertFalse(success, "Оценка с 0 не должна быть успешной.")
            self.assertIn("некорректное значение", message.lower())
            
            success, message = await self.rep_system.add_rating(self.user1, self.user2, 2, "Слишком большое изменение")
            self.assertFalse(success, "Оценка с +2 не должна быть успешной.")
            self.assertIn("некорректное значение", message.lower())
            
            self.assertEqual(self.rep_system.get_reputation(self.user2.id), 0, "Репутация не должна измениться при некорректной оценке.")
        self.async_test_wrapper(test_logic())

    def test_get_reputation_new_user(self):
        """
        Тест: Получение репутации нового пользователя (должна быть 0).
        """
        self.assertEqual(self.rep_system.get_reputation(self.user4.id), 0, "Репутация нового пользователя должна быть 0.")

    def test_get_reputation_existing_user(self):
        """
        Тест: Получение репутации существующего пользователя после оценки.
        """
        async def test_logic():
            await self.rep_system.add_rating(self.user1, self.user2, 1)
            self.assertEqual(self.rep_system.get_reputation(self.user2.id), 1)
            await self.rep_system.add_rating(self.user1, self.user2, 1)
            self.assertEqual(self.rep_system.get_reputation(self.user2.id), 2)
        self.async_test_wrapper(test_logic())

    def test_get_top_players_empty(self):
        """
        Тест: Получение списка лучших игроков, когда нет данных о репутации.
        Список должен быть пустым.
        """
        top_players = self.rep_system.get_top_players(5)
        self.assertEqual(len(top_players), 0, "Список лучших игроков должен быть пустым, если нет данных.")
        self.assertListEqual(top_players, [], "Список лучших игроков должен быть пустым.")

    def test_get_top_players_with_data_correct_sorting_and_limit(self):
        """
        Тест: Получение списка лучших игроков с данными.
        Проверяется корректность сортировки и ограничение количества.
        """
        async def test_logic():
            # Присваиваем репутации
            # user1: 0 (не оценивали)
            # user2: 3
            # user3: -2
            # user4: 5
            await self.rep_system.add_rating(self.user1, self.user2, 1) # user2 = 1
            await self.rep_system.add_rating(self.user3, self.user2, 1) # user2 = 2
            await self.rep_system.add_rating(self.user4, self.user2, 1) # user2 = 3

            await self.rep_system.add_rating(self.user1, self.user3, -1) # user3 = -1
            await self.rep_system.add_rating(self.user2, self.user3, -1) # user3 = -2
            
            await self.rep_system.add_rating(self.user1, self.user4, 1) # user4 = 1
            await self.rep_system.add_rating(self.user2, self.user4, 1) # user4 = 2
            await self.rep_system.add_rating(self.user3, self.user4, 1) # user4 = 3
            await self.rep_system.add_rating(self.user1, self.user4, 1) # user4 = 4
            await self.rep_system.add_rating(self.user2, self.user4, 1) # user4 = 5

            # Ожидаемый топ-3: user4 (5), user2 (3), user1 (0)
            expected_top_3_ids_scores = [
                (self.user4.id, 5),
                (self.user2.id, 3),
                (self.user1.id, 0) # user1 не получал оценок, репутация 0
            ]
            
            top_3_players = self.rep_system.get_top_players(3)
            self.assertEqual(len(top_3_players), 3, "Должно быть возвращено 3 игрока.")
            self.assertEqual(top_3_players, expected_top_3_ids_scores, "Список топ-3 игроков отсортирован некорректно или содержит неверные данные.")

            # Проверка, что если запросить больше игроков, чем есть с ненулевой репутацией, вернутся все с правильной сортировкой
            # У нас user1(0), user2(3), user3(-2), user4(5). Всего 4 игрока с измененной репутацией (или известной через get).
            # defaultdict вернет 0 для user1, если его id запросить через get_reputation, но он не будет в self.reputations.items(), если его не оценивали.
            # get_top_players работает с self.reputations.items().
            # user1 не оценивался, его репутация 0 по умолчанию, но его нет в self.reputations.
            # Чтобы он появился в .items(), его нужно хотя бы раз оценить или чтобы его репутация была запрошена и сохранена (но defaultdict не делает этого при .get)
            # Для теста добавим user1 оценку, чтобы он точно был в словаре reputations
            await self.rep_system.add_rating(self.user2, self.user1, 0) # Это не изменит его репутацию (0), но добавит в словарь, если бы add_rating позволял 0.
                                                                    # Поскольку не позволяет, его репутация останется 0 и он не будет в .items()
                                                                    # Исправляем: get_top_players должен учитывать всех, кого хоть раз оценивали.
                                                                    # user1.id не будет в self.reputations, если его никто не оценивал.
                                                                    # Если мы хотим, чтобы get_top_players включал игроков с репутацией 0, которых не оценивали,
                                                                    # но которые могут быть известны системе (например, все участники сервера),
                                                                    # то логика get_top_players должна быть сложнее.
                                                                    # Текущая реализация get_top_players вернет только тех, кто есть в self.reputations.
            
            # Ожидаемый топ всех (кто есть в self.reputations): user4 (5), user2 (3), user3 (-2)
            expected_top_all_ids_scores = [
                (self.user4.id, 5),
                (self.user2.id, 3),
                (self.user3.id, -2)
            ]
            top_all_players = self.rep_system.get_top_players(10) # Запрашиваем больше, чем есть
            self.assertEqual(len(top_all_players), 3, "Должны вернуться все игроки, чья репутация изменялась.")
            self.assertEqual(top_all_players, expected_top_all_ids_scores, "Список всех игроков отсортирован некорректно.")

        self.async_test_wrapper(test_logic())


if __name__ == '__main__':
    # Это позволяет запускать тесты напрямую из этого файла
    unittest.main()
