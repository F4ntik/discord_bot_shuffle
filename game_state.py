# game_state.py
import random
import discord
import asyncio
from components import VoteButton
from discord.ui import View
from discord import Embed
import config


class GameState:
    def __init__(self, bot, channel_id):
        self.bot = bot
        self.registered_players = []
        self.players_per_team = 5
        self.channel_id = channel_id
        self.votes = {"agree": 0, "reshuffle": 0}
        self.voting_active = False
        self.voting_message = None  # Добавляем атрибут для хранения сообщения голосования
        self.last_interaction = None  # Добавляем атрибут для сохранения последнего interaction
        self.reset_task = None  # Атрибут для отслеживания задачи сброса состояния игры по таймеру.

    async def start_reset_timer(self):
        """
        Запускает или перезапускает таймер автоматического сброса состояния игры.
        Если предыдущий таймер активен, он отменяется перед запуском нового.
        """
        if self.reset_task:
            self.reset_task.cancel()
        self.reset_task = asyncio.create_task(self.reset_game_state_after_delay())

    async def reset_game_state_after_delay(self):
        """
        Сбрасывает состояние игры после определенной задержки (config.RESET_DELAY).
        Очищает список зарегистрированных игроков и возвращает боту статус 'online'.
        Вызывается задачей, созданной в start_reset_timer.
        """
        await asyncio.sleep(config.RESET_DELAY)  # Ожидание согласно настройке в config.py
        print("Таймер сброса истек. Очистка состояния игры.")
        await self.clear_registered_players()
        # Статус бота обновится автоматически при очистке игроков через update_bot_status
        # Нет необходимости явно менять статус здесь, если clear_registered_players вызывает update_bot_status.
        # await self.bot.change_presence(status=discord.Status.online)

    async def _is_user_eligible_to_vote(self, user: discord.User, interaction: discord.Interaction) -> bool:
        """
        (Приватный) Проверяет, имеет ли пользователь право голосовать.
        Условия: голосование должно быть активно, и пользователь должен быть среди зарегистрированных игроков.
        Отправляет эфемерные сообщения пользователю в случае отказа.
        """
        if not self.voting_active:
            await interaction.followup.send("Голосование в данный момент неактивно или уже завершено.", ephemeral=True)
            return False
        if user not in self.registered_players:
            await interaction.followup.send("Ваш голос не учитывается, так как вы не зарегистрированы на текущий матч.", ephemeral=True)
            return False
        return True

    async def _update_voting_message(self):
        """
        (Приватный) Обновляет существующее сообщение о голосовании, отображая текущее количество голосов
        за "Согласен" и "Перемешать", а также их процентное соотношение.
        Обрабатывает возможные ошибки, если сообщение было удалено или возникла проблема с API Discord.
        """
        if self.voting_message:
            total_votes = sum(self.votes.values())
            if total_votes == 0:
                agree_percentage = 0
                reshuffle_percentage = 0
            else:
                agree_percentage = (self.votes["agree"] / total_votes) * 100 if total_votes > 0 else 0
                reshuffle_percentage = (self.votes["reshuffle"] / total_votes) * 100 if total_votes > 0 else 0

            new_content = (
                f"Текущее голосование: "
                f"Согласны - {self.votes['agree']} ({agree_percentage:.1f}%), "
                f"Перемешать - {self.votes['reshuffle']} ({reshuffle_percentage:.1f}%)"
            )
            try:
                await self.voting_message.edit(content=new_content)
            except discord.NotFound:
                print("Сообщение для голосования не найдено (возможно, удалено). Новое будет создано при необходимости.")
                self.voting_message = None # Сбрасываем, чтобы не пытаться обновить снова
            except discord.HTTPException as e:
                print(f"Ошибка HTTP при обновлении сообщения голосования: {e}")
            except Exception as e:
                print(f"Непредвиденная ошибка при обновлении сообщения голосования: {e}")


    async def process_vote(self, user: discord.User, vote_type: str, interaction: discord.Interaction):
        """
        Обрабатывает голос, отданный пользователем.
        Сначала проверяет право пользователя на голосование.
        Затем увеличивает счетчик для соответствующего типа голоса ("agree" или "reshuffle").
        Если после этого достигнут порог для принятия решения, вызывает evaluate_votes.
        В противном случае обновляет сообщение о голосовании.
        """
        self.last_interaction = interaction # Сохраняем последнее взаимодействие для использования в evaluate_votes или reshuffle
        if not await self._is_user_eligible_to_vote(user, interaction):
            return

        if vote_type in self.votes:
            self.votes[vote_type] += 1
            print(f"Голос от {user.display_name} за '{vote_type}'. Текущие голоса: {self.votes}")
        else:
            print(f"Неизвестный тип голоса от {user.display_name}: {vote_type}")
            await interaction.followup.send(f"Произошла внутренняя ошибка (неизвестный тип голоса: {vote_type}).", ephemeral=True)
            return

        # Проверяем, достаточно ли зарегистрированных игроков для корректного расчета порога
        if not self.registered_players:
            print("Предупреждение: process_vote вызван без зарегистрированных игроков.")
            # Если нет игроков, голосование не должно было начаться. Отправляем сообщение об ошибке.
            await interaction.followup.send("Ошибка: голосование обрабатывается без зарегистрированных игроков.", ephemeral=True)
            return

        players_needed_to_decide = max(int(config.VOTE_THRESHOLD * len(self.registered_players)), 1)

        if self.votes["agree"] >= players_needed_to_decide or self.votes["reshuffle"] >= players_needed_to_decide:
            print(f"Достигнут порог для голосования: {self.votes}. Игроков для решения: {players_needed_to_decide}. Вызов evaluate_votes.")
            await self.evaluate_votes(interaction=interaction)
        else:
            await self._update_voting_message()

    async def _can_register_player(self, player: discord.User, interaction: discord.Interaction) -> tuple[bool, str]:
        """
        (Приватный) Проверяет, может ли игрок быть зарегистрирован.
        Условия: голосование не должно быть активно, игрок не должен быть уже зарегистрирован,
        и количество зарегистрированных игроков не должно превышать максимально допустимое.
        Возвращает кортеж (bool, str), где bool - результат проверки, str - сообщение для пользователя.
        """
        if self.voting_active:
            # Сообщение должно быть отправлено через interaction оригинальной команды /register
            # Здесь мы просто возвращаем статус и текст сообщения
            return False, "Регистрация закрыта, так как идет активное голосование."
        if player in self.registered_players:
            return False, f'{player.mention}, вы уже зарегистрированы в текущем наборе.'
        if len(self.registered_players) >= self.players_per_team * 2:
            return False, 'Достигнуто максимальное количество игроков для этого матча.'
        return True, ""

    async def register_player(self, player: discord.User, interaction: discord.Interaction) -> tuple[bool, str]:
        """
        Регистрирует игрока для участия в матче.
        Использует _can_register_player для проверки возможности регистрации.
        Если регистрация успешна, добавляет игрока в список, обновляет статус бота.
        Если достигнуто максимальное количество игроков, инициирует отображение команд и начало голосования.
        Отправляет соответствующие сообщения пользователю через interaction.
        """
        can_register, message = await self._can_register_player(player, interaction)
        # Ответ пользователю в _can_register_player не отправляется, он возвращается сюда.
        if not can_register:
            # Отправляем сообщение об ошибке, если interaction еще не отвечен
            if not interaction.response.is_done():
                await interaction.response.send_message(message, ephemeral=True)
            else: # Если уже ответили (например, defer()), используем followup
                await interaction.followup.send(message, ephemeral=True)
            return False, message

        self.registered_players.append(player)
        self.last_interaction = interaction
        await self.update_bot_status()
        print(f"Игрок {player.display_name} зарегистрирован. Всего игроков: {len(self.registered_players)}/{self.players_per_team * 2}")

        response_message_key = "registration_successful_match_starting" if await self.check_ready_to_start() else "registration_successful_waiting_for_players"

        # Формируем основное сообщение для пользователя
        if response_message_key == "registration_successful_match_starting":
            user_message = f'{player.mention} успешно зарегистрирован! Все игроки набраны ({len(self.registered_players)}/{self.players_per_team * 2}). Формируем команды и начинаем голосование.'
        else:
            user_message = f'{player.mention} зарегистрирован на матч. Игроков зарегистрировано: {len(self.registered_players)} из {self.players_per_team * 2}.'

        # Отправляем ответ пользователю
        if not interaction.response.is_done():
            await interaction.response.send_message(user_message, ephemeral=True)
        else:
            await interaction.followup.send(user_message, ephemeral=True)


        if await self.check_ready_to_start():
            # Эти функции будут использовать followup для отправки публичных сообщений
            await self.display_teams_general(interaction=interaction, shuffle=True, display_voting_buttons=True)
            await self.start_voting(interaction)
            return True, 'Достигнуто максимальное количество игроков. Старт голосования.'

        return False, f'{player.mention} зарегистрирован. {len(self.registered_players)}/{self.players_per_team * 2}'


    async def unregister_player(self, player: discord.User, interaction: discord.Interaction) -> str:
        """
        Отменяет регистрацию игрока.
        Запрещает отмену, если голосование активно.
        Если игрок был зарегистрирован, удаляет его из списка и обновляет статус бота.
        Отправляет соответствующие сообщения пользователю через interaction.
        """
        if self.voting_active:
            message = "Отмена регистрации невозможна: идет активное голосование."
            if not interaction.response.is_done():
                await interaction.response.send_message(message, ephemeral=True)
            else:
                await interaction.followup.send(message, ephemeral=True)
            return message

        if player in self.registered_players:
            self.registered_players.remove(player)
            await self.update_bot_status()
            message = f'{player.mention}, ваша регистрация на матч отменена. Игроков зарегистрировано: {len(self.registered_players)} из {self.players_per_team * 2}.'
            print(f"Игрок {player.display_name} отменил регистрацию. Осталось игроков: {len(self.registered_players)}.")
            if not interaction.response.is_done():
                await interaction.response.send_message(message, ephemeral=True)
            else:
                await interaction.followup.send(message, ephemeral=True)
            return message

        message = f'{player.mention}, вы не были зарегистрированы в текущем наборе.'
        if not interaction.response.is_done():
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.followup.send(message, ephemeral=True)
        return message

    async def shuffle_teams(self):
        """Перемешивает текущий список зарегистрированных игроков случайным образом."""
        random.shuffle(self.registered_players)

    async def auto_split_teams(self, shuffle: bool = False) -> tuple[list, list]:
        """
        Автоматически разделяет зарегистрированных игроков на две команды.
        Если shuffle=True, предварительно перемешивает список игроков.
        Возвращает кортеж из двух списков (команда1, команда2).
        Если игроков меньше двух, возвращает два пустых списка и выводит сообщение об ошибке.
        """
        if shuffle:
            await self.shuffle_teams()

        if len(self.registered_players) < 2:
            print("Предупреждение: Недостаточно игроков для разделения на две команды.")
            return ([], [])

        mid_index = len(self.registered_players) // 2
        team1 = self.registered_players[:mid_index]
        team2 = self.registered_players[mid_index:]
        return (team1, team2)

    async def check_ready_to_start(self) -> bool:
        """Проверяет, достигнуто ли необходимое количество игроков для начала матча."""
        return len(self.registered_players) == self.players_per_team * 2

    async def clear_registered_players(self):
        """
        Полностью очищает состояние игры: список игроков, голоса, статус голосования.
        Удаляет сообщение о голосовании, если оно существует.
        Обновляет статус бота и отправляет сообщение в игровой канал об очистке.
        """
        self.registered_players = []
        self.voting_active = False
        self.votes = {"agree": 0, "reshuffle": 0}
        if self.voting_message:
            try:
                await self.voting_message.delete()
                print("Сообщение о голосовании удалено при очистке списка.")
            except discord.NotFound:
                print("Сообщение о голосовании не найдено при очистке (возможно, уже удалено).")
            except discord.HTTPException as e:
                print(f"Ошибка HTTP при удалении сообщения о голосовании: {e}")
            except Exception as e:
                print(f"Непредвиденная ошибка при удалении сообщения о голосовании: {e}")
            self.voting_message = None

        await self.update_bot_status() # Статус обновится на "ожидание регистрации"

        message_to_send = "Список зарегистрированных игроков очищен. Регистрация снова открыта!"
        # Попытка отправить сообщение в основной канал игры
        main_channel = self.bot.get_channel(self.channel_id)
        if main_channel:
            try:
                await main_channel.send(message_to_send)
            except discord.HTTPException as e:
                print(f"Не удалось отправить сообщение об очистке списка в канал {self.channel_id}: {e}")
        else:
            print(f"Канал {self.channel_id} не найден для отправки сообщения об очистке.")

        return "Список зарегистрированных игроков очищен."


    async def set_players_per_team(self, number: int, interaction: discord.Interaction) -> tuple[bool, str]:
        """
        Устанавливает желаемое количество игроков в каждой команде (от 1 до 6).
        Запрещает изменение, если голосование уже активно.
        Если игроки уже зарегистрированы, но голосование не начато, предупреждает об изменении цели.
        Обновляет статус бота. Отправляет сообщения пользователю через interaction.
        """
        if not (1 <= number <= config.MAX_PLAYERS_PER_TEAM): # Используем MAX_PLAYERS_PER_TEAM из config
            message = f'Количество игроков в команде должно быть от 1 до {config.MAX_PLAYERS_PER_TEAM}.'
            if not interaction.response.is_done():
                await interaction.response.send_message(message, ephemeral=True)
            else:
                await interaction.followup.send(message, ephemeral=True)
            return False, message

        if self.voting_active:
            message = 'Изменение количества игроков невозможно: идет активное голосование.'
            if not interaction.response.is_done():
                await interaction.response.send_message(message, ephemeral=True)
            else:
                await interaction.followup.send(message, ephemeral=True)
            return False, message

        current_total_players = self.players_per_team * 2
        self.players_per_team = number
        new_total_players = self.players_per_team * 2
        response_message = f'Количество игроков в команде установлено: {self.players_per_team} (всего {new_total_players}).'

        if self.registered_players and not self.voting_active:
            response_message += f'\n**Внимание:** Уже зарегистрировано {len(self.registered_players)} игроков. Цель изменилась с {current_total_players} на {new_total_players}.'

        await self.update_bot_status()

        if not interaction.response.is_done():
            await interaction.response.send_message(response_message, ephemeral=True)
        else: # Если defer() или предыдущий ответ уже был
            await interaction.followup.send(response_message, ephemeral=True)

        return True, response_message


    async def get_registered_players(self) -> list[discord.User]:
        """Возвращает текущий список зарегистрированных игроков."""
        return self.registered_players

    async def get_players_per_team(self) -> int:
        """Возвращает установленное количество игроков в одной команде."""
        return self.players_per_team

    async def _send_channel_message(self, message_content: str, embeds: list[Embed] = None, view: View = None) -> discord.Message | None:
        """
        (Приватный) Вспомогательный метод для отправки сообщения в основной игровой канал (self.channel_id).
        Обрабатывает возможные ошибки при отправке.
        Возвращает отправленное сообщение или None в случае ошибки.
        """
        channel = self.bot.get_channel(self.channel_id) #FIXED
        if not channel:
            print(f"Критическая ошибка: Основной игровой канал с ID {self.channel_id} не найден.")
            return None
        try:
            return await channel.send(content=message_content, embeds=embeds, view=view)
        except discord.Forbidden:
            print(f"Критическая ошибка: У бота нет прав на отправку сообщений в канал {self.channel_id}.")
        except discord.HTTPException as e:
            print(f"Ошибка HTTP при отправке сообщения в канал {self.channel_id}: {e}")
        except Exception as e: # Общий обработчик для других непредвиденных ошибок
            print(f"Непредвиденная ошибка при отправке сообщения в канал {self.channel_id}: {e}")
        return None

    async def display_voice_channel_links(self):
        """
        Отправляет в основной игровой канал сообщение со ссылками на голосовые каналы команд.
        Сообщение отправляется только если есть зарегистрированные игроки.
        Использует VOICE_CHANNEL_ID_TEAM1 и VOICE_CHANNEL_ID_TEAM2 из config.py.
        """
        if not self.registered_players:
            # await self._send_channel_message("Нет зарегистрированных игроков, ссылки на каналы не отображаются.")
            # Решено не отправлять сообщение, если нет игроков, т.к. finalize_teams вызовет это только при наличии команд
            return

        message = "Присоединитесь к голосовому каналу своей команды:\n"
        message += f"Команда 1: <#{config.VOICE_CHANNEL_ID_TEAM1}>\n"
        message += f"Команда 2: <#{config.VOICE_CHANNEL_ID_TEAM2}>"
        await self._send_channel_message(message)


    async def update_bot_status(self):
        """
        Обновляет статус присутствия бота в Discord в зависимости от текущего состояния игры.
        - "на голосование", если голосование активно.
        - "матч", если достигнуто нужное количество игроков и игра готова начаться (запускает таймер сброса).
        - "на X/Y игроков", если идет регистрация (также запускает таймер сброса, если есть игроки).
        - "на начало регистрации", если список игроков пуст (отменяет таймер сброса).
        Обрабатывает возможные ошибки при изменении статуса.
        """
        status_message = ""
        activity_type = discord.ActivityType.watching

        # Сначала проверяем, нужно ли отменить таймер
        should_cancel_timer = True

        if self.voting_active:
            status_message = "на голосование"
            should_cancel_timer = False # Не отменяем таймер во время голосования
        elif await self.check_ready_to_start(): # Команды полные, игра по сути началась или вот-вот начнется
            status_message = "матч"
            if not self.reset_task or self.reset_task.done(): # Запускаем таймер, если его нет или он завершен
                await self.start_reset_timer()
            should_cancel_timer = False
        elif self.registered_players: # Игроки есть, но не все
            status_message = f"на {len(self.registered_players)}/{self.players_per_team * 2} игроков"
            if not self.reset_task or self.reset_task.done():
                await self.start_reset_timer()
            should_cancel_timer = False
        else: # Список игроков пуст
            status_message = "на начало регистрации"
            # Таймер будет отменен ниже, если should_cancel_timer останется True

        if should_cancel_timer and self.reset_task and not self.reset_task.done():
            self.reset_task.cancel()
            self.reset_task = None
            print("Таймер автосброса отменен, так как список игроков пуст и нет активной игры/голосования.")

        activity = discord.Activity(type=activity_type, name=status_message)
        try:
            await self.bot.change_presence(status=discord.Status.online, activity=activity)
        except discord.HTTPException as e:
            print(f"Ошибка HTTP при обновлении статуса бота: {e}")
        except Exception as e:
            print(f"Непредвиденная ошибка при обновлении статуса бота: {e}")


    async def _check_vote_threshold_reached(self) -> bool:
        """
        (Приватный) Проверяет, достигнут ли порог голосов (config.VOTE_THRESHOLD)
        для принятия решения ("Согласен" или "Перемешать").
        Возвращает True, если порог достигнут хотя бы для одного из вариантов, иначе False.
        """
        if not self.registered_players:
            return False

        # Убедимся, что registered_players не пустой список перед доступом к config
        # Это уже проверяется выше, но для надежности.
        players_needed_to_decide = max(int(config.VOTE_THRESHOLD * len(self.registered_players)), 1)

        if self.votes["agree"] >= players_needed_to_decide or self.votes["reshuffle"] >= players_needed_to_decide:
            return True
        return False

    async def evaluate_votes(self, interaction: discord.Interaction, force_end_vote: bool = False):
        """
        Оценивает результаты голосования и предпринимает соответствующие действия.
        Вызывается, когда достигнут порог голосов или по истечении таймера (force_end_vote=True).
        - Удаляет сообщение о голосовании.
        - Деактивирует статус голосования.
        - Если force_end_vote=True и "Перемешать" не победило, присуждает победу "Согласен".
        - Если "Согласен" побеждает: финализирует команды.
        - Если "Перемешать" побеждает: перемешивает команды и начинает новое голосование.
        - Если решение не принято (порог не достигнут), по умолчанию финализирует команды.
        - Обновляет статус бота.
        """
        if self.voting_message: # Попытка удалить старое сообщение голосования
            try:
                await self.voting_message.delete()
                print("Сообщение о голосовании удалено при оценке результатов.")
            except discord.NotFound:
                print("Сообщение о голосовании не найдено при оценке (возможно, уже удалено).")
            except discord.HTTPException as e:
                print(f"Ошибка HTTP при удалении сообщения о голосовании: {e}")
            except Exception as e: # Общий обработчик
                print(f"Непредвиденная ошибка при удалении сообщения о голосовании: {e}")
            self.voting_message = None # Сбрасываем в любом случае

        self.voting_active = False # Голосование в любом случае завершается здесь
        print(f"Голосование деактивировано. Голоса на момент оценки: {self.votes}")

        if not self.registered_players:
            print("Оценка голосов вызвана, но нет зарегистрированных игроков. Сброс состояния.")
            await self.clear_registered_players() # Если нет игроков, чистим всё
            return

        required_votes = max(int(config.VOTE_THRESHOLD * len(self.registered_players)), 1)

        if force_end_vote:
            print("Принудительное завершение голосования (таймер истек или команда).")
            # Если "Перемешать" не набрало достаточно голосов для победы, "Согласен" побеждает.
            if self.votes["reshuffle"] < required_votes:
                # Устанавливаем голоса "Согласен" так, чтобы они точно победили,
                # учитывая уже проголосовавших за "Перемешать".
                self.votes["agree"] = len(self.registered_players) - self.votes["reshuffle"]
                print(f"Принудительная победа 'Согласен'. Голоса: {self.votes}")
            # Если "Перемешать" уже победило по голосам, эта логика не изменит исход.

        decision_made = False
        # Сначала проверяем на явную победу "Согласен"
        if self.votes["agree"] >= required_votes:
            print(f"'Согласен' победило. Голоса: {self.votes['agree']}/{required_votes}.")
            await self._send_channel_message("Голосование завершено: команды утверждены!")
            await self.finalize_teams()
            decision_made = True
        # Затем проверяем на явную победу "Перемешать"
        elif self.votes["reshuffle"] >= required_votes:
            print(f"'Перемешать' победило. Голоса: {self.votes['reshuffle']}/{required_votes}.")
            await self._send_channel_message("Голосование завершено: команды будут перемешаны!")
            await self.reshuffle_and_revote(interaction)
            decision_made = True

        # Если ни одна из опций не победила явно (например, порог не достигнут при force_end_vote=False,
        # или голоса разделились при force_end_vote=True, но "Согласен" не было назначено победителем выше)
        if not decision_made:
            print(f"Явного решения нет. Голоса: {self.votes}, порог: {required_votes}. Финализируем команды по умолчанию (как 'Согласен').")
            await self._send_channel_message("Результаты голосования не выявили явного победителя или порог не был достигнут. Команды финализируются в текущем составе.")
            await self.finalize_teams() # По умолчанию финализируем команды

        # Статус бота обновится внутри finalize_teams или reshuffle_and_revote
        # Голоса также сбрасываются в этих методах через reset_votes() или перед start_voting()
        # await self.update_bot_status() # Может быть избыточным здесь


    async def reset_votes(self):
        """
        Сбрасывает счетчики голосов ("agree", "reshuffle") в ноль и деактивирует флаг self.voting_active.
        Сообщение о голосовании (self.voting_message) обрабатывается (удаляется или заменяется)
        в других методах (evaluate_votes, display_teams_general).
        """
        self.votes = {"agree": 0, "reshuffle": 0}
        self.voting_active = False
        print("Счетчики голосов и флаг voting_active сброшены.")


    async def start_voting(self, interaction: discord.Interaction):
        """
        Начинает новый процесс голосования:
        - Активирует флаг voting_active.
        - Сбрасывает счетчики голосов.
        - Обновляет статус бота на "на голосование".
        - Запускает асинхронную задачу voting_timer, которая автоматически завершит голосование
          через VOTING_DURATION секунд (из config.py).
        Сообщение с кнопками голосования создается в display_teams_general.
        """
        self.voting_active = True
        self.votes = {"agree": 0, "reshuffle": 0} # Сброс перед каждым новым голосованием
        print("Новый раунд голосования начат.")
        await self.update_bot_status()

        # Сообщение о начале голосования и кнопки создаются в display_teams_general,
        # которое должно быть вызвано до start_voting, если это начало первого голосования,
        # или в reshuffle_and_revote.

        # Убедимся, что guild_id и channel_id извлекаются корректно
        guild_id = interaction.guild_id
        channel_id = interaction.channel_id
        if not guild_id or not channel_id:
            print("Критическая ошибка: guild_id или channel_id отсутствуют в interaction при старте таймера голосования.")
            # Можно попытаться использовать self.channel_id, но это менее надежно
            channel_id = self.channel_id
            if interaction.guild:
                 guild_id = interaction.guild.id
            else: # Если гильдии нет, таймер не может быть запущен корректно для уведомлений
                  print("Не удалось определить guild_id для таймера голосования.")
                  return


        asyncio.create_task(self.voting_timer(guild_id, channel_id, interaction))
        print(f"Таймер голосования запущен на {config.VOTING_DURATION} секунд.")


    async def voting_timer(self, guild_id: int, channel_id: int, interaction: discord.Interaction):
        """
        Асинхронный таймер для процесса голосования.
        Ожидает VOTING_DURATION секунд (из config.py).
        Если по истечении времени голосование все еще активно, принудительно завершает его,
        вызывая evaluate_votes с force_end_vote=True.
        Отправляет уведомление в игровой канал о завершении голосования по таймеру.
        """
        await asyncio.sleep(config.VOTING_DURATION) # Ожидаем указанное время
        if self.voting_active: # Если голосование всё ещё активно (не завершилось досрочно)
            print(f"Таймер голосования на {config.VOTING_DURATION}с истек. Принудительное завершение.")

            # Убедимся, что у нас есть актуальный interaction.
            # Если interaction из start_voting устарел, используем последний известный.
            current_interaction = interaction if interaction else self.last_interaction

            if not current_interaction:
                print("Критическая ошибка: Не удалось получить объект interaction для завершения голосования по таймеру.")
                # Попытка завершить без interaction, если это возможно (evaluate_votes должен быть готов к этому)
                # Однако, evaluate_votes теперь требует interaction. Это проблемная ситуация.
                # Возможно, нужно сохранить guild_id/channel_id и создать "пустой" interaction или найти другой способ.
                # Пока что просто логируем и не вызываем evaluate_votes, если нет interaction.
                # Это приведет к тому, что голосование "зависнет" без автоматического завершения.
                # TODO: Найти способ передать/создать актуальный interaction для таймера.
                # В качестве временного решения, если interaction не доступен, можно попробовать отправить сообщение напрямую в канал.
                channel_to_notify = self.bot.get_channel(channel_id)
                if channel_to_notify:
                    try:
                        await channel_to_notify.send("Время голосования истекло, но произошла ошибка при автоматическом подсчете. Пожалуйста, используйте команды для управления.")
                    except Exception as e_send:
                        print(f"Не удалось уведомить канал {channel_id} об ошибке таймера: {e_send}")
                return # Прерываем, так как evaluate_votes требует interaction

            await self.evaluate_votes(interaction=current_interaction, force_end_vote=True)

            # Уведомление в канал о том, что время вышло (evaluate_votes также может отправлять сообщения)
            # Это сообщение может дублировать сообщение из evaluate_votes, если там оно тоже отправляется.
            # Рекомендуется централизовать отправку сообщений о результате голосования в evaluate_votes.
            # channel_to_notify = self.bot.get_channel(channel_id)
            # if channel_to_notify:
            #     try:
            #         await channel_to_notify.send("Время голосования истекло! Подведение итогов...")
            #     except discord.HTTPException as e_timer_msg:
            #         print(f"Не удалось отправить сообщение об истечении времени голосования в канал {channel_id}: {e_timer_msg}")
            # else:
            #     print(f"Канал {channel_id} не найден для отправки сообщения об истечении таймера.")


    async def move_players_to_voice_channels(self, team1: list[discord.Member], team2: list[discord.Member]):
        """
        Перемещает участников команд team1 и team2 в соответствующие голосовые каналы,
        заданные в config.py (VOICE_CHANNEL_ID_TEAM1, VOICE_CHANNEL_ID_TEAM2).
        - Получает объекты гильдии и каналов по ID.
        - Для каждого участника:
            - Преобразует discord.User в discord.Member, если необходимо.
            - Если участник уже в голосовом канале, перемещает его.
            - Если не в канале, отправляет ему личное сообщение с просьбой присоединиться и
              дублирует сообщение в основной игровой канал.
        - Обрабатывает ошибки прав доступа (Forbidden), HTTP ошибки и другие исключения.
        """
        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            print(f"Критическая ошибка: Гильдия с ID {config.GUILD_ID} не найдена. Перемещение игроков невозможно.")
            await self._send_channel_message(f"**Ошибка:** Не удалось найти сервер (гильдию) для перемещения игроков.")
            return

        team1_channel = guild.get_channel(config.VOICE_CHANNEL_ID_TEAM1)
        team2_channel = guild.get_channel(config.VOICE_CHANNEL_ID_TEAM2)

        if not team1_channel or not isinstance(team1_channel, discord.VoiceChannel):
            msg = f"**Ошибка:** Голосовой канал для Команды 1 (<#{config.VOICE_CHANNEL_ID_TEAM1}>) не найден или не является голосовым."
            print(msg.replace("**",""))
            await self._send_channel_message(msg)
            # Продолжаем для второй команды, если первая не найдена, но перемещение будет неполным
        if not team2_channel or not isinstance(team2_channel, discord.VoiceChannel):
            msg = f"**Ошибка:** Голосовой канал для Команды 2 (<#{config.VOICE_CHANNEL_ID_TEAM2}>) не найден или не является голосовым."
            print(msg.replace("**",""))
            await self._send_channel_message(msg)
            if not team1_channel: return # Если оба не найдены, выходим

        async def _move_team(team: list[discord.User | discord.Member], target_channel: discord.VoiceChannel, team_name: str):
            if not target_channel: # Если целевой канал для этой команды не найден
                await self._send_channel_message(f"Невозможно переместить {team_name}, так как их целевой канал не найден.")
                return

            for member_user in team: # member_user может быть User или Member
                member_to_move = None
                if isinstance(member_user, discord.User):
                    member_to_move = guild.get_member(member_user.id)
                    if not member_to_move:
                        print(f"Не удалось найти участника {member_user.display_name} (ID: {member_user.id}) в гильдии для перемещения в {team_name}.")
                        await self._send_channel_message(f"Не удалось найти {member_user.mention} на сервере для перемещения в {team_name}.")
                        continue
                elif isinstance(member_user, discord.Member):
                    member_to_move = member_user
                else: # Неожиданный тип
                    print(f"Обнаружен некорректный тип участника {type(member_user)} в {team_name}.")
                    continue

                try:
                    if member_to_move.voice and member_to_move.voice.channel:
                        if member_to_move.voice.channel.id == target_channel.id:
                             print(f"{member_to_move.display_name} уже в целевом канале {target_channel.name}.")
                             continue # Уже в нужном канале
                        await member_to_move.move_to(target_channel)
                        print(f"Участник {member_to_move.display_name} перемещен в канал {target_channel.name} ({team_name}).")
                    else:
                        join_message = f"{member_to_move.mention}, пожалуйста, присоединитесь к голосовому каналу вашей команды ({team_name}): <#{target_channel.id}>"
                        try:
                            await member_to_move.send(join_message)
                        except discord.Forbidden:
                            print(f"Не удалось отправить ЛС {member_to_move.display_name} (ЛС закрыты или бот заблокирован).")
                        except discord.HTTPException as e_dm:
                            print(f"Ошибка HTTP при отправке ЛС {member_to_move.display_name}: {e_dm}")
                        await self._send_channel_message(join_message) # Дублируем в общий чат
                except discord.Forbidden:
                    err_msg = f"Ошибка прав: Не удалось переместить {member_to_move.mention} в канал {team_name} (<#{target_channel.id}>). Проверьте права бота."
                    print(err_msg.replace("*","").replace("<#","").replace(">",""))
                    await self._send_channel_message(err_msg)
                except discord.HTTPException as e_http:
                    err_msg_http = f"Ошибка HTTP при перемещении {member_to_move.mention} в {team_name}: {e_http}"
                    print(err_msg_http.replace("*",""))
                    await self._send_channel_message(err_msg_http)
                except Exception as e_generic:
                    err_msg_generic = f"Непредвиденная ошибка при перемещении {member_to_move.mention} ({team_name}): {e_generic}"
                    print(err_msg_generic.replace("*",""))
                    await self._send_channel_message(err_msg_generic)

        if team1_channel:
            await _move_team(team1, team1_channel, "Команда 1")
        if team2_channel:
            await _move_team(team2, team2_channel, "Команда 2")


    async def create_voice_channel_invite(self, voice_channel_id: int) -> str | None:
        """
        Создает приглашение в указанный голосовой канал (по ID).
        В текущей реализации этот метод не используется активно, так как предпочтение
        отдается прямым ссылкам на каналы (<#channel_id>) или автоматическому перемещению.
        Может быть полезен для особых случаев или будущих расширений.
        Возвращает URL приглашения или None в случае ошибки.
        """
        voice_channel = self.bot.get_channel(voice_channel_id)
        if not voice_channel or not isinstance(voice_channel, discord.VoiceChannel):
            print(f"Голосовой канал с ID {voice_channel_id} не найден или не является голосовым каналом.")
            return None
        try:
            # Для общедоступных каналов на сервере ссылка <#channel_id> достаточна.
            # Инвайт может быть нужен для приватных каналов или внешних пользователей.
            # invite = await voice_channel.create_invite(max_age=300, max_uses=5, reason="Приглашение для команды")
            # return invite.url
            return f"Для присоединения используйте прямую ссылку: <#{voice_channel_id}>"
        except discord.HTTPException as e:
            print(f"Ошибка HTTP при создании приглашения для канала {voice_channel_id}: {e}")
        except Exception as e:
            print(f"Непредвиденная ошибка при создании приглашения для канала {voice_channel_id}: {e}")
        return None


    async def finalize_teams(self):
        """
        Завершает формирование команд после успешного голосования "Согласен" или принудительного решения.
        - Деактивирует флаг голосования.
        - Получает текущий состав команд (без перемешивания, так как они уже были показаны).
        - Отправляет сообщение в игровой канал с финальным составом команд.
        - Вызывает move_players_to_voice_channels для перемещения игроков.
        - Вызывает display_voice_channel_links для отображения ссылок на каналы.
        - Обновляет статус бота на "матч".
        - Сбрасывает голоса для подготовки к следующему возможному циклу.
        """
        print("Финализация команд после голосования 'Согласен' или по умолчанию...")
        self.voting_active = False

        # Команды должны быть уже сформированы и показаны до голосования,
        # поэтому здесь shuffle=False.
        team1, team2 = await self.auto_split_teams(shuffle=False)

        # Дополнительная проверка: если команды пусты, но игроки есть, это ошибка.
        if self.registered_players and (not team1 and not team2):
             print("КРИТИЧЕСКАЯ ОШИБКА: finalize_teams вызвана с зарегистрированными игроками, но команды пусты!")
             # Попытка аварийного переформирования. Это не должно происходить в нормальной логике.
             team1, team2 = await self.auto_split_teams(shuffle=True) # Пробуем перемешать

        # Если после всех проверок игроков нет или команды не сформированы, сбрасываем игру.
        if not self.registered_players or (not team1 and not team2):
            await self._send_channel_message("Не удалось финализировать команды: недостаточно игроков или команды не сформированы. Игра сброшена.")
            print("Финализация команд прервана: нет игроков или команды пусты. Вызов clear_registered_players.")
            await self.clear_registered_players()
            return

        embed_team1 = Embed(title="**Команда 1 (ИТОГ)**", description="\n".join([f'- {member.mention}' for member in team1]) if team1 else "Пусто", color=0x00FF00)
        embed_team2 = Embed(title="**Команда 2 (ИТОГ)**", description="\n".join([f'- {member.mention}' for member in team2]) if team2 else "Пусто", color=0xFF0000)

        await self._send_channel_message("Команды утверждены и финализированы! Начинается перемещение в голосовые каналы.", embeds=[embed_team1, embed_team2])

        await self.move_players_to_voice_channels(team1, team2)
        await self.display_voice_channel_links()
        await self.update_bot_status() # Статус должен стать "матч"
        await self.reset_votes() # Сбрасываем голоса для чистоты перед возможной следующей игрой
        print("Процесс финализации команд завершен: игроки перемещены/уведомлены, статус обновлен, голоса сброшены.")


    async def _create_team_embeds(self, team1: list[discord.User], team2: list[discord.User]) -> tuple[Embed, Embed]:
        """
        (Приватный) Создает и возвращает два объекта Embed для отображения составов Команды 1 и Команды 2.
        Использует упоминания игроков для их отображения.
        """
        desc1 = "\n".join([f'- {member.mention}' for member in team1]) if team1 else "Нет игроков"
        desc2 = "\n".join([f'- {member.mention}' for member in team2]) if team2 else "Нет игроков"
        embed_team1 = Embed(title="**Команда 1**", description=desc1, color=0x00FF00) # Зеленый
        embed_team2 = Embed(title="**Команда 2**", description=desc2, color=0xFF0000) # Красный
        return embed_team1, embed_team2

    async def display_teams_general(self, interaction: discord.Interaction, shuffle: bool = False, display_voting_buttons: bool = False):
        """
        Отображает текущий (возможно, предварительный) состав команд в канале, откуда пришла interaction.
        - Получает команды через auto_split_teams (с возможностью перемешивания).
        - Создает эмбеды для команд с помощью _create_team_embeds.
        - Отправляет сообщение с эмбедами.
        - Если display_voting_buttons=True:
            - Удаляет предыдущее сообщение с кнопками голосования (если было).
            - Создает и добавляет кнопки "Согласен" и "Перемешать".
            - Отправляет новое сообщение с кнопками и сохраняет его в self.voting_message.
        Логика отправки сообщений (response vs followup) обрабатывается для корректной работы с discord.Interaction.
        """
        if not interaction: # Дополнительная проверка, хотя interaction - обязательный параметр
            print("Критическая ошибка: display_teams_general вызван без объекта interaction.")
            return

        team1, team2 = await self.auto_split_teams(shuffle=shuffle)

        # Проверка, что команды не пусты, если есть зарегистрированные игроки
        if self.registered_players and not team1 and not team2:
            message_text = "Не удалось сформировать команды. Возможно, нужно больше игроков."
            if not interaction.response.is_done():
                await interaction.response.send_message(message_text, ephemeral=True)
            else:
                await interaction.followup.send(message_text, ephemeral=True)
            return

        embed_team1, embed_team2 = await self._create_team_embeds(team1, team2)
        message_content = "**Предварительный состав команд:**"

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(message_content, embeds=[embed_team1, embed_team2], ephemeral=False)
            else:
                # Используем followup, если initial response уже был (например, от /register)
                await interaction.followup.send(message_content, embeds=[embed_team1, embed_team2], ephemeral=False)
        except discord.HTTPException as e:
            print(f"Ошибка HTTP при отправке сообщения о составах команд: {e}")
            # Попытка отправить в канал напрямую, если interaction не сработал
            await self._send_channel_message(message_content, embeds=[embed_team1, embed_team2])
        except Exception as e_gen:
            print(f"Непредвиденная ошибка при отправке сообщения о составах команд: {e_gen}")


        if display_voting_buttons:
            if self.voting_message: # Удаляем старое сообщение с кнопками, если оно существует
                try:
                    await self.voting_message.delete()
                    print("Старое сообщение с кнопками голосования удалено.")
                except discord.NotFound:
                    pass
                except discord.HTTPException as e_del_http:
                    print(f"Ошибка HTTP при удалении старого сообщения с кнопками: {e_del_http}")
                except Exception as e_del_gen:
                     print(f"Непредвиденная ошибка при удалении старого сообщения с кнопками: {e_del_gen}")
                self.voting_message = None

            agree_button = VoteButton(label="Согласен", vote_type="agree", game_state=self)
            reshuffle_button = VoteButton(label="Перемешать", vote_type="reshuffle", game_state=self)
            view = View(timeout=None) # Таймаут для View можно настроить или убрать (None - без таймаута View)
            view.add_item(agree_button)
            view.add_item(reshuffle_button)

            try:
                # Сообщение с кнопками всегда отправляется как followup после основного сообщения о командах,
                # или как новый message, если interaction уже был полностью использован.
                # Для простоты и избежания "Interaction has already been responded to",
                # если interaction.response.is_done() is True, используем followup.
                # Если display_teams_general был вызван с interaction, на который еще не отвечали,
                # предыдущий блок (send_message/followup) уже должен был ответить.
                self.voting_message = await interaction.followup.send("Согласны с составом или перемешать?", view=view, wait=False) # wait=False, т.к. обработка в VoteButton
                print("Сообщение с кнопками голосования отправлено.")
            except discord.HTTPException as e_buttons_http:
                 print(f"Ошибка HTTP при отправке сообщения с кнопками голосования: {e_buttons_http}")
                 # Попытка отправить в канал напрямую как запасной вариант
                 self.voting_message = await self._send_channel_message("Согласны с составом или перемешать?", view=view)
            except Exception as e_buttons_gen:
                print(f"Непредвиденная ошибка при отправке сообщения с кнопками голосования: {e_buttons_gen}")


    async def reshuffle_and_revote(self, interaction: discord.Interaction):
        """
        Вызывается, когда голосование "Перемешать" получает достаточно голосов.
        - Сбрасывает предыдущие голоса и активирует флаг голосования.
        - Перемешивает команды (shuffle=True в display_teams_general).
        - Отображает новый состав команд и кнопки для нового голосования.
        - Запускает таймер для нового раунда голосования.
        - Обновляет статус бота.
        """
        print("Результат голосования: 'Перемешать'. Инициируем перемешивание и новое голосование.")
        await self.reset_votes() # Сбрасываем результаты предыдущего голосования
        self.voting_active = True # Активируем флаг нового голосования

        # display_teams_general с shuffle=True покажет новые команды и создаст новые кнопки голосования
        # interaction должен быть актуальным для отправки новых сообщений (followup)
        await self.display_teams_general(interaction=interaction, shuffle=True, display_voting_buttons=True)

        # Запускаем новый таймер голосования
        await self.start_voting(interaction)
        await self.update_bot_status() # Обновляем статус бота на "на голосование"
        print("Новый раунд голосования после перемешивания успешно инициирован.")

    # Старый метод reshuffle_teams был переименован/интегрирован в reshuffle_and_revote или используется только shuffle_teams()
    # async def reshuffle_teams(self):
    #     team1, team2 = await self.auto_split_teams(shuffle=True)  # Явное перемешивание
    #     await self.reset_votes()  # Сбрасываем состояние голосования
    #     self.voting_active = True  # Активируем голосование
    #     # Используем сохраненный last_interaction для инициации нового раунда голосования
    #     if self.last_interaction: # Убедимся, что last_interaction существует
    #         await self.display_teams_general(interaction=self.last_interaction, shuffle=True, display_voting_buttons=True)
    #         await self.start_voting(self.last_interaction) # Передаем interaction в start_voting
    #     else:
    #         # Эту ситуацию нужно обработать, например, отправив сообщение в канал по умолчанию
    #         print("Ошибка: last_interaction не установлен, не могу начать новое голосование после перемешивания.")
    #         channel = self.bot.get_channel(self.channel_id)
    #         if channel:
    #             await channel.send("Команды были перемешаны, но произошла ошибка с началом нового голосования. Пожалуйста, попробуйте снова.")
    #         # Возможно, стоит сбросить состояние или предпринять другие действия
    #         self.voting_active = False # Отключаем голосование, так как оно не может начаться корректно
    #     await self.update_bot_status()
