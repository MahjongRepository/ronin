import pytest
from mahjong.tile import TilesConverter
from pydantic import ValidationError

from game.logic.mock import MockGameService
from game.messaging.encoder import decode, encode
from game.messaging.mock import MockConnection
from game.messaging.router import MessageRouter
from game.messaging.types import (
    AvailableAction,
    CallPromptMessage,
    ClientMessageType,
    DiscardInfo,
    DiscardMessage,
    DrawMessage,
    GameEndMessage,
    GameStartedMessage,
    MeldInfo,
    MeldMessage,
    PlayerInfo,
    RiichiMessage,
    RoundEndMessage,
    ServerMessageType,
    TileInfo,
    TurnMessage,
    YakuInfo,
    parse_client_message,
)
from game.session.manager import SessionManager


class TestParseClientMessage:
    def test_parse_join_game(self):
        data = {"type": "join_game", "game_id": "game1", "player_name": "Alice"}
        msg = parse_client_message(data)
        assert msg.type == ClientMessageType.JOIN_GAME
        assert msg.game_id == "game1"
        assert msg.player_name == "Alice"

    def test_parse_chat(self):
        data = {"type": "chat", "text": "Hello!"}
        msg = parse_client_message(data)
        assert msg.type == ClientMessageType.CHAT
        assert msg.text == "Hello!"

    def test_parse_invalid_type(self):
        data = {"type": "invalid_type"}
        with pytest.raises(ValidationError):
            parse_client_message(data)


class TestMessageRouter:
    @pytest.fixture
    async def setup(self):
        game_service = MockGameService()
        session_manager = SessionManager(game_service)
        router = MessageRouter(session_manager)
        connection = MockConnection()
        await router.handle_connect(connection)
        return router, connection, session_manager

    async def test_join_game(self, setup):
        router, connection, session_manager = setup
        session_manager.create_game("game1")

        await router.handle_message(
            connection,
            {
                "type": "join_game",
                "game_id": "game1",
                "player_name": "Alice",
            },
        )

        # check the response: game_joined + game_started event
        assert len(connection.sent_messages) == 2
        response = connection.sent_messages[0]
        assert response["type"] == ServerMessageType.GAME_JOINED
        assert response["game_id"] == "game1"
        assert response["players"] == ["Alice"]
        # second message is game_started from start_game
        game_event = connection.sent_messages[1]
        assert game_event["type"] == ServerMessageType.GAME_EVENT
        assert game_event["event"] == "game_started"

    async def test_invalid_message_returns_error(self, setup):
        router, connection, _ = setup

        await router.handle_message(connection, {"type": "bogus"})

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == ServerMessageType.ERROR
        assert response["code"] == "invalid_message"

    async def test_chat_requires_game(self, setup):
        router, connection, _ = setup

        await router.handle_message(
            connection,
            {
                "type": "chat",
                "text": "Hello!",
            },
        )

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == ServerMessageType.ERROR
        assert response["code"] == "not_in_game"

    async def test_leave_game_message(self, setup):
        """Leave game message calls session_manager.leave_game."""
        router, connection, session_manager = setup
        session_manager.create_game("game1")
        await router.handle_message(
            connection,
            {"type": "join_game", "game_id": "game1", "player_name": "Alice"},
        )
        connection._outbox.clear()

        await router.handle_message(connection, {"type": "leave_game"})

        # player should have received game_left
        assert any(m.get("type") == ServerMessageType.GAME_LEFT for m in connection.sent_messages)

    async def test_game_action_routes_to_session_manager(self, setup):
        """Game action message routes through session manager and returns events."""
        router, connection, session_manager = setup
        session_manager.create_game("game1")
        await router.handle_message(
            connection,
            {"type": "join_game", "game_id": "game1", "player_name": "Alice"},
        )
        connection._outbox.clear()

        await router.handle_message(
            connection,
            {
                "type": "game_action",
                "action": "discard",
                "data": {"tile_id": TilesConverter.string_to_136_array(man="1")[0]},
            },
        )

        # mock service returns events, so we get game_event messages
        assert len(connection.sent_messages) >= 1

    async def test_game_action_error_returns_action_failed(self, setup):
        """Game action that raises error returns action_failed error."""
        router, connection, session_manager = setup
        session_manager.create_game("game1")
        await router.handle_message(
            connection,
            {"type": "join_game", "game_id": "game1", "player_name": "Alice"},
        )
        connection._outbox.clear()

        # patch handle_game_action to raise ValueError
        async def raise_value_error(
            connection: object,  # noqa: ARG001
            action: object,  # noqa: ARG001
            data: object,  # noqa: ARG001
        ) -> None:
            raise ValueError("invalid tile")

        session_manager.handle_game_action = raise_value_error

        await router.handle_message(
            connection,
            {
                "type": "game_action",
                "action": "discard",
                "data": {"tile_id": TilesConverter.string_to_136_array(man="1")[0]},
            },
        )

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == ServerMessageType.ERROR
        assert response["code"] == "action_failed"
        assert response["message"] == "invalid tile"


