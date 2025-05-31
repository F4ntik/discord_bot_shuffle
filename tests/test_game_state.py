# tests/test_game_state.py
import unittest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import asyncio
import discord # Для type hints и некоторых констант, если нужны
import random # Для мока random.shuffle в auto_split_teams

# Добавляем путь к корневой директории проекта
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Теперь импортируем config ПЕРЕД game_state
# Это должно помочь найти модуль config.py из корневой директории
try:
    import config
except ModuleNotFoundError:
    # Этот блок больше для отладки; в идеале, sys.path должен работать.
    # Если тесты запускаются из корневой папки (`python -m unittest discover tests`),
    # то config должен быть доступен без манипуляций с sys.path в этом файле.
    # Однако, оставим эту заглушку на случай, если импорт все же не сработает.
    print("ПРЕДУПРЕЖДЕНИЕ TGS002: Не удалось импортировать реальный config.py. Используется мок-конфигурация для тестов.")
    class MockConfigModuleForGameState: # Даем уникальное имя, чтобы не конфликтовать с mock_config_data
        TOKEN = "TEST_TOKEN_MOCK_GS"
        GAME_CHANNEL_ID = 100000000000000000
        VOICE_CHANNEL_ID_TEAM1 = 100000000000000001
        VOICE_CHANNEL_ID_TEAM2 = 100000000000000002
        GUILD_ID = 200000000000000000
        VOTE_THRESHOLD = 0.5
        VOTING_DURATION = 30 # Секунд
        RESET_DELAY = 1800 # Секунд (30 минут)
        MAX_PLAYERS_PER_TEAM = 5
        ADMIN_GUILD_IDS = [200000000000000000]
        BOT_ADMIN_USER_IDS = ["99999999999999999"]

    config = MockConfigModuleForGameState()
    sys.modules['config'] = config # Заменяем модуль config этим моком в sys.modules

from game_state import GameState

# --- Мок-объекты для Discord (скопированы из test_reputation.py с небольшими изменениями) ---
# --- Копипаста моков ---
class MockUser(discord.User):
    def __init__(self, id: int, name: str, mention_override: str = None, bot_flag: bool = False):
        self.id = id
        self.name = name
        self.bot = bot_flag
        self._mention = mention_override if mention_override else f"<@{id}>"
        self.display_name = name
        self.guild = None
        self.voice = None

    @property
    def mention(self) -> str:
        return self._mention
    def __eq__(self, other):
        if isinstance(other, (MockUser, discord.User, discord.Member)): return self.id == other.id
        return False
    def __hash__(self): return hash(self.id)

class MockMember(discord.Member, MockUser):
    def __init__(self, id: int, name: str, guild_mock, mention_override: str = None, voice_state_mock = None):
        MockUser.__init__(self, id, name, mention_override)
        self.guild = guild_mock
        self.roles = [guild_mock.default_role]
        self.voice = voice_state_mock if voice_state_mock else MockVoiceState(None)
    async def move_to(self, channel, *, reason=None):
        if self.voice: self.voice.channel = channel
        # print(f"MockMember {self.name} moved to {channel.name if channel else 'None'}") # Reduced verbosity
    async def send(self, content=None, **kwargs):
        # print(f"MockMember {self.name} received DM: '{content}'") # Reduced verbosity
        return MockMessage(content=content, author=self, channel=None)

class MockVoiceState:
    def __init__(self, channel): self.channel = channel

class MockTextChannel(discord.TextChannel):
    def __init__(self, id: int, name: str, guild_mock):
        self.id = id; self.name = name; self.guild = guild_mock
        self._sent_messages = []
    async def send(self, content=None, *, embed=None, embeds=None, view=None, **kwargs) -> 'MockMessage':
        msg = MockMessage(content=content, author=self.guild.me, channel=self, embed=embed, embeds=embeds, view=view)
        self._sent_messages.append(msg)
        return msg
    async def delete_messages(self, messages):
        for msg in messages:
            if msg in self._sent_messages: self._sent_messages.remove(msg)

class MockVoiceChannel(discord.VoiceChannel):
     def __init__(self, id: int, name: str, guild_mock):
        self.id = id; self.name = name; self.guild = guild_mock; self.members = []
     def Guild(self): return self.guild

