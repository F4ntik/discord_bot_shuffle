import discord
from discord import Option
from discord.ui import Button, View
import random
from datetime import datetime
import asyncio

from config import TOKEN
from config import GAME_CHANNEL_ID 

from game_state import GameState


bot = discord.Bot(intents=discord.Intents.default())

game_state = GameState(bot, GAME_CHANNEL_ID)


class RegisterButton(Button):
    def __init__(self, label: str, game_state: GameState):
        super().__init__(label=label, style=discord.ButtonStyle.green)
        self.game_state = game_state  # Сохраняем ссылку на экземпляр GameState для использования в callback

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        is_full, response = await self.game_state.register_player(user)  # Попытка регистрации игрока
        await interaction.response.send_message(response, ephemeral=True)  # Отправляем уведомление пользователю


@bot.event
async def on_ready():
    print(f'{bot.user} подключился к Discord!')
    #вывод сообщения в тестовый канал
    channel = bot.get_channel(GAME_CHANNEL_ID)
    if channel:
        # Отправляем сообщение в канал о том, что бот подключился
        await channel.send("Бот подключен к Discord!")


@bot.event
async def on_slash_command_error(ctx, error):
    if isinstance(error, commands.errors.CheckFailure):
        await ctx.respond('У вас нет необходимых прав для использования этой команды.', ephemeral=True)
    else:
        await ctx.respond('При обработке вашей команды произошла ошибка.', ephemeral=True)
        print(f'Ошибка в команде {ctx.command.name}: {error}')


@bot.event
async def on_rate_limit(ctx, rate_limit_info):
    print(f"Достигнут лимит запросов: {rate_limit_info}")
    await ctx.respond('Бот сейчас ограничен в запросах. Пожалуйста, попробуйте позже.', ephemeral=True)


@bot.slash_command(name='start_registration', description='Начать регистрацию игроков. Можно указать кол-во игроков на команду.')
async def start_registration(ctx, players_per_team: Option(int, "Введите количество игроков в команде", required=False, default=5)):
    # Проверяем, что регистрация еще не началась
    if not await game_state.check_ready_to_start() and len(await game_state.get_registered_players()) == 0:
        # Устанавливаем количество игроков в команде
        success, message = await game_state.set_players_per_team(players_per_team)
        if success:
            await ctx.respond(f"Регистрация началась. Количество игроков в команде установлено в {players_per_team}.", ephemeral=True)
        else:
            await ctx.respond(f"Не удалось изменить количество игроков в команде. {message}", ephemeral=True)
    else:
        await ctx.respond("Регистрация уже началась или уже есть зарегистрированные игроки.", ephemeral=True)

    # Создаем кнопку для регистрации с передачей game_state
    button = RegisterButton(label="Регистрация на матч", game_state=game_state)
    view = View()
    view.add_item(button)
    await ctx.respond('Нажмите на кнопку для регистрации.', view=view)


@bot.slash_command(name='register', description='Зарегистрироваться на текущий матч.')
async def register(ctx):
    is_full, response = await game_state.register_player(ctx.author)
    await ctx.respond(response)
    if is_full:
        # Если регистрация полна, отобразите состав команд
        await show_teams(ctx)


@bot.slash_command(name='unregister', description='Отменить свою регистрацию на матч.')
async def unregister(ctx):
    response = await game_state.unregister_player(ctx.author)
    await ctx.respond(response)


@bot.slash_command(name='admin_register', description='Зарегистрировать игрока на матч командой администратора.', default_permission=False)
@discord.default_permissions(administrator=True)
async def admin_register(ctx, member: Option(discord.Member, "Выберите участника для регистрации")):
    is_full, response = await game_state.register_player(member) 
    await ctx.respond(response)
    if is_full:
        # Если регистрация полна, отобразите состав команд
        await show_teams(ctx)