class TestMahjongMessageTypes:
    def test_tile_info(self):
        tile = TileInfo(tile="1m", tile_id=TilesConverter.string_to_136_array(man="1")[0])
        assert tile.tile == "1m"
        assert tile.tile_id == TilesConverter.string_to_136_array(man="1")[0]

    def test_discard_info(self):
        discard = DiscardInfo(
            tile="5p",
            tile_id=TilesConverter.string_to_136_array(pin="5")[0],
            is_tsumogiri=True,
            is_riichi_discard=False,
        )
        assert discard.tile == "5p"
        assert discard.tile_id == TilesConverter.string_to_136_array(pin="5")[0]
        assert discard.is_tsumogiri is True
        assert discard.is_riichi_discard is False

    def test_discard_info_defaults(self):
        discard = DiscardInfo(tile="E", tile_id=TilesConverter.string_to_136_array(honors="1")[0])
        assert discard.is_tsumogiri is False
        assert discard.is_riichi_discard is False

    def test_meld_info(self):
        meld = MeldInfo(
            type="pon",
            tiles=["5m", "5m", "5m"],
            tile_ids=TilesConverter.string_to_136_array(man="555")[:3],
            opened=True,
            from_who=2,
        )
        assert meld.type == "pon"
        assert meld.tiles == ["5m", "5m", "5m"]
        assert meld.tile_ids == TilesConverter.string_to_136_array(man="555")[:3]
        assert meld.opened is True
        assert meld.from_who == 2

    def test_player_info_minimal(self):
        player = PlayerInfo(
            seat=0,
            name="Alice",
            is_bot=False,
            score=25000,
            is_riichi=False,
            discards=[],
            melds=[],
            tile_count=13,
        )
        assert player.seat == 0
        assert player.name == "Alice"
        assert player.is_bot is False
        assert player.score == 25000
        assert player.tiles is None
        assert player.hand is None

    def test_player_info_with_hand(self):
        tiles = TilesConverter.string_to_136_array(man="111122223334")
        player = PlayerInfo(
            seat=0,
            name="Alice",
            is_bot=False,
            score=25000,
            is_riichi=True,
            discards=[],
            melds=[],
            tile_count=13,
            tiles=tiles,
            hand="1m 1m 1m 2m 2m",
        )
        assert player.tiles == tiles
        assert player.hand == "1m 1m 1m 2m 2m"

    def test_available_action(self):
        action = AvailableAction(action="discard", tiles=TilesConverter.string_to_136_array(man="123"))
        assert action.action == "discard"
        assert action.tiles == TilesConverter.string_to_136_array(man="123")

    def test_available_action_no_tiles(self):
        action = AvailableAction(action="tsumo")
        assert action.action == "tsumo"
        assert action.tiles is None

    def test_game_started_message(self):
        player = PlayerInfo(
            seat=0,
            name="Alice",
            is_bot=False,
            score=25000,
            is_riichi=False,
            discards=[],
            melds=[],
            tile_count=13,
        )
        msg = GameStartedMessage(
            seat=0,
            round_wind="East",
            round_number=0,
            dealer_seat=0,
            wall_count=70,
            dora_indicators=[TileInfo(tile="3p", tile_id=TilesConverter.string_to_136_array(pin="3")[0])],
            honba_sticks=0,
            riichi_sticks=0,
            players=[player],
        )
        assert msg.type == ServerMessageType.GAME_STARTED
        assert msg.seat == 0
        assert msg.round_wind == "East"
        assert msg.dealer_seat == 0
        assert msg.wall_count == 70
        assert len(msg.dora_indicators) == 1
        assert msg.dora_indicators[0].tile == "3p"

    def test_draw_message(self):
        msg = DrawMessage(tile="7s", tile_id=TilesConverter.string_to_136_array(sou="7")[0])
        assert msg.type == ServerMessageType.DRAW
        assert msg.tile == "7s"
        assert msg.tile_id == TilesConverter.string_to_136_array(sou="7")[0]

    def test_discard_message(self):
        msg = DiscardMessage(
            seat=1,
            tile="9m",
            tile_id=TilesConverter.string_to_136_array(man="9")[0],
            is_tsumogiri=False,
            is_riichi=True,
        )
        assert msg.type == ServerMessageType.DISCARD
        assert msg.seat == 1
        assert msg.tile == "9m"
        assert msg.tile_id == TilesConverter.string_to_136_array(man="9")[0]
        assert msg.is_tsumogiri is False
        assert msg.is_riichi is True

    def test_meld_message(self):
        msg = MeldMessage(
            caller_seat=2,
            meld_type="chi",
            tiles=["1m", "2m", "3m"],
            tile_ids=TilesConverter.string_to_136_array(man="123"),
            from_seat=1,
        )
        assert msg.type == ServerMessageType.MELD
        assert msg.caller_seat == 2
        assert msg.meld_type == "chi"
        assert msg.tiles == ["1m", "2m", "3m"]
        assert msg.from_seat == 1

    def test_riichi_message(self):
        msg = RiichiMessage(seat=3)
        assert msg.type == ServerMessageType.RIICHI
        assert msg.seat == 3

    def test_turn_message(self):
        msg = TurnMessage(
            current_seat=0,
            available_actions=[
                AvailableAction(action="discard", tiles=TilesConverter.string_to_136_array(man="123")),
                AvailableAction(action="riichi"),
            ],
        )
        assert msg.type == ServerMessageType.TURN
        assert msg.current_seat == 0
        assert len(msg.available_actions) == 2
        assert msg.available_actions[0].action == "discard"
        assert msg.available_actions[1].action == "riichi"

    def test_call_prompt_message(self):
        msg = CallPromptMessage(
            available_calls=[
                AvailableAction(action="pon", tiles=TilesConverter.string_to_136_array(man="55")[:2]),
                AvailableAction(action="pass"),
            ],
            timeout_seconds=5,
        )
        assert msg.type == ServerMessageType.CALL_PROMPT
        assert len(msg.available_calls) == 2
        assert msg.available_calls[0].action == "pon"
        assert msg.timeout_seconds == 5

    def test_call_prompt_message_default_timeout(self):
        msg = CallPromptMessage(available_calls=[AvailableAction(action="pass")])
        assert msg.timeout_seconds == 10

    def test_yaku_info(self):
        yaku = YakuInfo(name="Riichi", han=1)
        assert yaku.name == "Riichi"
        assert yaku.han == 1

    def test_round_end_message_tsumo(self):
        msg = RoundEndMessage(
            result_type="tsumo",
            winner_seats=[0],
            winning_hand="1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 1p 2p 2p",
            yaku=[YakuInfo(name="Riichi", han=1), YakuInfo(name="Tsumo", han=1)],
            han=2,
            fu=30,
            score_changes={0: 3900, 1: -1300, 2: -1300, 3: -1300},
            final_scores={0: 28900, 1: 23700, 2: 23700, 3: 23700},
        )
        assert msg.type == ServerMessageType.ROUND_END
        assert msg.result_type == "tsumo"
        assert msg.winner_seats == [0]
        assert msg.loser_seat is None
        assert msg.han == 2
        assert msg.fu == 30
        assert len(msg.yaku) == 2

    def test_round_end_message_ron(self):
        msg = RoundEndMessage(
            result_type="ron",
            winner_seats=[2],
            loser_seat=1,
            winning_hand="1m 1m 1m 2m 2m 2m 3m 3m 3m 4m 4m 5m 5m",
            yaku=[YakuInfo(name="Toitoi", han=2)],
            han=2,
            fu=40,
            score_changes={2: 2600, 1: -2600},
            final_scores={0: 25000, 1: 22400, 2: 27600, 3: 25000},
        )
        assert msg.result_type == "ron"
        assert msg.loser_seat == 1

    def test_round_end_message_draw(self):
        msg = RoundEndMessage(
            result_type="draw",
            score_changes={0: 1500, 1: 1500, 2: -1500, 3: -1500},
            final_scores={0: 26500, 1: 26500, 2: 23500, 3: 23500},
        )
        assert msg.result_type == "draw"
        assert msg.winner_seats == []
        assert msg.yaku == []
        assert msg.han is None

    def test_round_end_message_abortive(self):
        msg = RoundEndMessage(
            result_type="abortive",
            final_scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
        )
        assert msg.result_type == "abortive"
        assert msg.score_changes == {}

    def test_game_end_message(self):
        msg = GameEndMessage(
            final_scores={0: 35000, 1: 28000, 2: 22000, 3: 15000},
            winner_seat=0,
            placements=[0, 1, 2, 3],
        )
        assert msg.type == ServerMessageType.GAME_END
        assert msg.final_scores[0] == 35000
        assert msg.winner_seat == 0
        assert msg.placements == [0, 1, 2, 3]

    def test_game_started_message_serialization(self):
        player = PlayerInfo(
            seat=0,
            name="Alice",
            is_bot=False,
            score=25000,
            is_riichi=False,
            discards=[],
            melds=[],
            tile_count=13,
        )
        msg = GameStartedMessage(
            seat=0,
            round_wind="East",
            round_number=0,
            dealer_seat=0,
            wall_count=70,
            dora_indicators=[TileInfo(tile="3p", tile_id=TilesConverter.string_to_136_array(pin="3")[0])],
            honba_sticks=0,
            riichi_sticks=0,
            players=[player],
        )
        data = msg.model_dump()
        assert data["type"] == "game_started"
        assert data["seat"] == 0
        assert data["round_wind"] == "East"

    def test_round_end_message_serialization(self):
        msg = RoundEndMessage(
            result_type="tsumo",
            winner_seats=[0],
            han=3,
            fu=30,
            score_changes={0: 5800, 1: -2000, 2: -2000, 3: -1800},
            final_scores={0: 30800, 1: 23000, 2: 23000, 3: 23200},
        )
        data = msg.model_dump()
        assert data["type"] == "round_end"
        assert data["result_type"] == "tsumo"
        assert data["score_changes"][0] == 5800


