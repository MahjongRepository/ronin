"""
Game state models for Mahjong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from mahjong.meld import Meld

from game.logic.enums import CallType, GameAction, MeldViewType, WindName
from game.logic.types import DiscardView, GameView, MeldCaller, MeldView, PlayerView

NUM_WINDS = 4


class RoundPhase(Enum):
    """Phase of a mahjong round."""

    WAITING = "waiting"
    PLAYING = "playing"
    FINISHED = "finished"


class GamePhase(Enum):
    """Phase of a mahjong game."""

    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


@dataclass
class Discard:
    """
    Represents a discarded tile with metadata.
    """

    tile_id: int
    is_tsumogiri: bool = False  # true if discarded immediately after draw
    is_riichi_discard: bool = False  # true if this was the riichi declaration discard


@dataclass
class CallResponse:
    """A player's recorded response to a call prompt."""

    seat: int
    action: GameAction
    sequence_tiles: tuple[int, int] | None = None  # for chi: the chosen sequence tiles


@dataclass
class PendingCallPrompt:
    """Tracks pending call responses from eligible players."""

    call_type: CallType
    tile_id: int
    from_seat: int
    pending_seats: set[int]  # seats that haven't responded yet
    callers: list[int] | list[MeldCaller]  # original callers list
    responses: list[CallResponse] = field(default_factory=list)


@dataclass
class MahjongPlayer:
    """
    Represents a player in a mahjong game.
    """

    seat: int  # 0-3
    name: str

    # hand state
    tiles: list[int] = field(default_factory=list)  # tiles in hand (136-format)
    discards: list[Discard] = field(default_factory=list)  # discard history
    melds: list[Meld] = field(default_factory=list)  # open/closed melds

    # riichi state
    is_riichi: bool = False  # has declared riichi
    is_ippatsu: bool = False  # can still get ippatsu (first go-around after riichi)
    is_daburi: bool = False  # double riichi (riichi on first turn)

    # special conditions
    is_rinshan: bool = False  # drew from dead wall after kan
    kuikae_tiles: list[int] = field(
        default_factory=list
    )  # tile_34 values forbidden for discard after meld call
    pao_seat: int | None = None  # seat of player liable for pao (None if no liability)
    is_temporary_furiten: bool = False  # passed on ron, cannot ron until next discard
    is_riichi_furiten: bool = False  # riichi player missed a winning tile, permanent for this hand

    # score
    score: int = 25000

    def has_open_melds(self) -> bool:
        """
        Check if player has any open melds (excluding closed kans).
        """
        return any(meld.opened for meld in self.melds)


@dataclass
class MahjongRoundState:
    """
    Represents the state of a single mahjong round.
    """

    # wall tiles
    wall: list[int] = field(default_factory=list)  # remaining drawable tiles
    dead_wall: list[int] = field(default_factory=list)  # 14 tiles, kan replacements
    dora_indicators: list[int] = field(default_factory=list)  # revealed dora indicators

    # players
    players: list[MahjongPlayer] = field(default_factory=list)

    # turn tracking
    dealer_seat: int = 0  # seat of the dealer (oya)
    current_player_seat: int = 0  # whose turn it is
    round_wind: int = 0  # 0=East, 1=South, 2=West, 3=North
    turn_count: int = 0  # number of turns played (for abortive draw checks)

    # tracking for abortive draws
    all_discards: list[int] = field(default_factory=list)  # all tile_ids discarded (for four winds check)
    players_with_open_hands: list[int] = field(default_factory=list)  # seats that have called melds

    # dora timing
    pending_dora_count: int = 0  # dora indicators to reveal after next discard (for open/added kan)

    # phase
    phase: RoundPhase = RoundPhase.WAITING

    # pending call prompt for multi-caller response collection
    pending_call_prompt: PendingCallPrompt | None = None


@dataclass
class MahjongGameState:
    """
    Represents the full game state across multiple rounds.
    """

    round_state: MahjongRoundState = field(default_factory=MahjongRoundState)

    # game progression
    round_number: int = 0  # 0-based round counter
    unique_dealers: int = 1  # tracks dealer rotation for wind progression

    # sticks
    honba_sticks: int = 0  # continuation sticks
    riichi_sticks: int = 0  # unclaimed riichi deposits

    # game phase
    game_phase: GamePhase = GamePhase.IN_PROGRESS

    # seed for wall generation
    seed: float = 0.0


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
        phase=round_state.phase.value,
        game_phase=game_state.game_phase.value,
    )


def _meld_to_view(meld: Meld) -> MeldView:
    """
    Convert a Meld object to a MeldView model.
    """
    meld_type_names = {
        Meld.CHI: MeldViewType.CHI,
        Meld.PON: MeldViewType.PON,
        Meld.KAN: MeldViewType.KAN,
        Meld.CHANKAN: MeldViewType.CHANKAN,
        Meld.SHOUMINKAN: MeldViewType.SHOUMINKAN,
    }

    return MeldView(
        type=meld_type_names.get(meld.type, MeldViewType.UNKNOWN),
        tile_ids=list(meld.tiles) if meld.tiles else [],
        opened=meld.opened,
        from_who=meld.from_who,
    )


def _wind_name(wind: int) -> str:
    """
    Convert wind index to name.
    """
    winds = [WindName.EAST, WindName.SOUTH, WindName.WEST, WindName.NORTH]
    return winds[wind] if 0 <= wind < NUM_WINDS else WindName.UNKNOWN


def seat_to_wind(seat: int, dealer_seat: int) -> int:
    """
    Calculate player's wind based on seat position relative to dealer.

    Dealer is always East (0), and winds rotate counter-clockwise from there.
    """
    return (seat - dealer_seat) % 4
