"""Tests for compact meld encoding/decoding."""

import pytest

from shared.lib.melds.compact import (
    ANKAN_COUNT,
    ANKAN_OFFSET,
    CHI_COUNT,
    DAIMINKAN_COUNT,
    DAIMINKAN_OFFSET,
    EVENT_TYPE_MELD,
    PON_COUNT,
    PON_OFFSET,
    SHOUMINKAN_COUNT,
    SHOUMINKAN_OFFSET,
    _encode_ankan,
    _encode_chi,
    _encode_daiminkan,
    _encode_pon,
    _encode_shouminkan,
    decode_game_event,
    decode_meld_compact,
    encode_game_event,
    encode_meld_compact,
)
from shared.lib.melds.fixtures import build_all_fixtures


class TestRoundTrip:
    """Encode every fixture to game event format and decode back; result must match."""

    @pytest.fixture
    def all_fixtures(self) -> list:
        return build_all_fixtures()

    def test_all_fixtures_round_trip(self, all_fixtures: list) -> None:
        for i, original in enumerate(all_fixtures):
            decoded = decode_game_event(encode_game_event(original))
            assert sorted(original["tile_ids"]) == sorted(decoded["tile_ids"]), f"[{i}] tile_ids"
            assert original["meld_type"] == decoded["meld_type"], f"[{i}] meld_type"
            assert original["caller_seat"] == decoded["caller_seat"], f"[{i}] caller_seat"
            assert original["from_seat"] == decoded["from_seat"], f"[{i}] from_seat"
            assert original["called_tile_id"] == decoded["called_tile_id"], f"[{i}] called_tile_id"

    def test_all_fixtures_produce_integer_payloads(self, all_fixtures: list) -> None:
        """Every meld type encodes to an integer payload."""
        for i, wire in enumerate(all_fixtures):
            event = encode_game_event(wire)
            assert isinstance(event["m"], int), (
                f"[{i}] {wire['meld_type']} produced {type(event['m']).__name__}, expected int"
            )


class TestChiEncoding:
    """Verify chi melds are encoded as integers and decode correctly."""

    def test_chi_produces_integer_payload(self) -> None:
        wire = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 0,
            "from_seat": 3,
            "tile_ids": [0, 4, 8],
            "called_tile_id": 0,
        }
        assert isinstance(encode_meld_compact(wire), int)

    def test_chi_different_copies_produce_different_integers(self) -> None:
        """Two chi melds with same base sequence but different tile copies encode differently."""
        wire1 = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 0,
            "from_seat": 3,
            "tile_ids": [0, 4, 8],
            "called_tile_id": 0,
        }
        wire2 = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 0,
            "from_seat": 3,
            "tile_ids": [1, 5, 9],
            "called_tile_id": 1,
        }
        assert encode_meld_compact(wire1) != encode_meld_compact(wire2)

    def test_chi_different_called_position_produce_different_integers(self) -> None:
        """Calling low vs mid vs high tile in the same sequence encodes differently."""
        base = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 0,
            "from_seat": 3,
            "tile_ids": [0, 4, 8],
        }
        results = []
        for called in [0, 4, 8]:
            wire = {**base, "called_tile_id": called}
            results.append(encode_meld_compact(wire))
        assert len(set(results)) == 3

    def test_chi_round_trip_man_1_2_3(self) -> None:
        """1m-2m-3m chi, caller seat 0, called low tile."""
        wire = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 0,
            "from_seat": 3,
            "tile_ids": [0, 4, 8],
            "called_tile_id": 0,
        }
        decoded = decode_game_event(encode_game_event(wire))
        assert decoded == wire

    def test_chi_round_trip_sou_7_8_9(self) -> None:
        """7s-8s-9s chi, caller seat 2, called high tile (copy 3)."""
        # sou 7 = tile34 24, 8 = 25, 9 = 26
        wire = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 2,
            "from_seat": 1,
            "tile_ids": [24 * 4 + 2, 25 * 4 + 1, 26 * 4 + 3],
            "called_tile_id": 26 * 4 + 3,
        }
        decoded = decode_game_event(encode_game_event(wire))
        assert decoded == wire

    def test_chi_round_trip_pin_4_5_6_caller_3(self) -> None:
        """4p-5p-6p chi, caller seat 3, called mid tile."""
        # pin 4 = tile34 12, 5 = 13, 6 = 14
        wire = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 3,
            "from_seat": 2,
            "tile_ids": [12 * 4 + 3, 13 * 4 + 0, 14 * 4 + 2],
            "called_tile_id": 13 * 4 + 0,
        }
        decoded = decode_game_event(encode_game_event(wire))
        assert decoded == wire

    def test_chi_from_seat_is_always_kamicha(self) -> None:
        """Chi can only be called from the left player (kamicha)."""
        for caller in range(4):
            wire = {
                "type": "meld",
                "meld_type": "chi",
                "caller_seat": caller,
                "from_seat": (caller + 3) % 4,
                "tile_ids": [0, 4, 8],
                "called_tile_id": 0,
            }
            decoded = decode_game_event(encode_game_event(wire))
            assert decoded["from_seat"] == (caller + 3) % 4

    def test_chi_index_range(self) -> None:
        """All chi meld indices should be within the defined range."""
        fixtures = [m for m in build_all_fixtures() if m["meld_type"] == "chi"]
        for wire in fixtures:
            encoded = _encode_chi(wire)
            meld_index = encoded // 4
            assert 0 <= meld_index < CHI_COUNT, f"Chi meld_index {meld_index} out of range [0, {CHI_COUNT})"

    def test_chi_unsorted_tile_ids_still_round_trip(self) -> None:
        """Tile IDs in the wire format may not be sorted; encoding handles this."""
        wire = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 1,
            "from_seat": 0,
            "tile_ids": [8, 0, 4],
            "called_tile_id": 4,
        }
        decoded = decode_game_event(encode_game_event(wire))
        # Decoded tile_ids come out sorted (canonical form)
        assert sorted(decoded["tile_ids"]) == sorted(wire["tile_ids"])
        assert decoded["meld_type"] == "chi"
        assert decoded["caller_seat"] == 1
        assert decoded["from_seat"] == 0
        assert decoded["called_tile_id"] == 4