@bot.slash_command(name='admin_unregister', description='Отменить регистрацию игрока командой администратора.', default_permission=False)
@discord.default_permissions(administrator=True)
async def admin_unregister(ctx, member: Option(discord.Member, "Выберите участника для отмены регистрации")):
    response = await game_state.unregister_player(member) 
    await ctx.respond(response)


@bot.slash_command(name='set_players', description='Изменить количество игроков в команде. Только для администраторов.', default_permission=False)
@discord.default_permissions(administrator=True)
async def set_players_per_team(ctx, number: Option(int, "Введите новое количество игроков в команде")):
    is_full, response = await game_state.set_players_per_team(number)
    if is_full:
        # Если регистрация полна, отобразите состав команд
        await show_teams(ctx)
    else:
        await ctx.respond(response)


@bot.slash_command(name='stop_registration', description='Остановить регистрацию и очистить список зарегистрированных игроков. Только для администраторов.', default_permission=False)
@discord.default_permissions(administrator=True)
async def stop_registration(ctx):
    response = await game_state.clear_registered_players()
    activity = discord.Activity(type=discord.ActivityType.watching, name="на выдру")
    await bot.change_presence(status=discord.Status.online, activity=activity)
    await asyncio.sleep(3)
    await bot.change_presence(status=discord.Status.online, activity=None)
    await ctx.respond(response)


@bot.slash_command(name='reshuffle', description='Пересортировать команды.')
@discord.default_permissions(administrator=True)
async def reshuffle(ctx):
    await game_state.reshuffle_teams()  # Пересортировка
    # Отправка обновленного состава команд


@bot.slash_command(name='show_teams', description='Показать текущий состав команд.')
async def show_teams(ctx):
    team1, team2 = await game_state.auto_split_teams()
    # Форматирование и отправка сообщения с составом команд
    if (await game_state.check_ready_to_start()):
        await display_teams(ctx, team1, team2)
    else:
        await ctx.respond("Команды не сформированы", ephemeral=True)


@bot.slash_command(name='info', description='Вывести информацию о зарегистрированных игроках.', default_permission=False)
async def info(ctx):
    players_per_team = await game_state.get_players_per_team()
    registered_players = await game_state.get_registered_players()
    mid_index = len(registered_players) // 2
        # Создаем Embed сообщение для более структурированного отображения информации
    embed_info = discord.Embed(
        title="**Информация о регистрации**",
        color=0xFFA500  # Оранжевый цвет
    )
    embed_info.add_field(
        name="Зарегистрировано игроков",
        value=f"**{len(registered_players)} из {players_per_team*2}**",  
        inline=False
    )
    if registered_players:  # Проверяем, есть ли зарегистрированные игроки
    # Формируем строку с упоминаниями всех зарегистрированных игроков
        registered_players_mentions1 = "\n".join([f'- {player.mention}' for player in registered_players[mid_index:]])
        registered_players_mentions2 = "\n".join([f'- {player.mention}' for player in registered_players[:mid_index]])
        embed_info.add_field(
            name="Зарегистрированные игроки:",
            value=registered_players_mentions1,
            inline=True
        )
        embed_info.add_field(
                name="📋",
                value=registered_players_mentions2,
                inline=True
        )    
    else:
        embed_info.add_field(
            name="Зарегистрированные игроки",
            value="Игроки еще не зарегистрированы.",
            inline=True
        )
    await ctx.respond(embed=embed_info)


async def display_teams(ctx, team1, team2):
    if await game_state.check_ready_to_start():  # Убедитесь, что используете await
        embed_team1 = discord.Embed(title="**Команда 1**", description="\n".join([f'- {player.mention}' for player in team1]), color=0x0000FF)
        embed_team2 = discord.Embed(title="**Команда 2**", description="\n".join([f'- {player.mention}' for player in team2]), color=0xFF0000)
        await ctx.respond(embeds=[embed_team1, embed_team2])  # Используйте await для асинхронного вызова
    else:
        await ctx.respond("Команды не сформированы")

bot.run(TOKEN)
