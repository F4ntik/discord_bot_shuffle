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

        # Определение необходимого количества голосов для решения
        players_needed_to_decide = max(int(VOTE_THRESHOLD * len(self.registered_players)), 1)  # Ensure at least 1 vote is required

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

    async def display_voice_channel_links(self):
        channel = self.bot.get_channel(self.channel_id)
        message = "Join your team's voice channel:\n"
        message += f"Team 1: <#{VOICE_CHANNEL_ID_TEAM1}>\n"
        message += f"Team 2: <#{VOICE_CHANNEL_ID_TEAM2}>"
        await channel.send(message)

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
        players_needed_to_decide = max(int(VOTE_THRESHOLD * len(self.registered_players)), 1)

        # Decide based on vote counts and threshold
        if self.votes["agree"] >= players_needed_to_decide:
            # Finalize teams and proceed with the game
            await self.finalize_teams()
        elif self.votes["reshuffle"] >= players_needed_to_decide:
            # Reshuffle teams and restart the voting process
            await self.reshuffle_teams()
            # Potentially initiate a new round of voting here

        # Reset the voting state for the next decision
        self.reset_votes()

    async def reset_votes(self):
        self.votes = {"agree": 0, "reshuffle": 0}
        self.voting_active = False

    async def move_players_to_voice_channels(self, team1, team2):
        guild_id = str(self.bot.guilds[0].id)  # Assuming the bot is only in one guild, adjust as necessary
        team1_channel = self.bot.get_channel(VOICE_CHANNEL_ID_TEAM1)
        team2_channel = self.bot.get_channel(VOICE_CHANNEL_ID_TEAM2)

        for team, voice_channel in [("team1", team1_channel), ("team2", team2_channel)]:
            for player in team1 if team == "team1" else team2:
                member = await self.bot.guilds[0].fetch_member(player.id)  # Adjust to correctly fetch Guild and Member
                if member.voice and member.voice.channel == voice_channel:
                    continue  # Skip if already in the correct voice channel
                try:
                    await member.move_to(voice_channel)
                except Exception:
                    # Correctly format the channel link
                    voice_channel_link = f"https://discord.com/channels/{guild_id}/{voice_channel.id}"
                    await member.send(f"Please join your team's voice channel: {voice_channel_link}")

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

    async def display_teams_with_voting(self, interaction):
        team1, team2 = await self.auto_split_teams()
        if await self.check_ready_to_start():
            self.voting_active = True

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
