# bot.py
import discord
import os # Для работы с файлами и директориями (для загрузки когов)
import asyncio
from greetings import get_greeting
import config
from game_state import GameState
from reputation import ReputationSystem # Импортируем систему репутации

# Определение интентов (Guilds - для информации о серверах, Messages - если нужны команды через сообщения, VoiceStates - для работы с голосовыми каналами)
intents = discord.Intents(guilds=True, messages=True, voice_states=True)
bot = discord.Bot(intents=intents)

# Инициализация состояния игры и привязка его к боту для доступа из когов
# game_state будет инициализирован в on_ready, чтобы бот был полностью готов
# bot.game_state = GameState(bot, config.GAME_CHANNEL_ID) 

@bot.event
async def on_ready():
    """
    Событие, вызываемое при успешном подключении и готовности бота.
    Инициализирует состояние игры, загружает коги и выводит информацию о подключении.
    """
    print(f'{bot.user} подключился к Discord!')

    # Перебор всех гильдий, к которым подключен бот
    for guild in bot.guilds:
        print(f'Подключен к серверу: {guild.name} (id: {guild.id})')

    # Инициализация GameState здесь, когда bot уже определен и готов
    # Это гарантирует, что GameState получает валидный объект bot
    bot.game_state = GameState(bot, config.GAME_CHANNEL_ID)
    print("Экземпляр GameState создан и привязан к боту.")

    # Инициализация ReputationSystem
    bot.reputation_system = ReputationSystem()
    print("Экземпляр ReputationSystem создан и привязан к боту.")

    # Загрузка когов
    # Путь к папке с когами относительно текущего файла bot.py
    cogs_path = os.path.join(os.path.dirname(__file__), 'cogs')
    if not os.path.exists(cogs_path):
        os.makedirs(cogs_path)
        print(f"Создана директория для когов: {cogs_path}")

    loaded_cogs = 0
    for filename in os.listdir(cogs_path):
        if filename.endswith('.py') and not filename.startswith('_'): # Загружаем все .py файлы, кроме __init__.py и т.п.
            cog_name = f'cogs.{filename[:-3]}'
            try:
                bot.load_extension(cog_name)
                print(f'Ког {cog_name} успешно загружен.')
                loaded_cogs += 1
            except Exception as e:
                print(f'Ошибка при загрузке кога {cog_name}: {e}')
    
    if loaded_cogs == 0:
        print("Внимание: Ни один ког не был загружен. Убедитесь, что коги находятся в папке /cogs и не содержат ошибок.")


    # Отправка приветственного сообщения в игровой канал
    # Этот канал используется GameState, поэтому он должен быть доступен
    channel = bot.get_channel(config.GAME_CHANNEL_ID)
    if channel:
        try:
            await channel.send(get_greeting())
            print(f"Приветственное сообщение отправлено в канал {channel.name}.")
        except discord.Forbidden:
            print(f"Ошибка: У бота нет прав на отправку сообщений в канал {channel.name} (ID: {config.GAME_CHANNEL_ID}).")
        except Exception as e:
            print(f"Не удалось отправить приветственное сообщение: {e}")
    else:
        print(f"Ошибка: Игровой канал с ID {config.GAME_CHANNEL_ID} не найден.")


@bot.event
async def on_slash_command_error(ctx: discord.ApplicationContext, error: discord.DiscordException):
    """
    Глобальный обработчик ошибок для слэш-команд.
    Отправляет пользователю сообщение об ошибке и логирует ошибку в консоль.
    """
    if isinstance(error, discord.errors.ApplicationCommandInvokeError) and isinstance(error.original, discord.errors.InteractionResponded):
        # Эта ошибка возникает, если на interaction уже был дан ответ (например, defer), а затем снова пытаются ответить.
        # Обычно это можно проигнорировать или просто залогировать, так как followup.send() должен использоваться после defer().
        print(f"Предупреждение в команде '{ctx.command.name}': InteractionResponded. Возможно, был вызван ctx.respond() после defer() или предыдущего ответа.")
        # await ctx.followup.send('Произошла небольшая заминка, но команда могла выполниться. Если нет, попробуйте снова.', ephemeral=True)
        return # Не отправляем пользователю сообщение в этом случае, если это не критично

    # Для других ошибок ApplicationCommandInvokeError, выводим исходную ошибку
    if isinstance(error, discord.errors.ApplicationCommandInvokeError):
        original_error = error.original
        print(f'Ошибка при выполнении команды /{ctx.command.name}: {original_error.__class__.__name__}: {original_error}')
        await ctx.respond(f'При выполнении команды /{ctx.command.name} произошла внутренняя ошибка: {original_error.__class__.__name__}. Пожалуйста, сообщите администратору.', ephemeral=True)
    elif isinstance(error, discord.CheckFailure):
        print(f"Ошибка проверки прав для команды /{ctx.command.name} пользователем {ctx.author}: {error}")
        await ctx.respond('У вас нет прав для выполнения этой команды.', ephemeral=True)
    elif isinstance(error, discord.errors.ApplicationCommandNotFound):
        print(f"Неизвестная команда была вызвана: {error}")
        # Discord обычно сам обрабатывает это, но можно добавить свой обработчик
        # await ctx.respond('Такой команды не существует.', ephemeral=True)
    else:
        print(f'Необработанная ошибка в команде /{ctx.command.name}: {error.__class__.__name__}: {error}')
        await ctx.respond('При обработке вашей команды произошла неизвестная ошибка. Пожалуйста, попробуйте позже.', ephemeral=True)


