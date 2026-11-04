import gzip
from dataclasses import dataclass
from pathlib import Path
from typing import Any, assert_never

import structlog
from mahjong.hand_calculating.yaku import Yaku
from mahjong.hand_calculating.yaku_config import YAKU_ID_TO_TENHOU_ID, YakuConfig
from mahjong.hand_calculating.yaku_list import Renhou
from mahjong.hand_calculating.yaku_list.yakuman import RenhouYakuman

from game.logic.enums import AbortiveDrawType, HandLimit, KanType
from game.logic.settings import NUM_PLAYERS, WIRE_SCORE_DIVISOR, GameSettings, GameType
from game.wire.compact import decode_discard, decode_draw, encode_discard, encode_draw
from game.wire.enums import WireEventType, WireRoundResultType
from game.wire.keys import WireKey
from game.wire.replay_format import MAX_REPLAY_BYTES, decode_replay_records, decode_replay_settings
from shared.lib.melds.compact import MeldData, decode_meld_compact, encode_meld_compact

logger = structlog.get_logger()

REPLAYS_DIR = Path("backend/data/replays")
OUTPUT_DIR = Path("backend/data/tenhou_replays")

DRAW_LETTERS = ["T", "U", "V", "W"]
DISCARD_LETTERS = ["D", "E", "F", "G"]

ABORTIVE_REASON_TO_TENHOU = {
    AbortiveDrawType.NINE_TERMINALS: "yao9",
    AbortiveDrawType.FOUR_WINDS: "kaze4",
    AbortiveDrawType.FOUR_KANS: "kan4",
    AbortiveDrawType.FOUR_RIICHI: "reach4",
    AbortiveDrawType.TRIPLE_RON: "ron3",
}

TENHOU_LIMIT = {
    HandLimit.NONE: 0,
    HandLimit.MANGAN: 1,
    HandLimit.HANEMAN: 2,
    HandLimit.BAIMAN: 3,
    HandLimit.SANBAIMAN: 4,
    HandLimit.YAKUMAN: 5,
    HandLimit.KAZOE_YAKUMAN: 5,
}

YAKUMAN_YAKU_IDS = frozenset(
    yaku.yaku_id for yaku in vars(YakuConfig()).values() if isinstance(yaku, Yaku) and yaku.is_yakuman
)
TENHOU_ID_BY_YAKU_ID = {
    **YAKU_ID_TO_TENHOU_ID,
    RenhouYakuman.yaku_id: YAKU_ID_TO_TENHOU_ID[Renhou.yaku_id],
}
TENHOU_GO_VS_HUMAN = 0x01
TENHOU_GO_NO_AKADORA = 0x02
TENHOU_GO_NO_KUITAN = 0x04
TENHOU_GO_HANCHAN = 0x08
TENHOU_GO_LENGTH_BITS = {
    GameType.HANCHAN: TENHOU_GO_HANCHAN,
    GameType.TONPUSEN: 0,
}

_RESULT_SEAT_KEYS = frozenset({WireKey.WINNER_SEAT, WireKey.LOSER_SEAT, WireKey.PAO_SEAT, WireKey.SEAT})
_RESULT_SCORE_MAP_KEYS = frozenset({WireKey.SCORES, WireKey.SCORE_CHANGES})
_RESULT_NESTED_LIST_KEYS = frozenset({WireKey.WINNERS, WireKey.TENPAI_HANDS})


def _to_binary_string(number: int, size: int | None = None) -> str:
    result = bin(number).replace("0b", "")
    if size and len(result) < size:
        result = "0" * (size - len(result)) + result

    return result


def _from_who_offset(who: int, from_who: int) -> int:
    result = from_who - who
    if result < 0:
        result += 4

    return result


