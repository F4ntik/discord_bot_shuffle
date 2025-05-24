# cogs/admin_cog.py
import discord
from discord.ext import commands
from discord.commands import Option # Используем Option из discord.commands для slash команд
from datetime import datetime, timedelta
from game_state import GameState # Импортируем GameState
import config # Для доступа к ADMIN_GUILD_IDS и BOT_ADMIN_USER_IDS

class AdminCog(commands.Cog):
    """
    Ког, содержащий административные команды для управления ботом и состоянием игры.
    Доступ к этим командам должен быть ограничен администраторами.
    """
    def __init__(self, bot: discord.Bot):
        """
        Инициализация кога.
        :param bot: Экземпляр бота.
        """
        self.bot = bot
        # Доступ к game_state через self.bot.game_state

    # --- Вспомогательная проверка на администратора ---
    async def is_bot_admin(self, ctx: discord.ApplicationContext) -> bool:
        """
        Проверяет, является ли автор interaction администратором бота
        (согласно списку BOT_ADMIN_USER_IDS в config.py).
        """
        is_admin = str(ctx.author.id) in config.BOT_ADMIN_USER_IDS
        if not is_admin:
            # Проверяем также права администратора на сервере как дополнительный уровень, если BOT_ADMIN_USER_IDS не настроен
            # или если хотим дать доступ админам сервера на определенных серверах.
            # Это более сложная логика, пока оставим только проверку по BOT_ADMIN_USER_IDS для глобальных админ-команд.
            # if ctx.guild and ctx.author.guild_permissions.administrator:
            #     is_admin = True
            # else:
            await ctx.respond("У вас нет прав на выполнение этой административной команды.", ephemeral=True)
        return is_admin

    # --- Команды администрирования игры ---
    @commands.slash_command(
        name='admin_register',
        description='[АДМИН] Зарегистрировать игрока на матч.',
        guild_ids=config.ADMIN_GUILD_IDS or [] # Ограничиваем доступность команды определенными серверами
    )
    @discord.default_permissions(manage_events=True) # Права Discord для управления событиями
    async def admin_register(self, ctx: discord.ApplicationContext,
                             member: Option(discord.Member, "Выберите участника для регистрации", required=True)):
        """
        Административная команда для принудительной регистрации указанного пользователя на матч.
        """
        # Проверка на администратора бота (из config.py) не требуется, если default_permissions достаточно
        # Однако, для дополнительной защиты можно добавить вызов self.is_bot_admin(ctx)
        game_state: GameState = self.bot.game_state
        
        # defer() должен быть первым, если далее идут длительные операции или несколько ответов
        # В данном случае register_player сам обрабатывает interaction.response/followup
        # await ctx.defer(ephemeral=True) # register_player сделает это или ответит напрямую

        # Передаем ctx.interaction в register_player
        success_flag, response = await game_state.register_player(member, ctx.interaction)
        
        # register_player уже должен был ответить на interaction.
        # Если нет, то здесь нужен followup.send.
        # Убедимся, что register_player отвечает или мы отвечаем здесь.
        # В текущей реализации game_state.register_player отвечает на interaction.
        # Поэтому здесь дополнительный ответ не нужен, если только не хотим подтвердить действие администратору.
        # await ctx.followup.send(f"Результат admin_register для {member.mention}: {response}", ephemeral=True)


    @commands.slash_command(
        name='admin_unregister',
        description='[АДМИН] Отменить регистрацию игрока с матча.',
        guild_ids=config.ADMIN_GUILD_IDS or []
    )
    @discord.default_permissions(manage_events=True)
    async def admin_unregister(self, ctx: discord.ApplicationContext,
                               member: Option(discord.Member, "Выберите участника для отмены регистрации", required=True)):
        """
        Административная команда для принудительной отмены регистрации указанного пользователя.
        """
        game_state: GameState = self.bot.game_state
        # await ctx.defer(ephemeral=True) # unregister_player сделает это или ответит напрямую
        
        # Передаем ctx.interaction в unregister_player
        response = await game_state.unregister_player(member, ctx.interaction)
        # Аналогично admin_register, game_state.unregister_player должен обработать ответ.
        # await ctx.followup.send(f"Результат admin_unregister для {member.mention}: {response}", ephemeral=True)

    @commands.slash_command(
        name='set_players',
        description='[АДМИН] Изменить количество игроков в команде.',
        guild_ids=config.ADMIN_GUILD_IDS or []
    )
    @discord.default_permissions(manage_events=True)
    async def set_players_per_team(self, ctx: discord.ApplicationContext,
                                   number: Option(int, "Новое количество игроков в команде (2-5)", required=True, min_value=2, max_value=config.MAX_PLAYERS_PER_TEAM)):
        """
        Административная команда для установки количества игроков в каждой команде.
        """
        game_state: GameState = self.bot.game_state
        # await ctx.defer(ephemeral=True) # set_players_per_team из game_state обработает ответ
        
        # Передаем ctx.interaction
        success, response = await game_state.set_players_per_team(number, ctx.interaction)
        # game_state.set_players_per_team должен обработать ответ.
        # await ctx.followup.send(response, ephemeral=True)

    @commands.slash_command(
        name='stop_registration',
        description='[АДМИН] Остановить регистрацию и очистить список игроков.',
        guild_ids=config.ADMIN_GUILD_IDS or []
    )
    @discord.default_permissions(manage_events=True)
    async def stop_registration(self, ctx: discord.ApplicationContext):
        """
        Административная команда для полной остановки текущего процесса регистрации
        и очистки списка всех зарегистрированных игроков.
        """
        game_state: GameState = self.bot.game_state
        await ctx.defer(ephemeral=True) # Ответ будет виден только администратору
        
        response = await game_state.clear_registered_players()
        # game_state.clear_registered_players НЕ отвечает на interaction, он только возвращает строку
        # и отправляет сообщение в игровой канал. Поэтому здесь нужен followup.
        await ctx.followup.send(f"Команда выполнена: {response}", ephemeral=True)
        print(f"Регистрация остановлена и список очищен администратором {ctx.author.name}.")

    @commands.slash_command(
        name='force_voice_moving',
        description="[АДМИН] Принудительно распределить текущих игроков по голосовым каналам.",
        guild_ids=config.ADMIN_GUILD_IDS or []
    )
    @discord.default_permissions(manage_events=True, move_members=True) # Требуются права на перемещение участников
    async def force_voice_moving(self, ctx: discord.ApplicationContext):
        """
        Административная команда для принудительного запуска процесса распределения
        зарегистрированных игроков по голосовым каналам команд.
        Это полезно, если автоматическое распределение не сработало или нужно повторить.
        """
        game_state: GameState = self.bot.game_state
        await ctx.defer(ephemeral=True)

        if not game_state.registered_players:
            await ctx.followup.send("Нет зарегистрированных игроков для распределения.", ephemeral=True)
            return
        
        if len(game_state.registered_players) < game_state.players_per_team * 2 :
             await ctx.followup.send(f"Недостаточно игроков для формирования полных команд ({len(game_state.registered_players)} из {game_state.players_per_team*2}). Перемещение может быть некорректным. Продолжить?",
                                     view=ConfirmActionView(game_state, "finalize_teams_anyway", ctx.interaction), ephemeral=True)
             return


        # Предполагается, что команды уже как-то определены (например, после /show_teams или предыдущего голосования)
        # finalize_teams сама разделит на команды и переместит
        await game_state.finalize_teams() # finalize_teams теперь сама отправляет сообщения о результате
        await ctx.followup.send("Запущено принудительное распределение игроков по голосовым каналам.", ephemeral=True)
        print(f"Принудительное перемещение в голосовые каналы инициировано администратором {ctx.author.name}.")


    @commands.slash_command(
        name='clear_bot_messages',
        description='[АДМИН] Удалить сообщения бота из текущего канала за указанный период.',
        guild_ids=config.ADMIN_GUILD_IDS or []
    )
    @discord.default_permissions(manage_messages=True) # Требуются права на управление сообщениями
    async def clear_bot_messages(self, ctx: discord.ApplicationContext,
                                 days: Option(int, "Количество дней, за которые удалить сообщения (1-30)", min_value=1, max_value=30, default=14)):
        """
        Удаляет все сообщения, отправленные этим ботом, из канала, где была вызвана команда,
        за последние N дней.
        """
        # Проверка на глобального администратора бота для дополнительной безопасности
        if not await self.is_bot_admin(ctx):
             # Сообщение об отсутствии прав уже отправлено в is_bot_admin
             return
        
        await ctx.defer(ephemeral=True) # Ответ будет виден только администратору
        
        channel = ctx.channel # Канал, где была вызвана команда
        deleted_count = 0
        # Рассчитываем временную метку для ограничения поиска сообщений
        cutoff_datetime = datetime.utcnow() - timedelta(days=days) # Используем UTC для согласованности с Discord

        # Проверка типа канала (должен быть текстовым)
        if not isinstance(channel, discord.TextChannel):
            await ctx.followup.send("Эту команду можно использовать только в текстовых каналах.", ephemeral=True)
            return

        to_delete = []
        try:
            # Собираем сообщения бота. history() может быть медленной для большого количества сообщений.
            # Discord может ограничивать количество сообщений, которые можно получить за один раз.
            # limit=None может быть очень ресурсоемким. Лучше ограничить или обрабатывать порциями.
            async for message in channel.history(limit=2000, after=cutoff_datetime): # Ограничиваем поиск последними 2000 сообщениями
                if message.author == self.bot.user:
                    # Проверяем, что сообщение не старше cutoff_datetime (на случай если after не идеально точен)
                    if message.created_at >= cutoff_datetime:
                        to_delete.append(message)
            
            if not to_delete:
                await ctx.followup.send(f"Не найдено сообщений от бота для удаления за последние {days} дней.", ephemeral=True)
                return

            # Удаление сообщений пакетами (Discord API позволяет удалять до 100 сообщений за раз,
            # и они не должны быть старше 14 дней - это ограничение delete_messages)
            # Сообщения старше 14 дней нужно удалять по одному (message.delete()).
            
            # Разделяем сообщения на те, что можно удалить массово, и те, что нужно удалять по одному
            bulk_delete_limit_datetime = datetime.utcnow() - timedelta(days=14)
            
            messages_for_bulk_delete = []
            messages_for_single_delete = []

            for msg in to_delete:
                if msg.created_at > bulk_delete_limit_datetime:
                    messages_for_bulk_delete.append(msg)
                else:
                    messages_for_single_delete.append(msg)
            
            if messages_for_bulk_delete:
                # Удаляем пакетами по 100
                for i in range(0, len(messages_for_bulk_delete), 100):
                    chunk = messages_for_bulk_delete[i:i+100]
                    await channel.delete_messages(chunk)
                    deleted_count += len(chunk)
                    await asyncio.sleep(1) # Небольшая задержка между массовыми удалениями

            for msg in messages_for_single_delete:
                try:
                    await msg.delete()
                    deleted_count += 1
                    await asyncio.sleep(0.5) # Задержка, чтобы не перегружать API
                except discord.HTTPException as e_single:
                    print(f"Не удалось удалить старое сообщение (ID: {msg.id}): {e_single}")


            await ctx.followup.send(f'Удалено сообщений от бота ({self.bot.user.name}) в этом канале за последние {days} дней: {deleted_count}.', ephemeral=True)
            print(f"Удалено {deleted_count} сообщений бота в канале {channel.name} по команде от {ctx.author.name}.")

        except discord.Forbidden:
            await ctx.followup.send("Ошибка: У бота нет прав на чтение истории или удаление сообщений в этом канале.", ephemeral=True)
        except discord.HTTPException as e:
            await ctx.followup.send(f"Произошла ошибка HTTP при удалении сообщений: {e}", ephemeral=True)
        except Exception as e_main:
            await ctx.followup.send(f"Произошла непредвиденная ошибка: {e_main}", ephemeral=True)
            print(f"Непредвиденная ошибка в clear_bot_messages: {e_main}")


