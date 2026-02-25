"""Tests for compact meld encoding/decoding."""

import pytest

from shared.lib.melds.compact import (
    EVENT_TYPE_MELD,
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


class TestChiEncoding:
    """Verify chi uniqueness and edge cases not covered by fixture round-trip."""

    def test_different_copies_produce_different_integers(self) -> None:
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

    def test_different_called_position_produce_different_integers(self) -> None:
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

    def test_unsorted_tile_ids_still_round_trip(self) -> None:
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
        assert sorted(decoded["tile_ids"]) == sorted(wire["tile_ids"])
        assert decoded["meld_type"] == "chi"
        assert decoded["caller_seat"] == 1
        assert decoded["from_seat"] == 0
        assert decoded["called_tile_id"] == 4


class TestPonEncoding:
    """Verify pon uniqueness and edge cases not covered by fixture round-trip."""

    def test_different_missing_copies_produce_different_integers(self) -> None:
        """Two pon melds of the same tile type but different missing copies encode differently."""
        wire1 = {
            "type": "meld",
            "meld_type": "pon",
            "caller_seat": 0,
            "from_seat": 1,
            "tile_ids": [0, 1, 2],
            "called_tile_id": 2,
        }
        wire2 = {
            "type": "meld",
            "meld_type": "pon",
            "caller_seat": 0,
            "from_seat": 1,
            "tile_ids": [0, 1, 3],
            "called_tile_id": 3,
        }
        assert encode_meld_compact(wire1) != encode_meld_compact(wire2)

    def test_different_from_seats_produce_different_integers(self) -> None:
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

    def test_unsorted_tile_ids_still_round_trip(self) -> None:
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
    """Verify shouminkan uniqueness not covered by fixture round-trip."""

    def test_different_called_copies_produce_different_integers(self) -> None:
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


class TestDaiminkanEncoding:
    """Verify daiminkan uniqueness not covered by fixture round-trip."""

    def test_different_from_seats_produce_different_integers(self) -> None:
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

    def test_same_seat_raises(self) -> None:
        """Meld with from_seat == caller_seat should raise ValueError."""
        for meld_type in ["pon", "open_kan", "added_kan"]:
            tile_ids = [0, 1, 2] if meld_type == "pon" else [0, 1, 2, 3]
            wire = {
                "type": "meld",
                "meld_type": meld_type,
                "caller_seat": 0,
                "from_seat": 0,
                "tile_ids": tile_ids,
                "called_tile_id": 2,
            }
            with pytest.raises(ValueError, match="Invalid from_seat/caller_seat"):
                encode_game_event(wire)

    def test_seat_out_of_range_raises(self) -> None:
        """Seats outside 0-3 should raise ValueError."""
        with pytest.raises(ValueError, match="caller_seat must be"):
            encode_game_event(
                {
                    "type": "meld",
                    "meld_type": "chi",
                    "caller_seat": 5,
                    "from_seat": 4,
                    "tile_ids": [0, 4, 8],
                    "called_tile_id": 0,
                },
            )
        with pytest.raises(ValueError, match="from_seat must be"):
            encode_game_event(
                {
                    "type": "meld",
                    "meld_type": "pon",
                    "caller_seat": 0,
                    "from_seat": 6,
                    "tile_ids": [0, 1, 2],
                    "called_tile_id": 2,
                },
            )

    def test_non_integer_seat_raises(self) -> None:
        """Float and bool seats should raise ValueError."""
        with pytest.raises(ValueError, match="caller_seat must be"):
            encode_game_event(
                {
                    "type": "meld",
                    "meld_type": "pon",
                    "caller_seat": 1.0,
                    "from_seat": 2,
                    "tile_ids": [0, 1, 2],
                    "called_tile_id": 2,
                },
            )
        with pytest.raises(ValueError, match="caller_seat must be"):
            encode_game_event(
                {
                    "type": "meld",
                    "meld_type": "chi",
                    "caller_seat": True,
                    "from_seat": 0,
                    "tile_ids": [0, 4, 8],
                    "called_tile_id": 0,
                },
            )
        with pytest.raises(ValueError, match="from_seat must be"):
            encode_game_event(
                {
                    "type": "meld",
                    "meld_type": "pon",
                    "caller_seat": 0,
                    "from_seat": 1.0,
                    "tile_ids": [0, 1, 2],
                    "called_tile_id": 2,
                },
            )

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

    def test_chi_non_integer_from_seat_raises(self) -> None:
        """Chi with non-integer from_seat should raise ValueError."""
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
    """Verify negative integers and bools are rejected by decode_meld_compact."""

    def test_negative_integer_raises(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            decode_meld_compact(-1)

    def test_bool_raises(self) -> None:
        value: int = True
        with pytest.raises(TypeError, match="Expected integer"):
            decode_meld_compact(value)


class TestNoneFieldValidation:
    """Verify that None fields are rejected where required."""

    def test_none_called_tile_raises(self) -> None:
        """All open meld types require called_tile_id."""
        for meld_type in ["chi", "pon", "open_kan", "added_kan"]:
            tile_ids = [0, 4, 8] if meld_type == "chi" else ([0, 1, 2] if meld_type == "pon" else [0, 1, 2, 3])
            from_seat = 3 if meld_type == "chi" else 1
            wire = {
                "type": "meld",
                "meld_type": meld_type,
                "caller_seat": 0,
                "from_seat": from_seat,
                "tile_ids": tile_ids,
                "called_tile_id": None,
            }
            with pytest.raises(ValueError, match="called_tile_id"):
                encode_meld_compact(wire)

    def test_none_from_seat_raises(self) -> None:
        """Open melds requiring from_seat reject None."""
        for meld_type in ["pon", "open_kan", "added_kan"]:
            tile_ids = [0, 1, 2] if meld_type == "pon" else [0, 1, 2, 3]
            wire = {
                "type": "meld",
                "meld_type": meld_type,
                "caller_seat": 0,
                "from_seat": None,
                "tile_ids": tile_ids,
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