class TestMockConnectionProtocol:
    async def test_send_message_encodes_to_msgpack(self):
        connection = MockConnection()
        message = {"type": "test", "value": 42}

        await connection.send_message(message)

        assert len(connection.sent_messages) == 1
        assert connection.sent_messages[0] == message

    async def test_receive_message_decodes_from_msgpack(self):
        connection = MockConnection()
        message = {"type": "test", "value": 42}
        await connection.simulate_receive(message)

        received = await connection.receive_message()

        assert received == message

    async def test_send_bytes_stores_decoded_message(self):
        connection = MockConnection()
        message = {"type": "test", "data": [1, 2, 3]}
        encoded = encode(message)

        await connection.send_bytes(encoded)

        assert connection.sent_messages[0] == message

    async def test_receive_bytes_returns_encoded_data(self):
        connection = MockConnection()
        message = {"type": "test", "nested": {"key": "value"}}
        await connection.simulate_receive(message)

        raw_bytes = await connection.receive_bytes()

        assert decode(raw_bytes) == message

    async def test_closed_connection_raises_on_send(self):
        connection = MockConnection()
        await connection.close()

        with pytest.raises(RuntimeError, match="Connection is closed"):
            await connection.send_message({"type": "test"})

    async def test_closed_connection_raises_on_receive(self):
        connection = MockConnection()
        await connection.close()

        with pytest.raises(RuntimeError, match="Connection is closed"):
            await connection.receive_message()

    def test_is_closed_property_default_false(self):
        """MockConnection starts as not closed."""
        connection = MockConnection()

        assert connection.is_closed is False

    async def test_is_closed_property_true_after_close(self):
        """MockConnection is_closed returns True after close."""
        connection = MockConnection()
        await connection.close()

        assert connection.is_closed is True

    async def test_simulate_receive_nowait(self):
        """simulate_receive_nowait queues message without awaiting."""
        connection = MockConnection()
        connection.simulate_receive_nowait({"type": "test", "value": 42})

        received = await connection.receive_message()

        assert received == {"type": "test", "value": 42}


class TestMockGameServiceGetPlayerSeat:
    def test_get_player_seat_unknown_game_returns_none(self):
        """Return None when game_id is not found."""
        service = MockGameService()

        result = service.get_player_seat("nonexistent_game", "Alice")

        assert result is None
