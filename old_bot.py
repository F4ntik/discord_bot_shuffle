import discord
from discord import Option
from discord.ui import Button, View
import random
from datetime import datetime
import asyncio
from config import TOKEN


bot = discord.Bot(intents=discord.Intents.default())

registered_players = []
players_per_team = 5

class RegisterButton(Button):
    def __init__(self, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.green)
    
    async def callback(self, interaction: discord.Interaction):
        # Используем interaction вместо context_or_interaction и interaction.user для пользователя
        await common_register(interaction.user, interaction)

@bot.event
async def on_ready():
    print(f'{bot.user} подключился к Discord!')
    #вывод сообщения в тестовый канал
    channel = bot.get_channel(1181262662991106130)
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

@bot.slash_command(name='start_registration', description='Начать регистрацию игроков с необязательным количеством игроков в команде.')
async def start_registration(ctx, number_of_players: Option(int, "Введите количество игроков в команде", required=False, default=5)):
    global registered_players, players_per_team
    players_per_team = number_of_players
    registered_players = []
    
    # Создаем кнопку для регистрации
    button = RegisterButton(label="Регистрация на матч")
    view = View()
    view.add_item(button)
    
    await ctx.respond(f'Регистрация началась! Нажмите на кнопку для регистрации. Игроков в команде: {players_per_team}', view=view)
    await update_bot_status()

@bot.slash_command(name='register', description='Зарегистрироваться на текущий матч.')
async def register(ctx):
    # Передаём ctx.author как пользователя и ctx для ответа
    await common_register(ctx.author, ctx)



@bot.slash_command(name='unregister', description='Отменить свою регистрацию на матч.')
async def unregister(ctx):
    await unregister_player(ctx, ctx.author)
    await update_bot_status()

@bot.slash_command(name='admin_register', description='Зарегистрировать игрока на матч командой администратора.', default_permission=False)
@discord.default_permissions(administrator=True)
async def admin_register(ctx, member: Option(discord.Member, "Выберите участника для регистрации")):
    # Передаём member как пользователя и ctx для ответа
    await common_register(member, ctx)




@bot.slash_command(name='admin_unregister', description='Отменить регистрацию игрока командой администратора.', default_permission=False)
@discord.default_permissions(administrator=True)
async def admin_unregister(ctx, member: Option(discord.Member, "Выберите участника для отмены регистрации")):
    await common_register(ctx, user=member)

@bot.slash_command(name='set_players', description='Изменить количество игроков в команде. Только для администраторов.', default_permission=False)
@discord.default_permissions(administrator=True)
async def set_players_per_team(ctx, number: Option(int, "Введите новое количество игроков в команде")):
    global players_per_team
    if number < 1 or number > 6:
        await ctx.respond('Количество игроков в команде должно быть от 2 до 5.')
    else:
        players_per_team = number
        await ctx.respond(f'Количество игроков в команде установлено в {players_per_team}. Всего игроков, необходимых для начала матча: {2 * players_per_team}.')
    update_bot_status()

@bot.slash_command(name='stop_registration', description='Остановить регистрацию и очистить список зарегистрированных игроков. Только для администраторов.', default_permission=False)
@discord.default_permissions(administrator=True)
async def stop_registration(ctx):
    global registered_players
    registered_players = []
    await ctx.respond('Регистрация остановлена и список игроков очищен.')

@bot.slash_command(name='reshuffle_teams', description='Пересортировать игроков и вывести новые списки команд. Только для администраторов.', default_permission=False)
@discord.default_permissions(administrator=True)
async def reshuffle_teams(ctx):
    await split_teams(ctx, reshuffle=True)

@bot.slash_command(name='info', description='Вывести информацию о зарегистрированных игроках.', default_permission=False)
async def info(ctx):
    # Создаем Embed сообщение для более структурированного отображения информации
    embed_info = discord.Embed(
        title="**Информация о регистрации**",
        color=0xFFA500  # Оранжевый цвет
    )
    embed_info.add_field(
        name="Необходимое количество игроков в команде",
        value=f"**{players_per_team}**",  # Выделение жирным для визуального акцента
        inline=True
    )
    embed_info.add_field(
        name="Зарегистрировано игроков",
        value=f"**{len(registered_players)} из {players_per_team*2}**",  # Аналогичное выделение
        inline=True
    )
    # Формируем строку с упоминаниями всех зарегистрированных игроков
    registered_players_mentions = "\n".join([f'- {player.mention}' for player in registered_players])
    if registered_players_mentions:  # Проверяем, есть ли зарегистрированные игроки
        embed_info.add_field(
            name="Зарегистрированные игроки",
            value=registered_players_mentions,
            inline=True
        )
    else:
        embed_info.add_field(
            name="Зарегистрированные игроки",
            value="Игроки еще не зарегистрированы.",
            inline=True
        )

    # Выводим информацию в чат с помощью Embed
    await ctx.respond(embed=embed_info)

