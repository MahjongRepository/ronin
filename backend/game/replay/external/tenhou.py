"""
Tenhou XML replay format converter.

All rights related to tenhou XML replay format are reserved by tenhou.net.
This converter is not affiliated with tenhou.net.

Convert Ronin replay files to tenhou.net XML format.
We need that compatibility with services that use tenhou XML as a common replay format.

Load all files from data/replays/ and write tenhou XML files to data/tenhou_replays/.

Replay files use the compact wire format with integer event types and short field aliases:
- GAME_STARTED (t=8): game ID, player names, seed
- ROUND_STARTED (t=9, merged): all players' tiles, dora indicators, round metadata, scores
- DRAW (t=1): packed seat+tile_id in "d" field
- DISCARD (t=2): packed seat+tile_id+flags in "d" field
- RIICHI_DECLARED (t=5): seat that declared riichi (score deduction)
- MELD (t=0): compact IMME-encoded meld integer in "m" field
- DORA_REVEALED (t=6): single revealed dora tile_id after kan
- ROUND_END (t=4): round result with winner closed_tiles/melds/win_tile embedded
- GAME_END (t=10): final standings with scores and placement deltas
"""

import json
import logging
from pathlib import Path
from typing import Any

from mahjong.hand_calculating.yaku_config import YAKU_ID_TO_TENHOU_ID

from game.logic.enums import WireEventType, WireRoundResultType
from game.logic.types import WIRE_SCORE_DIVISOR
from game.messaging.compact import decode_discard, decode_draw
from shared.lib.melds.compact import decode_meld_compact

logger = logging.getLogger(__name__)

REPLAYS_DIR = Path("backend/data/replays")
OUTPUT_DIR = Path("backend/data/tenhou_replays")

DRAW_LETTERS = ["T", "U", "V", "W"]
DISCARD_LETTERS = ["D", "E", "F", "G"]

ABORTIVE_REASON_TO_TENHOU = {
    "nine_terminals": "yao9",
    "four_winds": "kaze4",
    "four_kans": "kan4",
    "four_riichi": "reach4",
    "triple_ron": "ron3",
}

# Han thresholds for tenhou limit field.
_HAN_MANGAN = 5
_HAN_HANEMAN = 6
_HAN_BAIMAN = 8
_HAN_SANBAIMAN = 11
_HAN_YAKUMAN = 13


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

    if meld_type == "chi":
        return _encode_chi(tiles, called_tile, who, meld_event["from_seat"])
    if meld_type == "pon":
        return _encode_pon(tiles, called_tile, who, meld_event["from_seat"])
    if meld_type == "added_kan":
        tile = called_tile if called_tile is not None else sorted(tiles)[0]
        source: int = meld_event.get("from_seat", who)
        added = meld_event.get("_added_tile")
        return _encode_pon(tiles, tile, who, source, is_shouminkan=True, added_tile=added)
    if meld_type == "closed_kan":
        tile = called_tile if called_tile is not None else sorted(tiles)[0]
        return _encode_kan(tiles, tile, who, who)
    if meld_type == "open_kan":
        return _encode_kan(tiles, called_tile, who, meld_event["from_seat"])

    return "0"


def build_yaku_string(yaku_list: list[dict[str, Any]]) -> str:
    """Build tenhou yaku string from per-yaku breakdown in replay data.

    Each yaku dict contains yi (yaku_id) and han, which are passed through
    with only an ID translation to tenhou format.
    """
    parts = []
    for yaku in yaku_list:
        tenhou_id = YAKU_ID_TO_TENHOU_ID.get(yaku["yi"])
        if tenhou_id is not None:
            parts.append(f"{tenhou_id},{yaku['han']}")
    return ",".join(parts)


def _format_sc(scores: dict[str, int], score_changes: dict[str, int]) -> str:
    """Format the sc attribute: 'score0,change0,score1,change1,...' (in hundreds).

    Both scores and score_changes are dicts with string keys in wire format
    (already divided by WIRE_SCORE_DIVISOR, i.e. in hundreds).
    """
    parts = []
    for i in range(4):
        score = scores.get(str(i), 0)
        change = score_changes.get(str(i), 0)
        parts.append(f"{score},{change}")
    return ",".join(parts)


def _hand_payment_from_winner_change(
    winner_change_wire: int,
    riichi_sticks_collected: int,
) -> int:
    """Compute the hand payment for the tenhou ten attribute.

    winner_change_wire is in wire format (divided by WIRE_SCORE_DIVISOR).
    Tenhou ten uses full points (not hundreds), so convert back.
    Tenhou ten includes honba but excludes riichi.
    """
    riichi_bonus = riichi_sticks_collected * 1000
    return winner_change_wire * WIRE_SCORE_DIVISOR - riichi_bonus