class TestPonEncoding:
    """Verify pon melds are encoded as integers and decode correctly."""

    def test_pon_produces_integer_payload(self) -> None:
        wire = {
            "type": "meld",
            "meld_type": "pon",
            "caller_seat": 1,
            "from_seat": 2,
            "tile_ids": [108, 109, 110],
            "called_tile_id": 110,
        }
        assert isinstance(encode_meld_compact(wire), int)

    def test_pon_different_missing_copies_produce_different_integers(self) -> None:
        """Two pon melds of the same tile type but different missing copies encode differently."""
        # 1m copies 0,1,2 (missing 3)
        wire1 = {
            "type": "meld",
            "meld_type": "pon",
            "caller_seat": 0,
            "from_seat": 1,
            "tile_ids": [0, 1, 2],
            "called_tile_id": 2,
        }
        # 1m copies 0,1,3 (missing 2)
        wire2 = {
            "type": "meld",
            "meld_type": "pon",
            "caller_seat": 0,
            "from_seat": 1,
            "tile_ids": [0, 1, 3],
            "called_tile_id": 3,
        }
        assert encode_meld_compact(wire1) != encode_meld_compact(wire2)

    def test_pon_different_from_seats_produce_different_integers(self) -> None:
        """Pon called from different opponents encodes differently."""
        results = []
        for frm in [1, 2, 3]:
            wire = {
                "type": "meld",
                "meld_type": "pon",
                "caller_seat": 0,
                "from_seat": frm,
                "tile_ids": [0, 1, 2],
                "called_tile_id": 2,
            }
            results.append(encode_meld_compact(wire))
        assert len(set(results)) == 3

    def test_pon_round_trip_man_1(self) -> None:
        """Pon of 1m (copies 0,1,3), caller seat 0, from seat 1."""
        wire = {
            "type": "meld",
            "meld_type": "pon",
            "caller_seat": 0,
            "from_seat": 1,
            "tile_ids": [0, 1, 3],
            "called_tile_id": 3,
        }
        decoded = decode_game_event(encode_game_event(wire))
        assert decoded == wire

    def test_pon_round_trip_honor_chun(self) -> None:
        """Pon of chun/red dragon (tile34=33), caller seat 2, from seat 0."""
        # chun = tile34 33, copies 0,1,2
        wire = {
            "type": "meld",
            "meld_type": "pon",
            "caller_seat": 2,
            "from_seat": 0,
            "tile_ids": [33 * 4, 33 * 4 + 1, 33 * 4 + 2],
            "called_tile_id": 33 * 4 + 1,
        }
        decoded = decode_game_event(encode_game_event(wire))
        assert decoded == wire

    def test_pon_round_trip_sou_5_from_toimen(self) -> None:
        """Pon of 5s (tile34=22) from toimen (across), caller seat 1, from seat 3."""
        # 5s = tile34 22, copies 1,2,3 (missing 0)
        wire = {
            "type": "meld",
            "meld_type": "pon",
            "caller_seat": 1,
            "from_seat": 3,
            "tile_ids": [22 * 4 + 1, 22 * 4 + 2, 22 * 4 + 3],
            "called_tile_id": 22 * 4 + 2,
        }
        decoded = decode_game_event(encode_game_event(wire))
        assert decoded == wire

    def test_pon_from_seat_preserved_for_all_offsets(self) -> None:
        """Pon from_seat is correctly preserved for shimocha, toimen, and kamicha."""
        for caller in range(4):
            for offset in [1, 2, 3]:
                frm = (caller + offset) % 4
                wire = {
                    "type": "meld",
                    "meld_type": "pon",
                    "caller_seat": caller,
                    "from_seat": frm,
                    "tile_ids": [0, 1, 2],
                    "called_tile_id": 0,
                }
                decoded = decode_game_event(encode_game_event(wire))
                assert decoded["from_seat"] == frm

    def test_pon_index_range(self) -> None:
        """All pon meld indices should be within the defined range."""
        fixtures = [m for m in build_all_fixtures() if m["meld_type"] == "pon"]
        for wire in fixtures:
            encoded = _encode_pon(wire)
            meld_index = encoded // 4
            assert PON_OFFSET <= meld_index < PON_OFFSET + PON_COUNT, (
                f"Pon meld_index {meld_index} out of range [{PON_OFFSET}, {PON_OFFSET + PON_COUNT})"
            )

    def test_pon_unsorted_tile_ids_still_round_trip(self) -> None:
        """Tile IDs in wire format may not be sorted; encoding handles this."""
        wire = {
            "type": "meld",
            "meld_type": "pon",
            "caller_seat": 0,
            "from_seat": 2,
            "tile_ids": [2, 0, 1],
            "called_tile_id": 2,
        }
        decoded = decode_game_event(encode_game_event(wire))
        assert sorted(decoded["tile_ids"]) == sorted(wire["tile_ids"])
        assert decoded["meld_type"] == "pon"
        assert decoded["caller_seat"] == 0
        assert decoded["from_seat"] == 2
        assert decoded["called_tile_id"] == 2