# Вспомогательный View для подтверждения действий (пример)
class ConfirmActionView(View):
    def __init__(self, game_state: GameState, action: str, original_interaction: discord.Interaction):
        super().__init__(timeout=30.0) # Таймаут для View
        self.game_state = game_state
        self.action = action
        self.original_interaction = original_interaction
        self.confirmed = None

    @discord.ui.button(label="✅ Подтвердить", style=discord.ButtonStyle.danger)
    async def confirm_button(self, button: Button, interaction: discord.Interaction):
        if interaction.user.id != self.original_interaction.user.id:
            await interaction.response.send_message("Только пользователь, вызвавший команду, может подтвердить это действие.", ephemeral=True)
            return

        self.confirmed = True
        # Отключаем кнопки после нажатия
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self) # Обновляем исходное сообщение с View
        self.stop() # Останавливаем View

    @discord.ui.button(label="❌ Отмена", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, button: Button, interaction: discord.Interaction):
        if interaction.user.id != self.original_interaction.user.id:
            await interaction.response.send_message("Только пользователь, вызвавший команду, может отменить это действие.", ephemeral=True)
            return
            
        self.confirmed = False
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    async def on_timeout(self):
        # Если время вышло, отключаем кнопки и можно уведомить пользователя
        for item in self.children:
            item.disabled = True
        # Сообщение, на которое был прикреплен View, уже существует. Мы можем его отредактировать.
        # original_interaction.edit_original_response(content="Время на подтверждение истекло.", view=self)
        # или followup, если edit_original_response не подходит.
        # await self.original_interaction.followup.send("Время на подтверждение действия истекло.", ephemeral=True)
        print("View подтверждения действия истек по таймауту.")


def setup(bot: discord.Bot):
    """
    Функция для загрузки кога в бота.
    """
    bot.add_cog(AdminCog(bot))
    print("AdminCog успешно добавлен и готов к работе.")
