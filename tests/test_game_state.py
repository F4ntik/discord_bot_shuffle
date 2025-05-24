# tests/test_game_state.py
import unittest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import asyncio
import discord # Для type hints и некоторых констант, если нужны

# Добавляем путь к корневой директории проекта
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game_state import GameState
# from reputation import ReputationSystem # Если понадобится для интеграционных тестов

# --- Мок-объекты для Discord ---
class MockUser(discord.User): # Наследуемся от discord.User для isinstance и type hints
    def __init__(self, id: int, name: str, mention_override: str = None, bot_flag: bool = False):
        # Инициализируем только необходимые атрибуты для discord.User
        # super().__init__(state=None, data={'id': str(id), 'username': name, 'discriminator': '0000', 'bot': bot_flag, 'avatar': None})
        # Поскольку super().__init__ для discord.User сложен, мокаем атрибуты напрямую.
        self.id = id
        self.name = name
        self.bot = bot_flag
        self._mention = mention_override if mention_override else f"<@{id}>"
        self.display_name = name
        self.guild = None # Будет установлено, если это MockMember
        self.voice = None # Для MockMember

    @property
    def mention(self) -> str:
        return self._mention

    def __eq__(self, other):
        if isinstance(other, (MockUser, discord.User, discord.Member)):
            return self.id == other.id
        return False

    def __hash__(self):
        return hash(self.id)

class MockMember(discord.Member, MockUser): # Наследуемся также от MockUser
    def __init__(self, id: int, name: str, guild_mock, mention_override: str = None, voice_state_mock = None):
        # super().__init__(data={'user': {'id': str(id), 'username': name, 'discriminator': '0000', 'bot': False, 'avatar': None}, 'roles': []}, guild=guild_mock, state=None)
        # Прямое присвоение атрибутов, так как super() для Member тоже сложный
        MockUser.__init__(self, id, name, mention_override) # Вызываем __init__ от MockUser
        self.guild = guild_mock
        self.roles = [guild_mock.default_role] # Базовая роль
        self.voice = voice_state_mock if voice_state_mock else MockVoiceState(None) # Мок состояния голоса

    async def move_to(self, channel, *, reason=None):
        """Мок-метод для перемещения пользователя."""
        if self.voice:
            self.voice.channel = channel
            print(f"MockMember {self.name} moved to {channel.name if channel else 'None'}")
        else:
            print(f"MockMember {self.name} has no voice state to move.")
        return None # Обычно ничего не возвращает или self

    async def send(self, content=None, *, tts=False, embed=None, embeds=None, file=None, files=None, view=None, suppress_embeds=False, delete_after=None, nonce=None, allowed_mentions=None, reference=None, mention_author=None):
        """Мок-метод для отправки ЛС."""
        print(f"MockMember {self.name} received DM: '{content}' Embed: {embed is not None or embeds is not None} View: {view is not None}")
        return MockMessage(content=content, author=self, channel=None) # Возвращаем мок-сообщение


class MockVoiceState:
    def __init__(self, channel):
        self.channel = channel # Может быть MockVoiceChannel или None

class MockTextChannel(discord.TextChannel):
    def __init__(self, id: int, name: str, guild_mock):
        # super().__init__(state=None, guild=guild_mock, data={'id': str(id), 'name': name, 'type': 0})
        self.id = id
        self.name = name
        self.guild = guild_mock
        self._sent_messages = [] # Для отслеживания отправленных сообщений

    async def send(self, content=None, *, tts=False, embed=None, embeds=None, view=None, **kwargs) -> 'MockMessage':
        print(f"MockChannel {self.name} received message: '{content}' Embed: {embed is not None or embeds is not None} View: {view is not None}")
        msg = MockMessage(content=content, author=self.guild.me if self.guild else None, channel=self, embed=embed, embeds=embeds, view=view)
        self._sent_messages.append(msg)
        return msg
        
    async def delete_messages(self, messages):
        count = len(messages)
        print(f"MockChannel {self.name} deleted {count} messages.")
        for msg in messages:
            if msg in self._sent_messages:
                self._sent_messages.remove(msg)
        return None

class MockVoiceChannel(discord.VoiceChannel):
     def __init__(self, id: int, name: str, guild_mock):
        # super().__init__(state=None, guild=guild_mock, data={'id': str(id), 'name': name, 'type': 2})
        self.id = id
        self.name = name
        self.guild = guild_mock
        self.members = [] # Список участников в канале

     def Guild(self):
        return self.guild

class MockMessage(discord.Message):
    def __init__(self, *, content, author, channel, embed=None, embeds=None, view=None, id_override=None):
        # super().__init__(state=None, channel=channel, data={'id': str(id_override or random.randint(1000000,9999999)), 'content': content, 'author': author.to_dict() if hasattr(author, 'to_dict') else {'id': author.id, 'username': author.name, 'discriminator': '0000'}, 'attachments': [], 'embeds': [], 'edited_timestamp': None, 'type': 0, 'pinned': False, 'mention_everyone': False, 'tts': False})
        self.id = id_override or random.randint(1000000,9999999)
        self.content = content
        self.author = author
        self.channel = channel
        self.embeds = embeds or ([embed] if embed else [])
        self.view = view
        self._deleted = False

    async def edit(self, **fields):
        if self._deleted:
            raise discord.NotFound(MagicMock(), "Message already deleted")
        self.content = fields.get('content', self.content)
        self.embeds = fields.get('embeds', self.embeds)
        if 'embed' in fields: # discord.py v2 позволяет embed или embeds
            self.embeds = [fields['embed']] if fields['embed'] else []
        self.view = fields.get('view', self.view)
        print(f"MockMessage {self.id} edited. New content: '{self.content}'")

    async def delete(self, *, delay=None):
        if delay:
            await asyncio.sleep(delay)
        self._deleted = True
        print(f"MockMessage {self.id} deleted.")