def _encode_chi(tiles: list[int], called_tile: int, who: int, from_who: int) -> str:
    result = []
    tiles = sorted(tiles)
    base = tiles[0] // 4

    called = tiles.index(called_tile)
    base_and_called = ((base // 9) * 7 + base % 9) * 3 + called
    result.append(_to_binary_string(base_and_called))

    # chi format marker
    result.append("0")

    t0 = tiles[0] - base * 4
    t1 = tiles[1] - 4 - base * 4
    t2 = tiles[2] - 8 - base * 4

    result.append(_to_binary_string(t2, 2))
    result.append(_to_binary_string(t1, 2))
    result.append(_to_binary_string(t0, 2))

    # chi flag
    result.append("1")

    offset = _from_who_offset(who, from_who)
    result.append(_to_binary_string(offset, 2))

    return str(int("".join(result), 2))


def _encode_pon(  # noqa: PLR0913
    tiles: list[int],
    called_tile: int,
    who: int,
    from_who: int,
    *,
    is_shouminkan: bool = False,
    added_tile: int | None = None,
) -> str:
    result = []
    tiles = sorted(tiles)
    base = tiles[0] // 4

    if is_shouminkan:
        # Compute called index from the 3 pon tiles only (not all 4).
        # Using all 4 sorted tiles could give called=3, which overflows
        # the base_and_called formula (expects 0-2).
        added: int = added_tile if added_tile is not None else 0
        pon_tiles = sorted(t for t in tiles if t != added)
        called = pon_tiles.index(called_tile)
        base_and_called = base * 3 + called
        delta_index = added % 4
    else:
        called = tiles.index(called_tile)
        base_and_called = base * 3 + called
        delta_array = [[1, 2, 3], [0, 2, 3], [0, 1, 3], [0, 1, 2]]
        delta = [t - base * 4 for t in tiles[:3]]
        delta_index = delta_array.index(delta)

    result.append(_to_binary_string(base_and_called))

    result.append("00")

    result.append(_to_binary_string(delta_index, 2))

    # kan flag
    result.append("1" if is_shouminkan else "0")
    # pon flag
    result.append("0" if is_shouminkan else "1")
    # not a chi
    result.append("0")

    offset = _from_who_offset(who, from_who)
    result.append(_to_binary_string(offset, 2))

    return str(int("".join(result), 2))


def _encode_kan(tiles: list[int], called_tile: int, who: int, from_who: int) -> str:
    result = []
    tiles = sorted(tiles)
    base = tiles[0] // 4

    called = tiles.index(called_tile)
    base_and_called = base * 4 + called
    result.append(_to_binary_string(base_and_called))

    result.extend(["0", "0", "0", "0", "0", "0"])

    offset = _from_who_offset(who, from_who)
    result.append(_to_binary_string(offset, 2))

    return str(int("".join(result), 2))


def encode_meld(meld_event: dict[str, Any]) -> str:
    meld_type = meld_event["meld_type"]
    tiles = meld_event["tile_ids"]
    called_tile = meld_event["called_tile_id"]
    who: int = meld_event["caller_seat"]

    match meld_type:
        case "chi":
            return _encode_chi(tiles=tiles, called_tile=called_tile, who=who, from_who=meld_event["from_seat"])
        case "pon":
            return _encode_pon(tiles, called_tile, who, meld_event["from_seat"])
        case "added_kan":
            tile = called_tile if called_tile is not None else min(tiles)
            source: int = meld_event.get("from_seat", who)
            return _encode_pon(tiles, tile, who, source, is_shouminkan=True, added_tile=meld_event["added_tile_id"])
        case "closed_kan":
            tile = called_tile if called_tile is not None else min(tiles)
            return _encode_kan(tiles=tiles, called_tile=tile, who=who, from_who=who)
        case "open_kan":
            return _encode_kan(tiles=tiles, called_tile=called_tile, who=who, from_who=meld_event["from_seat"])
        case _:  # pragma: no cover (exhaustive)
            raise ValueError(f"unknown meld type: {meld_type}")


def _format_yaku_attr(yaku_list: list[dict[int, Any]]) -> str:
    """
    Format the yaku attribute as tenhou id and han pairs, or for a yakuman hand the yakuman attribute of its ids alone.

    Each yaku dict carries yi (the library yaku id) and han. Tenhou lists a yakuman by id with no han, one id per
    yakuman, so a double yakuman keeps a single id and only the ten points carry its doubled value. Renhou as a yakuman
    keeps tenhou's renhou id; any other local yakuman tenhou has no id for is left out, which loses nothing for
    daichisei as it always comes with tsuuiisou, and a yakuman hand left with no tenhou id raises rather than write an
    empty yakuman attribute.
    """
    tenhou_ids = [(TENHOU_ID_BY_YAKU_ID.get(yaku[WireKey.YAKU_ID]), yaku) for yaku in yaku_list]
    if not any(yaku[WireKey.YAKU_ID] in YAKUMAN_YAKU_IDS for yaku in yaku_list):
        pairs = [f"{tenhou_id},{yaku[WireKey.HAN]}" for tenhou_id, yaku in tenhou_ids if tenhou_id is not None]
        return f' yaku="{",".join(pairs)}"'

    yakuman_ids = [str(tenhou_id) for tenhou_id, _yaku in tenhou_ids if tenhou_id is not None]
    if not yakuman_ids:
        raise ValueError(f"yakuman hand has no tenhou yaku id: {[yaku[WireKey.YAKU_ID] for yaku in yaku_list]}")

    return f' yakuman="{",".join(yakuman_ids)}"'


def _format_winning_hand(closed_tiles: list[int], win_tile: int) -> str:
    """
    Format the hai attribute: the winner's closed tiles with the winning tile, ascending as tenhou writes them.
    """
    return ",".join(str(t) for t in sorted([*closed_tiles, win_tile]))


def _format_sc(scores: dict[str, int], score_changes: dict[str, int]) -> str:
    """
    Format the sc attribute: 'score0,change0,score1,change1,...' (in hundreds).

    Both scores and score_changes are dicts with string keys in wire format (already divided by WIRE_SCORE_DIVISOR, i.e.
    in hundreds).
    """
    parts = []
    for i in range(4):
        score = scores[str(i)]
        change = score_changes[str(i)]
        parts.append(f"{score},{change}")

    return ",".join(parts)


def _double_ron_score_steps(result: dict[int, Any]) -> list[tuple[dict[str, int], dict[str, int]]]:
    """
    Each double ron winner's sc pair: the scores before that win and the changes it alone made, so each AGARI starts
    from the scores the one before it left.
    """
    steps = []
    scores = result[WireKey.SCORES]
    for w in result[WireKey.WINNERS]:
        steps.append((scores, w[WireKey.SCORE_CHANGES]))
        scores = {seat: scores[seat] + w[WireKey.SCORE_CHANGES][seat] for seat in map(str, range(4))}

    return steps


def _format_ten(hand: dict[int, Any]) -> str:
    """
    Format the AGARI ten attribute: fu, the hand's value in full points and the limit the engine paid it at.

    Tenhou writes the bare hand value: honba and riichi sticks appear only in ba and sc.
    """
    points = hand[WireKey.POINTS] * WIRE_SCORE_DIVISOR
    return f"{hand[WireKey.FU]},{points},{TENHOU_LIMIT[HandLimit(hand[WireKey.HAND_LIMIT])]}"


def _tenhou_go_type(settings: GameSettings) -> int:
    """
    Compute the tenhou GO type bitfield for a game's settings.

    Four players against humans, the no-red-fives and no-open-tanyao bits set when the game had them off, plus the
    hanchan bit for an East-South game.
    """
    go_type = TENHOU_GO_VS_HUMAN | TENHOU_GO_LENGTH_BITS[settings.game_type]
    if not settings.has_akadora:
        go_type |= TENHOU_GO_NO_AKADORA

    if not settings.has_kuitan:
        go_type |= TENHOU_GO_NO_KUITAN

    return go_type


def _game_started_event(events: list[dict[int, Any]]) -> dict[int, Any]:
    """
    Return the replay's game_started event, raising when the replay has none.
    """
    game_started = next((e for e in events if e.get(WireKey.EVENT_TYPE) == WireEventType.GAME_STARTED), None)
    if game_started is None:
        raise ValueError("replay has no game_started event")

    return game_started


@dataclass(frozen=True)
class _TenhouSeating:
    """
    Move a replay's seats to tenhou's, which number the seats from the first dealer counter-clockwise.

    A tenhou log seats its first dealer at 0, so its seat order is the dealer order and the round counter of each INIT
    seed counts the dealer rotations; readers take both for granted. Ronin's first dealer is any seat.
    """

    first_dealer: int

    def _tenhou_seat(self, seat: int) -> int:
        return (seat - self.first_dealer) % NUM_PLAYERS

    def move_seats(self, event: dict[int, Any]) -> dict[int, Any]:  # noqa: PLR0911
        """
        Return a copy of an event with every seat the export reads from it moved to its tenhou seat.

        A packed draw, discard or meld is re-packed with the moved seat; a record the export does not read is returned
        as it is. A field the export starts reading joins its event's case here.
        """
        match event.get(WireKey.EVENT_TYPE):
            case WireEventType.GAME_STARTED | WireEventType.ROUND_STARTED:
                return {
                    **event,
                    WireKey.DEALER: self._tenhou_seat(event[WireKey.DEALER]),
                    WireKey.PLAYERS: self._move_entry_seats(event[WireKey.PLAYERS]),
                }
            case WireEventType.DRAW:
                seat, tile = decode_draw(event[WireKey.PACKED_MOVE])
                return {**event, WireKey.PACKED_MOVE: encode_draw(self._tenhou_seat(seat), tile)}
            case WireEventType.DISCARD:
                seat, tile, is_tsumogiri, is_riichi = decode_discard(event[WireKey.PACKED_MOVE])
                return {
                    **event,
                    WireKey.PACKED_MOVE: encode_discard(
                        self._tenhou_seat(seat), tile, is_tsumogiri=is_tsumogiri, is_riichi=is_riichi
                    ),
                }
            case WireEventType.RIICHI_DECLARED:
                return {**event, WireKey.SEAT: self._tenhou_seat(event[WireKey.SEAT])}
            case WireEventType.MELD:
                return {**event, WireKey.PACKED_MELD: self._move_meld_seats(event[WireKey.PACKED_MELD])}
            case WireEventType.ROUND_END:
                return self._move_result_seats(event)
            case WireEventType.GAME_END:
                return {**event, WireKey.STANDINGS: self._move_entry_seats(event[WireKey.STANDINGS])}
            case _:
                return event

    def _move_entry_seats(self, entries: list[dict[int, Any]]) -> list[dict[int, Any]]:
        return [{**entry, WireKey.SEAT: self._tenhou_seat(entry[WireKey.SEAT])} for entry in entries]

    def _move_meld_seats(self, compact: int) -> int:
        meld = decode_meld_compact(compact)
        from_seat = meld["from_seat"]
        return encode_meld_compact(
            {
                **meld,
                "caller_seat": self._tenhou_seat(meld["caller_seat"]),
                "from_seat": None if from_seat is None else self._tenhou_seat(from_seat),
            },
        )

    def _move_result_seats(self, fields: dict[int, Any]) -> dict[int, Any]:
        """
        Return round result fields with the seats the export reads moved: the result's own and those of its robbed kan,
        double ron winners and tenpai hands, which name theirs under the same keys.
        """
        moved = dict(fields)
        for key in _RESULT_SEAT_KEYS & fields.keys():
            moved[key] = self._tenhou_seat(fields[key])

        if WireKey.RON_CALLERS in fields:
            moved[WireKey.RON_CALLERS] = [self._tenhou_seat(seat) for seat in fields[WireKey.RON_CALLERS]]

        for key in _RESULT_SCORE_MAP_KEYS & fields.keys():
            moved[key] = {str(self._tenhou_seat(int(seat))): score for seat, score in fields[key].items()}

        if WireKey.ROBBED_KAN in fields:
            moved[WireKey.ROBBED_KAN] = self._move_result_seats(fields[WireKey.ROBBED_KAN])

        for key in _RESULT_NESTED_LIST_KEYS & fields.keys():
            moved[key] = [self._move_result_seats(entry) for entry in fields[key]]

        return moved


def _format_ura_dora_attr(ura_dora_indicators: list[int] | None) -> str:
    """
    Format the doraHaiUra attribute, or empty string when absent.
    """
    if not ura_dora_indicators:
        return ""

    ura_string = ",".join(str(d) for d in ura_dora_indicators)
    return f' doraHaiUra="{ura_string}"'


def _format_revealed_hands(hands_by_seat: dict[int, list[int]]) -> str:
    """
    Format the haiN attributes of the hands a RYUUKYOKU reveals, by seat and each ascending, as tenhou writes them.
    """
    return "".join(
        f' hai{seat}="{",".join(str(t) for t in sorted(tiles))}"' for seat, tiles in sorted(hands_by_seat.items())
    )


def _format_pao_attr(pao_seat: int | None) -> str:
    """
    Format the paoWho attribute naming the seat liable for the yakuman, or empty string when nobody is.
    """
    if pao_seat is None:
        return ""

    return f' paoWho="{pao_seat}"'


class IncompleteReplayError(ValueError):
    """
    A replay without a game end (a failed game), which a tenhou.net log cannot represent.
    """


class TenhouConverter:
    """
    Convert a Ronin replay event log to tenhou.net XML, the common replay format of other mahjong services.

    The tenhou XML replay format belongs to tenhou.net; this converter is not affiliated with tenhou.net.

    Each event is moved to tenhou's seats as the converter takes it, so every seat the handlers read and write is a
    tenhou seat: the first dealer is seat 0, so the round wind and dealer seat give the INIT round counter.
    """

    def __init__(self, events: list[dict[int, Any]]) -> None:
        game_started = _game_started_event(events)
        self.settings = decode_replay_settings(game_started.get(WireKey.GAME_SETTINGS))
        seating = _TenhouSeating(first_dealer=game_started[WireKey.DEALER])
        self.events = [seating.move_seats(event) for event in events]
        self.tags: list[str] = []

        # Scores in wire format (hundreds), set from the first round_started event.
        self.scores: list[int] = [0, 0, 0, 0]
        self.round_wind_number: int = 0
        self.honba: int = 0
        self.table_riichi_sticks: int = 0
        self.dealer: int = 0
        self.dora_indicators: list[int] = []
        self.dice: list[int] = [0, 0]
        self.hands: dict[int, list[int]] = {}

        # Per-round state
        self._round_riichi_count: int = 0
        self._seat_melds: dict[int, list[str]] = {}
        self._pons_by_seat_and_tile_34: dict[tuple[int, int], MeldData] = {}

    @property
    def _total_riichi_sticks(self) -> int:
        """
        Riichi sticks on the table: carryovers from previous rounds plus deposits this round.
        """
        return self.table_riichi_sticks + self._round_riichi_count

    def convert(self) -> str:
        for event in self.events:
            self._process_event(event)

        return "".join(self.tags)

    def _process_event(self, event: dict[int, Any]) -> None:
        event_type = event.get(WireKey.EVENT_TYPE)
        if event_type is None:
            return

        handler = {
            WireEventType.GAME_STARTED: self._handle_game_started,
            WireEventType.ROUND_STARTED: self._handle_round_started,
            WireEventType.DRAW: self._handle_draw,
            WireEventType.DORA_REVEALED: self._handle_dora_revealed,
            WireEventType.DISCARD: self._handle_discard,
            WireEventType.RIICHI_DECLARED: self._handle_riichi_declared,
            WireEventType.MELD: self._handle_meld,
            WireEventType.ROUND_END: self._handle_round_end,
            WireEventType.GAME_END: self._handle_game_end,
        }.get(event_type)
        if handler:
            handler(event)

    # -- Header ---------------------------------------------------------------

    def _handle_game_started(self, event: dict[int, Any]) -> None:
        seed = event[WireKey.SEED]
        players = sorted(event[WireKey.PLAYERS], key=lambda p: p[WireKey.SEAT])
        first_dealer = event[WireKey.DEALER]

        self.tags.append('<mjloggm ver="2.3">')
        rng_version = event[WireKey.RNG_VERSION]
        self.tags.append(f'<SHUFFLE seed="{seed}" ref="{rng_version}"/>')
        go_type = _tenhou_go_type(self.settings)
        self.tags.append(f'<GO type="{go_type}" lobby="0"/>')

        names = [p[WireKey.NAME] for p in players]
        self.tags.append(
            f'<UN n0="{names[0]}" n1="{names[1]}" '
            f'n2="{names[2]}" n3="{names[3]}" '
            f'dan="0,0,0,0" rate="1500.00,1500.00,1500.00,1500.00" sx="M,M,M,M"/>',
        )
        self.tags.append(f'<TAIKYOKU oya="{first_dealer}"/>')

    # -- Round started (merged, 1 per round) ----------------------------------

    def _handle_round_started(self, event: dict[int, Any]) -> None:
        wind_index = event[WireKey.WIND]
        self.round_wind_number = wind_index * 4 + event[WireKey.DEALER]
        self.honba = event[WireKey.HONBA]
        self.table_riichi_sticks = event[WireKey.RIICHI_STICKS]
        self.dealer = event[WireKey.DEALER]
        self.dora_indicators = list(event[WireKey.DORA_INDICATORS])
        self.dice = event[WireKey.DICE]

        self.hands = {}
        for player in event[WireKey.PLAYERS]:
            self.scores[player[WireKey.SEAT]] = player[WireKey.SCORE]
            self.hands[player[WireKey.SEAT]] = list(player[WireKey.TILES])

        self._emit_init()

    # -- Round init -----------------------------------------------------------

    def _emit_init(self) -> None:
        self._round_riichi_count = 0
        self._seat_melds = {}
        self._pons_by_seat_and_tile_34 = {}

        scores_str = ",".join(str(s) for s in self.scores)
        first_dora = self.dora_indicators[0] if self.dora_indicators else 0
        dice0, dice1 = self.dice

        hai_strs = []
        for seat in range(4):
            tiles = self.hands[seat]
            hai_strs.append(",".join(str(t) for t in tiles))

        seed_attr = f"{self.round_wind_number},{self.honba},{self.table_riichi_sticks},{dice0},{dice1},{first_dora}"
        self.tags.append(
            f'<INIT seed="{seed_attr}" '
            f'ten="{scores_str}" oya="{self.dealer}" '
            f'hai0="{hai_strs[0]}" hai1="{hai_strs[1]}" hai2="{hai_strs[2]}" hai3="{hai_strs[3]}"/>',
        )

    # -- Draw (packed seat+tile_id) -------------------------------------------

    def _handle_draw(self, event: dict[int, Any]) -> None:
        seat, tile = decode_draw(event[WireKey.PACKED_MOVE])
        self.hands[seat].append(tile)
        self.tags.append(f"<{DRAW_LETTERS[seat]}{tile}/>")

    # -- Dora revealed --------------------------------------------------------

    def _handle_dora_revealed(self, event: dict[int, Any]) -> None:
        tile_id = event[WireKey.TILE_ID]
        self.dora_indicators.append(tile_id)
        self.tags.append(f'<DORA hai="{tile_id}"/>')

    # -- Discard (packed seat+tile_id+flags) ----------------------------------

    def _handle_discard(self, event: dict[int, Any]) -> None:
        seat, tile, _is_tsumogiri, is_riichi = decode_discard(event[WireKey.PACKED_MOVE])
        self.hands[seat].remove(tile)

        if is_riichi:
            self.tags.append(f'<REACH who="{seat}" step="1"/>')

        # Always use uppercase discard letters. The tenhou viewer's scroll-back
        # REINIT builder (mg function) only handles uppercase D/E/F/G; lowercase
        # d/e/f/g tsumogiri tags are silently skipped, leaving tiles in hands and
        # causing "can't access property X, x is undefined" crashes. The viewer's
        # D handler detects tsumogiri via tile ID comparison (l === h[0]), so
        # uppercase tags produce identical visual results.
        self.tags.append(f"<{DISCARD_LETTERS[seat]}{tile}/>")

    # -- Riichi ---------------------------------------------------------------

    def _handle_riichi_declared(self, event: dict[int, Any]) -> None:
        seat = event[WireKey.SEAT]
        self._round_riichi_count += 1
        self.scores[seat] = event[WireKey.SCORE]
        scores_string = ",".join(str(score) for score in self.scores)
        self.tags.append(f'<REACH who="{seat}" ten="{scores_string}" step="2"/>')

    # -- Meld (compact IMME encoding) -----------------------------------------

    def _handle_meld(self, event: dict[int, Any]) -> None:
        """
        Emit a meld's N tag, take its tiles from the caller's hand and track it for the caller's AGARI.

        An added kan takes its pon's place among the caller's melds, as tenhou lists only the kan.
        """
        meld_data = decode_meld_compact(event[WireKey.PACKED_MELD])
        who = meld_data["caller_seat"]
        tile_34 = min(meld_data["tile_ids"]) // 4
        seat_melds = self._seat_melds.setdefault(who, [])

        if meld_data["meld_type"] == "added_kan":
            added_tile = meld_data["added_tile_id"]
            if added_tile is None:
                raise ValueError(f"added kan by seat {who} on tile {tile_34} carries no added tile")

            pon = self._recorded_pon(who, tile_34)
            meld_str = encode_meld(dict(meld_data))
            seat_melds[seat_melds.index(encode_meld(dict(pon)))] = meld_str
            self.hands[who].remove(added_tile)
        else:
            meld_str = encode_meld(dict(meld_data))
            seat_melds.append(meld_str)
            for tile in meld_data["tile_ids"]:
                if tile != meld_data["called_tile_id"]:
                    self.hands[who].remove(tile)

        if meld_data["meld_type"] == "pon":
            self._pons_by_seat_and_tile_34[(who, tile_34)] = meld_data

        self.tags.append(f'<N who="{who}" m="{meld_str}" />')

    def _recorded_pon(self, seat: int, tile_34: int) -> MeldData:
        """
        Return the pon a kan on tile_34 by seat extends, raising when the replay recorded no such pon this round.
        """
        pon = self._pons_by_seat_and_tile_34.get((seat, tile_34))
        if pon is None:
            raise ValueError(f"added kan by seat {seat} on tile {tile_34} has no recorded pon this round")

        return pon

    # -- Round end ------------------------------------------------------------

    def _handle_round_end(self, event: dict[int, Any]) -> None:
        result_type = event[WireKey.RESULT_TYPE]
        robbed_kan = event.get(WireKey.ROBBED_KAN)
        if robbed_kan is not None:
            self._emit_robbed_kan(robbed_kan)

        if result_type in (WireRoundResultType.RON, WireRoundResultType.TSUMO):
            self._emit_agari(event)
        elif result_type == WireRoundResultType.DOUBLE_RON:
            self._emit_double_ron(event)
        elif result_type == WireRoundResultType.EXHAUSTIVE_DRAW:
            self._emit_exhaustive_draw(event, type_attr="")
        elif result_type == WireRoundResultType.NAGASHI_MANGAN:
            self._emit_exhaustive_draw(event, type_attr=' type="nm"')
        elif result_type == WireRoundResultType.ABORTIVE_DRAW:
            self._emit_abortive_draw(event)

        self._update_scores_from_round_end(event)

    def _emit_robbed_kan(self, robbed_kan: dict[int, Any]) -> None:
        """
        Emit the N tag of a kan robbed by chankan, which tenhou logs before the win like any declared kan.

        The robbed kan never completed, so no meld event recorded it: an added kan is rebuilt from its declarer's pon, a
        closed kan from the four copies of its tile.
        """
        who = robbed_kan[WireKey.SEAT]
        tile = robbed_kan[WireKey.TILE_ID]
        tile_34 = tile // 4
        if robbed_kan[WireKey.KAN_TYPE] == KanType.ADDED:
            pon = self._recorded_pon(who, tile_34)
            kan: dict[str, Any] = {
                **pon,
                "meld_type": "added_kan",
                "tile_ids": [*pon["tile_ids"], tile],
                "added_tile_id": tile,
            }
        else:
            kan = {
                "meld_type": "closed_kan",
                "caller_seat": who,
                "tile_ids": [tile_34 * 4 + copy for copy in range(4)],
                "called_tile_id": None,
            }

        self.tags.append(f'<N who="{who}" m="{encode_meld(kan)}" />')

    def _update_scores_from_round_end(self, event: dict[int, Any]) -> None:
        """
        Update tracked scores from round_end scores and score_changes.
        """
        scores = event[WireKey.SCORES]
        changes = event[WireKey.SCORE_CHANGES]
        for i in range(4):
            self.scores[i] = scores[str(i)] + changes[str(i)]

    def _emit_agari(self, result: dict[int, Any]) -> None:
        winner = result[WireKey.WINNER_SEAT]
        from_who = result[WireKey.LOSER_SEAT] if result[WireKey.RESULT_TYPE] == WireRoundResultType.RON else winner
        hand = result[WireKey.HAND_RESULT]
        ten_string = _format_ten(hand)

        yaku_attr = _format_yaku_attr(hand[WireKey.YAKU])
        sc_string = _format_sc(result[WireKey.SCORES], result[WireKey.SCORE_CHANGES])

        win_tile = result[WireKey.WINNING_TILE]
        hai_string = _format_winning_hand(result[WireKey.CLOSED_TILES], win_tile)

        dora_string = ",".join(str(d) for d in self.dora_indicators)
        ura_dora_attr = _format_ura_dora_attr(result.get(WireKey.URA_DORA))
        pao_attr = _format_pao_attr(result.get(WireKey.PAO_SEAT))

        meld_attr = self._format_meld_attr(winner)

        self.tags.append(
            f'<AGARI ba="{self.honba},{self._total_riichi_sticks}" '
            f'hai="{hai_string}"{meld_attr} machi="{win_tile}" ten="{ten_string}"'
            f'{yaku_attr} doraHai="{dora_string}"{ura_dora_attr} '
            f'who="{winner}" fromWho="{from_who}"{pao_attr} sc="{sc_string}" />',
        )

    def _format_meld_attr(self, winner: int) -> str:
        """
        Format the AGARI m attribute: the winner's melds newest first, as tenhou lists them, or empty without melds.
        """
        if not self._seat_melds.get(winner):
            return ""

        return f' m="{",".join(reversed(self._seat_melds[winner]))}"'

    def _emit_double_ron(self, result: dict[int, Any]) -> None:
        """
        Emit one AGARI tag per winner in a double-ron.

        The first winner, the closest counter-clockwise to the loser, takes the riichi sticks, so the later AGARIs find
        none on the table.
        """
        loser = result[WireKey.LOSER_SEAT]
        winning_tile = result[WireKey.WINNING_TILE]
        dora_string = ",".join(str(d) for d in self.dora_indicators)

        steps = _double_ron_score_steps(result)
        for i, (w, (scores, changes)) in enumerate(zip(result[WireKey.WINNERS], steps, strict=True)):
            winner = w[WireKey.WINNER_SEAT]
            riichi_sticks = self._total_riichi_sticks if i == 0 else 0
            sc_string = _format_sc(scores, changes)
            hand = w[WireKey.HAND_RESULT]
            ten_string = _format_ten(hand)
            yaku_attr = _format_yaku_attr(hand[WireKey.YAKU])

            hai_string = _format_winning_hand(w[WireKey.CLOSED_TILES], winning_tile)
            ura_dora_attr = _format_ura_dora_attr(w.get(WireKey.URA_DORA))
            pao_attr = _format_pao_attr(w.get(WireKey.PAO_SEAT))

            meld_attr = self._format_meld_attr(winner)

            self.tags.append(
                f'<AGARI ba="{self.honba},{riichi_sticks}" '
                f'hai="{hai_string}"{meld_attr} machi="{winning_tile}" '
                f'ten="{ten_string}"'
                f'{yaku_attr} doraHai="{dora_string}"{ura_dora_attr} '
                f'who="{winner}" fromWho="{loser}"{pao_attr} sc="{sc_string}" />',
            )

    def _emit_exhaustive_draw(self, result: dict[int, Any], *, type_attr: str) -> None:
        """
        Emit the RYUUKYOKU of a wall run out, a nagashi mangan carrying type_attr, revealing the tenpai hands.
        """
        sc_string = _format_sc(result[WireKey.SCORES], result[WireKey.SCORE_CHANGES])
        tenpai_hands = {hand[WireKey.SEAT]: hand[WireKey.CLOSED_TILES] for hand in result[WireKey.TENPAI_HANDS]}
        hai_attrs = _format_revealed_hands(tenpai_hands)

        self.tags.append(
            f'<RYUUKYOKU{type_attr} ba="{self.honba},{self._total_riichi_sticks}" sc="{sc_string}"{hai_attrs} />',
        )

    def _emit_abortive_draw(self, result: dict[int, Any]) -> None:
        """
        Emit the RYUUKYOKU of an abortive draw, revealing the hands tenhou shows for it.

        Kyuushu kyuuhai shows its declarer's hand, four riichi every hand and a triple ron its three declarers' hands;
        four winds and four kans show none.
        """
        reason = AbortiveDrawType(result[WireKey.ABORTIVE_REASON])
        match reason:
            case AbortiveDrawType.NINE_TERMINALS:
                revealed_seats = [result[WireKey.SEAT]]
            case AbortiveDrawType.FOUR_RIICHI:
                revealed_seats = list(self.hands)
            case AbortiveDrawType.TRIPLE_RON:
                revealed_seats = result[WireKey.RON_CALLERS]
            case AbortiveDrawType.FOUR_WINDS | AbortiveDrawType.FOUR_KANS:
                revealed_seats = []
            case _:  # pragma: no cover (exhaustive)
                assert_never(reason)

        sc_string = _format_sc(result[WireKey.SCORES], result[WireKey.SCORE_CHANGES])
        hai_attrs = _format_revealed_hands({seat: self.hands[seat] for seat in revealed_seats})

        self.tags.append(
            f'<RYUUKYOKU type="{ABORTIVE_REASON_TO_TENHOU[reason]}" ba="{self.honba},{self._total_riichi_sticks}" '
            f'sc="{sc_string}"{hai_attrs} />',
        )

    # -- Game end -------------------------------------------------------------

    def _handle_game_end(self, event: dict[int, Any]) -> None:
        standings = event[WireKey.STANDINGS]
        owari_parts = []
        for seat in range(4):
            standing = next(s for s in standings if s[WireKey.SEAT] == seat)
            final_score = float(standing[WireKey.FINAL_SCORE])
            owari_parts.append(f"{standing[WireKey.SCORE]},{final_score:.1f}")

        owari_string = ",".join(owari_parts)

        self.tags[-1] = self.tags[-1].removesuffix(" />") + f' owari="{owari_string}" />'
        self.tags.append("</mjloggm>")


def convert_replay_content(content: bytes) -> str:
    """
    Convert independent MessagePack replay records to tenhou.net XML.

    Raise IncompleteReplayError for the replay of a failed game, which has no game end to close the log with.
    """
    events = decode_replay_records(content)
    if not any(event.get(WireKey.EVENT_TYPE) == WireEventType.GAME_END for event in events):
        raise IncompleteReplayError("replay has no game end")

    return TenhouConverter(events).convert()


def convert_replay(filepath: Path) -> str:
    if filepath.name.endswith(".gz"):
        with gzip.open(filepath, "rb") as f:
            content = f.read(MAX_REPLAY_BYTES + 1)
    else:
        with filepath.open("rb") as f:
            content = f.read(MAX_REPLAY_BYTES + 1)

    return convert_replay_content(content)


def main() -> None:
    # Remove all existing tenhou replays before generating new ones.
    if OUTPUT_DIR.exists():
        for old_file in OUTPUT_DIR.iterdir():
            old_file.unlink()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    replay_files = sorted(REPLAYS_DIR.glob("??/??/*.msgpack.gz"))
    if not replay_files:
        logger.info("No replay files found in %s", REPLAYS_DIR)
        return

    converted = 0
    for filepath in replay_files:
        logger.info("Converting %s...", filepath.name)
        try:
            tenhou_xml = convert_replay(filepath)
        except IncompleteReplayError:
            logger.warning("  skipped: a failed game's replay has no game end")
            continue

        output_path = OUTPUT_DIR / (filepath.name.removesuffix(".msgpack.gz") + ".xml")
        output_path.write_text(tenhou_xml)
        logger.info("  -> %s", output_path)
        converted += 1

    logger.info("Converted %d of %d file(s).", converted, len(replay_files))


if __name__ == "__main__":
    main()