@bot.event
async def on_application_command_completion(ctx: discord.ApplicationContext):
    """
    Событие, вызываемое после успешного выполнения слэш-команды.
    """
    print(f"Команда /{ctx.command.name} успешно выполнена пользователем {ctx.author.name} (ID: {ctx.author.id}) на сервере '{ctx.guild.name if ctx.guild else 'DM'}' в канале '{ctx.channel.name if ctx.channel else 'DM'}'.")


# Команды управления когами (для администратора бота)
# Эти команды лучше всего определять в основном файле или в специальном коге для управления ботом.
# Для простоты, пока оставим их здесь.
@bot.slash_command(name="load_cog", description="[АДМИН] Загрузить ког.", guild_ids=config.ADMIN_GUILD_IDS or [])
@discord.default_permissions(administrator=True) # Ограничение прав на уровне Discord
async def load_cog(ctx, cog_name: discord.Option(str, description="Имя кога для загрузки (например, admin_cog)")):
    """Загружает указанный ког."""
    if str(ctx.author.id) not in config.BOT_ADMIN_USER_IDS:
        await ctx.respond("У вас нет прав на выполнение этой команды.", ephemeral=True)
        return
    try:
        bot.load_extension(f"cogs.{cog_name}")
        await ctx.respond(f"Ког `cogs.{cog_name}` успешно загружен.", ephemeral=True)
        print(f"Ког cogs.{cog_name} загружен по команде от {ctx.author.name}")
    except Exception as e:
        await ctx.respond(f"Ошибка при загрузке кога `cogs.{cog_name}`: `{e}`", ephemeral=True)
        print(f"Ошибка загрузки кога cogs.{cog_name} по команде от {ctx.author.name}: {e}")

@bot.slash_command(name="unload_cog", description="[АДМИН] Выгрузить ког.", guild_ids=config.ADMIN_GUILD_IDS or [])
@discord.default_permissions(administrator=True)
async def unload_cog(ctx, cog_name: discord.Option(str, description="Имя кога для выгрузки (например, admin_cog)")):
    """Выгружает указанный ког."""
    if str(ctx.author.id) not in config.BOT_ADMIN_USER_IDS:
        await ctx.respond("У вас нет прав на выполнение этой команды.", ephemeral=True)
        return
    try:
        bot.unload_extension(f"cogs.{cog_name}")
        await ctx.respond(f"Ког `cogs.{cog_name}` успешно выгружен.", ephemeral=True)
        print(f"Ког cogs.{cog_name} выгружен по команде от {ctx.author.name}")
    except Exception as e:
        await ctx.respond(f"Ошибка при выгрузке кога `cogs.{cog_name}`: `{e}`", ephemeral=True)
        print(f"Ошибка выгрузки кога cogs.{cog_name} по команде от {ctx.author.name}: {e}")

@bot.slash_command(name="reload_cog", description="[АДМИН] Перезагрузить ког.", guild_ids=config.ADMIN_GUILD_IDS or [])
@discord.default_permissions(administrator=True)
async def reload_cog(ctx, cog_name: discord.Option(str, description="Имя кога для перезагрузки (например, admin_cog)")):
    """Перезагружает указанный ког."""
    if str(ctx.author.id) not in config.BOT_ADMIN_USER_IDS:
        await ctx.respond("У вас нет прав на выполнение этой команды.", ephemeral=True)
        return
    try:
        bot.reload_extension(f"cogs.{cog_name}")
        await ctx.respond(f"Ког `cogs.{cog_name}` успешно перезагружен.", ephemeral=True)
        print(f"Ког cogs.{cog_name} перезагружен по команде от {ctx.author.name}")
    except Exception as e:
        await ctx.respond(f"Ошибка при перезагрузке кога `cogs.{cog_name}`: `{e}`", ephemeral=True)
        print(f"Ошибка перезагрузки кога cogs.{cog_name} по команде от {ctx.author.name}: {e}")

if __name__ == "__main__":
    if not config.TOKEN:
        print("Ошибка: Токен бота не найден. Пожалуйста, установите TOKEN в config.py")
    else:
        bot.run(config.TOKEN)