class MockInteractionResponse(discord.InteractionResponse):
    def __init__(self, interaction):
        # super().__init__(interaction) # discord.InteractionResponse не имеет простого конструктора
        self._interaction = interaction
        self._is_done = False

    async def defer(self, *, ephemeral: bool = False) -> None:
        if self._is_done:
            # raise discord.InteractionResponded(self._interaction) # В тестах можем просто логировать
            print(f"MockInteractionResponse: Defer called on already responded interaction for {self._interaction.id}.")
            return
        print(f"MockInteractionResponse: Defer called for interaction {self._interaction.id}. Ephemeral: {ephemeral}")
        self._is_done = True
        # В реальном API, defer() фактически отправляет ack. Здесь мы просто меняем флаг.

    async def send_message(self, content=None, *, embed=None, embeds=None, view=None, ephemeral: bool = False, **kwargs) -> None:
        if self._is_done:
            print(f"MockInteractionResponse: send_message called on already responded interaction for {self._interaction.id}. Use followup.")
            # В реальной ситуации это вызовет ошибку. Для тестов мы можем имитировать это или просто логировать.
            # Здесь мы позволим followup.send обработать это, если is_done=True
            await self._interaction.followup.send(content=content, embed=embed, embeds=embeds, view=view, ephemeral=ephemeral)
            return

        print(f"MockInteractionResponse: send_message for interaction {self._interaction.id}. Content: '{content}', Ephemeral: {ephemeral}")
        # Имитация отправки сообщения через канал взаимодействия или как "original response"
        if self._interaction.channel:
            msg = await self._interaction.channel.send(content=content, embed=embed, embeds=embeds, view=view)
            self._interaction._original_message = msg # Сохраняем как "оригинальный ответ"
        self._is_done = True

    def is_done(self) -> bool:
        return self._is_done

class MockInteractionFollowup(discord.Webhook): # Webhook - базовый класс для followup
    def __init__(self, interaction):
        # super().__init__(data={}, state=None) # Сложно мокнуть Webhook полностью
        self._interaction = interaction
        self._sent_followups = []

    async def send(self, content=None, *, embed=None, embeds=None, view=None, ephemeral: bool = False, **kwargs) -> 'MockMessage':
        print(f"MockInteractionFollowup: send for interaction {self._interaction.id}. Content: '{content}', Ephemeral: {ephemeral}")
        # В реальном API, followup отправляет новое сообщение через webhook.
        # Здесь мы имитируем это, отправляя сообщение в тот же канал.
        if self._interaction.channel:
            msg = await self._interaction.channel.send(content=content, embed=embed, embeds=embeds, view=view)
            self._sent_followups.append(msg)
            return msg
        # Если канала нет (например, в некоторых редких случаях или неполных моках), просто создаем мок-сообщение
        mock_msg = MockMessage(content=content, author=self._interaction.user, channel=self._interaction.channel, embed=embed, embeds=embeds, view=view)
        self._sent_followups.append(mock_msg)
        return mock_msg


class MockInteraction(discord.Interaction): # Наследуемся от discord.Interaction
    def __init__(self, user_mock: MockUser, channel_mock: MockTextChannel = None, guild_mock = None, interaction_id = None):
        # super().__init__(data={}, state=None) # Конструктор discord.Interaction сложен
        self.id = interaction_id or random.randint(10000000, 99999999)
        self.user = user_mock
        self.author = user_mock # Для совместимости с ctx.author
        self.channel = channel_mock
        self.guild = guild_mock if guild_mock else (channel_mock.guild if channel_mock else None)
        
        self.response = MockInteractionResponse(self)
        self.followup = MockInteractionFollowup(self)
        self._original_message = None # Для хранения "оригинального" сообщения от response.send_message

    # async def original_response(self) -> discord.InteractionMessage:
    #     return self._original_message

    # @property # discord.py v2 использует message для этого
    # async def message(self) -> discord.Message | None:
    #    """The message that this interaction is related to, if any."""
    #    # Для кнопок и select'ов это сообщение, к которому они прикреплены.
    #    # Для slash-команд это None до первого ответа, потом это InteractionMessage.
    #    return self._original_message


class MockGuild(discord.Guild):
    def __init__(self, id: int, name: str, bot_user_mock: MockUser):
        # super().__init__(data={'id': str(id), 'name': name, 'owner_id': '0', 'roles': [], 'emojis': []}, state=None)
        self.id = id
        self.name = name
        self.me = MockMember(bot_user_mock.id, bot_user_mock.name, self) # Бот как участник этой гильдии
        self._channels = {} # Словарь для хранения мок-каналов
        self._members = {bot_user_mock.id: self.me} # Словарь для хранения мок-участников

    def add_channel(self, channel_mock):
        self._channels[channel_mock.id] = channel_mock
        channel_mock.guild = self

    def get_channel(self, channel_id: int):
        return self._channels.get(channel_id)

    def add_member(self, member_mock: MockMember):
        self._members[member_mock.id] = member_mock
        member_mock.guild = self # Убедимся, что у участника есть ссылка на гильдию

    def get_member(self, user_id: int) -> MockMember | None:
        return self._members.get(user_id)
    
    @property
    def default_role(self):
        mock_role = Mock(id=self.id, name="@everyone") # Простой мок для @everyone
        mock_role.is_default = lambda: True
        return mock_role


class MockBot(commands.Bot):
    def __init__(self, user_mock: MockUser, *args, **kwargs):
        super().__init__(*args, **kwargs) # Инициализируем базовый commands.Bot
        self.user = user_mock # Мок-пользователь для бота
        self._guilds = {} # Словарь для хранения мок-гильдий
        self.game_state = None # Будет установлен в тесте
        self.reputation_system = None # Будет установлен в тесте
        self._activity = None
        self._status = discord.Status.online

    def add_guild(self, guild_mock: MockGuild):
        self._guilds[guild_mock.id] = guild_mock
        guild_mock.me = MockMember(self.user.id, self.user.name, guild_mock) # Убедимся, что у бота есть member объект в гильдии

    def get_guild(self, guild_id: int) -> MockGuild | None:
        return self._guilds.get(guild_id)

    def get_channel(self, channel_id: int):
        for guild in self._guilds.values():
            channel = guild.get_channel(channel_id)
            if channel:
                return channel
        return None
        
    async def change_presence(self, *, activity=None, status=None, afk=False):
        self._activity = activity
        self._status = status
        print(f"MockBot presence changed: Activity='{activity.name if activity else None}', Status='{status}'")


# --- Мок для config ---
# Вместо импорта реального config, мы можем создать мок-объект или словарь
# Это позволяет изолировать тесты от реальных значений конфигурации
mock_config_data = {
    "TOKEN": "TEST_TOKEN",
    "GAME_CHANNEL_ID": 100000000000000000, # ID игрового канала
    "VOICE_CHANNEL_ID_TEAM1": 100000000000000001,
    "VOICE_CHANNEL_ID_TEAM2": 100000000000000002,
    "GUILD_ID": 200000000000000000, # ID основного сервера
    "VOTE_THRESHOLD": 0.5, # 50% голосов для принятия решения
    "VOTING_DURATION": 30, # Секунд на голосование
    "RESET_DELAY": 1800, # 30 минут на сброс состояния
    "MAX_PLAYERS_PER_TEAM": 5,
    "ADMIN_GUILD_IDS": [200000000000000000], # ID серверов для админ-команд
    "BOT_ADMIN_USER_IDS": ["99999999999999999"] # ID пользователей-администраторов бота
}

