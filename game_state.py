import random
import discord
import asyncio


class GameState:
    def __init__(self, bot, channel_id):
        self.bot = bot
        self.registered_players = []
        self.players_per_team = 5
        self.channel_id = channel_id

    async def register_player(self, player):
        if player not in self.registered_players and len(self.registered_players) < self.players_per_team * 2:
            self.registered_players.append(player)
            await self.update_bot_status()
            if await self.check_ready_to_start():
                team1, team2 = await self.auto_split_teams()
                # Используйте self.channel_id здесь, без передачи как параметра
                await self.display_teams(team1, team2)
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
            await asyncio.sleep(20)  # Задержка в 2 минуты (120 секунд)
            await self.bot.change_presence(status=discord.Status.online, activity=None)
        elif self.registered_players:  
            activity = discord.Activity(type=discord.ActivityType.watching, name=f"{len(self.registered_players)}/{self.players_per_team*2} игроков")
            await self.bot.change_presence(status=discord.Status.online, activity=activity)
        else:
            activity = discord.Activity(type=discord.ActivityType.watching, name="Регистрация")
            await self.bot.change_presence(status=discord.Status.online, activity=activity)

    async def display_teams(self, team1, team2):
        channel = self.bot.get_channel(self.channel_id)
        if channel:
            embed_team1 = discord.Embed(title="**Команда 1**", description="\n".join([f'- {player.mention}' for player in team1]), color=0x0000FF)
            embed_team2 = discord.Embed(title="**Команда 2**", description="\n".join([f'- {player.mention}' for player in team2]), color=0xFF0000)
            await channel.send(embeds=[embed_team1, embed_team2])
        else:
            print("Невозможно отправить сообщение: канал не найден.")
