from game.logic.enums import GamePhase, RoundPhase, WindName
from game.logic.types import GameView, PlayerView
from game.session.manager import SessionManager
from game.session.models import Game, Player
from game.tests.mocks import MockConnection


def make_dummy_game_view() -> GameView:
    """Create a minimal GameView for testing."""
    return GameView(
        seat=0,
        round_wind=WindName.EAST,
        round_number=1,
        dealer_seat=0,
        current_player_seat=0,
        wall_count=70,
        dora_indicators=[],
        honba_sticks=0,
        riichi_sticks=0,
        players=[
            PlayerView(
                seat=0,
                name="Alice",
                is_bot=False,
                score=25000,
                is_riichi=False,
                discards=[],
                melds=[],
                tile_count=13,
            ),
        ],
        phase=RoundPhase.PLAYING,
        game_phase=GamePhase.IN_PROGRESS,
    )


def make_game_with_human(manager: SessionManager) -> tuple[Game, Player, MockConnection]:
    """Create a game with a human player who has an assigned seat."""
    conn = MockConnection()
    game = Game(game_id="game1")
    player = Player(connection=conn, name="Alice", game_id="game1", seat=0)
    game.players[conn.connection_id] = player
    manager._games["game1"] = game  # noqa: SLF001
    manager._players[conn.connection_id] = player  # noqa: SLF001
    manager._connections[conn.connection_id] = conn  # noqa: SLF001
    return game, player, conn