class TestGameState(unittest.TestCase):
    """
    Набор тестов для класса GameState.
    """
    def setUp(self):
        """
        Настройка перед каждым тестом.
        """
        # Мок пользователя бота
        self.bot_user_mock = MockUser(id=123456789, name="ТестБот", bot_flag=True)
        # Мок бота
        self.bot_mock = MockBot(user_mock=self.bot_user_mock, command_prefix="!", intents=discord.Intents.default())
        
        # Мок гильдии
        self.guild_mock = MockGuild(id=mock_config_data["GUILD_ID"], name="Тестовый Сервер", bot_user_mock=self.bot_user_mock)
        self.bot_mock.add_guild(self.guild_mock) # Добавляем гильдию к боту

        # Мок игрового канала (текстовый)
        self.game_channel_mock = MockTextChannel(id=mock_config_data["GAME_CHANNEL_ID"], name="игровой-чат", guild_mock=self.guild_mock)
        self.guild_mock.add_channel(self.game_channel_mock)

        # Мок голосовых каналов
        self.voice_channel_team1_mock = MockVoiceChannel(id=mock_config_data["VOICE_CHANNEL_ID_TEAM1"], name="Команда 1 Войс", guild_mock=self.guild_mock)
        self.voice_channel_team2_mock = MockVoiceChannel(id=mock_config_data["VOICE_CHANNEL_ID_TEAM2"], name="Команда 2 Войс", guild_mock=self.guild_mock)
        self.guild_mock.add_channel(self.voice_channel_team1_mock)
        self.guild_mock.add_channel(self.voice_channel_team2_mock)

        # Патчим config для GameState
        # Мы можем либо передать мок config в GameState, либо использовать patch.dict,
        # если GameState импортирует config напрямую и обращается к его атрибутам.
        # Предположим, GameState импортирует 'import config'
        self.config_patcher = patch.dict(sys.modules['config'].__dict__, mock_config_data, clear=True)
        self.config_patcher.start() # Активируем патч перед созданием GameState

        # Создаем экземпляр GameState с моком бота и ID игрового канала
        self.game_state = GameState(self.bot_mock, mock_config_data["GAME_CHANNEL_ID"])
        self.bot_mock.game_state = self.game_state # Привязываем game_state к моку бота

        # Моки игроков (Member)
        self.player1_voice_state = MockVoiceState(channel=None) # Изначально не в голосовом канале
        self.player1 = MockMember(id=1, name="Игрок1", guild_mock=self.guild_mock, voice_state_mock=self.player1_voice_state)
        
        self.player2_voice_state = MockVoiceState(channel=None)
        self.player2 = MockMember(id=2, name="Игрок2", guild_mock=self.guild_mock, voice_state_mock=self.player2_voice_state)

        self.player3_voice_state = MockVoiceState(channel=None)
        self.player3 = MockMember(id=3, name="Игрок3", guild_mock=self.guild_mock, voice_state_mock=self.player3_voice_state)
        
        # Добавляем игроков в мок гильдии, чтобы get_member их находил
        self.guild_mock.add_member(self.player1)
        self.guild_mock.add_member(self.player2)
        self.guild_mock.add_member(self.player3)


    def tearDown(self):
        """
        Очистка после каждого теста.
        """
        self.config_patcher.stop() # Отключаем патч config
        # Дополнительная очистка, если требуется (например, отмена задач asyncio)
        if self.game_state.reset_task and not self.game_state.reset_task.done():
            self.game_state.reset_task.cancel()

    def async_test_wrapper(self, coro):
        """Обертка для выполнения асинхронного теста."""
        return asyncio.run(coro)

    # --- Тесты для register_player ---
    def test_register_player_successful(self):
        """Тест успешной регистрации игрока."""
        async def test_logic():
            interaction_mock = MockInteraction(user_mock=self.player1, channel_mock=self.game_channel_mock, guild_mock=self.guild_mock)
            # Устанавливаем максимальное количество игроков в команде, например 1, чтобы сразу проверить заполнение
            await self.game_state.set_players_per_team(1, interaction_mock) 
            
            # Первая регистрация
            interaction_p1 = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            is_full, response = await self.game_state.register_player(self.player1, interaction_p1)
            
            self.assertIn(self.player1, self.game_state.registered_players, "Игрок1 должен быть в списке зарегистрированных.")
            self.assertFalse(is_full, "Команды не должны быть полными после регистрации одного игрока при настройке 1 в команде (нужно 2).")
            self.assertIn("зарегистрирован на матч", response.lower())
            self.assertEqual(len(self.game_state.registered_players), 1)

            # Вторая регистрация, команды заполняются
            interaction_p2 = MockInteraction(self.player2, self.game_channel_mock, self.guild_mock)
            is_full_after_p2, response_p2 = await self.game_state.register_player(self.player2, interaction_p2)
            
            self.assertIn(self.player2, self.game_state.registered_players)
            self.assertTrue(is_full_after_p2, "Команды должны быть полными.")
            self.assertIn("старт голосования", response_p2.lower()) # Или другое сообщение о полноте
            self.assertEqual(len(self.game_state.registered_players), 2)
            self.assertTrue(self.game_state.voting_active, "Голосование должно было начаться после заполнения команд.")

        self.async_test_wrapper(test_logic())

    def test_register_player_duplicate(self):
        """Тест на попытку повторной регистрации одного и того же игрока."""
        async def test_logic():
            interaction_p1_first = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            await self.game_state.register_player(self.player1, interaction_p1_first) # Первая регистрация

            interaction_p1_second = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            is_full, response = await self.game_state.register_player(self.player1, interaction_p1_second) # Повторная
            
            self.assertFalse(is_full) # Статус полноты не должен измениться
            self.assertIn("вы уже зарегистрированы", response.lower())
            self.assertEqual(len(self.game_state.registered_players), 1, "Количество игроков не должно измениться.")
        self.async_test_wrapper(test_logic())

    def test_register_player_teams_full(self):
        """Тест на попытку регистрации, когда команды уже полностью заполнены."""
        async def test_logic():
            # Устанавливаем PPT=1, значит всего 2 игрока
            interaction_admin = MockInteraction(MockUser(99, "Admin"), self.game_channel_mock, self.guild_mock)
            await self.game_state.set_players_per_team(1, interaction_admin)

            interaction_p1 = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            await self.game_state.register_player(self.player1, interaction_p1)
            interaction_p2 = MockInteraction(self.player2, self.game_channel_mock, self.guild_mock)
            await self.game_state.register_player(self.player2, interaction_p2) # Команды заполнены

            self.assertTrue(await self.game_state.check_ready_to_start())

            interaction_p3 = MockInteraction(self.player3, self.game_channel_mock, self.guild_mock)
            is_full, response = await self.game_state.register_player(self.player3, interaction_p3) # Попытка зарегистрировать третьего
            
            self.assertFalse(is_full) # Флаг is_full из register_player может быть False, если регистрация не удалась
            self.assertIn("максимальное количество игроков", response.lower())
            self.assertNotIn(self.player3, self.game_state.registered_players)
            self.assertEqual(len(self.game_state.registered_players), 2)
        self.async_test_wrapper(test_logic())
        
    def test_register_player_during_voting(self):
        """Тест: Попытка регистрации, когда голосование уже активно."""
        async def test_logic():
            interaction_admin = MockInteraction(MockUser(99, "Admin"), self.game_channel_mock, self.guild_mock)
            await self.game_state.set_players_per_team(1, interaction_admin) # 2 игрока для старта

            interaction_p1 = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            await self.game_state.register_player(self.player1, interaction_p1)
            
            interaction_p2 = MockInteraction(self.player2, self.game_channel_mock, self.guild_mock)
            await self.game_state.register_player(self.player2, interaction_p2) # Голосование должно начаться

            self.assertTrue(self.game_state.voting_active, "Голосование должно быть активно.")

            interaction_p3 = MockInteraction(self.player3, self.game_channel_mock, self.guild_mock)
            _ , response = await self.game_state.register_player(self.player3, interaction_p3)
            
            self.assertIn("регистрация закрыта", response.lower())
            self.assertNotIn(self.player3, self.game_state.registered_players)
        self.async_test_wrapper(test_logic())

    # --- Тесты для unregister_player ---
    def test_unregister_player_successful(self):
        """Тест успешной отмены регистрации."""
        async def test_logic():
            interaction_p1_reg = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            await self.game_state.register_player(self.player1, interaction_p1_reg)
            self.assertIn(self.player1, self.game_state.registered_players)

            interaction_p1_unreg = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            response = await self.game_state.unregister_player(self.player1, interaction_p1_unreg)
            
            self.assertNotIn(self.player1, self.game_state.registered_players)
            self.assertIn("регистрация отменена", response.lower())
            self.assertEqual(len(self.game_state.registered_players), 0)
        self.async_test_wrapper(test_logic())

    def test_unregister_player_not_registered(self):
        """Тест отмены регистрации для игрока, который не был зарегистрирован."""
        async def test_logic():
            interaction_p1_unreg = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            response = await self.game_state.unregister_player(self.player1, interaction_p1_unreg)
            self.assertIn("вы не были зарегистрированы", response.lower())
        self.async_test_wrapper(test_logic())
        
    def test_unregister_player_during_voting(self):
        """Тест: Попытка отмены регистрации, когда голосование уже активно."""
        async def test_logic():
            interaction_admin = MockInteraction(MockUser(99, "Admin"), self.game_channel_mock, self.guild_mock)
            await self.game_state.set_players_per_team(1, interaction_admin) 

            interaction_p1 = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            await self.game_state.register_player(self.player1, interaction_p1)
            
            interaction_p2 = MockInteraction(self.player2, self.game_channel_mock, self.guild_mock)
            await self.game_state.register_player(self.player2, interaction_p2) # Голосование началось

            self.assertTrue(self.game_state.voting_active)

            interaction_p1_unreg = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            response = await self.game_state.unregister_player(self.player1, interaction_p1_unreg)
            
            self.assertIn("отмена регистрации невозможна", response.lower()) # Или "закрыта"
            self.assertIn(self.player1, self.game_state.registered_players, "Игрок должен остаться в списке, если отмена не удалась.")
        self.async_test_wrapper(test_logic())


    # --- Тесты для set_players_per_team ---
    def test_set_players_per_team_valid(self):
        """Тест установки корректного количества игроков в команде."""
        async def test_logic():
            interaction = MockInteraction(MockUser(99, "Admin"), self.game_channel_mock, self.guild_mock)
            success, response = await self.game_state.set_players_per_team(3, interaction)
            self.assertTrue(success)
            self.assertEqual(self.game_state.players_per_team, 3)
            self.assertIn("количество игроков в команде установлено в 3", response.lower())
        self.async_test_wrapper(test_logic())

    def test_set_players_per_team_invalid_too_low_or_high(self):
        """Тест установки некорректного количества игроков (слишком мало или много)."""
        async def test_logic():
            interaction = MockInteraction(MockUser(99, "Admin"), self.game_channel_mock, self.guild_mock)
            initial_ppt = self.game_state.players_per_team

            success, response = await self.game_state.set_players_per_team(0, interaction) # Слишком мало
            self.assertFalse(success)
            self.assertIn("должно быть от 1 до", response.lower())
            self.assertEqual(self.game_state.players_per_team, initial_ppt) # Значение не должно измениться

            success, response = await self.game_state.set_players_per_team(mock_config_data["MAX_PLAYERS_PER_TEAM"] + 1, interaction) # Слишком много
            self.assertFalse(success)
            self.assertIn(f"от 1 до {mock_config_data['MAX_PLAYERS_PER_TEAM']}", response.lower())
            self.assertEqual(self.game_state.players_per_team, initial_ppt)
        self.async_test_wrapper(test_logic())
        
    def test_set_players_per_team_while_voting_active(self):
        """Тест: Попытка изменить PPT, когда голосование активно."""
        async def test_logic():
            # Заполняем команды и начинаем голосование
            admin_interaction = MockInteraction(MockUser(99, "Admin"), self.game_channel_mock, self.guild_mock)
            await self.game_state.set_players_per_team(1, admin_interaction)
            await self.game_state.register_player(self.player1, MockInteraction(self.player1, self.game_channel_mock, self.guild_mock))
            await self.game_state.register_player(self.player2, MockInteraction(self.player2, self.game_channel_mock, self.guild_mock))
            self.assertTrue(self.game_state.voting_active)
            
            initial_ppt = self.game_state.players_per_team
            set_interaction = MockInteraction(MockUser(100, "AnotherAdmin"), self.game_channel_mock, self.guild_mock)
            success, response = await self.game_state.set_players_per_team(3, set_interaction)
            
            self.assertFalse(success)
            self.assertIn("невозможно: идет активное голосование", response.lower())
            self.assertEqual(self.game_state.players_per_team, initial_ppt)
        self.async_test_wrapper(test_logic())

    # --- Тесты для auto_split_teams ---
    def test_auto_split_teams_even_players(self):
        """Тест разделения на команды с четным количеством игроков."""
        async def test_logic():
            interaction_admin = MockInteraction(MockUser(99, "Admin"), self.game_channel_mock, self.guild_mock)
            await self.game_state.set_players_per_team(2, interaction_admin) # 4 игрока всего
            
            players = [self.player1, self.player2, MockMember(3, "P3", self.guild_mock), MockMember(4, "P4", self.guild_mock)]
            for p in players:
                 self.guild_mock.add_member(p) # Убедимся, что они в гильдии
                 await self.game_state.register_player(p, MockInteraction(p, self.game_channel_mock, self.guild_mock))
            
            team1, team2 = await self.game_state.auto_split_teams(shuffle=False) # Без перемешивания для предсказуемости
            
            self.assertEqual(len(team1), 2)
            self.assertEqual(len(team2), 2)
            # Проверяем, что игроки разные в командах (без shuffle они должны идти по порядку регистрации)
            self.assertListEqual(team1, [players[0], players[1]])
            self.assertListEqual(team2, [players[2], players[3]])
        self.async_test_wrapper(test_logic())
        
    def test_auto_split_teams_odd_players(self):
        """Тест разделения на команды с нечетным количеством зарегистрированных игроков (не должно происходить, если PPT установлено)."""
        # Этот тест проверяет само разделение, а не процесс регистрации
        async def test_logic():
            self.game_state.registered_players = [self.player1, self.player2, self.player3] # 3 игрока
            # PPT не так важен здесь, так как мы тестируем сам механизм auto_split_teams
            
            team1, team2 = await self.game_state.auto_split_teams(shuffle=False)
            
            # Ожидаем, что одна команда будет больше
            self.assertTrue((len(team1) == 2 and len(team2) == 1) or (len(team1) == 1 and len(team2) == 2))
            if len(team1) == 2:
                self.assertListEqual(team1, [self.player1, self.player2])
                self.assertListEqual(team2, [self.player3])
            else:
                self.assertListEqual(team1, [self.player1])
                self.assertListEqual(team2, [self.player2, self.player3])

        self.async_test_wrapper(test_logic())

    def test_auto_split_teams_shuffle(self):
        """Тест разделения с перемешиванием."""
        async def test_logic():
            players = [self.player1, self.player2, MockMember(3,"P3",self.guild_mock), MockMember(4,"P4",self.guild_mock)]
            for p in players: self.guild_mock.add_member(p)
            self.game_state.registered_players = list(players) # Копируем список
            
            # Просто проверяем, что команды формируются и имеют правильную общую длину
            # Точный состав проверить сложно из-за случайности
            with patch.object(random, 'shuffle') as mock_shuffle:
                team1, team2 = await self.game_state.auto_split_teams(shuffle=True)
                mock_shuffle.assert_called_once_with(self.game_state.registered_players)

            self.assertEqual(len(team1) + len(team2), len(players))
            self.assertTrue(abs(len(team1) - len(team2)) <= 1) # Разница в размере команд не более 1
        self.async_test_wrapper(test_logic())
        
    def test_auto_split_teams_insufficient_players(self):
        """Тест разделения, когда игроков меньше 2."""
        async def test_logic():
            self.game_state.registered_players = [self.player1]
            team1, team2 = await self.game_state.auto_split_teams()
            self.assertEqual(len(team1), 0) # Ожидаем пустые команды или спец. обработку
            self.assertEqual(len(team2), 0)

            self.game_state.registered_players = []
            team1, team2 = await self.game_state.auto_split_teams()
            self.assertEqual(len(team1), 0)
            self.assertEqual(len(team2), 0)
        self.async_test_wrapper(test_logic())

    # --- Тесты для clear_registered_players ---
    @patch('game_state.GameState.update_bot_status', new_callable=AsyncMock) # Мокаем, чтобы не проверять реальное изменение статуса
    def test_clear_registered_players(self, mock_update_status):
        """Тест полной очистки состояния игры."""
        async def test_logic():
            # Регистрируем игроков, начинаем голосование
            interaction_admin = MockInteraction(MockUser(99, "Admin"), self.game_channel_mock, self.guild_mock)
            await self.game_state.set_players_per_team(1, interaction_admin)
            await self.game_state.register_player(self.player1, MockInteraction(self.player1, self.game_channel_mock, self.guild_mock))
            await self.game_state.register_player(self.player2, MockInteraction(self.player2, self.game_channel_mock, self.guild_mock))
            
            # Мокаем сообщение о голосовании, если оно создается
            mock_voting_msg = AsyncMock(spec=discord.Message)
            mock_voting_msg.delete = AsyncMock()
            self.game_state.voting_message = mock_voting_msg
            
            self.assertTrue(self.game_state.voting_active)
            self.assertNotEqual(len(self.game_state.registered_players), 0)
            self.assertNotEqual(self.game_state.votes["agree"], 0) # Голоса могут быть не 0, если кто-то проголосовал (не тестируем здесь)
                                                                # Но clear должен их сбросить
            
            response = await self.game_state.clear_registered_players()
            
            self.assertEqual(len(self.game_state.registered_players), 0)
            self.assertFalse(self.game_state.voting_active)
            self.assertEqual(self.game_state.votes, {"agree": 0, "reshuffle": 0})
            if mock_config_data["GAME_CHANNEL_ID"]: # Если канал настроен
                 mock_update_status.assert_called_once() # Проверяем, что статус бота обновляется
            
            self.assertIn("список зарегистрированных игроков очищен", response.lower())
            if self.game_state.voting_message: # Должен быть None
                 mock_voting_msg.delete.assert_called_once() # Проверяем, что сообщение удаляется
            self.assertIsNone(self.game_state.voting_message)
            
        self.async_test_wrapper(test_logic())

    # --- Тесты для process_vote и evaluate_votes ---
    # Эти тесты будут сложнее из-за взаимодействия и состояния
    # Начнем с process_vote
    
    @patch('game_state.GameState._update_voting_message', new_callable=AsyncMock)
    @patch('game_state.GameState.evaluate_votes', new_callable=AsyncMock)
    async def run_process_vote_test(self, players_for_vote, vote_type, expected_votes, 
                                    should_evaluate_be_called, mock_eval_votes, mock_update_msg):
        """Вспомогательный метод для тестирования process_vote."""
        # Настройка
        admin_interaction = MockInteraction(MockUser(99, "Admin"), self.game_channel_mock, self.guild_mock)
        # Устанавливаем количество игроков в команде = len(players_for_vote) / 2
        # Это гарантирует, что VOTE_THRESHOLD * len(registered_players) будет корректно рассчитываться
        # Например, если 2 игрока, то PPT=1. Если 10 игроков, PPT=5.
        # Для простоты, используем фиксированное количество, например 5 игроков в команде (10 всего)
        # или настраиваем VOTE_THRESHOLD = 1 / len(players_for_vote) чтобы 1 голос решал
        
        # Для теста, где 1 голос решает, установим VOTE_THRESHOLD так,
        # чтобы len(players_for_vote) * VOTE_THRESHOLD = 1
        # mock_config_data['VOTE_THRESHOLD'] = 1 / len(players_for_vote) if players_for_vote else 1
        # Но это меняет глобальный мок. Лучше настроить игроков под стандартный VOTE_THRESHOLD = 0.5
        # Если нужно 2 голоса для решения, то нужно 2 / 0.5 = 4 игрока в registered_players
        
        # Обновляем config для текущего теста, если нужно
        current_vote_threshold = 0.5 # Стандартный
        # Если нужно, чтобы 1 голос решал при 2х игроках:
        # current_vote_threshold = 0.1 # 2 * 0.1 = 0.2 -> max(int(0.2), 1) = 1
        # Если нужно, чтобы 2 голоса решали при 2х игроках:
        # current_vote_threshold = 1.0 # 2 * 1.0 = 2.0 -> max(int(2.0), 1) = 2
        
        # Для теста, где 1 голос решает из 2х зарегистрированных:
        if len(players_for_vote) == 2 and expected_votes[vote_type] == 1 and should_evaluate_be_called:
             # 2 игрока * 0.1 порог = 0.2 -> округляется до 1 необходимого голоса
            with patch.dict(sys.modules['config'].__dict__, {"VOTE_THRESHOLD": 0.1}):
                self.game_state.registered_players = list(players_for_vote)
                self.game_state.voting_active = True
                self.game_state.votes = {"agree": 0, "reshuffle": 0} # Сброс перед тестом

                voter = players_for_vote[0]
                vote_interaction = MockInteraction(voter, self.game_channel_mock, self.guild_mock)
                await self.game_state.process_vote(voter, vote_type, vote_interaction)
        else: # Стандартный порог
            with patch.dict(sys.modules['config'].__dict__, {"VOTE_THRESHOLD": 0.5}):
                self.game_state.registered_players = list(players_for_vote)
                self.game_state.voting_active = True
                self.game_state.votes = {"agree": 0, "reshuffle": 0} 

                voter = players_for_vote[0]
                vote_interaction = MockInteraction(voter, self.game_channel_mock, self.guild_mock)
                await self.game_state.process_vote(voter, vote_type, vote_interaction)

        self.assertEqual(self.game_state.votes, expected_votes)
        if should_evaluate_be_called:
            mock_eval_votes.assert_called_once()
            mock_update_msg.assert_not_called()
        else:
            mock_eval_votes.assert_not_called()
            if players_for_vote : # Обновление сообщения только если есть игроки и голосование не завершено
                 mock_update_msg.assert_called_once()


    def test_process_vote_agree_reaches_threshold(self):
        """Тест: Голос 'за' достигает порога, evaluate_votes вызывается."""
        # Нужны игроки, чтобы порог был > 0. Например, 2 игрока, порог 0.1 -> 1 голос решает.
        asyncio.run(self.run_process_vote_test(
            players_for_vote=[self.player1, self.player2], 
            vote_type="agree", 
            expected_votes={"agree": 1, "reshuffle": 0},
            should_evaluate_be_called=True
        ))
        
    def test_process_vote_reshuffle_reaches_threshold(self):
        """Тест: Голос 'перемешать' достигает порога, evaluate_votes вызывается."""
        asyncio.run(self.run_process_vote_test(
            players_for_vote=[self.player1, self.player2], 
            vote_type="reshuffle", 
            expected_votes={"agree": 0, "reshuffle": 1},
            should_evaluate_be_called=True
        ))

    def test_process_vote_not_reaches_threshold(self):
        """Тест: Голос не достигает порога, _update_voting_message вызывается."""
        # Понадобится больше игроков или выше порог, чтобы один голос не решал.
        # Например, 4 игрока, порог 0.5 -> нужно 2 голоса.
        players = [self.player1, self.player2, self.player3, MockMember(4,"P4",self.guild_mock)]
        for p in players: self.guild_mock.add_member(p)

        asyncio.run(self.run_process_vote_test(
            players_for_vote=players,
            vote_type="agree", 
            expected_votes={"agree": 1, "reshuffle": 0},
            should_evaluate_be_called=False 
        ))
        
    def test_process_vote_user_not_registered(self):
        """Тест: Голосующий пользователь не зарегистрирован."""
        async def test_logic():
            self.game_state.registered_players = [self.player1] # Только player1 зарегистрирован
            self.game_state.voting_active = True
            
            # player2 пытается голосовать
            vote_interaction = MockInteraction(self.player2, self.game_channel_mock, self.guild_mock)
            # Мокаем followup.send, чтобы проверить, что он был вызван с правильным сообщением
            vote_interaction.followup.send = AsyncMock()

            await self.game_state.process_vote(self.player2, "agree", vote_interaction)
            
            self.assertEqual(self.game_state.votes["agree"], 0) # Голос не должен быть учтен
            vote_interaction.followup.send.assert_called_once()
            # Проверяем, что в аргументах вызова есть нужное сообщение (или его часть)
            args, kwargs = vote_interaction.followup.send.call_args
            self.assertTrue(any("не зарегистрированы" in str(arg).lower() for arg in args) or \
                            any("не зарегистрированы" in str(val).lower() for val in kwargs.values()))

        self.async_test_wrapper(test_logic())

    def test_process_vote_voting_not_active(self):
        """Тест: Попытка голосовать, когда голосование неактивно."""
        async def test_logic():
            self.game_state.registered_players = [self.player1]
            self.game_state.voting_active = False # Голосование НЕ активно
            
            vote_interaction = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            vote_interaction.followup.send = AsyncMock()
            
            await self.game_state.process_vote(self.player1, "agree", vote_interaction)
            
            self.assertEqual(self.game_state.votes["agree"], 0)
            vote_interaction.followup.send.assert_called_once()
            args, kwargs = vote_interaction.followup.send.call_args
            self.assertTrue(any("неактивно" in str(arg).lower() or "завершено" in str(arg).lower() for arg in args) or \
                            any("неактивно" in str(val).lower() or "завершено" in str(val).lower() for val in kwargs.values()))
        self.async_test_wrapper(test_logic())

    # --- Тесты для evaluate_votes ---
    @patch('game_state.GameState.finalize_teams', new_callable=AsyncMock)
    @patch('game_state.GameState.reshuffle_and_revote', new_callable=AsyncMock)
    @patch('game_state.GameState._send_channel_message', new_callable=AsyncMock) # Мокаем отправку сообщений в канал
    async def run_evaluate_votes_test(self, registered_players_count, agree_votes, reshuffle_votes,
                                      force_end_vote,
                                      expected_finalize_calls, expected_reshuffle_calls,
                                      mock_send_msg, mock_reshuffle, mock_finalize):
        """Вспомогательный метод для тестирования evaluate_votes."""
        # Настройка игроков и голосов
        self.game_state.registered_players = [MockMember(i, f"P{i}", self.guild_mock) for i in range(1, registered_players_count + 1)]
        for p in self.game_state.registered_players: self.guild_mock.add_member(p)

        self.game_state.votes = {"agree": agree_votes, "reshuffle": reshuffle_votes}
        self.game_state.voting_active = True # Голосование должно быть активно перед оценкой
        
        # Мокаем сообщение о голосовании, чтобы проверить его удаление
        mock_voting_msg = AsyncMock(spec=discord.Message)
        mock_voting_msg.delete = AsyncMock()
        self.game_state.voting_message = mock_voting_msg

        mock_interaction = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
        
        # Используем VOTE_THRESHOLD из мок-конфига (0.5)
        # required_votes = max(int(mock_config_data["VOTE_THRESHOLD"] * registered_players_count), 1)
        # print(f"Для теста evaluate_votes: {registered_players_count} игроков, agree={agree_votes}, reshuffle={reshuffle_votes}, force={force_end_vote}, порог={mock_config_data['VOTE_THRESHOLD']}. Ожидаемый порог голосов: {required_votes}")

        await self.game_state.evaluate_votes(interaction=mock_interaction, force_end_vote=force_end_vote)

        self.assertFalse(self.game_state.voting_active, "voting_active должен быть False после evaluate_votes.")
        if mock_voting_msg: # Если сообщение было
            mock_voting_msg.delete.assert_called_once()
        self.assertIsNone(self.game_state.voting_message, "Сообщение о голосовании должно быть сброшено.")
        
        self.assertEqual(mock_finalize.call_count, expected_finalize_calls, f"finalize_teams вызван неверное количество раз ({mock_finalize.call_count} вместо {expected_finalize_calls})")
        self.assertEqual(mock_reshuffle.call_count, expected_reshuffle_calls, f"reshuffle_and_revote вызван неверное количество раз ({mock_reshuffle.call_count} вместо {expected_reshuffle_calls})")


    def test_evaluate_votes_agree_wins(self):
        """Тест: 'Согласны' побеждает (явный порог)."""
        # 4 игрока, порог 0.5 -> нужно 2 голоса. Даем 2 голоса "за".
        asyncio.run(self.run_evaluate_votes_test(registered_players_count=4, agree_votes=2, reshuffle_votes=1, force_end_vote=False,
                                                 expected_finalize_calls=1, expected_reshuffle_calls=0))

    def test_evaluate_votes_reshuffle_wins(self):
        """Тест: 'Перемешать' побеждает (явный порог)."""
        # 4 игрока, порог 0.5 -> нужно 2 голоса. Даем 2 голоса "перемешать".
        asyncio.run(self.run_evaluate_votes_test(registered_players_count=4, agree_votes=1, reshuffle_votes=2, force_end_vote=False,
                                                 expected_finalize_calls=0, expected_reshuffle_calls=1))

    def test_evaluate_votes_force_end_agree_wins_due_to_force(self):
        """Тест: Принудительное завершение, 'Согласны' побеждает, т.к. 'Перемешать' не набрало порог."""
        # 10 игроков, порог 0.5 -> нужно 5 голосов.
        # 'Согласны' = 3, 'Перемешать' = 2. Никто не набрал. При force=True, 'Согласны' должно победить.
        # (10 - 2 = 8 голосов за "Согласны" после принуждения)
        asyncio.run(self.run_evaluate_votes_test(registered_players_count=10, agree_votes=3, reshuffle_votes=2, force_end_vote=True,
                                                 expected_finalize_calls=1, expected_reshuffle_calls=0))

    def test_evaluate_votes_force_end_reshuffle_still_wins_if_already_met_threshold(self):
        """Тест: Принудительное завершение, но 'Перемешать' уже победило по голосам."""
        # 10 игроков, порог 0.5 -> нужно 5 голосов.
        # 'Согласны' = 1, 'Перемешать' = 6. 'Перемешать' уже победило. force=True не должен ничего менять.
        asyncio.run(self.run_evaluate_votes_test(registered_players_count=10, agree_votes=1, reshuffle_votes=6, force_end_vote=True,
                                                 expected_finalize_calls=0, expected_reshuffle_calls=1))

    def test_evaluate_votes_no_clear_winner_not_forced_defaults_to_finalize(self):
        """Тест: Нет явного победителя, не принудительно -> финализация по умолчанию."""
        # 10 игроков, порог 0.5 -> нужно 5 голосов.
        # 'Согласны' = 2, 'Перемешать' = 1. Никто не набрал. Не принудительно. Должна быть финализация.
        asyncio.run(self.run_evaluate_votes_test(registered_players_count=10, agree_votes=2, reshuffle_votes=1, force_end_vote=False,
                                                 expected_finalize_calls=1, expected_reshuffle_calls=0))
                                                 
    def test_evaluate_votes_no_registered_players(self):
        """Тест: evaluate_votes вызывается без зарегистрированных игроков."""
        async def test_logic():
            self.game_state.registered_players = []
            self.game_state.voting_active = True
            mock_interaction = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            
            # Моки методов, которые не должны быть вызваны
            self.game_state.finalize_teams = AsyncMock()
            self.game_state.reshuffle_and_revote = AsyncMock()
            self.game_state.update_bot_status = AsyncMock() # update_bot_status будет вызван

            await self.game_state.evaluate_votes(interaction=mock_interaction, force_end_vote=False)
            
            self.assertFalse(self.game_state.voting_active)
            self.game_state.finalize_teams.assert_not_called()
            self.game_state.reshuffle_and_revote.assert_not_called()
            self.game_state.update_bot_status.assert_called_once() # Должен быть вызван для обновления статуса
        self.async_test_wrapper(test_logic())


    # --- Тесты для start_voting и voting_timer ---
    @patch('asyncio.create_task') # Мокаем создание задачи
    @patch('game_state.GameState.update_bot_status', new_callable=AsyncMock)
    def test_start_voting(self, mock_update_status, mock_create_task):
        """Тест начала процесса голосования."""
        async def test_logic():
            self.game_state.voting_active = False
            self.game_state.votes = {"agree": 1, "reshuffle": 1} # Старые голоса
            
            mock_interaction = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            await self.game_state.start_voting(mock_interaction)
            
            self.assertTrue(self.game_state.voting_active)
            self.assertEqual(self.game_state.votes, {"agree": 0, "reshuffle": 0}, "Голоса должны быть сброшены.")
            mock_update_status.assert_called_once()
            mock_create_task.assert_called_once() # Проверяем, что таймер был запущен
            # Можно также проверить аргументы mock_create_task, если важно, какой корутин запускается
            args, _ = mock_create_task.call_args
            self.assertTrue(isinstance(args[0], asyncio.coroutines.CoroWrapper)) # Проверяем, что это корутина
            # self.assertEqual(args[0].cr_code.co_name, 'voting_timer') # Ненадежно, зависит от реализации CoroWrapper
        self.async_test_wrapper(test_logic())

    @patch('asyncio.sleep', new_callable=AsyncMock) # Мокаем sleep
    @patch('game_state.GameState.evaluate_votes', new_callable=AsyncMock)
    def test_voting_timer_ends_voting_when_active(self, mock_evaluate_votes, mock_sleep):
        """Тест: Таймер голосования завершает голосование, если оно еще активно."""
        async def test_logic():
            self.game_state.voting_active = True
            mock_interaction = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            
            # Запускаем таймер (он сам по себе не тестируется, а его эффект)
            # Передаем guild_id и channel_id из моков
            await self.game_state.voting_timer(self.guild_mock.id, self.game_channel_mock.id, mock_interaction)
            
            mock_sleep.assert_called_once_with(mock_config_data["VOTING_DURATION"])
            mock_evaluate_votes.assert_called_once_with(interaction=mock_interaction, force_end_vote=True)
        self.async_test_wrapper(test_logic())

    @patch('asyncio.sleep', new_callable=AsyncMock)
    @patch('game_state.GameState.evaluate_votes', new_callable=AsyncMock)
    def test_voting_timer_does_nothing_if_not_active(self, mock_evaluate_votes, mock_sleep):
        """Тест: Таймер голосования ничего не делает, если голосование уже неактивно."""
        async def test_logic():
            self.game_state.voting_active = False # Голосование уже завершено
            mock_interaction = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            
            await self.game_state.voting_timer(self.guild_mock.id, self.game_channel_mock.id, mock_interaction)
            
            mock_sleep.assert_called_once_with(mock_config_data["VOTING_DURATION"])
            mock_evaluate_votes.assert_not_called() # evaluate_votes не должен быть вызван
        self.async_test_wrapper(test_logic())

    # --- Тесты для таймера сброса игры ---
    @patch('asyncio.create_task')
    def test_start_reset_timer_creates_task_and_cancels_existing(self, mock_create_task):
        """Тест: start_reset_timer создает новую задачу и отменяет существующую."""
        async def test_logic():
            # Первая задача
            mock_task1 = AsyncMock(spec=asyncio.Task)
            mock_task1.cancel = MagicMock() # Используем MagicMock для .cancel()
            self.game_state.reset_task = mock_task1
            
            await self.game_state.start_reset_timer()
            
            mock_task1.cancel.assert_called_once()
            mock_create_task.assert_called_once()
            self.assertIsNotNone(self.game_state.reset_task)
            self.assertNotEqual(self.game_state.reset_task, mock_task1) # Должна быть новая задача
            
            # Вторая задача (проверка, что новая задача тоже будет моком)
            new_mock_task_obj = mock_create_task.return_value
            self.assertEqual(self.game_state.reset_task, new_mock_task_obj)

        self.async_test_wrapper(test_logic())


    @patch('asyncio.sleep', new_callable=AsyncMock)
    @patch('game_state.GameState.clear_registered_players', new_callable=AsyncMock)
    def test_reset_game_state_after_delay(self, mock_clear_players, mock_sleep):
        """Тест: reset_game_state_after_delay ждет и вызывает clear_registered_players."""
        async def test_logic():
            await self.game_state.reset_game_state_after_delay()
            mock_sleep.assert_called_once_with(mock_config_data["RESET_DELAY"])
            mock_clear_players.assert_called_once()
        self.async_test_wrapper(test_logic())
        
    # --- Тесты для finalize_teams и reshuffle_and_revote ---
    @patch('game_state.GameState.auto_split_teams', new_callable=AsyncMock)
    @patch('game_state.GameState.move_players_to_voice_channels', new_callable=AsyncMock)
    @patch('game_state.GameState.display_voice_channel_links', new_callable=AsyncMock)
    @patch('game_state.GameState.update_bot_status', new_callable=AsyncMock)
    @patch('game_state.GameState.reset_votes', new_callable=AsyncMock)
    @patch('game_state.GameState._send_channel_message', new_callable=AsyncMock)
    async def run_finalize_teams_test(self, mock_send_msg, mock_reset_votes, mock_update_status, 
                                      mock_display_links, mock_move_players, mock_auto_split):
        """Тест логики finalize_teams."""
        # Устанавливаем некоторое начальное состояние
        self.game_state.registered_players = [self.player1, self.player2] # Допустим, есть игроки
        self.guild_mock.add_member(self.player1)
        self.guild_mock.add_member(self.player2)
        self.game_state.voting_active = True # Голосование было активно

        # auto_split_teams должен вернуть какие-то команды
        mock_auto_split.return_value = ([self.player1], [self.player2])

        await self.game_state.finalize_teams()

        self.assertFalse(self.game_state.voting_active)
        mock_auto_split.assert_called_once_with(shuffle=False)
        mock_send_msg.assert_called() # Проверяем, что сообщение о финализации было отправлено
        mock_move_players.assert_called_once_with([self.player1], [self.player2])
        mock_display_links.assert_called_once()
        mock_update_status.assert_called_once()
        mock_reset_votes.assert_called_once()

    def test_finalize_teams_calls_all_helpers(self):
        asyncio.run(self.run_finalize_teams_test())

    @patch('game_state.GameState.reset_votes', new_callable=AsyncMock)
    @patch('game_state.GameState.display_teams_general', new_callable=AsyncMock)
    @patch('game_state.GameState.start_voting', new_callable=AsyncMock)
    @patch('game_state.GameState.update_bot_status', new_callable=AsyncMock)
    async def run_reshuffle_and_revote_test(self, mock_update_status, mock_start_voting, 
                                           mock_display_teams, mock_reset_votes):
        """Тест логики reshuffle_and_revote."""
        mock_interaction = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
        self.game_state.voting_active = False # Голосование было неактивно перед этим

        await self.game_state.reshuffle_and_revote(mock_interaction)

        mock_reset_votes.assert_called_once()
        self.assertTrue(self.game_state.voting_active)
        mock_display_teams.assert_called_once_with(interaction=mock_interaction, shuffle=True, display_voting_buttons=True)
        mock_start_voting.assert_called_once_with(mock_interaction)
        mock_update_status.assert_called_once()

    def test_reshuffle_and_revote_calls_all_helpers(self):
        asyncio.run(self.run_reshuffle_and_revote_test())


if __name__ == '__main__':
    unittest.main()
