from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from game.logic.enums import GameAction, GamePhase, MeldCallType, PromptKind, RoundPhase, WindName
from game.logic.events import RoundStartedEvent, SeatTarget
from game.logic.meld_wrapper import FrozenMeld
from game.logic.rng import RNG_VERSION
from game.logic.settings import NUM_PLAYERS, GameSettings
from game.logic.tiles import WINDS_34
from game.logic.types import PlayerView, RoundHistoryEntry, RoundResult
from game.logic.wall import Wall

_WIND_NAMES = (WindName.EAST, WindName.SOUTH, WindName.WEST, WindName.NORTH)


class Discard(BaseModel):
    """
    Immutable discard record.
    """

    model_config = ConfigDict(frozen=True)

    tile_id: int
    is_tsumogiri: bool = False
    is_riichi_discard: bool = False


class CallResponse(BaseModel):
    """
    Immutable call response record.
    """

    model_config = ConfigDict(frozen=True)

    seat: int
    action: GameAction
    sequence_tiles: tuple[int, int] | None = None


class MeldOption(BaseModel):
    """
    One meld a caller may make on the prompt's tile; options holds the chi shapes as pairs of hand tiles.
    """

    model_config = ConfigDict(frozen=True)

    call_type: MeldCallType
    options: tuple[tuple[int, int], ...] | None = None


class Caller(BaseModel):
    """
    A seat eligible to respond to a call prompt: by ron, or by one of its melds (kan > pon > chi).

    A seat that could both ron and meld is a ron caller only, with no melds.
    """

    model_config = ConfigDict(frozen=True)

    seat: int
    can_ron: bool = False
    melds: tuple[MeldOption, ...] = ()


class PendingCallPrompt(BaseModel):
    """
    Immutable pending call prompt.

    Callers are in prompt order, which is also the order of the per-seat prompt events and the order ron winners are
    ranked in: for a discard, ron callers by distance from the discarder, then meld callers by their best meld (kan >
    pon > chi), then seat index; for a chankan, ron callers counter-clockwise from the kan caller.
    """

    model_config = ConfigDict(frozen=True)

    kind: PromptKind
    tile_id: int
    from_seat: int
    pending_seats: frozenset[int]
    callers: tuple[Caller, ...]
    responses: tuple[CallResponse, ...] = ()

    def caller(self, seat: int) -> Caller:
        """
        Return the seat's caller entry; the seat must be one of the prompt's callers.
        """
        caller = next((c for c in self.callers if c.seat == seat), None)
        if caller is None:
            raise AssertionError(f"seat {seat} is not a caller on the prompt")

        return caller


class MahjongPlayer(BaseModel):
    """
    Immutable player state.

    Uses FrozenMeld wrapper for true immutability of meld data.
    """

    model_config = ConfigDict(frozen=True)

    seat: int
    name: str
    tiles: tuple[int, ...] = ()
    discards: tuple[Discard, ...] = ()
    melds: tuple[FrozenMeld, ...] = ()
    is_riichi: bool = False
    is_ippatsu: bool = False
    is_daburi: bool = False
    is_rinshan: bool = False
    kuikae_tiles: tuple[int, ...] = ()
    pao_seat: int | None = None
    is_temporary_furiten: bool = False
    is_riichi_furiten: bool = False
    score: int

    def has_open_melds(self) -> bool:
        """
        Check if player has any open melds (excluding closed kans).
        """
        return any(meld.opened for meld in self.melds)


class MahjongRoundState(BaseModel):
    """
    Immutable round state.

    result is set together with phase FINISHED (finish_round) and kept through the round-advance wait; a new round
    starts without one.
    """

    model_config = ConfigDict(frozen=True)

    wall: Wall
    players: tuple[MahjongPlayer, ...] = ()
    dealer_seat: int = 0
    current_player_seat: int = 0
    round_wind: int = 0
    all_discards: tuple[int, ...] = ()
    phase: RoundPhase = RoundPhase.WAITING
    result: RoundResult | None = None
    pending_call_prompt: PendingCallPrompt | None = None
    is_after_meld_call: bool = False

    def has_any_call(self) -> bool:
        """
        Check if any player has called a meld this round, closed kans included.
        """
        return any(p.melds for p in self.players)


class MahjongGameState(BaseModel):
    """
    Immutable game state.

    wait_id identifies the current wait (see `Awaiting`): the service bumps it once per call that ends the wait.
    round_history holds one entry per finished round, in play order, appended by `finish_round()`.
    """

    model_config = ConfigDict(frozen=True)

    round_state: MahjongRoundState
    round_history: tuple[RoundHistoryEntry, ...] = ()
    round_number: int = 0
    unique_dealers: int = 1
    honba_sticks: int = 0
    riichi_sticks: int = 0
    game_phase: GamePhase = GamePhase.IN_PROGRESS
    seed: str = ""
    rng_version: str = RNG_VERSION
    settings: GameSettings = Field(default_factory=GameSettings)
    dealer_dice: tuple[tuple[int, int], tuple[int, int]] = ((1, 1), (1, 1))
    starting_dealer_seat: int = 0
    wait_id: int = 0


def get_player_view(game_state: MahjongGameState, seat: int) -> RoundStartedEvent:
    """
    Return the round-start view for a specific player, as the round_started event sent to that seat.
    """
    round_state = game_state.round_state

    players_view: list[PlayerView] = []
    my_tiles: list[int] = []
    found = False
    for p in round_state.players:
        if p.seat == seat:
            my_tiles = list(p.tiles)
            found = True

        players_view.append(
            PlayerView(
                seat=p.seat,
                score=p.score,
            ),
        )

    if not found:
        raise ValueError(f"No player found at seat {seat}")

    return RoundStartedEvent(
        target=SeatTarget(seat=seat),
        seat=seat,
        round_wind=wind_name(round_state.round_wind),
        round_number=game_state.round_number,
        dealer_seat=round_state.dealer_seat,
        current_player_seat=round_state.current_player_seat,
        dora_indicators=list(round_state.wall.dora_indicators),
        honba_sticks=game_state.honba_sticks,
        riichi_sticks=game_state.riichi_sticks,
        my_tiles=my_tiles,
        players=players_view,
        dice=round_state.wall.dice,
    )


def wind_name(wind: int) -> WindName:
    """
    Convert wind index to name.
    """
    return _WIND_NAMES[wind] if 0 <= wind < len(_WIND_NAMES) else WindName.UNKNOWN


def seat_to_wind(seat: int, dealer_seat: int) -> int:
    """
    Calculate player's wind tile constant based on seat position relative to dealer.

    Dealer is always East, and winds rotate counter-clockwise from there. Returns the wind tile constant (27-30) for use
    with mahjong library HandConfig.
    """
    relative_position = (seat - dealer_seat) % NUM_PLAYERS
    return WINDS_34[relative_position]
