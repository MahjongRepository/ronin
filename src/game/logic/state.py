"""
Game state models for Mahjong.

Uses frozen Pydantic models for immutable state management with undo/redo capability.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from game.logic.enums import CallType, GameAction, GamePhase, MeldViewType, RoundPhase, WindName
from game.logic.meld_wrapper import FrozenMeld
from game.logic.settings import GameSettings
from game.logic.tiles import WINDS_34
from game.logic.types import DiscardView, GameView, MeldCaller, MeldView, PlayerView

NUM_WINDS = 4


class Discard(BaseModel):
    """Immutable discard record."""

    model_config = ConfigDict(frozen=True)

    tile_id: int
    is_tsumogiri: bool = False
    is_riichi_discard: bool = False


class CallResponse(BaseModel):
    """Immutable call response record."""

    model_config = ConfigDict(frozen=True)

    seat: int
    action: GameAction
    sequence_tiles: tuple[int, int] | None = None


class PendingCallPrompt(BaseModel):
    """
    Immutable pending call prompt.

    Uses frozenset for pending_seats and tuple for responses/callers
    to ensure complete immutability.
    """

    model_config = ConfigDict(frozen=True)

    call_type: CallType
    tile_id: int
    from_seat: int
    pending_seats: frozenset[int]
    callers: tuple[int | MeldCaller, ...]
    responses: tuple[CallResponse, ...] = ()


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
        """Check if player has any open melds (excluding closed kans)."""
        return any(meld.opened for meld in self.melds)


class MahjongRoundState(BaseModel):
    """Immutable round state."""

    model_config = ConfigDict(frozen=True)

    wall: tuple[int, ...] = ()
    dead_wall: tuple[int, ...] = ()
    dora_indicators: tuple[int, ...] = ()
    players: tuple[MahjongPlayer, ...] = ()
    dealer_seat: int = 0
    current_player_seat: int = 0
    round_wind: int = 0
    turn_count: int = 0
    all_discards: tuple[int, ...] = ()
    players_with_open_hands: tuple[int, ...] = ()
    pending_dora_count: int = 0
    phase: RoundPhase = RoundPhase.WAITING
    pending_call_prompt: PendingCallPrompt | None = None


class MahjongGameState(BaseModel):
    """
    Immutable game state.

    NOTE: round_state defaults to an empty MahjongRoundState.
    For actual game initialization, always provide a properly initialized round_state.
    """

    model_config = ConfigDict(frozen=True)

    round_state: MahjongRoundState = Field(default_factory=MahjongRoundState)
    round_number: int = 0
    unique_dealers: int = 1
    honba_sticks: int = 0
    riichi_sticks: int = 0
    game_phase: GamePhase = GamePhase.IN_PROGRESS
    seed: float = 0.0
    settings: GameSettings = Field(default_factory=GameSettings)


def get_player_view(game_state: MahjongGameState, seat: int, bot_seats: set[int] | None = None) -> GameView:
    """
    Return the visible game state for a specific player.

    Each player can see:
    - Their own hand
    - Their own melds
    - All players' discards
    - All players' open melds
    - All players' riichi status
    - All players' scores
    - Dora indicators
    - Wall count
    - Round info

    They cannot see:
    - Other players' hands
    - Other players' closed kans (tiles hidden)
    - Wall tiles
    - Dead wall tiles (except dora indicators)
    """
    round_state = game_state.round_state

    # build player info for all players
    players_view: list[PlayerView] = []
    for p in round_state.players:
        tiles = list(p.tiles) if p.seat == seat else None

        players_view.append(
            PlayerView(
                seat=p.seat,
                name=p.name,
                is_bot=p.seat in (bot_seats or set()),
                score=p.score,
                is_riichi=p.is_riichi,
                discards=[
                    DiscardView(
                        tile_id=d.tile_id,
                        is_tsumogiri=d.is_tsumogiri,
                        is_riichi_discard=d.is_riichi_discard,
                    )
                    for d in p.discards
                ],
                melds=[_meld_to_view(m) for m in p.melds],
                tile_count=len(p.tiles),
                tiles=tiles,
            )
        )

    return GameView(
        seat=seat,
        round_wind=_wind_name(round_state.round_wind),
        round_number=game_state.round_number,
        dealer_seat=round_state.dealer_seat,
        current_player_seat=round_state.current_player_seat,
        wall_count=len(round_state.wall),
        dora_indicators=list(round_state.dora_indicators),
        honba_sticks=game_state.honba_sticks,
        riichi_sticks=game_state.riichi_sticks,
        players=players_view,
        phase=round_state.phase,
        game_phase=game_state.game_phase,
    )


def _meld_to_view(meld: FrozenMeld) -> MeldView:
    """
    Convert a FrozenMeld object to a MeldView model.
    """
    meld_type_names = {
        FrozenMeld.CHI: MeldViewType.CHI,
        FrozenMeld.PON: MeldViewType.PON,
        FrozenMeld.KAN: MeldViewType.KAN,
        FrozenMeld.CHANKAN: MeldViewType.CHANKAN,
        FrozenMeld.SHOUMINKAN: MeldViewType.SHOUMINKAN,
    }

    return MeldView(
        type=meld_type_names.get(meld.type, MeldViewType.UNKNOWN),
        tile_ids=list(meld.tiles) if meld.tiles else [],
        opened=meld.opened,
        from_who=meld.from_who,
    )


def _wind_name(wind: int) -> WindName:
    """
    Convert wind index to name.
    """
    winds = [WindName.EAST, WindName.SOUTH, WindName.WEST, WindName.NORTH]
    return winds[wind] if 0 <= wind < NUM_WINDS else WindName.UNKNOWN


def seat_to_wind(seat: int, dealer_seat: int) -> int:
    """
    Calculate player's wind tile constant based on seat position relative to dealer.

    Dealer is always East, and winds rotate counter-clockwise from there.
    Returns the wind tile constant (27-30) for use with mahjong library HandConfig.
    """
    relative_position = (seat - dealer_seat) % 4
    return WINDS_34[relative_position]
