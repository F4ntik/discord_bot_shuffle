# cogs/user_cog.py
import discord
from discord.ext import commands
from discord.commands import Option # Используем Option из discord.commands для slash команд
from discord.ui import Button, View
from game_state import GameState # Импортируем GameState
import config # Для доступа к конфигурационным переменным, если потребуется

# --- Кнопка регистрации ---
class RegisterButton(Button):
    """
    Кнопка для регистрации или отмены регистрации на матч.
    """
    def __init__(self, label: str, game_state: GameState, register: bool = True):
        """
        Инициализация кнопки.
        :param label: Текст на кнопке.
        :param game_state: Экземпляр GameState для взаимодействия с логикой игры.
        :param register: True, если кнопка для регистрации, False - для отмены.
        """
        super().__init__(label=label, style=discord.ButtonStyle.green if register else discord.ButtonStyle.red)
        self.game_state = game_state
        self.should_register = register # Атрибут для определения действия кнопки

    async def callback(self, interaction: discord.Interaction):
        """
        Обработчик нажатия кнопки. Регистрирует или отменяет регистрацию пользователя.
        """
        user = interaction.user

        # Ответ пользователю всегда должен быть эфемерным для команд регистрации
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        response_message = ""
        if self.should_register:
            # Логика регистрации игрока
            # register_player теперь ожидает interaction как второй аргумент
            success_flag, response_message = await self.game_state.register_player(user, interaction)
        else:
            # Логика отмены регистрации игрока
            # unregister_player теперь ожидает interaction
            response_message = await self.game_state.unregister_player(user, interaction)

        # Отправляем итоговое сообщение как followup, так как defer() уже был вызван
        # или если register_player/unregister_player уже ответили через interaction.response
        if interaction.response.is_done(): # Если defer был вызван или первоначальный ответ был дан
             await interaction.followup.send(response_message, ephemeral=True)
        # else: # Эта ветка не должна выполняться, если defer() всегда вызывается
             # await interaction.response.send_message(response_message, ephemeral=True)


