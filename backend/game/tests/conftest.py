from typing import TYPE_CHECKING, Any

import pytest

from game.logic.enums import RoundPhase
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
)
from game.server.app import create_app
from game.server.router import MessageRouter
from game.tests.helpers.auth import TEST_TICKET_SECRET
from game.tests.helpers.session import make_session_manager
from game.tests.helpers.wall import make_wall
from game.tests.mocks import MockConnection, MockGameService

if TYPE_CHECKING:
    from collections.abc import Sequence

    from game.logic.meld_wrapper import FrozenMeld
    from game.logic.settings import GameSettings
    from game.logic.wall import Wall


# ============================================================================
# Test State Builder Helpers
# ============================================================================


def create_player(
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


def create_round_state(
    *,
    players: Sequence[MahjongPlayer] | None = None,
    wall: Sequence[int] | None = None,
    dead_wall: Sequence[int | None] | None = None,
    dora_indicators: Sequence[int] | None = None,
    dealer_seat: int = 0,
    current_player_seat: int = 0,
    round_wind: int = 0,
    all_discards: Sequence[int] | None = None,
    pending_dora_count: int = 0,
    phase: RoundPhase = RoundPhase.WAITING,
    pending_call_prompt: Any = None,
    wall_obj: Wall | None = None,
) -> MahjongRoundState:
    if players is None:
        players = tuple(create_player(seat=i) for i in range(4))

    if wall_obj is not None:
        game_wall = wall_obj
    else:
        in_play = [
            t
            for p in players
            for t in (*p.tiles, *(t for m in p.melds for t in m.tiles), *(d.tile_id for d in p.discards))
        ]
        game_wall = make_wall(
            live_tiles=tuple(wall) if wall is not None else (),
            dead_wall=dead_wall,
            dora_indicators=tuple(dora_indicators) if dora_indicators is not None else (),
            reserved=in_play,
            pending_dora_count=pending_dora_count,
        )

    return MahjongRoundState(
        players=tuple(players),
        wall=game_wall,
        dealer_seat=dealer_seat,
        current_player_seat=current_player_seat,
        round_wind=round_wind,
        all_discards=tuple(all_discards) if all_discards is not None else (),
        phase=phase,
        pending_call_prompt=pending_call_prompt,
    )


def create_game_state(
    round_state: MahjongRoundState | None = None,
    *,
    round_number: int = 0,
    unique_dealers: int = 1,
    honba_sticks: int = 0,
    riichi_sticks: int = 0,
    seed: str = "",
    settings: GameSettings | None = None,
) -> MahjongGameState:
    if round_state is None:
        round_state = create_round_state()

    kwargs: dict[str, Any] = {
        "round_state": round_state,
        "round_number": round_number,
        "unique_dealers": unique_dealers,
        "honba_sticks": honba_sticks,
        "riichi_sticks": riichi_sticks,
        "seed": seed,
    }
    if settings is not None:
        kwargs["settings"] = settings

    return MahjongGameState(**kwargs)


@pytest.fixture
def game_service():
    return MockGameService()


@pytest.fixture
def session_manager(game_service):
    return make_session_manager(game_service)


@pytest.fixture
def message_router(session_manager):
    return MessageRouter(session_manager, game_ticket_secret=TEST_TICKET_SECRET)


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
