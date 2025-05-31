# reputation.py
import discord
from collections import defaultdict

class ReputationSystem:
    """
    Класс для управления системой репутации игроков.
    Позволяет игрокам оценивать друг друга, отслеживать репутацию и просматривать лучших игроков.
    """

    def __init__(self):
        """
        Инициализирует систему репутации.
        - self.reputations: Словарь для хранения очков репутации каждого игрока.
                             Ключ: user_id (int), Значение: score (int).
        - self.rating_history: Словарь для отслеживания, кто кого оценивал,
                               чтобы предотвратить повторные оценки (пока не используется для строгой проверки).
                               Ключ: (rater_user_id, rated_user_id), Значение: последнее изменение (int) или временная метка.
                               Для простоты, пока не будем реализовывать сложную защиту от накрутки.
        """
        self.reputations = defaultdict(int)  # Очки репутации, по умолчанию 0 для новых игроков
        # self.rating_history = {} # Пока не используем сложную историю для предотвращения накрутки

    async def add_rating(self, rater_user: discord.User, rated_user: discord.User, rating_change: int, reason: str = None) -> tuple[bool, str]:
        """
        Добавляет или изменяет оценку репутации для указанного пользователя.

        :param rater_user: Объект discord.User, который ставит оценку.
        :param rated_user: Объект discord.User, которому ставят оценку.
        :param rating_change: Изменение репутации (+1 для положительной, -1 для отрицательной).
        :param reason: (Опционально) Причина оценки.
        :return: Кортеж (bool, str), где bool - успех операции, str - сообщение для пользователя.
        """
        rater_user_id = rater_user.id
        rated_user_id = rated_user.id

        if rater_user_id == rated_user_id:
            return False, "Вы не можете оценивать самого себя."

        if rating_change not in [1, -1]:
            return False, "Некорректное значение изменения репутации. Используйте +1 или -1."

        # Простое обновление репутации
        self.reputations[rated_user_id] += rating_change

        # Логирование действия (можно расширить для записи в файл или базу данных)
        print(f"Игрок {rater_user.name} ({rater_user_id}) оценил игрока {rated_user.name} ({rated_user_id}) на {rating_change}. Причина: {reason if reason else 'не указана'}. Новая репутация: {self.reputations[rated_user_id]}")

        if rating_change > 0:
            return True, f"Вы успешно повысили репутацию игрока {rated_user.mention}. Его новая репутация: {self.reputations[rated_user_id]}."
        else:
            return True, f"Вы успешно понизили репутацию игрока {rated_user.mention}. Его новая репутация: {self.reputations[rated_user_id]}."

    def get_reputation(self, user_id: int) -> int:
        """
        Возвращает текущий счет репутации для указанного пользователя.

        :param user_id: ID пользователя Discord.
        :return: Целочисленное значение репутации. Если игрок не найден, возвращает 0.
        """
        return self.reputations.get(user_id, 0) # Используем .get для безопасного получения, или defaultdict сам вернет 0

    def get_top_players(self, n: int = 10) -> list[tuple[int, int]]:
        """
        Возвращает список лучших N игроков по очкам репутации.

        :param n: Количество лучших игроков для отображения.
        :return: Список кортежей, где каждый кортеж содержит (user_id, reputation_score),
                 отсортированный по убыванию очков репутации.
        """
        if not self.reputations:
            return []

        # Сортируем словарь по значениям (очкам репутации) в убывающем порядке
        sorted_reputations = sorted(self.reputations.items(), key=lambda item: item[1], reverse=True)

        return sorted_reputations[:n]

if __name__ == '__main__':
    # Пример использования (для локального тестирования)
    # Этот блок не будет выполняться при импорте класса в другие файлы.

    # Создаем мок-объекты User для тестирования
    class MockUser:
        def __init__(self, id, name, mention_override=None):
            self.id = id
            self.name = name
            self._mention = mention_override if mention_override else f"<@{id}>"

        @property
        def mention(self):
            return self._mention

    async def test_reputation_system():
        rep_system = ReputationSystem()

        user1 = MockUser(1, "Игрок1")
        user2 = MockUser(2, "Игрок2")
        user3 = MockUser(3, "Игрок3")

        # Тест добавления рейтинга
        success, msg = await rep_system.add_rating(user1, user2, 1, "Хорошая игра")
        print(f"Тест 1: {msg} (Успех: {success})")
        success, msg = await rep_system.add_rating(user1, user2, 1, "Снова хорошая игра") # Повторная оценка
        print(f"Тест 2: {msg} (Успех: {success})")
        success, msg = await rep_system.add_rating(user3, user2, 1, "Присоединяюсь, отличный тиммейт")
        print(f"Тест 3: {msg} (Успех: {success})")
        success, msg = await rep_system.add_rating(user2, user1, -1, "Плохое поведение")
        print(f"Тест 4: {msg} (Успех: {success})")
        success, msg = await rep_system.add_rating(user1, user1, 1, "Самооценка") # Попытка оценить себя
        print(f"Тест 5: {msg} (Успех: {success})")

        # Тест получения репутации
        print(f"\nРепутация Игрока1 ({user1.id}): {rep_system.get_reputation(user1.id)}")
        print(f"Репутация Игрока2 ({user2.id}): {rep_system.get_reputation(user2.id)}")
        print(f"Репутация Игрока3 ({user3.id}): {rep_system.get_reputation(user3.id)}") # Должен быть 0, т.к. его не оценивали
        print(f"Репутация Игрока4 (не существует): {rep_system.get_reputation(4)}")

        # Тест получения топ игроков
        top_players = rep_system.get_top_players(5)
        print("\nТоп игроков:")
        if top_players:
            for user_id, score in top_players:
                print(f"  ID Игрока: {user_id}, Репутация: {score}")
        else:
            print("  Список топ игроков пуст.")

        # Еще оценки для проверки топа
        user4 = MockUser(4, "Игрок4_топ")
        await rep_system.add_rating(user1, user4, 1)
        await rep_system.add_rating(user2, user4, 1)
        await rep_system.add_rating(user3, user4, 1)

        user5 = MockUser(5, "Игрок5_низкий")
        await rep_system.add_rating(user1, user5, -1)

        top_players_updated = rep_system.get_top_players(3)
        print("\nОбновленный Топ 3 игроков:")
        if top_players_updated:
            for user_id, score in top_players_updated:
                 # В реальном боте мы бы получали объект User по ID, чтобы показать имя
                print(f"  ID Игрока: {user_id}, Репутация: {score}")
        else:
            print("  Список топ игроков пуст.")

    # Запуск асинхронного теста
    # asyncio.run(test_reputation_system()) # Это потребует asyncio для запуска, если запускать файл напрямую
    # Для простоты, можно убрать async из add_rating на время теста или обернуть вызов в asyncio.run()
    # Поскольку add_rating теперь async из-за discord.User, оставим так и закомментируем прямой запуск.
    # Для тестирования этого файла отдельно, нужно будет создать event loop.
    # Например:
    # if __name__ == '__main__':
    #     loop = asyncio.get_event_loop()
    #     loop.run_until_complete(test_reputation_system())
    #     loop.close()
    pass # Закомментировано, чтобы не было ошибок при импорте в основном коде бота.