class MockMessage(discord.Message):
    def __init__(self, *, content, author, channel, embed=None, embeds=None, view=None, id_override=None):
        self.id = id_override or random.randint(1000000,9999999); self.content = content
        self.author = author; self.channel = channel; self.embeds = embeds or ([embed] if embed else [])
        self.view = view; self._deleted = False
    async def edit(self, **fields):
        if self._deleted: raise discord.NotFound(MagicMock(), "Message deleted")
        self.content = fields.get('content', self.content); self.embeds = fields.get('embeds', self.embeds)
        if 'embed' in fields: self.embeds = [fields['embed']] if fields['embed'] else []
        self.view = fields.get('view', self.view)
    async def delete(self, *, delay=None):
        if delay: await asyncio.sleep(delay)
        self._deleted = True

class MockInteractionResponse(discord.InteractionResponse):
    def __init__(self, interaction): self._interaction = interaction; self._is_done = False
    async def defer(self, *, ephemeral: bool = False) -> None:
        if self._is_done: return # print(f"Defer on responded interaction {self._interaction.id}.")
        self._is_done = True
    async def send_message(self, content=None, *, embed=None, embeds=None, view=None, ephemeral: bool = False, **kwargs) -> None:
        if self._is_done: await self._interaction.followup.send(content=content, embed=embed, embeds=embeds, view=view, ephemeral=ephemeral); return
        if self._interaction.channel: self._interaction._original_message = await self._interaction.channel.send(content=content, embed=embed, embeds=embeds, view=view)
        self._is_done = True
    def is_done(self) -> bool: return self._is_done

class MockInteractionFollowup(discord.Webhook):
    def __init__(self, interaction): self._interaction = interaction; self._sent_followups = []
    async def send(self, content=None, *, embed=None, embeds=None, view=None, ephemeral: bool = False, **kwargs) -> 'MockMessage':
        msg = MockMessage(content=content, author=self._interaction.user, channel=self._interaction.channel, embed=embed, embeds=embeds, view=view)
        if self._interaction.channel: msg = await self._interaction.channel.send(content=content, embed=embed, embeds=embeds, view=view)
        self._sent_followups.append(msg); return msg

class MockInteraction(discord.Interaction):
    def __init__(self, user_mock: MockUser, channel_mock: MockTextChannel = None, guild_mock = None, interaction_id = None):
        self.id = interaction_id or random.randint(10000000,99999999); self.user = user_mock; self.author = user_mock
        self.channel = channel_mock; self.guild = guild_mock if guild_mock else (channel_mock.guild if channel_mock else None)
        self.response = MockInteractionResponse(self); self.followup = MockInteractionFollowup(self); self._original_message = None

class MockGuild(discord.Guild):
    def __init__(self, id: int, name: str, bot_user_mock: MockUser):
        self.id = id; self.name = name; self.me = MockMember(bot_user_mock.id, bot_user_mock.name, self)
        self._channels = {}; self._members = {bot_user_mock.id: self.me}
    def add_channel(self, channel_mock): self._channels[channel_mock.id] = channel_mock; channel_mock.guild = self
    def get_channel(self, channel_id: int): return self._channels.get(channel_id)
    def add_member(self, member_mock: MockMember): self._members[member_mock.id] = member_mock; member_mock.guild = self
    def get_member(self, user_id: int) -> MockMember | None: return self._members.get(user_id)
    @property
    def default_role(self): mock_role = Mock(id=self.id, name="@everyone"); mock_role.is_default = lambda: True; return mock_role

class MockBot(commands.Bot):
    def __init__(self, user_mock: MockUser, *args, **kwargs):
        self.user = user_mock; self._guilds = {}; self.game_state = None; self.reputation_system = None
        self._activity = None; self._status = discord.Status.online
        self.intents = kwargs.get('intents', discord.Intents.default())

    def add_guild(self, guild_mock: MockGuild): self._guilds[guild_mock.id] = guild_mock; guild_mock.me = MockMember(self.user.id, self.user.name, guild_mock)
    def get_guild(self, guild_id: int) -> MockGuild | None: return self._guilds.get(guild_id)
    def get_channel(self, channel_id: int):
        for guild in self._guilds.values():
            channel = guild.get_channel(channel_id)
            if channel: return channel
        return None
    async def change_presence(self, *, activity=None, status=None, afk=False):
        self._activity = activity; self._status = status
