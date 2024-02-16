# game_state.py
import random
import discord
import asyncio
from components import VoteButton
from discord.ui import View
from discord import Embed


class GameState:
    def __init__(self, bot, channel_id):
        self.bot = bot
        self.registered_players = []
        self.players_per_team = 5
        self.channel_id = channel_id
        self.votes = {"agree": 0, "reshuffle": 0}
        self.voting_active = False
        self.voting_message = None  # Добавляем атрибут для хранения сообщения голосования

    async def process_vote(self, user, vote_type):
        if not self.voting_active:
            print("Голосование не активно.")
            return

        # Учет голосов
        self.votes[vote_type] += 1
        total_votes = sum(self.votes.values())

        # Проверка условий окончания голосования
        if total_votes >= len(self.registered_players):
            await self.evaluate_votes()
        else:
            # Обновляем сообщение с текущим состоянием голосования (псевдокод)
            if self.voting_message:
                new_content = f"Текущее голосование: Согласны - {self.votes['agree']}, Перемешать - {self.votes['reshuffle']}"
                await self.voting_message.edit(content=new_content)       

    async def register_player(self, player, interaction):
        if player not in self.registered_players and len(self.registered_players) < self.players_per_team * 2:
            self.registered_players.append(player)
            await self.update_bot_status()
            if await self.check_ready_to_start():
                # После регистрации последнего игрока отображаем команды с кнопками для голосования
                await self.display_teams_with_voting(interaction)  # Предполагается, что этот метод уже включает логику отображения команд и добавления кнопок
                return (True, 'Достигнуто максимальное количество игроков. Старт матча')
            return (False, f'{player.mention} зарегистрирован на матч. Игроков зарегистрировано {len(self.registered_players)} из {self.players_per_team * 2}.')
        return (False, f'{player.mention}, вы уже зарегистрированы или достигнуто максимальное количество игроков.')

    async def unregister_player(self, player):
        if player in self.registered_players:
            self.registered_players.remove(player)
            await self.update_bot_status()
            return f'{player.mention}, ваша регистрация отменена. Игроков зарегистрировано {len(self.registered_players)} из {self.players_per_team * 2}.'
        return f'{player.mention}, вы не были зарегистрированы.'

    async def shuffle_teams(self):
        random.shuffle(self.registered_players)

    async def auto_split_teams(self):
        await self.shuffle_teams()  # Ensure teams are shuffled before splitting
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

    async def update_bot_status(self):
        if await self.check_ready_to_start():
            activity = discord.Activity(type=discord.ActivityType.watching, name="матч")
            await self.bot.change_presence(status=discord.Status.online, activity=activity)
            await asyncio.sleep(3)  
        elif self.registered_players:  
            activity = discord.Activity(type=discord.ActivityType.watching, name=f"{len(self.registered_players)}/{self.players_per_team*2} игроков")
            await self.bot.change_presence(status=discord.Status.online, activity=activity)
        else:
            activity = discord.Activity(type=discord.ActivityType.watching, name="Регистрация")
            await self.bot.change_presence(status=discord.Status.online, activity=activity)

    async def display_teams(self, ctx, team1, team2):
        channel = self.bot.get_channel(self.channel_id)
        if channel:
            embed_team1 = discord.Embed(title="**Команда 1**", description="\n".join([f'- {player.mention}' for player in team1]), color=0x0000FF)
            embed_team2 = discord.Embed(title="**Команда 2**", description="\n".join([f'- {player.mention}' for player in team2]), color=0xFF0000)
            await channel.send(embeds=[embed_team1, embed_team2])
        else:
            print("Невозможно отправить сообщение: канал не найден.")

    async def evaluate_votes(self):
        total_votes = sum(self.votes.values())
        agree_percentage = self.votes["agree"] / total_votes
        if agree_percentage >= VOTE_THRESHOLD:
            await self.finalize_teams()
        else:
            await self.reshuffle_teams()
        self.reset_votes()

    async def reset_votes(self):
        self.votes = {"agree": 0, "reshuffle": 0}
        self.voting_active = False

    async def move_players_to_voice_channels(self, team1, team2):
        for team, voice_channel_id in self.voice_channel_ids.items():
            voice_channel = self.bot.get_channel(voice_channel_id)
            if voice_channel:
                for player in team1 if team == "team1" else team2:
                    member = voice_channel.guild.get_member(player.id)
                    if member:
                        try:
                            await member.move_to(voice_channel)
                        except discord.Forbidden:
                            # Handle cases where the bot doesn't have permissions to move members
                            await player.send(f"Unable to move you to the voice channel. Please join {voice_channel.mention} manually.")
                    else:
                        await player.send(f"Join your team's voice channel: {voice_channel.mention}")
            else:
                print(f"Voice channel not found for {team}.")

    async def finalize_teams(self):
        team1, team2 = await self.auto_split_teams()
        await self.move_players_to_voice_channels(team1, team2)

    async def display_teams_with_voting(self, interaction: discord.Interaction):
        team1, team2 = await self.auto_split_teams()
        if await self.check_ready_to_start():
            self.voting_active = True

    async def display_teams_with_voting(self, interaction):
        team1, team2 = await self.auto_split_teams()

        # Logic to display teams with Embeds
        embed_team1 = Embed(title="Команда 1", description="\n".join([member.mention for member in team1]), color=0x00FF00)
        embed_team2 = Embed(title="Команда 2", description="\n".join([member.mention for member in team2]), color=0xFF0000)

        # Assuming interaction.followup.send() is correctly awaited elsewhere in the context of handling the interaction
        await interaction.followup.send("Команды сформированы:", embeds=[embed_team1, embed_team2], ephemeral=False)

        # Add voting buttons
        agree_button = VoteButton(label="Согласен", vote_type="agree", game_state=self)
        reshuffle_button = VoteButton(label="Перемешать", vote_type="reshuffle", game_state=self)

        view = View()
        view.add_item(agree_button)
        view.add_item(reshuffle_button)

        # Send the message with voting buttons
        await interaction.followup.send("Выберите действие:", view=view, ephemeral=False)

    async def reshuffle_teams(self):
        await self.shuffle_teams()
        # Метод для пересортировки команд; дополнительная логика может быть добавлена здесь