async def split_teams(context_or_interaction, reshuffle=False):
    global registered_players, players_per_team
    if reshuffle or not hasattr(split_teams, "last_teams"):
        random.shuffle(registered_players)
        team1 = registered_players[:players_per_team]
        team2 = registered_players[players_per_team:]
        split_teams.last_teams = (team1, team2)  # Сохраняем последние команды для возможности пересортировки
    else:
        team1, team2 = split_teams.last_teams

    await display_teams(context_or_interaction, team1, team2)


async def common_register(user: discord.Member, response_target):
    global registered_players, players_per_team

    if len(registered_players) >= 2 * players_per_team:
        message = f'Достигнуто максимальное количество игроков: {players_per_team * 2}.'
        if isinstance(response_target, discord.Interaction):
            await response_target.response.send_message(message, ephemeral=True)
        else:
            await response_target.send(message)
        return

    if user not in registered_players:
        registered_players.append(user)
        message = f'{user.mention} зарегистрирован на матч. Игроков зарегистрировано {len(registered_players)} из {players_per_team * 2}'
        if isinstance(response_target, discord.Interaction):
            await response_target.response.send_message(message, ephemeral=False)
        else:
            await response_target.send(message)

        # Проверяем, достигнуто ли максимальное количество игроков после регистрации
        if len(registered_players) == 2 * players_per_team:
            # Вызываем функцию разделения на команды
            await split_teams(response_target, reshuffle=False)
        
        await update_bot_status()
    else:
        message = f'{user.mention}, вы уже зарегистрированы.'
        if isinstance(response_target, discord.Interaction):
            await response_target.response.send_message(message, ephemeral=True)
        else:
            await response_target.send(message)



async def unregister_player(ctx, player):
    global registered_players
    if player in registered_players:
        registered_players.remove(player)
        await ctx.respond(f'{player.mention}, ваша регистрация отменена. Игроков зарегистрировано {len(registered_players)} из {players_per_team*2}', ephemeral=True)
    else:
        await ctx.respond(f'{player.mention}, вы не были зарегистрированы.', ephemeral=True)

async def display_teams(context_or_interaction, team1, team2):
    embed_team1 = discord.Embed(title="**Команда 1**", description="\n".join([f'- {player.mention}' for player in team1]), color=0x0000FF)
    embed_team2 = discord.Embed(title="**Команда 2**", description="\n".join([f'- {player.mention}' for player in team2]), color=0xFF0000)
    
    if isinstance(context_or_interaction, discord.Interaction):
        # Если context_or_interaction является Interaction, используем followup.send, так как предполагается, что interaction.response уже использовался
        await context_or_interaction.followup.send(embeds=[embed_team1, embed_team2])
    else:
        # Используем ctx.send для отправки сообщений, если context_or_interaction является контекстом команды
        await context_or_interaction.send(embeds=[embed_team1, embed_team2])

import asyncio

async def update_bot_status():
    global registered_players, players_per_team
    if len(registered_players) == 2 * players_per_team:
        # Все игроки набраны, показываем статус "Матч"
        activity = discord.Activity(type=discord.ActivityType.watching, name="Матч")
        await bot.change_presence(status=discord.Status.online, activity=activity)
        # Ждём 2 минуты, прежде чем сбросить статус
        await asyncio.sleep(120)  # Задержка в 2 минуты (120 секунд)
        # Сбрасываем статус
        await bot.change_presence(status=discord.Status.online, activity=None)
    elif registered_players:
        # Есть зарегистрированные игроки, показываем их количество
        activity = discord.Activity(type=discord.ActivityType.watching, name=f"{len(registered_players)}/{players_per_team*2} игроков")
        await bot.change_presence(status=discord.Status.online, activity=activity)
    else:
        # Регистрация открыта, но игроков нет
        activity = discord.Activity(type=discord.ActivityType.watching, name="Регистрация")
        await bot.change_presence(status=discord.Status.online, activity=activity)


bot.run(TOKEN)