class UserCog(commands.Cog):
    """
    Ког, содержащий команды для взаимодействия пользователей с процессом регистрации на матч.
    """
    def __init__(self, bot: discord.Bot):
        """
        Инициализация кога.
        :param bot: Экземпляр бота.
        """
        self.bot = bot
        # Доступ к game_state через self.bot.game_state, который инициализируется в on_ready

    @commands.slash_command(name='start_registration', description='Начать регистрацию игроков на матч и создать кнопки.')
    @discord.default_permissions(manage_events=True) # Только пользователи с правом управлять событиями могут начать регистрацию
    async def start_registration(self, ctx: discord.ApplicationContext,
                                 players_per_team: Option(int, "Введите количество игроков в команде (2-5)", required=False, default=5, min_value=2, max_value=config.MAX_PLAYERS_PER_TEAM)):
        """
        Команда для начала процесса регистрации на матч.
        Создает сообщение с кнопками "Регистрация" и "Отменить регистрацию".
        Доступна только пользователям с правом 'manage_events'.
        """
        game_state: GameState = self.bot.game_state # Получаем game_state из бота

        if not ctx.guild:
            await ctx.respond("Эта команда может быть использована только на сервере.", ephemeral=True)
            return

        # Первоначальный defer, чтобы избежать тайм-аута interaction
        # Ответ будет виден только пользователю, который вызвал команду
        await ctx.defer(ephemeral=True)

        # Проверка, можно ли начать новую регистрацию
        if game_state.voting_active:
            await ctx.followup.send("Нельзя начать новую регистрацию: текущее голосование активно.", ephemeral=True)
            return
        if len(await game_state.get_registered_players()) > 0 and not await game_state.check_ready_to_start():
             # Если есть зарегистрированные, но игра не полная, спрашиваем подтверждение
            # Это более сложная логика, пока просто запретим, если есть игроки
            await ctx.followup.send("Нельзя начать новую регистрацию: уже есть зарегистрированные игроки. Сначала остановите текущую регистрацию (/stop_registration).", ephemeral=True)
            return

        # Установка количества игроков в команде
        success, message = await game_state.set_players_per_team(players_per_team, ctx.interaction) # Передаем interaction
        if not success:
            await ctx.followup.send(f"Не удалось установить количество игроков: {message}", ephemeral=True)
            return

        # Очистка предыдущего состояния (если вдруг что-то осталось, хотя проверки выше должны это покрывать)
        await game_state.clear_registered_players()
        await game_state.update_bot_status() # Обновляем статус бота

        # Создание кнопок
        # Передаем game_state в кнопки
        register_button = RegisterButton(label="✅ Регистрация", game_state=game_state, register=True)
        unregister_button = RegisterButton(label="❌ Отменить регистрацию", game_state=game_state, register=False)

        view = View(timeout=None) # View без таймаута, кнопки будут активны всегда
        view.add_item(register_button)
        view.add_item(unregister_button)

        # Отправка сообщения с кнопками в публичный канал игры
        game_channel = self.bot.get_channel(config.GAME_CHANNEL_ID)
        if game_channel:
            try:
                # Удаляем старое сообщение с кнопками, если оно было сохранено в game_state
                if game_state.voting_message: # Используем voting_message для хранения сообщения с кнопками регистрации
                    try:
                        await game_state.voting_message.delete()
                        print("Старое сообщение с кнопками регистрации удалено.")
                    except discord.NotFound:
                        print("Старое сообщение с кнопками регистрации не найдено (возможно, уже удалено).")
                    except discord.HTTPException as e_del:
                        print(f"Ошибка при удалении старого сообщения с кнопками регистрации: {e_del}")

                # Отправляем новое сообщение и сохраняем его
                message_with_buttons = await game_channel.send(
                    f"📢 **Началась регистрация на матч!**\n"
                    f"Команды по {players_per_team} игроков. Всего нужно: {players_per_team * 2}.\n"
                    f"Нажмите кнопку для участия или отмены.",
                    view=view
                )
                game_state.voting_message = message_with_buttons # Сохраняем сообщение для возможного удаления
                print(f"Сообщение с кнопками регистрации отправлено в канал {game_channel.name}.")
                await ctx.followup.send(f"Регистрация успешно начата в канале {game_channel.mention}. Количество игроков в команде: {players_per_team}.", ephemeral=True)
            except discord.Forbidden:
                await ctx.followup.send(f"Ошибка: У бота нет прав на отправку сообщений или создание View в канале {game_channel.mention}.", ephemeral=True)
            except Exception as e:
                await ctx.followup.send(f"Произошла ошибка при отправке сообщения с кнопками: {e}", ephemeral=True)
        else:
            await ctx.followup.send(f"Ошибка: Игровой канал (ID: {config.GAME_CHANNEL_ID}) не найден. Не удалось отправить кнопки регистрации.", ephemeral=True)


    @commands.slash_command(name='register', description='Зарегистрироваться на текущий матч (используйте кнопки).')
    async def register(self, ctx: discord.ApplicationContext):
        """
        Команда для регистрации на матч. Пользователю рекомендуется использовать кнопки.
        Эта команда оставлена для обратной совместимости или прямого вызова,
        но основной способ регистрации - через кнопки.
        """
        game_state: GameState = self.bot.game_state

        # defer() должен быть первым в ответе на interaction
        await ctx.defer(ephemeral=True)

        # Передаем ctx.interaction в register_player
        success_flag, response = await game_state.register_player(ctx.author, ctx.interaction)
        await ctx.followup.send(response, ephemeral=True)


    @commands.slash_command(name='unregister', description='Отменить свою регистрацию на матч (используйте кнопки).')
    async def unregister(self, ctx: discord.ApplicationContext):
        """
        Команда для отмены регистрации на матч. Пользователю рекомендуется использовать кнопки.
        """
        game_state: GameState = self.bot.game_state
        await ctx.defer(ephemeral=True)
        # Передаем ctx.interaction в unregister_player
        response = await game_state.unregister_player(ctx.author, ctx.interaction)
        await ctx.followup.send(response, ephemeral=True)


    @commands.slash_command(name='show_teams', description='Показать текущие составы команд (без голосования).')
    async def show_teams(self, ctx: discord.ApplicationContext):
        """
        Отображает текущие составы команд без возможности голосования.
        Сообщение видно всем в канале, где была вызвана команда.
        """
        game_state: GameState = self.bot.game_state
        if not game_state.registered_players:
            await ctx.respond("Пока нет зарегистрированных игроков для отображения команд.", ephemeral=True)
            return

        # defer с ephemeral=False, если хотим, чтобы сообщение о командах было видно всем,
        # но display_teams_general сам управляет видимостью своих сообщений.
        # Здесь defer() нужен, чтобы interaction не "умер".
        # display_teams_general будет использовать followup.send() для основного сообщения.
        if not ctx.interaction.response.is_done():
             await ctx.interaction.response.defer(ephemeral=False) # ephemeral=False, чтобы ответ был виден

        await game_state.display_teams_general(interaction=ctx.interaction, shuffle=False, display_voting_buttons=False)
        # Если display_teams_general уже отправил видимый всем ответ, то этот followup может быть излишним или вызвать ошибку.
        # display_teams_general должен сам полностью обработать ответ на interaction.
        # В текущей реализации display_teams_general использует followup, предполагая, что defer был.
        # Если ctx.interaction.response.defer(ephemeral=False) был, то display_teams_general должен использовать ctx.interaction.followup.send
        # Если мы хотим, чтобы "Команды показаны" было эфемерным, а сами команды - нет:
        # await ctx.respond("Команды сейчас будут показаны.", ephemeral=True)
        # await game_state.display_teams_general(interaction=ctx.interaction, shuffle=False, display_voting_buttons=False) - это отправит новое сообщение.


    @commands.slash_command(name='info', description='Вывести информацию о текущей регистрации и игроках.')
    async def info(self, ctx: discord.ApplicationContext):
        """
        Выводит подробную информацию о текущей регистрации и игроках.
        Сообщение видно только вызвавшему пользователю.
        """
        game_state: GameState = self.bot.game_state
        await ctx.defer(ephemeral=True) # Ответ будет виден только пользователю

        players_per_team = await game_state.get_players_per_team()
        registered_players = await game_state.get_registered_players()

        embed_info = discord.Embed(
            title="ℹ️ Информация о текущей игре",
            color=discord.Color.orange() # Оранжевый цвет для информации
        )
        embed_info.add_field(
            name="⚙️ Статус регистрации",
            value="Активна" if not await game_state.check_ready_to_start() and not game_state.voting_active else "Завершена (команды полные)" if await game_state.check_ready_to_start() else "Голосование",
            inline=False
        )
        embed_info.add_field(
            name="👥 Игроков в команде",
            value=f"{players_per_team} (всего нужно: {players_per_team * 2})",
            inline=True
        )
        embed_info.add_field(
            name="📝 Зарегистрировано",
            value=f"**{len(registered_players)} из {players_per_team * 2}**",
            inline=True
        )

        if game_state.voting_active:
            embed_info.add_field(
                name="🗳️ Статус голосования",
                value=f"Активно. Голоса: 👍 {game_state.votes['agree']} | 🔄 {game_state.votes['reshuffle']}",
                inline=False
            )

        if registered_players:
            registered_players_mentions = "\n".join([f'• {player.mention} (`{player.name}`)' for player in registered_players])
            embed_info.add_field(
                name="📜 Список зарегистрированных игроков:",
                value=registered_players_mentions,
                inline=False # Для лучшей читаемости списка
            )
        else:
            embed_info.add_field(
                name="📜 Список зарегистрированных игроков:",
                value="На данный момент нет зарегистрированных игроков.",
                inline=False
            )

        embed_info.set_footer(text=f"Информация актуальна на момент запроса.")
        await ctx.followup.send(embed=embed_info, ephemeral=True)

    # --- Команды системы репутации ---
    @commands.slash_command(name='rate_player', description='Оценить другого игрока (повысить/понизить репутацию).')
    async def rate_player(self, ctx: discord.ApplicationContext,
                          user: Option(discord.Member, "Игрок, которого вы хотите оценить", required=True),
                          rating: Option(str, "Тип оценки: 'positive' или 'negative'", choices=["positive", "negative"], required=True),
                          reason: Option(str, "Причина оценки (необязательно)", required=False, max_length=100)):
        """
        Позволяет текущему пользователю оценить другого игрока, изменив его репутацию.
        Нельзя оценивать самого себя.
        """
        await ctx.defer(ephemeral=True) # Ответ будет виден только тому, кто ставит оценку

        rater_user = ctx.author
        rated_user = user # 'user' это уже объект discord.Member из параметра команды
        reputation_system = self.bot.reputation_system # Доступ к системе репутации

        if not reputation_system:
            await ctx.followup.send("Ошибка: Система репутации не инициализирована. Обратитесь к администратору.", ephemeral=True)
            return

        if rater_user.id == rated_user.id:
            await ctx.followup.send("Вы не можете оценивать самого себя.", ephemeral=True)
            return

        rating_change = 1 if rating == "positive" else -1

        success, message = await reputation_system.add_rating(rater_user, rated_user, rating_change, reason)

        if success:
            # Дополнительно можно отправить уведомление оцененному игроку (если это желательно)
            # try:
            #     dm_message = f"Игрок {rater_user.mention} изменил вашу репутацию на {rating_change}."
            #     if reason:
            #         dm_message += f" Причина: {reason}"
            #     await rated_user.send(dm_message)
            # except discord.Forbidden:
            #     print(f"Не удалось отправить ЛС игроку {rated_user.name} о изменении репутации (ЛС закрыты).")
            # except Exception as e_dm:
            #     print(f"Ошибка при отправке ЛС о репутации игроку {rated_user.name}: {e_dm}")
            pass # Пока не отправляем ЛС

        await ctx.followup.send(message, ephemeral=True)


    @commands.slash_command(name='my_reputation', description='Показать ваш текущий уровень репутации.')
    async def my_reputation(self, ctx: discord.ApplicationContext):
        """
        Отображает текущий уровень репутации пользователя, вызвавшего команду.
        """
        await ctx.defer(ephemeral=True)
        reputation_system = self.bot.reputation_system

        if not reputation_system:
            await ctx.followup.send("Ошибка: Система репутации не инициализирована. Обратитесь к администратору.", ephemeral=True)
            return

        user_id = ctx.author.id
        score = reputation_system.get_reputation(user_id)

        embed = discord.Embed(
            title=f"🏅 Ваша репутация, {ctx.author.name}",
            description=f"Ваш текущий счет репутации: **{score}**",
            color=discord.Color.gold() if score >= 0 else discord.Color.dark_red()
        )
        if score > 10:
            embed.add_field(name="Статус", value="🌟 Образец для подражания!", inline=False)
        elif score < -5:
            embed.add_field(name="Статус", value="💀 Изгой общества... Пора задуматься!", inline=False)

        await ctx.followup.send(embed=embed, ephemeral=True)

    @commands.slash_command(name='top_reputation', description='Показать топ игроков по уровню репутации.')
    async def top_reputation(self, ctx: discord.ApplicationContext,
                             count: Option(int, "Количество игроков для отображения в топе (1-15)", default=5, min_value=1, max_value=15)):
        """
        Отображает список лучших игроков сервера по уровню репутации.
        Список виден всем в канале.
        """
        # Defer ephemeral=False если хотим, чтобы результат был виден всем, но это может быть изменено на True,
        # если информация считается чувствительной или для уменьшения спама.
        # Для топа игроков, обычно это публичная информация.
        await ctx.defer(ephemeral=False)
        reputation_system = self.bot.reputation_system

        if not reputation_system:
            await ctx.followup.send("Ошибка: Система репутации не инициализирована. Обратитесь к администратору.", ephemeral=True)
            return

        top_players_data = reputation_system.get_top_players(n=count)

        embed = discord.Embed(
            title=f"🏆 Топ-{count} игроков по репутации",
            color=discord.Color.blue()
        )

        if not top_players_data:
            embed.description = "На сервере пока нет игроков с репутацией, или система пуста."
        else:
            description_lines = []
            for i, (user_id, score) in enumerate(top_players_data):
                try:
                    # Пытаемся получить пользователя. Если бот на многих серверах, это может быть медленно или не найти,
                    # если пользователь покинул все общие сервера.
                    # Для одного сервера ctx.guild.get_member(user_id) будет лучше.
                    user = await self.bot.fetch_user(user_id) # Асинхронный вызов
                    user_display_name = user.global_name if user.global_name else user.name # Предпочитаем global_name
                    user_mention = user.mention
                    line = f"{i+1}. {user_mention} (`{user_display_name}`) - **{score}** очков"
                except discord.NotFound:
                    line = f"{i+1}. `ID: {user_id}` (пользователь не найден) - **{score}** очков"
                except Exception as e_fetch:
                    print(f"Ошибка при получении пользователя {user_id} для топа репутации: {e_fetch}")
                    line = f"{i+1}. `ID: {user_id}` (ошибка получения) - **{score}** очков"
                description_lines.append(line)
            embed.description = "\n".join(description_lines)

        embed.set_footer(text=f"Топ составлен на основе данных репутации. Обновляется в реальном времени.")
        await ctx.followup.send(embed=embed)


def setup(bot: discord.Bot):
    """
    Функция для загрузки кога в бота.
    """
    bot.add_cog(UserCog(bot))
    print("UserCog успешно добавлен и готов к работе.")