class TestShouminkanEncoding:
    """Verify shouminkan (added_kan) melds are encoded as integers and decode correctly."""

    def test_shouminkan_produces_integer_payload(self) -> None:
        wire = {
            "type": "meld",
            "meld_type": "added_kan",
            "caller_seat": 0,
            "from_seat": 1,
            "tile_ids": [0, 1, 2, 3],
            "called_tile_id": 2,
        }
        assert isinstance(encode_meld_compact(wire), int)

    def test_shouminkan_round_trip_terminal(self) -> None:
        """Shouminkan of 1m, caller seat 0, from seat 1, called copy 2."""
        wire = {
            "type": "meld",
            "meld_type": "added_kan",
            "caller_seat": 0,
            "from_seat": 1,
            "tile_ids": [0, 1, 2, 3],
            "called_tile_id": 2,
        }
        decoded = decode_game_event(encode_game_event(wire))
        assert decoded == wire

    def test_shouminkan_round_trip_honor(self) -> None:
        """Shouminkan of haku (tile34=31), caller seat 2, from seat 0."""
        # haku = tile34 31
        wire = {
            "type": "meld",
            "meld_type": "added_kan",
            "caller_seat": 2,
            "from_seat": 0,
            "tile_ids": [31 * 4, 31 * 4 + 1, 31 * 4 + 2, 31 * 4 + 3],
            "called_tile_id": 31 * 4 + 3,
        }
        decoded = decode_game_event(encode_game_event(wire))
        assert decoded == wire

    def test_shouminkan_different_called_copies_produce_different_integers(self) -> None:
        """Shouminkan with different called tiles encode differently."""
        results = []
        for called_copy in range(4):
            wire = {
                "type": "meld",
                "meld_type": "added_kan",
                "caller_seat": 0,
                "from_seat": 1,
                "tile_ids": [0, 1, 2, 3],
                "called_tile_id": called_copy,
            }
            results.append(encode_meld_compact(wire))
        assert len(set(results)) == 4

    def test_shouminkan_from_seat_preserved_for_all_offsets(self) -> None:
        """Shouminkan from_seat is correctly preserved for all opponents."""
        for caller in range(4):
            for offset in [1, 2, 3]:
                frm = (caller + offset) % 4
                wire = {
                    "type": "meld",
                    "meld_type": "added_kan",
                    "caller_seat": caller,
                    "from_seat": frm,
                    "tile_ids": [0, 1, 2, 3],
                    "called_tile_id": 2,
                }
                decoded = decode_game_event(encode_game_event(wire))
                assert decoded["from_seat"] == frm

    def test_shouminkan_index_range(self) -> None:
        """All shouminkan meld indices should be within the defined range."""
        fixtures = [m for m in build_all_fixtures() if m["meld_type"] == "added_kan"]
        for wire in fixtures:
            encoded = _encode_shouminkan(wire)
            meld_index = encoded // 4
            assert SHOUMINKAN_OFFSET <= meld_index < SHOUMINKAN_OFFSET + SHOUMINKAN_COUNT, (
                f"Shouminkan meld_index {meld_index} out of range "
                f"[{SHOUMINKAN_OFFSET}, {SHOUMINKAN_OFFSET + SHOUMINKAN_COUNT})"
            )


