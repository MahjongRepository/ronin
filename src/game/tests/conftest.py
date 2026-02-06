from typing import TYPE_CHECKING, Any

import pytest

from game.logic.enums import RoundPhase
from game.logic.meld_wrapper import FrozenMeld
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
)
from game.messaging.router import MessageRouter
from game.server.app import create_app
from game.session.manager import SessionManager
from game.tests.mocks import MockConnection, MockGameService

if TYPE_CHECKING:
    from collections.abc import Sequence


# ============================================================================
# Test State Builder Helpers
# ============================================================================


def create_player(  # noqa: PLR0913
    seat: int = 0,
    name: str | None = None,
    *,
    tiles: Sequence[int] | None = None,
    discards: Sequence[Discard] | None = None,
    melds: Sequence[FrozenMeld] | None = None,
    is_riichi: bool = False,
    is_ippatsu: bool = False,
    is_daburi: bool = False,
    is_rinshan: bool = False,
    kuikae_tiles: Sequence[int] | None = None,
    pao_seat: int | None = None,
    is_temporary_furiten: bool = False,
    is_riichi_furiten: bool = False,
    score: int = 25000,
) -> MahjongPlayer:
    """Create a MahjongPlayer with sensible defaults for testing."""
    return MahjongPlayer(
        seat=seat,
        name=name if name is not None else f"Player{seat}",
        tiles=tuple(tiles) if tiles is not None else (),
        discards=tuple(discards) if discards is not None else (),
        melds=tuple(melds) if melds is not None else (),
        is_riichi=is_riichi,
        is_ippatsu=is_ippatsu,
        is_daburi=is_daburi,
        is_rinshan=is_rinshan,
        kuikae_tiles=tuple(kuikae_tiles) if kuikae_tiles is not None else (),
        pao_seat=pao_seat,
        is_temporary_furiten=is_temporary_furiten,
        is_riichi_furiten=is_riichi_furiten,
        score=score,
    )


def create_round_state(  # noqa: PLR0913
    *,
    players: Sequence[MahjongPlayer] | None = None,
    wall: Sequence[int] | None = None,
    dead_wall: Sequence[int] | None = None,
    dora_indicators: Sequence[int] | None = None,
    dealer_seat: int = 0,
    current_player_seat: int = 0,
    round_wind: int = 0,
    turn_count: int = 0,
    all_discards: Sequence[int] | None = None,
    players_with_open_hands: Sequence[int] | None = None,
    pending_dora_count: int = 0,
    phase: RoundPhase = RoundPhase.WAITING,
    pending_call_prompt: Any = None,  # noqa: ANN401
) -> MahjongRoundState:
    """Create a MahjongRoundState with sensible defaults for testing."""
    if players is None:
        players = tuple(create_player(seat=i) for i in range(4))
    return MahjongRoundState(
        players=tuple(players),
        wall=tuple(wall) if wall is not None else (),
        dead_wall=tuple(dead_wall) if dead_wall is not None else (),
        dora_indicators=tuple(dora_indicators) if dora_indicators is not None else (),
        dealer_seat=dealer_seat,
        current_player_seat=current_player_seat,
        round_wind=round_wind,
        turn_count=turn_count,
        all_discards=tuple(all_discards) if all_discards is not None else (),
        players_with_open_hands=tuple(players_with_open_hands) if players_with_open_hands is not None else (),
        pending_dora_count=pending_dora_count,
        phase=phase,
        pending_call_prompt=pending_call_prompt,
    )


def create_game_state(  # noqa: PLR0913
    round_state: MahjongRoundState | None = None,
    *,
    round_number: int = 0,
    unique_dealers: int = 1,
    honba_sticks: int = 0,
    riichi_sticks: int = 0,
    seed: float = 0.0,
) -> MahjongGameState:
    """Create a MahjongGameState with sensible defaults for testing."""
    if round_state is None:
        round_state = create_round_state()
    return MahjongGameState(
        round_state=round_state,
        round_number=round_number,
        unique_dealers=unique_dealers,
        honba_sticks=honba_sticks,
        riichi_sticks=riichi_sticks,
        seed=seed,
    )


@pytest.fixture
def game_service():
    return MockGameService()


@pytest.fixture
def session_manager(game_service):
    return SessionManager(game_service)


@pytest.fixture
def message_router(session_manager):
    return MessageRouter(session_manager)


@pytest.fixture
def mock_connection():
    return MockConnection()


@pytest.fixture
def app(game_service, session_manager, message_router):
    return create_app(
        game_service=game_service,
        session_manager=session_manager,
        message_router=message_router,
    )
