from typing import TYPE_CHECKING, Any

import pytest

from game.logic.enums import RoundPhase
from game.logic.invariants import verify_tile_ownership
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
)
from game.logic.tiles import NUM_TILES
from game.logic.wall import DEAD_WALL_SIZE
from game.server.app import create_app
from game.server.router import MessageRouter
from game.tests.helpers.auth import TEST_TICKET_SECRET
from game.tests.helpers.session import make_session_manager
from game.tests.helpers.wall import FIRST_DORA_POSITION, URA_OFFSET, make_wall
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


_RINSHAN_SLOTS = (0, URA_OFFSET, 1, URA_OFFSET + 1)


def create_dealt_game_state(
    players: Sequence[MahjongPlayer],
    *,
    draws: Sequence[int] = (),
    rinshan_draws: Sequence[int] = (),
    dora_indicator: int | None = None,
    current_player_seat: int = 0,
    all_discards: Sequence[int] | None = None,
    settings: GameSettings | None = None,
    riichi_sticks: int = 0,
    seed: str = "",
) -> MahjongGameState:
    """
    Build a running round from staged players, dealing every tile they do not own to the walls.

    The draws lead the live wall in order and the rinshan_draws lead the dead wall's replacement draws; dora_indicator,
    when given, is the revealed indicator. The dead wall takes the last free tiles and the live wall the rest.
    all_discards defaults to the players' discards in seat order. Raises when the staged tiles overlap, so the state
    owns each of the 136 tiles exactly once.
    """
    if len(rinshan_draws) > len(_RINSHAN_SLOTS):
        raise ValueError(f"the dead wall holds {len(_RINSHAN_SLOTS)} rinshan draws, got {len(rinshan_draws)}")

    in_play = {
        tile
        for player in players
        for tile in (*player.tiles, *(t for m in player.melds for t in m.tiles), *(d.tile_id for d in player.discards))
    }
    fixed_by_slot = dict(zip(_RINSHAN_SLOTS[: len(rinshan_draws)], rinshan_draws, strict=True))
    if dora_indicator is not None:
        fixed_by_slot[FIRST_DORA_POSITION] = dora_indicator

    free = [
        tile
        for tile in range(NUM_TILES)
        if tile not in in_play and tile not in draws and tile not in fixed_by_slot.values()
    ]
    if all_discards is None:
        all_discards = [d.tile_id for player in players for d in player.discards]

    live_size = len(free) - DEAD_WALL_SIZE + len(fixed_by_slot)
    dead_free = iter(free[live_size:])
    dead_wall = [fixed_by_slot[slot] if slot in fixed_by_slot else next(dead_free) for slot in range(DEAD_WALL_SIZE)]
    round_state = create_round_state(
        players=players,
        wall=(*draws, *free[:live_size]),
        dead_wall=dead_wall,
        current_player_seat=current_player_seat,
        all_discards=all_discards,
        phase=RoundPhase.PLAYING,
    )
    game_state = create_game_state(round_state, riichi_sticks=riichi_sticks, seed=seed, settings=settings)
    verify_tile_ownership(game_state)
    return game_state


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