class TestDaiminkanEncoding:
    """Verify daiminkan (open_kan) melds are encoded as integers and decode correctly."""

    def test_daiminkan_produces_integer_payload(self) -> None:
        wire = {
            "type": "meld",
            "meld_type": "open_kan",
            "caller_seat": 0,
            "from_seat": 1,
            "tile_ids": [0, 1, 2, 3],
            "called_tile_id": 3,
        }
        assert isinstance(encode_meld_compact(wire), int)

    def test_daiminkan_round_trip_terminal(self) -> None:
        """Daiminkan of 1m, caller seat 0, from seat 1, called copy 3."""
        wire = {
            "type": "meld",
            "meld_type": "open_kan",
            "caller_seat": 0,
            "from_seat": 1,
            "tile_ids": [0, 1, 2, 3],
            "called_tile_id": 3,
        }
        decoded = decode_game_event(encode_game_event(wire))
        assert decoded == wire

    def test_daiminkan_round_trip_honor(self) -> None:
        """Daiminkan of chun (tile34=33), caller seat 1, from seat 3."""
        wire = {
            "type": "meld",
            "meld_type": "open_kan",
            "caller_seat": 1,
            "from_seat": 3,
            "tile_ids": [33 * 4, 33 * 4 + 1, 33 * 4 + 2, 33 * 4 + 3],
            "called_tile_id": 33 * 4 + 3,
        }
        decoded = decode_game_event(encode_game_event(wire))
        assert decoded == wire

    def test_daiminkan_different_from_seats_produce_different_integers(self) -> None:
        """Daiminkan called from different opponents encodes differently."""
        results = []
        for frm in [1, 2, 3]:
            wire = {
                "type": "meld",
                "meld_type": "open_kan",
                "caller_seat": 0,
                "from_seat": frm,
                "tile_ids": [0, 1, 2, 3],
                "called_tile_id": 3,
            }
            results.append(encode_meld_compact(wire))
        assert len(set(results)) == 3

    def test_daiminkan_from_seat_preserved_for_all_offsets(self) -> None:
        """Daiminkan from_seat is correctly preserved for all opponents."""
        for caller in range(4):
            for offset in [1, 2, 3]:
                frm = (caller + offset) % 4
                wire = {
                    "type": "meld",
                    "meld_type": "open_kan",
                    "caller_seat": caller,
                    "from_seat": frm,
                    "tile_ids": [0, 1, 2, 3],
                    "called_tile_id": 3,
                }
                decoded = decode_game_event(encode_game_event(wire))
                assert decoded["from_seat"] == frm

    def test_daiminkan_index_range(self) -> None:
        """All daiminkan meld indices should be within the defined range."""
        fixtures = [m for m in build_all_fixtures() if m["meld_type"] == "open_kan"]
        for wire in fixtures:
            encoded = _encode_daiminkan(wire)
            meld_index = encoded // 4
            assert DAIMINKAN_OFFSET <= meld_index < DAIMINKAN_OFFSET + DAIMINKAN_COUNT, (
                f"Daiminkan meld_index {meld_index} out of range "
                f"[{DAIMINKAN_OFFSET}, {DAIMINKAN_OFFSET + DAIMINKAN_COUNT})"
            )