def _compute_limit(han: int) -> int:
    """Compute the tenhou limit field from han count.

    0 = below mangan, 1 = mangan, 2 = haneman, 3 = baiman,
    4 = sanbaiman, 5 = yakuman.
    """
    if han >= _HAN_YAKUMAN:
        return 5
    if han >= _HAN_SANBAIMAN:
        return 4
    if han >= _HAN_BAIMAN:
        return 3
    if han >= _HAN_HANEMAN:
        return 2
    if han >= _HAN_MANGAN:
        return 1
    return 0


def _format_ura_dora_attr(ura_dora_indicators: list[int] | None) -> str:
    """Format the doraHaiUra attribute, or empty string when absent."""
    if not ura_dora_indicators:
        return ""
    ura_string = ",".join(str(d) for d in ura_dora_indicators)
    return f' doraHaiUra="{ura_string}"'


class TenhouConverter:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = events
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
        self.last_discard_tile: int | None = None
        self._round_riichi_count: int = 0
        self._seat_melds: dict[int, list[str]] = {}
        # Track pon tile lists per seat so added-kan can identify the added tile.
        # Key: (caller_seat, tile_group), Value: list of pon tile IDs
        self._pon_history: dict[tuple[int, int], list[int]] = {}

    @property
    def _total_riichi_sticks(self) -> int:
        """Riichi sticks on the table: carryovers from previous rounds plus deposits this round."""
        return self.table_riichi_sticks + self._round_riichi_count

    def convert(self) -> str:
        for event in self.events:
            self._process_event(event)
        return "".join(self.tags)

    def _process_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("t")
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

    def _handle_game_started(self, event: dict[str, Any]) -> None:
        seed = event["sd"]
        players = sorted(event["p"], key=lambda p: p["s"])
        first_dealer = event.get("dl", 0)

        self.tags.append('<mjloggm ver="2.3">')
        rng_version = event.get("rv", "")
        self.tags.append(f'<SHUFFLE seed="{seed}" ref="{rng_version}"/>')
        self.tags.append('<GO type="9" lobby="0"/>')

        names = [p["nm"] for p in players]
        self.tags.append(
            f'<UN n0="{names[0]}" n1="{names[1]}" '
            f'n2="{names[2]}" n3="{names[3]}" '
            f'dan="0,0,0,0" rate="1500.00,1500.00,1500.00,1500.00" sx="M,M,M,M"/>',
        )
        self.tags.append(f'<TAIKYOKU oya="{first_dealer}"/>')

    # -- Round started (merged, 1 per round) ----------------------------------

    def _handle_round_started(self, event: dict[str, Any]) -> None:
        wind_index = event["w"]
        self.round_wind_number = wind_index * 4 + event["dl"]
        self.honba = event["h"]
        self.table_riichi_sticks = event["r"]
        self.dealer = event["dl"]
        self.dora_indicators = event["di"]
        self.dice = event.get("dc", [0, 0])

        self.hands = {}
        for player in event["p"]:
            self.scores[player["s"]] = player["sc"]
            self.hands[player["s"]] = player["tl"]

        self._emit_init()

    # -- Round init -----------------------------------------------------------

    def _emit_init(self) -> None:
        self.last_discard_tile = None
        self._round_riichi_count = 0
        self._seat_melds = {}

        scores_str = ",".join(str(s) for s in self.scores)
        first_dora = self.dora_indicators[0] if self.dora_indicators else 0
        dice0, dice1 = self.dice

        hai_strs = []
        for seat in range(4):
            tiles = self.hands.get(seat, [])
            hai_strs.append(",".join(str(t) for t in tiles))

        seed_attr = f"{self.round_wind_number},{self.honba},{self.table_riichi_sticks},{dice0},{dice1},{first_dora}"
        self.tags.append(
            f'<INIT seed="{seed_attr}" '
            f'ten="{scores_str}" oya="{self.dealer}" '
            f'hai0="{hai_strs[0]}" hai1="{hai_strs[1]}" hai2="{hai_strs[2]}" hai3="{hai_strs[3]}"/>',
        )

    # -- Draw (packed seat+tile_id) -------------------------------------------

    def _handle_draw(self, event: dict[str, Any]) -> None:
        seat, tile = decode_draw(event["d"])
        self.tags.append(f"<{DRAW_LETTERS[seat]}{tile}/>")

    # -- Dora revealed --------------------------------------------------------

    def _handle_dora_revealed(self, event: dict[str, Any]) -> None:
        tile_id = event["ti"]
        self.dora_indicators.append(tile_id)
        self.tags.append(f'<DORA hai="{tile_id}"/>')

    # -- Discard (packed seat+tile_id+flags) ----------------------------------

    def _handle_discard(self, event: dict[str, Any]) -> None:
        seat, tile, _is_tsumogiri, is_riichi = decode_discard(event["d"])

        if is_riichi:
            self.tags.append(f'<REACH who="{seat}" step="1"/>')

        # Always use uppercase discard letters. The tenhou viewer's scroll-back
        # REINIT builder (mg function) only handles uppercase D/E/F/G; lowercase
        # d/e/f/g tsumogiri tags are silently skipped, leaving tiles in hands and
        # causing "can't access property X, x is undefined" crashes. The viewer's
        # D handler detects tsumogiri via tile ID comparison (l === h[0]), so
        # uppercase tags produce identical visual results.
        self.tags.append(f"<{DISCARD_LETTERS[seat]}{tile}/>")
        self.last_discard_tile = tile

    # -- Riichi ---------------------------------------------------------------

    def _handle_riichi_declared(self, event: dict[str, Any]) -> None:
        seat = event["s"]
        self._round_riichi_count += 1
        self.tags.append(f'<REACH who="{seat}" step="2"/>')

    # -- Meld (compact IMME encoding) -----------------------------------------

    def _handle_meld(self, event: dict[str, Any]) -> None:
        meld_data = decode_meld_compact(event["m"])

        who = meld_data["caller_seat"]
        tiles = meld_data["tile_ids"]
        tile_group = sorted(tiles)[0] // 4

        meld_event = dict(meld_data)

        # For added kan, identify the added tile using the original pon's tiles.
        if meld_data["meld_type"] == "added_kan":
            pon_key = (who, tile_group)
            if pon_key in self._pon_history:
                pon_tiles = self._pon_history[pon_key]
                added_tile = next(t for t in tiles if t not in pon_tiles)
                meld_event["_added_tile"] = added_tile

        # Record pon tiles for later added-kan lookup.
        if meld_data["meld_type"] == "pon":
            self._pon_history[(who, tile_group)] = list(tiles)

        meld_str = encode_meld(meld_event)
        self._seat_melds.setdefault(who, []).append(meld_str)
        self.tags.append(f'<N who="{who}" m="{meld_str}" />')

    # -- Round end ------------------------------------------------------------

    def _handle_round_end(self, event: dict[str, Any]) -> None:
        result_type = event["rt"]

        if result_type in (WireRoundResultType.RON, WireRoundResultType.TSUMO):
            self._emit_agari(event)
        elif result_type == WireRoundResultType.DOUBLE_RON:
            self._emit_double_ron(event)
        elif result_type == WireRoundResultType.EXHAUSTIVE_DRAW:
            self._emit_exhaustive_draw(event)
        elif result_type == WireRoundResultType.ABORTIVE_DRAW:
            self._emit_abortive_draw(event)

        self._update_scores_from_round_end(event)

    def _update_scores_from_round_end(self, event: dict[str, Any]) -> None:
        """Update tracked scores from round_end scores and score_changes."""
        scores = event.get("scs", {})
        changes = event.get("sch", {})
        for i in range(4):
            self.scores[i] = scores.get(str(i), 0) + changes.get(str(i), 0)

    def _emit_agari(self, result: dict[str, Any]) -> None:
        winner = result["ws"]
        from_who = result.get("ls", winner)
        hand = result["hr"]
        fu = hand["fu"]
        limit = _compute_limit(hand["han"])

        yaku_string = build_yaku_string(hand["yk"])
        sc_string = _format_sc(result["scs"], result["sch"])

        winner_change = result["sch"].get(str(winner), 0)
        riichi_sticks = result.get("rc", 0)
        payment = _hand_payment_from_winner_change(winner_change, riichi_sticks)

        # Winner's hand and winning tile from result
        hai_string = ",".join(str(t) for t in result.get("ct", []))
        if result["rt"] == WireRoundResultType.TSUMO:
            win_tile = result.get("wt", 0)
        else:
            win_tile = result.get("wt", self.last_discard_tile or 0)

        dora_string = ",".join(str(d) for d in self.dora_indicators)
        ura_dora_attr = _format_ura_dora_attr(result.get("ud"))

        meld_attr = ""
        if self._seat_melds.get(winner):
            meld_string = ",".join(self._seat_melds[winner])
            meld_attr = f' m="{meld_string}"'

        self.tags.append(
            f'<AGARI ba="{self.honba},{self._total_riichi_sticks}" '
            f'hai="{hai_string}"{meld_attr} machi="{win_tile}" ten="{fu},{payment},{limit}" '
            f'yaku="{yaku_string}" doraHai="{dora_string}"{ura_dora_attr} '
            f'who="{winner}" fromWho="{from_who}" sc="{sc_string}" />',
        )

    def _emit_double_ron(self, result: dict[str, Any]) -> None:
        """Emit one AGARI tag per winner in a double-ron."""
        loser = result["ls"]
        winning_tile = result["wt"]
        sc_string = _format_sc(result["scs"], result["sch"])
        dora_string = ",".join(str(d) for d in self.dora_indicators)

        for w in result["wn"]:
            winner = w["ws"]
            hand = w["hr"]
            fu = hand["fu"]
            limit = _compute_limit(hand["han"])
            yaku_string = build_yaku_string(hand["yk"])

            winner_change = result["sch"].get(str(winner), 0)
            riichi_sticks = w.get("rc", 0)
            payment = _hand_payment_from_winner_change(winner_change, riichi_sticks)

            hai_string = ",".join(str(t) for t in w.get("ct", []))
            ura_dora_attr = _format_ura_dora_attr(w.get("ud"))

            meld_attr = ""
            if self._seat_melds.get(winner):
                meld_string = ",".join(self._seat_melds[winner])
                meld_attr = f' m="{meld_string}"'

            self.tags.append(
                f'<AGARI ba="{self.honba},{self._total_riichi_sticks}" '
                f'hai="{hai_string}"{meld_attr} machi="{winning_tile}" '
                f'ten="{fu},{payment},{limit}" '
                f'yaku="{yaku_string}" doraHai="{dora_string}"{ura_dora_attr} '
                f'who="{winner}" fromWho="{loser}" sc="{sc_string}" />',
            )

    def _emit_exhaustive_draw(self, result: dict[str, Any]) -> None:
        sc_string = _format_sc(result["scs"], result["sch"])
        hai_attrs = ""
        for hand in result.get("th", []):
            seat = hand["s"]
            tiles_str = ",".join(str(t) for t in hand["ct"])
            hai_attrs += f' hai{seat}="{tiles_str}"'
        self.tags.append(
            f'<RYUUKYOKU ba="{self.honba},{self._total_riichi_sticks}" sc="{sc_string}"{hai_attrs} />',
        )

    def _emit_abortive_draw(self, result: dict[str, Any]) -> None:
        reason = result.get("rn", "")
        tenhou_reason = ABORTIVE_REASON_TO_TENHOU.get(reason, reason)

        sc_string = _format_sc(result["scs"], result.get("sch", {}))

        self.tags.append(
            f'<RYUUKYOKU type="{tenhou_reason}" ba="{self.honba},{self._total_riichi_sticks}" sc="{sc_string}"/>',
        )

    # -- Game end -------------------------------------------------------------

    def _handle_game_end(self, event: dict[str, Any]) -> None:
        standings = event["st"]
        owari_parts = []
        for seat in range(4):
            standing = next(s for s in standings if s["s"] == seat)
            final_score = float(standing["fs"])
            owari_parts.append(f"{standing['sc']},{final_score:.1f}")
        owari_string = ",".join(owari_parts)

        # Append owari to the last AGARI/RYUUKYOKU tag
        if self.tags[-1].endswith("/>"):
            self.tags[-1] = self.tags[-1][:-2] + f' owari="{owari_string}" />'

        self.tags.append("</mjloggm>")


def convert_replay(filepath: Path) -> str:
    with filepath.open() as f:
        content = f.read().strip()
    events = [json.loads(line) for line in content.split("\n") if line]
    converter = TenhouConverter(events)
    return converter.convert()


def main() -> None:
    # Remove all existing tenhou replays before generating new ones.
    if OUTPUT_DIR.exists():
        for old_file in OUTPUT_DIR.iterdir():
            old_file.unlink()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    replay_files = sorted(REPLAYS_DIR.glob("*.txt"))
    if not replay_files:
        logger.info("No replay files found in %s", REPLAYS_DIR)
        return

    for filepath in replay_files:
        logger.info("Converting %s...", filepath.name)
        tenhou_xml = convert_replay(filepath)
        output_path = OUTPUT_DIR / filepath.name
        output_path.write_text(tenhou_xml)
        logger.info("  -> %s", output_path)

    logger.info("Converted %d file(s).", len(replay_files))


if __name__ == "__main__":
    main()