# --- Конец копипасты моков ---

current_config = config

class TestGameState(unittest.TestCase):
    def setUp(self):
        self.bot_user_mock = MockUser(id=123456789, name="ТестБот", bot_flag=True)
        self.bot_mock = MockBot(user_mock=self.bot_user_mock, intents=discord.Intents.default())
        self.guild_mock = MockGuild(id=current_config.GUILD_ID, name="Тестовый Сервер", bot_user_mock=self.bot_user_mock)
        self.bot_mock.add_guild(self.guild_mock)
        self.game_channel_mock = MockTextChannel(id=current_config.GAME_CHANNEL_ID, name="игровой-чат", guild_mock=self.guild_mock)
        self.guild_mock.add_channel(self.game_channel_mock)
        self.voice_channel_team1_mock = MockVoiceChannel(id=current_config.VOICE_CHANNEL_ID_TEAM1, name="Команда 1 Войс", guild_mock=self.guild_mock)
        self.voice_channel_team2_mock = MockVoiceChannel(id=current_config.VOICE_CHANNEL_ID_TEAM2, name="Команда 2 Войс", guild_mock=self.guild_mock)
        self.guild_mock.add_channel(self.voice_channel_team1_mock)
        self.guild_mock.add_channel(self.voice_channel_team2_mock)
        self.game_state = GameState(self.bot_mock, current_config.GAME_CHANNEL_ID)
        self.bot_mock.game_state = self.game_state
        self.player1 = MockMember(id=1, name="Игрок1", guild_mock=self.guild_mock)
        self.player2 = MockMember(id=2, name="Игрок2", guild_mock=self.guild_mock)
        self.player3 = MockMember(id=3, name="Игрок3", guild_mock=self.guild_mock)
        self.guild_mock.add_member(self.player1)
        self.guild_mock.add_member(self.player2)
        self.guild_mock.add_member(self.player3)

    def tearDown(self):
        if self.game_state.reset_task and not self.game_state.reset_task.done():
            self.game_state.reset_task.cancel()

    def async_test_wrapper(self, coro):
        return asyncio.run(coro)

    def test_register_player_successful(self):
        async def test_logic():
            interaction_mock = MockInteraction(user_mock=self.player1, channel_mock=self.game_channel_mock, guild_mock=self.guild_mock)
            await self.game_state.set_players_per_team(1, interaction_mock)
            interaction_p1 = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            is_full, response = await self.game_state.register_player(self.player1, interaction_p1)
            self.assertIn(self.player1, self.game_state.registered_players)
            self.assertFalse(is_full)
            self.assertIn("зарегистрирован на матч", response.lower())
            self.assertEqual(len(self.game_state.registered_players), 1)
            interaction_p2 = MockInteraction(self.player2, self.game_channel_mock, self.guild_mock)
            is_full_after_p2, response_p2 = await self.game_state.register_player(self.player2, interaction_p2)
            self.assertIn(self.player2, self.game_state.registered_players)
            self.assertTrue(is_full_after_p2)
            self.assertIn("старт голосования", response_p2.lower())
            self.assertEqual(len(self.game_state.registered_players), 2)
            self.assertTrue(self.game_state.voting_active)
        self.async_test_wrapper(test_logic())

    def test_register_player_duplicate(self):
        async def test_logic():
            interaction_p1_first = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            await self.game_state.register_player(self.player1, interaction_p1_first)
            interaction_p1_second = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            is_full, response = await self.game_state.register_player(self.player1, interaction_p1_second)
            self.assertFalse(is_full)
            self.assertIn("вы уже зарегистрированы", response.lower())
            self.assertEqual(len(self.game_state.registered_players), 1)
        self.async_test_wrapper(test_logic())

    def test_register_player_teams_full(self):
        async def test_logic():
            interaction_admin = MockInteraction(MockUser(99, "Admin"), self.game_channel_mock, self.guild_mock)
            await self.game_state.set_players_per_team(1, interaction_admin)
            await self.game_state.register_player(self.player1, MockInteraction(self.player1, self.game_channel_mock, self.guild_mock))
            await self.game_state.register_player(self.player2, MockInteraction(self.player2, self.game_channel_mock, self.guild_mock))
            self.assertTrue(await self.game_state.check_ready_to_start())
            interaction_p3 = MockInteraction(self.player3, self.game_channel_mock, self.guild_mock)
            is_full, response = await self.game_state.register_player(self.player3, interaction_p3)
            self.assertFalse(is_full)
            self.assertIn("максимальное количество игроков", response.lower())
            self.assertNotIn(self.player3, self.game_state.registered_players)
            self.assertEqual(len(self.game_state.registered_players), 2)
        self.async_test_wrapper(test_logic())

    def test_register_player_during_voting(self):
        async def test_logic():
            interaction_admin = MockInteraction(MockUser(99, "Admin"), self.game_channel_mock, self.guild_mock)
            await self.game_state.set_players_per_team(1, interaction_admin)
            await self.game_state.register_player(self.player1, MockInteraction(self.player1, self.game_channel_mock, self.guild_mock))
            await self.game_state.register_player(self.player2, MockInteraction(self.player2, self.game_channel_mock, self.guild_mock))
            self.assertTrue(self.game_state.voting_active)
            interaction_p3 = MockInteraction(self.player3, self.game_channel_mock, self.guild_mock)
            _ , response = await self.game_state.register_player(self.player3, interaction_p3)
            self.assertIn("регистрация закрыта", response.lower())
            self.assertNotIn(self.player3, self.game_state.registered_players)
        self.async_test_wrapper(test_logic())

    def test_unregister_player_successful(self):
        async def test_logic():
            await self.game_state.register_player(self.player1, MockInteraction(self.player1, self.game_channel_mock, self.guild_mock))
            self.assertIn(self.player1, self.game_state.registered_players)
            response = await self.game_state.unregister_player(self.player1, MockInteraction(self.player1, self.game_channel_mock, self.guild_mock))
            self.assertNotIn(self.player1, self.game_state.registered_players)
            self.assertIn("регистрация отменена", response.lower())
            self.assertEqual(len(self.game_state.registered_players), 0)
        self.async_test_wrapper(test_logic())

    def test_unregister_player_not_registered(self):
        async def test_logic():
            response = await self.game_state.unregister_player(self.player1, MockInteraction(self.player1, self.game_channel_mock, self.guild_mock))
            self.assertIn("вы не были зарегистрированы", response.lower())
        self.async_test_wrapper(test_logic())

    def test_unregister_player_during_voting(self):
        async def test_logic():
            interaction_admin = MockInteraction(MockUser(99, "Admin"), self.game_channel_mock, self.guild_mock)
            await self.game_state.set_players_per_team(1, interaction_admin)
            await self.game_state.register_player(self.player1, MockInteraction(self.player1, self.game_channel_mock, self.guild_mock))
            await self.game_state.register_player(self.player2, MockInteraction(self.player2, self.game_channel_mock, self.guild_mock))
            self.assertTrue(self.game_state.voting_active)
            response = await self.game_state.unregister_player(self.player1, MockInteraction(self.player1, self.game_channel_mock, self.guild_mock))
            self.assertIn("отмена регистрации невозможна", response.lower())
            self.assertIn(self.player1, self.game_state.registered_players)
        self.async_test_wrapper(test_logic())

    def test_set_players_per_team_valid(self):
        async def test_logic():
            interaction = MockInteraction(MockUser(99, "Admin"), self.game_channel_mock, self.guild_mock)
            success, response = await self.game_state.set_players_per_team(3, interaction)
            self.assertTrue(success)
            self.assertEqual(self.game_state.players_per_team, 3)
            self.assertIn("количество игроков в команде установлено в 3", response.lower())
        self.async_test_wrapper(test_logic())

    def test_set_players_per_team_invalid_too_low_or_high(self):
        async def test_logic():
            interaction = MockInteraction(MockUser(99, "Admin"), self.game_channel_mock, self.guild_mock)
            initial_ppt = self.game_state.players_per_team
            success, response = await self.game_state.set_players_per_team(0, interaction)
            self.assertFalse(success)
            self.assertIn("должно быть от 1 до", response.lower())
            self.assertEqual(self.game_state.players_per_team, initial_ppt)
            success, response = await self.game_state.set_players_per_team(current_config.MAX_PLAYERS_PER_TEAM + 1, interaction)
            self.assertFalse(success)
            self.assertIn(f"от 1 до {current_config.MAX_PLAYERS_PER_TEAM}", response.lower())
            self.assertEqual(self.game_state.players_per_team, initial_ppt)
        self.async_test_wrapper(test_logic())

    def test_set_players_per_team_while_voting_active(self):
        async def test_logic():
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

    def test_auto_split_teams_even_players(self):
        async def test_logic():
            admin_interaction = MockInteraction(MockUser(99, "Admin"), self.game_channel_mock, self.guild_mock)
            await self.game_state.set_players_per_team(2, admin_interaction)
            players_list = [self.player1, self.player2, MockMember(3, "P3", self.guild_mock), MockMember(4, "P4", self.guild_mock)]
            for p_obj in players_list:
                 if not self.guild_mock.get_member(p_obj.id): self.guild_mock.add_member(p_obj)
                 await self.game_state.register_player(p_obj, MockInteraction(p_obj, self.game_channel_mock, self.guild_mock))
            team1, team2 = await self.game_state.auto_split_teams(shuffle=False)
            self.assertEqual(len(team1), 2); self.assertEqual(len(team2), 2)
            self.assertListEqual(team1, [players_list[0], players_list[1]])
            self.assertListEqual(team2, [players_list[2], players_list[3]])
        self.async_test_wrapper(test_logic())

    def test_auto_split_teams_odd_players(self):
        async def test_logic():
            self.game_state.registered_players = [self.player1, self.player2, self.player3]
            team1, team2 = await self.game_state.auto_split_teams(shuffle=False)
            self.assertTrue((len(team1) == 2 and len(team2) == 1) or (len(team1) == 1 and len(team2) == 2))
        self.async_test_wrapper(test_logic())

    def test_auto_split_teams_shuffle(self):
        async def test_logic():
            players_list = [self.player1, self.player2, MockMember(3,"P3",self.guild_mock), MockMember(4,"P4",self.guild_mock)]
            for p_obj in players_list:
                if not self.guild_mock.get_member(p_obj.id): self.guild_mock.add_member(p_obj)
            self.game_state.registered_players = list(players_list)
            with patch.object(random, 'shuffle') as mock_shuffle:
                team1, team2 = await self.game_state.auto_split_teams(shuffle=True)
                mock_shuffle.assert_called_once_with(self.game_state.registered_players)
            self.assertEqual(len(team1) + len(team2), len(players_list))
            self.assertTrue(abs(len(team1) - len(team2)) <= 1)
        self.async_test_wrapper(test_logic())

    def test_auto_split_teams_insufficient_players(self):
        async def test_logic():
            self.game_state.registered_players = [self.player1]
            team1, team2 = await self.game_state.auto_split_teams()
            self.assertEqual(len(team1), 0); self.assertEqual(len(team2), 0)
            self.game_state.registered_players = []
            team1, team2 = await self.game_state.auto_split_teams()
            self.assertEqual(len(team1), 0); self.assertEqual(len(team2), 0)
        self.async_test_wrapper(test_logic())

    @patch('game_state.GameState.update_bot_status', new_callable=AsyncMock)
    def test_clear_registered_players(self, mock_update_status):
        async def test_logic():
            admin_interaction = MockInteraction(MockUser(99, "Admin"), self.game_channel_mock, self.guild_mock)
            await self.game_state.set_players_per_team(1, admin_interaction)
            await self.game_state.register_player(self.player1, MockInteraction(self.player1, self.game_channel_mock, self.guild_mock))
            await self.game_state.register_player(self.player2, MockInteraction(self.player2, self.game_channel_mock, self.guild_mock))
            mock_voting_msg = AsyncMock(spec=discord.Message); mock_voting_msg.delete = AsyncMock()
            self.game_state.voting_message = mock_voting_msg
            self.assertTrue(self.game_state.voting_active)
            response = await self.game_state.clear_registered_players()
            self.assertEqual(len(self.game_state.registered_players), 0)
            self.assertFalse(self.game_state.voting_active)
            self.assertEqual(self.game_state.votes, {"agree": 0, "reshuffle": 0})
            mock_update_status.assert_called_once()
            self.assertIn("список зарегистрированных игроков очищен", response.lower())
            if self.game_state.voting_message: mock_voting_msg.delete.assert_called_once()
            self.assertIsNone(self.game_state.voting_message)
        self.async_test_wrapper(test_logic())

    @patch('game_state.GameState._update_voting_message', new_callable=AsyncMock)
    @patch('game_state.GameState.evaluate_votes', new_callable=AsyncMock)
    async def run_process_vote_test(self, players_for_vote, vote_type, expected_votes,
                                    should_evaluate_be_called, mock_eval_votes, mock_update_msg):
        test_config = {"VOTE_THRESHOLD": 0.5}
        if len(players_for_vote) == 2 and expected_votes.get(vote_type) == 1 and should_evaluate_be_called:
            test_config["VOTE_THRESHOLD"] = 0.1
        with patch.dict(sys.modules['config'].__dict__, test_config, clear=True):
            self.game_state.registered_players = list(players_for_vote)
            self.game_state.voting_active = True
            self.game_state.votes = {"agree": 0, "reshuffle": 0}
            voter = players_for_vote[0] if players_for_vote else self.player1
            vote_interaction = MockInteraction(voter, self.game_channel_mock, self.guild_mock)
            await self.game_state.process_vote(voter, vote_type, vote_interaction)
        self.assertEqual(self.game_state.votes, expected_votes)
        if should_evaluate_be_called:
            mock_eval_votes.assert_called_once()
            mock_update_msg.assert_not_called()
        else:
            mock_eval_votes.assert_not_called()
            if players_for_vote : mock_update_msg.assert_called_once()

    def test_process_vote_agree_reaches_threshold(self):
        asyncio.run(self.run_process_vote_test(
            players_for_vote=[self.player1, self.player2], vote_type="agree",
            expected_votes={"agree": 1, "reshuffle": 0}, should_evaluate_be_called=True))

    def test_process_vote_reshuffle_reaches_threshold(self):
        asyncio.run(self.run_process_vote_test(
            players_for_vote=[self.player1, self.player2], vote_type="reshuffle",
            expected_votes={"agree": 0, "reshuffle": 1}, should_evaluate_be_called=True))

    def test_process_vote_not_reaches_threshold(self):
        players = [self.player1, self.player2, self.player3, MockMember(4,"P4",self.guild_mock)]
        for p_obj in players:
            if not self.guild_mock.get_member(p_obj.id): self.guild_mock.add_member(p_obj)
        asyncio.run(self.run_process_vote_test(
            players_for_vote=players, vote_type="agree",
            expected_votes={"agree": 1, "reshuffle": 0}, should_evaluate_be_called=False ))

    def test_process_vote_user_not_registered(self):
        async def test_logic():
            self.game_state.registered_players = [self.player1]; self.game_state.voting_active = True
            vote_interaction = MockInteraction(self.player2, self.game_channel_mock, self.guild_mock)
            vote_interaction.followup.send = AsyncMock()
            await self.game_state.process_vote(self.player2, "agree", vote_interaction)
            self.assertEqual(self.game_state.votes["agree"], 0)
            vote_interaction.followup.send.assert_called_once()
            args, _ = vote_interaction.followup.send.call_args
            self.assertIn("не зарегистрированы", str(args[0]).lower())
        self.async_test_wrapper(test_logic())

    def test_process_vote_voting_not_active(self):
        async def test_logic():
            self.game_state.registered_players = [self.player1]; self.game_state.voting_active = False
            vote_interaction = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            vote_interaction.followup.send = AsyncMock()
            await self.game_state.process_vote(self.player1, "agree", vote_interaction)
            self.assertEqual(self.game_state.votes["agree"], 0)
            vote_interaction.followup.send.assert_called_once()
            args, _ = vote_interaction.followup.send.call_args
            self.assertTrue("неактивно" in str(args[0]).lower() or "завершено" in str(args[0]).lower())
        self.async_test_wrapper(test_logic())

    @patch('game_state.GameState.finalize_teams', new_callable=AsyncMock)
    @patch('game_state.GameState.reshuffle_and_revote', new_callable=AsyncMock)
    @patch('game_state.GameState._send_channel_message', new_callable=AsyncMock)
    async def run_evaluate_votes_test_logic(self, registered_players_count, agree_votes, reshuffle_votes,
                                      force_end_vote, expected_finalize_calls, expected_reshuffle_calls,
                                      mock_send_msg, mock_reshuffle, mock_finalize):
        self.game_state.registered_players = [MockMember(i, f"P{i}", self.guild_mock) for i in range(1, registered_players_count + 1)]
        for p_obj in self.game_state.registered_players:
            if not self.guild_mock.get_member(p_obj.id): self.guild_mock.add_member(p_obj)
        self.game_state.votes = {"agree": agree_votes, "reshuffle": reshuffle_votes}
        self.game_state.voting_active = True
        mock_voting_msg = AsyncMock(spec=discord.Message); mock_voting_msg.delete = AsyncMock()
        self.game_state.voting_message = mock_voting_msg
        mock_interaction = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
        with patch.object(config, 'VOTE_THRESHOLD', 0.5):
            await self.game_state.evaluate_votes(interaction=mock_interaction, force_end_vote=force_end_vote)
        self.assertFalse(self.game_state.voting_active)
        if mock_voting_msg: mock_voting_msg.delete.assert_called_once()
        self.assertIsNone(self.game_state.voting_message)
        self.assertEqual(mock_finalize.call_count, expected_finalize_calls)
        self.assertEqual(mock_reshuffle.call_count, expected_reshuffle_calls)

    def test_evaluate_votes_agree_wins(self): asyncio.run(self.run_evaluate_votes_test_logic(4,2,1,False,1,0))
    def test_evaluate_votes_reshuffle_wins(self): asyncio.run(self.run_evaluate_votes_test_logic(4,1,2,False,0,1))
    def test_evaluate_votes_force_end_agree_wins_due_to_force(self): asyncio.run(self.run_evaluate_votes_test_logic(10,3,2,True,1,0))
    def test_evaluate_votes_force_end_reshuffle_still_wins_if_already_met_threshold(self): asyncio.run(self.run_evaluate_votes_test_logic(10,1,6,True,0,1))
    def test_evaluate_votes_no_clear_winner_not_forced_defaults_to_finalize(self): asyncio.run(self.run_evaluate_votes_test_logic(10,2,1,False,1,0))

    def test_evaluate_votes_no_registered_players(self):
        async def test_logic():
            self.game_state.registered_players = []
            self.game_state.voting_active = True
            mock_interaction = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
            self.game_state.finalize_teams = AsyncMock()
            self.game_state.reshuffle_and_revote = AsyncMock()
            self.game_state.update_bot_status = AsyncMock()
            await self.game_state.evaluate_votes(interaction=mock_interaction, force_end_vote=False)
            self.assertFalse(self.game_state.voting_active)
            self.game_state.finalize_teams.assert_not_called()
            self.game_state.reshuffle_and_revote.assert_not_called()
            self.game_state.update_bot_status.assert_called_once()
        self.async_test_wrapper(test_logic())

    @patch('asyncio.create_task')
    @patch('game_state.GameState.update_bot_status', new_callable=AsyncMock)
    def test_start_voting(self, mock_update_status, mock_create_task):
        async def test_logic():
            self.game_state.voting_active = False; self.game_state.votes = {"agree":1,"reshuffle":1}
            mock_interaction = MockInteraction(self.player1,self.game_channel_mock,self.guild_mock)
            await self.game_state.start_voting(mock_interaction)
            self.assertTrue(self.game_state.voting_active)
            self.assertEqual(self.game_state.votes, {"agree":0,"reshuffle":0})
            mock_update_status.assert_called_once()
            mock_create_task.assert_called_once()
        self.async_test_wrapper(test_logic())

    @patch('asyncio.sleep', new_callable=AsyncMock)
    @patch('game_state.GameState.evaluate_votes', new_callable=AsyncMock)
    def test_voting_timer_ends_voting_when_active(self, mock_evaluate_votes, mock_sleep):
        async def test_logic():
            self.game_state.voting_active = True
            mock_interaction = MockInteraction(self.player1,self.game_channel_mock,self.guild_mock)
            await self.game_state.voting_timer(self.guild_mock.id,self.game_channel_mock.id,mock_interaction)
            mock_sleep.assert_called_once_with(current_config.VOTING_DURATION)
            mock_evaluate_votes.assert_called_once_with(interaction=mock_interaction,force_end_vote=True)
        self.async_test_wrapper(test_logic())

    @patch('asyncio.sleep', new_callable=AsyncMock)
    @patch('game_state.GameState.evaluate_votes', new_callable=AsyncMock)
    def test_voting_timer_does_nothing_if_not_active(self, mock_evaluate_votes, mock_sleep):
        async def test_logic():
            self.game_state.voting_active = False
            mock_interaction = MockInteraction(self.player1,self.game_channel_mock,self.guild_mock)
            await self.game_state.voting_timer(self.guild_mock.id,self.game_channel_mock.id,mock_interaction)
            mock_sleep.assert_called_once_with(current_config.VOTING_DURATION)
            mock_evaluate_votes.assert_not_called()
        self.async_test_wrapper(test_logic())

    @patch('asyncio.create_task')
    def test_start_reset_timer_creates_task_and_cancels_existing(self, mock_create_task):
        async def test_logic():
            mock_task1 = AsyncMock(spec=asyncio.Task); mock_task1.cancel = MagicMock()
            self.game_state.reset_task = mock_task1
            await self.game_state.start_reset_timer()
            mock_task1.cancel.assert_called_once()
            mock_create_task.assert_called_once()
            self.assertEqual(self.game_state.reset_task, mock_create_task.return_value)
        self.async_test_wrapper(test_logic())

    @patch('asyncio.sleep', new_callable=AsyncMock)
    @patch('game_state.GameState.clear_registered_players', new_callable=AsyncMock)
    def test_reset_game_state_after_delay(self, mock_clear_players, mock_sleep):
        async def test_logic():
            await self.game_state.reset_game_state_after_delay()
            mock_sleep.assert_called_once_with(current_config.RESET_DELAY)
            mock_clear_players.assert_called_once()
        self.async_test_wrapper(test_logic())

    @patch('game_state.GameState.auto_split_teams', new_callable=AsyncMock)
    @patch('game_state.GameState.move_players_to_voice_channels', new_callable=AsyncMock)
    @patch('game_state.GameState.display_voice_channel_links', new_callable=AsyncMock)
    @patch('game_state.GameState.update_bot_status', new_callable=AsyncMock)
    @patch('game_state.GameState.reset_votes', new_callable=AsyncMock)
    @patch('game_state.GameState._send_channel_message', new_callable=AsyncMock)
    async def run_finalize_teams_test_logic(self, mock_send_msg, mock_reset_votes, mock_update_status,
                                      mock_display_links, mock_move_players, mock_auto_split):
        self.game_state.registered_players = [self.player1, self.player2]
        for p_obj in self.game_state.registered_players:
            if not self.guild_mock.get_member(p_obj.id): self.guild_mock.add_member(p_obj)
        self.game_state.voting_active = True
        mock_auto_split.return_value = ([self.player1], [self.player2])
        await self.game_state.finalize_teams()
        self.assertFalse(self.game_state.voting_active)
        mock_auto_split.assert_called_once_with(shuffle=False)
        mock_send_msg.assert_called()
        mock_move_players.assert_called_once_with([self.player1], [self.player2])
        mock_display_links.assert_called_once()
        mock_update_status.assert_called_once()
        mock_reset_votes.assert_called_once()

    def test_finalize_teams_calls_all_helpers(self):
        asyncio.run(self.run_finalize_teams_test_logic())

    @patch('game_state.GameState.reset_votes', new_callable=AsyncMock)
    @patch('game_state.GameState.display_teams_general', new_callable=AsyncMock)
    @patch('game_state.GameState.start_voting', new_callable=AsyncMock)
    @patch('game_state.GameState.update_bot_status', new_callable=AsyncMock)
    async def run_reshuffle_and_revote_test_logic(self, mock_update_status, mock_start_voting,
                                           mock_display_teams, mock_reset_votes):
        mock_interaction = MockInteraction(self.player1, self.game_channel_mock, self.guild_mock)
        self.game_state.voting_active = False
        await self.game_state.reshuffle_and_revote(mock_interaction)
        mock_reset_votes.assert_called_once()
        self.assertTrue(self.game_state.voting_active)
        mock_display_teams.assert_called_once_with(interaction=mock_interaction, shuffle=True, display_voting_buttons=True)
        mock_start_voting.assert_called_once_with(mock_interaction)
        mock_update_status.assert_called_once()

    def test_reshuffle_and_revote_calls_all_helpers(self):
        asyncio.run(self.run_reshuffle_and_revote_test_logic())

if __name__ == '__main__':
    unittest.main()
[end of tests/test_game_state.py]

[end of tests/test_game_state.py]