class TestAnkanEncoding:
    """Verify ankan (closed_kan) melds are encoded as integers and decode correctly."""

    def test_ankan_produces_integer_payload(self) -> None:
        wire = {
            "type": "meld",
            "meld_type": "closed_kan",
            "caller_seat": 2,
            "from_seat": None,
            "tile_ids": [124, 125, 126, 127],
            "called_tile_id": None,
        }
        assert isinstance(encode_meld_compact(wire), int)

    def test_ankan_round_trip_chun(self) -> None:
        """Ankan of chun (tile34=33), caller seat 2."""
        wire = {
            "type": "meld",
            "meld_type": "closed_kan",
            "caller_seat": 2,
            "from_seat": None,
            "tile_ids": [33 * 4, 33 * 4 + 1, 33 * 4 + 2, 33 * 4 + 3],
            "called_tile_id": None,
        }
        decoded = decode_game_event(encode_game_event(wire))
        assert decoded == wire

    def test_ankan_round_trip_terminal(self) -> None:
        """Ankan of 1m (tile34=0), caller seat 0."""
        wire = {
            "type": "meld",
            "meld_type": "closed_kan",
            "caller_seat": 0,
            "from_seat": None,
            "tile_ids": [0, 1, 2, 3],
            "called_tile_id": None,
        }
        decoded = decode_game_event(encode_game_event(wire))
        assert decoded == wire

    def test_ankan_from_seat_is_none(self) -> None:
        """Ankan always has from_seat=None (no opponent involved)."""
        for caller in range(4):
            wire = {
                "type": "meld",
                "meld_type": "closed_kan",
                "caller_seat": caller,
                "from_seat": None,
                "tile_ids": [0, 1, 2, 3],
                "called_tile_id": None,
            }
            decoded = decode_game_event(encode_game_event(wire))
            assert decoded["from_seat"] is None
            assert decoded["called_tile_id"] is None

    def test_ankan_index_range(self) -> None:
        """All ankan meld indices should be within the defined range."""
        fixtures = [m for m in build_all_fixtures() if m["meld_type"] == "closed_kan"]
        for wire in fixtures:
            encoded = _encode_ankan(wire)
            meld_index = encoded // 4
            assert ANKAN_OFFSET <= meld_index < ANKAN_OFFSET + ANKAN_COUNT, (
                f"Ankan meld_index {meld_index} out of range [{ANKAN_OFFSET}, {ANKAN_OFFSET + ANKAN_COUNT})"
            )


