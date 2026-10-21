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
    @pytest.fixture
    def all_fixtures(self) -> list:
        return build_all_fixtures()

    def test_game_event_codec__when_all_fixtures_encoded__should_round_trip(self, all_fixtures: list):
        for i, original in enumerate(all_fixtures):
            decoded = decode_game_event(encode_game_event(original))
            assert sorted(original["tile_ids"]) == sorted(decoded["tile_ids"]), f"[{i}] tile_ids"
            assert original["meld_type"] == decoded["meld_type"], f"[{i}] meld_type"
            assert original["caller_seat"] == decoded["caller_seat"], f"[{i}] caller_seat"
            assert original["from_seat"] == decoded["from_seat"], f"[{i}] from_seat"
            assert original["called_tile_id"] == decoded["called_tile_id"], f"[{i}] called_tile_id"


class TestChiEncoding:
    def test_encode_meld_compact__when_chi_copies_differ__should_produce_different_integers(self):
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

    def test_encode_meld_compact__when_chi_called_position_differs__should_produce_different_integers(self):
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

    def test_game_event_codec__when_chi_tile_ids_unsorted__should_round_trip(self):
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
    def test_encode_meld_compact__when_pon_missing_copy_differs__should_produce_different_integers(self):
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

    def test_encode_meld_compact__when_pon_from_seat_differs__should_produce_different_integers(self):
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

    def test_game_event_codec__when_pon_tile_ids_unsorted__should_round_trip(self):
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
    def test_encode_meld_compact__when_added_kan_called_copy_differs__should_produce_different_integers(self):
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
    def test_encode_meld_compact__when_open_kan_from_seat_differs__should_produce_different_integers(self):
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
    def test_encode_game_event__when_meld__should_produce_t_and_m_keys(self):
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

    def test_decode_game_event__when_integer_out_of_range__should_raise(self):
        with pytest.raises(ValueError, match="out of range"):
            decode_game_event({"t": 0, "m": 999999})

    def test_decode_game_event__when_event_type_unsupported__should_raise(self):
        with pytest.raises(ValueError, match="Unsupported event type"):
            decode_game_event({"t": 99, "m": 0})

    def test_decode_game_event__when_payload_not_integer__should_raise(self):
        with pytest.raises(TypeError, match="Expected integer payload"):
            decode_game_event({"t": 0, "m": "bad"})

    def test_decode_game_event__when_payload_is_bool__should_raise(self):
        with pytest.raises(TypeError, match="Expected integer payload"):
            decode_game_event({"t": 0, "m": True})

    def test_encode_game_event__when_meld_type_unknown__should_raise(self):
        wire = {
            "type": "meld",
            "meld_type": "unknown_type",
            "caller_seat": 0,
        }
        with pytest.raises(ValueError, match="Unknown meld type"):
            encode_game_event(wire)


class TestSeatValidation:
    def test_encode_game_event__when_from_seat_equals_caller_seat__should_raise(self):
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

    def test_encode_game_event__when_seat_out_of_range__should_raise(self):
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

    def test_encode_game_event__when_seat_not_integer__should_raise(self):
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

    def test_encode_game_event__when_chi_from_seat_not_kamicha__should_raise(self):
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

    def test_encode_game_event__when_chi_from_seat_not_integer__should_raise(self):
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
    def test_decode_meld_compact__when_integer_negative__should_raise(self):
        with pytest.raises(ValueError, match="negative"):
            decode_meld_compact(-1)

    def test_decode_meld_compact__when_value_is_bool__should_raise(self):
        value: int = True
        with pytest.raises(TypeError, match="Expected integer"):
            decode_meld_compact(value)


class TestNoneFieldValidation:
    def test_encode_meld_compact__when_called_tile_is_none__should_raise(self):
        cases = [
            ("chi", [0, 4, 8], 3),
            ("pon", [0, 1, 2], 1),
            ("open_kan", [0, 1, 2, 3], 1),
            ("added_kan", [0, 1, 2, 3], 1),
        ]
        for meld_type, tile_ids, from_seat in cases:
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

    def test_encode_meld_compact__when_from_seat_is_none__should_raise(self):
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
    def test_encode_meld_compact__when_chi_uses_honor_tiles__should_raise(self):
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

    def test_encode_meld_compact__when_chi_starts_at_suit_position_8__should_raise(self):
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
