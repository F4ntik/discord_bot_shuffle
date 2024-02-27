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
        self.reset_task = None  # Для отслеживания задачи сброса

    async def start_reset_timer(self):
        # Отменяем предыдущий таймер, если он был запущен
        if self.reset_task:
            self.reset_task.cancel()
        # Запускаем новый таймер
        self.reset_task = asyncio.create_task(self.reset_game_state_after_delay())

    async def reset_game_state_after_delay(self):
        # Ждем 30 минут
        await asyncio.sleep(1800)  # 30 минут
        # Сбрасываем состояние игры и обновляем статус бота
        await self.clear_registered_players()
        await self.bot.change_presence(status=discord.Status.online)

    async def process_vote(self, user, vote_type):
        if not self.voting_active:
            await self.last_interaction.followup.send("Голосование закончено, матч начался.", ephemeral=True)
            return

        # Проверяем, является ли пользователь зарегистрированным игроком
        if user not in self.registered_players:
            await self.last_interaction.followup.send("Ваш голос не учитывается, так как вы не зарегистрированы на матч.", ephemeral=True)
            return

        # Учет голосов
        self.votes[vote_type] += 1
        total_votes = sum(self.votes.values())

        # Определение необходимого количества голосов для решения
        players_needed_to_decide = max(int(config.VOTE_THRESHOLD * len(self.registered_players)), 1)  # Ensure at least 1 vote is required

        # Check if enough votes have been cast to make a decision
        if self.votes["agree"] >= players_needed_to_decide or self.votes["reshuffle"] >= players_needed_to_decide:
            await self.evaluate_votes()
        else:
            # Update voting message with the current state if the vote has not reached a decision
            if self.voting_message:
                agree_percentage = (self.votes["agree"] / total_votes) * 100
                reshuffle_percentage = (self.votes["reshuffle"] / total_votes) * 100
                new_content = f"Текущее голосование: Согласны - {self.votes['agree']} ({agree_percentage:.1f}%), Перемешать - {self.votes['reshuffle']} ({reshuffle_percentage:.1f}%)"
                await self.voting_message.edit(content=new_content)

    async def register_player(self, player, interaction):
        if self.voting_active:
            # Если голосование активно, запретить регистрацию
            await interaction.response.send_message("Регистрация закрыта, так как голосование началось.", ephemeral=True)
            return (False, "Регистрация закрыта.")
        if player not in self.registered_players and len(self.registered_players) < self.players_per_team * 2:
            self.registered_players.append(player)
            self.last_interaction = interaction  # Сохраняем последний interaction для использования в будущем
            await self.update_bot_status()
            if await self.check_ready_to_start():
                await self.display_teams_general(interaction=interaction, shuffle=True, display_voting_buttons=True)
                return (True, 'Достигнуто максимальное количество игроков. Старт матча')
            return (False, f'{player.mention} зарегистрирован на матч. Игроков зарегистрировано {len(self.registered_players)} из {self.players_per_team * 2}.')
        return (False, f'{player.mention}, вы уже зарегистрированы или достигнуто максимальное количество игроков.')

    async def unregister_player(self, player):
        if self.voting_active:
            # Если голосование активно, запретить отмену регистрации
            return f"Отмена регистрации закрыта, так как голосование началось."
        if player in self.registered_players:
            self.registered_players.remove(player)
            await self.update_bot_status()
            return f'{player.mention}, ваша регистрация отменена. Игроков зарегистрировано {len(self.registered_players)} из {self.players_per_team * 2}.'
        return f'{player.mention}, вы не были зарегистрированы.'

    async def shuffle_teams(self):
        random.shuffle(self.registered_players)

    async def auto_split_teams(self, shuffle=False):
        if shuffle:
            await self.shuffle_teams()  # Перемешивание происходит только по требованию
        mid_index = len(self.registered_players) // 2
        team1 = self.registered_players[:mid_index]
        team2 = self.registered_players[mid_index:]
        return (team1, team2)

    async def check_ready_to_start(self):
        return len(self.registered_players) == self.players_per_team * 2

    async def clear_registered_players(self):
        self.registered_players = []
        await self.update_bot_status()
        return "Список зарегистрированных игроков очищен."

    async def set_players_per_team(self, number):
        if not(1 <= number <= 6):
            return False, 'Количество игроков в команде должно быть от 1 до 6.'
        elif await self.check_ready_to_start():
            # Если игра уже началась, изменение количества игроков не разрешается
            return False, 'Изменение количества игроков невозможно после начала регистрации.'
        else:
            self.players_per_team = number
            await self.update_bot_status()
            return True, f'Количество игроков в команде установлено в {self.players_per_team}.'

    async def get_registered_players(self):
        return self.registered_players

    async def get_players_per_team(self):
        return self.players_per_team

    async def display_voice_channel_links(self):
        channel = self.bot.get_channel(self.channel_id)
        if self.registered_players:
            message = "Присоединитесь к голосовому каналу своей команды:\n"
            message += f"Команда 1: <#{config.VOICE_CHANNEL_ID_TEAM1}>\n"
            message += f"Команда 2: <#{config.VOICE_CHANNEL_ID_TEAM2}>"
            await channel.send(message)
        else:
            await channel.send("Пустой список игроков.")

    async def update_bot_status(self):
        if self.voting_active:
            # Если голосование активно, устанавливаем статус "на голосование"
            activity = discord.Activity(type=discord.ActivityType.watching, name="на голосование")
            await self.bot.change_presence(status=discord.Status.online, activity=activity)

        elif await self.check_ready_to_start():
            activity = discord.Activity(type=discord.ActivityType.watching, name="матч")
            await self.bot.change_presence(status=discord.Status.online, activity=activity)
            await self.start_reset_timer()
        elif self.registered_players:  
            activity = discord.Activity(type=discord.ActivityType.watching, name=f"на {len(self.registered_players)}/{self.players_per_team*2} игроков")
            await self.bot.change_presence(status=discord.Status.online, activity=activity)
        else:
            activity = discord.Activity(type=discord.ActivityType.watching, name="на начало регистрации")
            await self.bot.change_presence(status=discord.Status.online, activity=activity)

    async def evaluate_votes(self):
        total_votes = sum(self.votes.values())
        if total_votes == 0:
            return  # Avoid division by zero

        agree_percentage = (self.votes["agree"] / total_votes) * 100
        reshuffle_percentage = (self.votes["reshuffle"] / total_votes) * 100

        if agree_percentage >= config.VOTE_THRESHOLD * 100:
            await self.finalize_teams()
            await self.update_bot_status()
        elif reshuffle_percentage >= config.VOTE_THRESHOLD * 100:
            await self.reshuffle_teams()
            await self.update_bot_status()
            if self.last_interaction:
                await self.display_teams_general(interaction=interaction, shuffle=True, display_voting_buttons=True)
            else:
                print("last_interaction is None, cannot display teams with voting")

        await self.reset_votes()  # Reset votes after handling

    async def reset_votes(self):
        self.votes = {"agree": 0, "reshuffle": 0}
        self.voting_active = False

    async def move_players_to_voice_channels(self, team1, team2):
        # Получаем объекты гильдии и каналов напрямую по ID из конфигурации
        guild = self.bot.get_guild(config.GUILD_ID)

        team1_channel = guild.get_channel(config.VOICE_CHANNEL_ID_TEAM1)
        team2_channel = guild.get_channel(config.VOICE_CHANNEL_ID_TEAM2)

        if not team1_channel or not team2_channel:
            print("Один из каналов не найден.")
            return

        # Логика перемещения игроков команды 1
        for member in team1:
            try:
                await member.move_to(team1_channel)
            except Exception as e:
                print(f"Ошибка при перемещении участника {member.display_name} в канал команды 1 (Команда 1): {e}")

        # Логика перемещения игроков команды 2
        for member in team2:
            try:
                await member.move_to(team2_channel)
            except Exception as e:
                print(f"Ошибка при перемещении участника {member.display_name} в канал команды 2 (Команда 2): {e}")

    async def create_voice_channel_invite(self, voice_channel):
        invite = await voice_channel.create_invite(max_age=300)  # 5 minutes for example
        return invite.url

        # Use this method in your player moving/shuffling logic
        invite_url = await self.create_voice_channel_invite(team1_channel if team == "team1" else team2_channel)
        await member.send(f"Please join your team's voice channel: {invite_url}")

    async def finalize_teams(self):
        team1, team2 = await self.auto_split_teams()
        await self.move_players_to_voice_channels(team1, team2)
        await self.display_voice_channel_links()

    async def display_teams_general(self, interaction=None, shuffle=False, display_voting_buttons=False):
        team1, team2 = await self.auto_split_teams(shuffle=shuffle)

        # Создаем embed сообщения для каждой команды
        embed_team1 = discord.Embed(title="**Команда 1**", description="\n".join([f'- {member.mention}' for member in team1]), color=0x00FF00)
        embed_team2 = discord.Embed(title="**Команда 2**", description="\n".join([f'- {member.mention}' for member in team2]), color=0xFF0000)

        # Определяем канал для отправки сообщений
        channel = self.bot.get_channel(self.channel_id)

        # Отправляем предварительное сообщение о списке команд, гарантируя его видимость всем пользователям
        preliminary_message_content = "**Список команд**"
        if interaction:
            # Для интеракций используем followup.send без указания ephemeral, чтобы сообщение было видно всем
            await interaction.followup.send(preliminary_message_content)
        else:
            # Если интеракции нет, отправляем сообщение напрямую в канал
            await channel.send(preliminary_message_content)

        # Отправляем embed сообщения с командами
        message_content = "Команды сформированы:"
        if interaction:
            await interaction.followup.send(message_content, embeds=[embed_team1, embed_team2])
        else:
            await channel.send(message_content, embeds=[embed_team1, embed_team2])

        # Если нужно отображать кнопки голосования, добавляем их
        if display_voting_buttons:
            agree_button = VoteButton(label="Согласен", vote_type="agree", game_state=self)
            reshuffle_button = VoteButton(label="Перемешать", vote_type="reshuffle", game_state=self)
            view = discord.ui.View()
            view.add_item(agree_button)
            view.add_item(reshuffle_button)

            # Отправляем сообщение с кнопками голосования
            if interaction:
                await interaction.followup.send("Выберите действие:", view=view)
            else:
                await channel.send("Выберите действие:", view=view)

    async def reshuffle_teams(self):
        team1, team2 = await self.auto_split_teams(shuffle=True)  # Явное перемешивание
        await self.reset_votes()  # Сбрасываем состояние голосования
        self.voting_active = True  # Активируем голосование
        # Используем сохраненный last_interaction для инициации нового раунда голосования
        if self.last_interaction:
            await self.display_teams_general(interaction=interaction, shuffle=True, display_voting_buttons=True)