class TestGameEvent:
    """Verify game event encode/decode: {"t": 0, "m": <IMME_int>}."""

    def test_encode_produces_t_and_m_keys(self) -> None:
        wire = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 0,
            "from_seat": 3,
            "tile_ids": [0, 4, 8],
            "called_tile_id": 0,
        }
        event = encode_game_event(wire)
        assert event["t"] == EVENT_TYPE_MELD
        assert isinstance(event["m"], int)

    def test_out_of_range_integer_raises(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            decode_game_event({"t": 0, "m": 999999})

    def test_unsupported_event_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported event type"):
            decode_game_event({"t": 99, "m": 0})

    def test_non_integer_payload_raises(self) -> None:
        with pytest.raises(TypeError, match="Expected integer payload"):
            decode_game_event({"t": 0, "m": "bad"})

    def test_bool_payload_raises(self) -> None:
        with pytest.raises(TypeError, match="Expected integer payload"):
            decode_game_event({"t": 0, "m": True})

    def test_unknown_meld_type_raises(self) -> None:
        wire = {
            "type": "meld",
            "meld_type": "unknown_type",
            "caller_seat": 0,
        }
        with pytest.raises(ValueError, match="Unknown meld type"):
            encode_game_event(wire)


class TestSeatValidation:
    """Verify that invalid seat values are rejected."""

    def test_pon_same_seat_raises(self) -> None:
        """Pon with from_seat == caller_seat should raise ValueError."""
        wire = {
            "type": "meld",
            "meld_type": "pon",
            "caller_seat": 0,
            "from_seat": 0,
            "tile_ids": [0, 1, 2],
            "called_tile_id": 2,
        }
        with pytest.raises(ValueError, match="Invalid from_seat/caller_seat"):
            encode_game_event(wire)

    def test_open_kan_same_seat_raises(self) -> None:
        """Daiminkan with from_seat == caller_seat should raise ValueError."""
        wire = {
            "type": "meld",
            "meld_type": "open_kan",
            "caller_seat": 2,
            "from_seat": 2,
            "tile_ids": [0, 1, 2, 3],
            "called_tile_id": 3,
        }
        with pytest.raises(ValueError, match="Invalid from_seat/caller_seat"):
            encode_game_event(wire)

    def test_added_kan_same_seat_raises(self) -> None:
        """Shouminkan with from_seat == caller_seat should raise ValueError."""
        wire = {
            "type": "meld",
            "meld_type": "added_kan",
            "caller_seat": 1,
            "from_seat": 1,
            "tile_ids": [0, 1, 2, 3],
            "called_tile_id": 2,
        }
        with pytest.raises(ValueError, match="Invalid from_seat/caller_seat"):
            encode_game_event(wire)

    def test_caller_seat_out_of_range_raises(self) -> None:
        """caller_seat outside 0-3 should raise ValueError."""
        wire = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 5,
            "from_seat": 4,
            "tile_ids": [0, 4, 8],
            "called_tile_id": 0,
        }
        with pytest.raises(ValueError, match="caller_seat must be"):
            encode_game_event(wire)

    def test_caller_seat_negative_raises(self) -> None:
        """Negative caller_seat should raise ValueError."""
        wire = {
            "type": "meld",
            "meld_type": "pon",
            "caller_seat": -1,
            "from_seat": 1,
            "tile_ids": [0, 1, 2],
            "called_tile_id": 2,
        }
        with pytest.raises(ValueError, match="caller_seat must be"):
            encode_game_event(wire)

    def test_from_seat_out_of_range_raises(self) -> None:
        """from_seat outside 0-3 should raise ValueError."""
        wire = {
            "type": "meld",
            "meld_type": "pon",
            "caller_seat": 0,
            "from_seat": 6,
            "tile_ids": [0, 1, 2],
            "called_tile_id": 2,
        }
        with pytest.raises(ValueError, match="from_seat must be"):
            encode_game_event(wire)

    def test_caller_seat_float_raises(self) -> None:
        """Float caller_seat like 1.0 should raise ValueError."""
        wire = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 1.0,
            "from_seat": 0,
            "tile_ids": [0, 4, 8],
            "called_tile_id": 0,
        }
        with pytest.raises(ValueError, match="caller_seat must be"):
            encode_game_event(wire)

    def test_from_seat_float_raises(self) -> None:
        """Float from_seat like 1.0 should raise ValueError."""
        wire = {
            "type": "meld",
            "meld_type": "pon",
            "caller_seat": 0,
            "from_seat": 1.0,
            "tile_ids": [0, 1, 2],
            "called_tile_id": 2,
        }
        with pytest.raises(ValueError, match="from_seat must be"):
            encode_game_event(wire)

    def test_caller_seat_bool_raises(self) -> None:
        """Bool caller_seat like True should raise ValueError."""
        wire = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": True,
            "from_seat": 0,
            "tile_ids": [0, 4, 8],
            "called_tile_id": 0,
        }
        with pytest.raises(ValueError, match="caller_seat must be"):
            encode_game_event(wire)

    def test_chi_wrong_from_seat_raises(self) -> None:
        """Chi with from_seat != kamicha should raise ValueError."""
        wire = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 0,
            "from_seat": 1,
            "tile_ids": [0, 4, 8],
            "called_tile_id": 0,
        }
        with pytest.raises(ValueError, match="Chi from_seat must be kamicha"):
            encode_game_event(wire)

    def test_chi_from_seat_out_of_range_raises(self) -> None:
        """Chi with from_seat outside 0-3 should raise ValueError."""
        wire = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 0,
            "from_seat": 5,
            "tile_ids": [0, 4, 8],
            "called_tile_id": 0,
        }
        with pytest.raises(ValueError, match="from_seat must be an integer 0-3"):
            encode_game_event(wire)

    def test_chi_from_seat_float_raises(self) -> None:
        """Chi with float from_seat should raise ValueError."""
        wire = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 0,
            "from_seat": 3.0,
            "tile_ids": [0, 4, 8],
            "called_tile_id": 0,
        }
        with pytest.raises(ValueError, match="from_seat must be an integer 0-3"):
            encode_game_event(wire)


