#bot.py
import discord
from discord import Option
import random
from datetime import datetime
import asyncio

from config import TOKEN
from config import GAME_CHANNEL_ID
from config import VOICE_CHANNEL_ID_TEAM1
from config import VOICE_CHANNEL_ID_TEAM2 

from game_state import GameState


bot = discord.Bot(intents=discord.Intents(guilds=True, messages=True, voice_states=True))


class RegisterButton(Button):
    def __init__(self, label: str, game_state: GameState):
        super().__init__(label=label, style=discord.ButtonStyle.green)
        self.game_state = game_state

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user
        is_full, response = await self.game_state.register_player(user, interaction)
        await interaction.followup.send(response, ephemeral=True)


game_state = GameState(bot, GAME_CHANNEL_ID)


@bot.event
async def on_ready():
    print(f'{bot.user} подключился к Discord!')
    channel = bot.get_channel(GAME_CHANNEL_ID)
    if channel:
        await channel.send("Бот подключен к Discord!")


@bot.event
async def on_slash_command_error(ctx, error):
    await ctx.respond('При обработке вашей команды произошла ошибка.', ephemeral=True)
    print(f'Ошибка в команде {ctx.command.name}: {error}')


@bot.event
async def on_rate_limit(ctx, rate_limit_info):
    print(f"Достигнут лимит запросов: {rate_limit_info}")
    await ctx.respond('Бот сейчас ограничен в запросах. Пожалуйста, попробуйте позже.', ephemeral=True)


@bot.slash_command(name='start_registration', description='Начать регистрацию игроков.')
async def start_registration(ctx, players_per_team: Option(int, "Введите количество игроков в команде", required=False, default=5)):
    await ctx.defer(ephemeral=True)
    if not await game_state.check_ready_to_start() and len(await game_state.get_registered_players()) == 0:
        success, message = await game_state.set_players_per_team(players_per_team)
        if success:
            await ctx.respond(f"Регистрация началась. Количество игроков в команде установлено в {players_per_team}.", ephemeral=True)
        else:
            await ctx.respond(f"Не удалось изменить количество игроков в команде. {message}", ephemeral=True)
    else:
        await ctx.respond("Регистрация уже началась или уже есть зарегистрированные игроки.", ephemeral=True)

    button = RegisterButton(label="Регистрация на матч", game_state=game_state)
    view = View()
    view.add_item(button)
    await ctx.respond('Нажмите на кнопку для регистрации.', view=view, ephemeral=True)


@bot.slash_command(name='register', description='Зарегистрироваться на текущий матч.')
async def register(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    is_full, response = await game_state.register_player(interaction.user, interaction)
    await interaction.followup.send(response, ephemeral=True)


@bot.slash_command(name='unregister', description='Отменить свою регистрацию на матч.')
async def unregister(ctx):
    response = await game_state.unregister_player(ctx.author)
    await ctx.respond(response)


@bot.slash_command(name='admin_register', description='Зарегистрировать игрока на матч командой администратора.', default_permission=False)
@discord.default_permissions(administrator=True)
async def admin_register(interaction: discord.Interaction, member: Option(discord.Member, "Выберите участника для регистрации")):
    await interaction.response.defer(ephemeral=True)
    is_full, response = await game_state.register_player(member, interaction)
    await interaction.followup.send(response, ephemeral=True)


@bot.slash_command(name='admin_unregister', description='Отменить регистрацию игрока командой администратора.', default_permission=False)
@discord.default_permissions(administrator=True)
async def admin_unregister(ctx, member: Option(discord.Member, "Выберите участника для отмены регистрации")):
    await ctx.defer(ephemeral=True)
    response = await game_state.unregister_player(member)
    await ctx.followup.send(response, ephemeral=True)


@bot.slash_command(name='set_players', description='Изменить количество игроков в команде.', default_permission=False)
@discord.default_permissions(administrator=True)
async def set_players_per_team(interaction: discord.Interaction, number: Option(int, "Введите новое количество игроков в команде")):
    await interaction.response.defer(ephemeral=True)
    success, response = await game_state.set_players_per_team(number)
    await interaction.followup.send(response, ephemeral=True)


@bot.slash_command(name='stop_registration', description='Остановить регистрацию и очистить список зарегистрированных игроков.', default_permission=False)
@discord.default_permissions(administrator=True)
async def stop_registration(ctx):
    response = await game_state.clear_registered_players()
    await ctx.respond(response)


@bot.slash_command(name='voice_moving', description="Распределить игроков в войс каналах по командам", default_permission=False)
@discord.default_permissions(administrator=True)
async def voice_moving(ctx):
    # Предполагаем, что у вас есть доступ к экземпляру GameState через ctx или глобально
    await game_state.finalize_teams()
    await ctx.respond("Команды распределены, ссылки на голосовые каналы отправлены.", ephemeral=True)


@bot.slash_command(name='info', description='Вывести информацию о зарегистрированных игроках.')
async def info(ctx):
    players_per_team = await game_state.get_players_per_team()
    registered_players = await game_state.get_registered_players()
    embed_info = discord.Embed(
        title="**Информация о регистрации**",
        color=0xFFA500
    )
    embed_info.add_field(
        name="Зарегистрировано игроков",
        value=f"**{len(registered_players)} из {players_per_team*2}**",
        inline=False
    )
    if registered_players:
        registered_players_mentions = "\n".join([f'- {player.mention}' for player in registered_players])
        embed_info.add_field(
            name="Зарегистрированные игроки:",
            value=registered_players_mentions,
            inline=True
        )
    else:
        embed_info.add_field(
            name="Зарегистрированные игроки",
            value="Игроки еще не зарегистрированы.",
            inline=True
        )
    await ctx.respond(embed=embed_info, ephemeral=True)

bot.run(TOKEN)