class TestNegativeInteger:
    """Verify negative integers are rejected by decode_meld_compact."""

    def test_negative_integer_raises(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            decode_meld_compact(-1)

    def test_large_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            decode_meld_compact(-999)

    def test_bool_true_raises(self) -> None:
        value: int = True
        with pytest.raises(TypeError, match="Expected integer"):
            decode_meld_compact(value)

    def test_bool_false_raises(self) -> None:
        value: int = False
        with pytest.raises(TypeError, match="Expected integer"):
            decode_meld_compact(value)


class TestNoneFieldValidation:
    """Verify that None fields are rejected where required."""

    def test_chi_with_none_called_tile_raises(self) -> None:
        wire = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 0,
            "from_seat": 3,
            "tile_ids": [0, 4, 8],
            "called_tile_id": None,
        }
        with pytest.raises(ValueError, match="called_tile_id"):
            encode_meld_compact(wire)

    def test_pon_with_none_called_tile_raises(self) -> None:
        wire = {
            "type": "meld",
            "meld_type": "pon",
            "caller_seat": 0,
            "from_seat": 1,
            "tile_ids": [0, 1, 2],
            "called_tile_id": None,
        }
        with pytest.raises(ValueError, match="called_tile_id"):
            encode_meld_compact(wire)

    def test_pon_with_none_from_seat_raises(self) -> None:
        wire = {
            "type": "meld",
            "meld_type": "pon",
            "caller_seat": 0,
            "from_seat": None,
            "tile_ids": [0, 1, 2],
            "called_tile_id": 2,
        }
        with pytest.raises(ValueError, match="from_seat"):
            encode_meld_compact(wire)

    def test_open_kan_with_none_called_tile_raises(self) -> None:
        wire = {
            "type": "meld",
            "meld_type": "open_kan",
            "caller_seat": 0,
            "from_seat": 1,
            "tile_ids": [0, 1, 2, 3],
            "called_tile_id": None,
        }
        with pytest.raises(ValueError, match="called_tile_id"):
            encode_meld_compact(wire)

    def test_open_kan_with_none_from_seat_raises(self) -> None:
        wire = {
            "type": "meld",
            "meld_type": "open_kan",
            "caller_seat": 0,
            "from_seat": None,
            "tile_ids": [0, 1, 2, 3],
            "called_tile_id": 3,
        }
        with pytest.raises(ValueError, match="from_seat"):
            encode_meld_compact(wire)

    def test_added_kan_with_none_called_tile_raises(self) -> None:
        wire = {
            "type": "meld",
            "meld_type": "added_kan",
            "caller_seat": 0,
            "from_seat": 1,
            "tile_ids": [0, 1, 2, 3],
            "called_tile_id": None,
        }
        with pytest.raises(ValueError, match="called_tile_id"):
            encode_meld_compact(wire)

    def test_added_kan_with_none_from_seat_raises(self) -> None:
        wire = {
            "type": "meld",
            "meld_type": "added_kan",
            "caller_seat": 0,
            "from_seat": None,
            "tile_ids": [0, 1, 2, 3],
            "called_tile_id": 2,
        }
        with pytest.raises(ValueError, match="from_seat"):
            encode_meld_compact(wire)


class TestChiValidation:
    """Chi encoder rejects invalid tile configurations."""

    def test_chi_with_honor_tiles_raises(self) -> None:
        """Chi with honor tiles (tile_34 >= 27) raises ValueError."""
        wire = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 1,
            "from_seat": 0,
            "tile_ids": [108, 112, 116],  # tile_34=27,28,29 (E,S,W)
            "called_tile_id": 108,
        }
        with pytest.raises(ValueError, match="Chi tiles must be suited"):
            encode_meld_compact(wire)

    def test_chi_starting_at_position_8_in_suit_raises(self) -> None:
        """Chi cannot start at position 7+ in a suit (max sequence start is 6)."""
        # 8m-9m-? has start_in_suit=7, which is invalid
        wire = {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 1,
            "from_seat": 0,
            "tile_ids": [28, 32, 36],  # tile_34=7,8,9 -> start_in_suit=7
            "called_tile_id": 28,
        }
        with pytest.raises(ValueError, match="Chi sequence cannot start"):
            encode_meld_compact(wire)
