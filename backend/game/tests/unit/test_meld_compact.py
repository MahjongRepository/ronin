"""Unit tests for game-to-IMME bridge in meld_compact.py.

Tests round-trip encoding for each meld type, verifying that the vocabulary
mapping between game objects (FrozenMeld, MeldEvent) and the shared IMME
encoder's MeldData is correct.
"""

import pytest

from game.logic.enums import MeldViewType
from game.logic.events import MeldEvent
from game.logic.meld_compact import (
    frozen_meld_to_compact,
    frozen_meld_to_meld_data,
    meld_event_to_compact,
)
from game.logic.meld_wrapper import FrozenMeld
from shared.lib.melds import decode_meld_compact


class TestFrozenMeldToMeldData:
    """Verify vocabulary mapping from FrozenMeld types to wire MeldData types."""

    def test_unknown_meld_type_raises(self):
        """A meld_type not in the mapping raises ValueError."""
        meld = FrozenMeld(
            tiles=(0, 4, 8),
            meld_type="chi",
            opened=True,
            called_tile=0,
            who=1,
            from_who=0,
        )
        patched = meld.model_copy(update={"meld_type": "bogus"})
        with pytest.raises(ValueError, match="Unknown FrozenMeld type"):
            frozen_meld_to_meld_data(patched)


class TestFrozenMeldRoundTrip:
    """Encode FrozenMeld -> IMME int -> decode and verify all fields survive."""

    def test_chi_round_trip(self):
        # 1m-2m-3m chi, caller=1, from kamicha (seat 0), called tile is 1m copy 0
        meld = FrozenMeld(
            tiles=(0, 4, 8),
            meld_type=FrozenMeld.CHI,
            opened=True,
            called_tile=0,
            who=1,
            from_who=0,
        )
        compact = frozen_meld_to_compact(meld)
        decoded = decode_meld_compact(compact)
        assert decoded["meld_type"] == "chi"
        assert decoded["caller_seat"] == 1
        assert decoded["from_seat"] == 0
        assert sorted(decoded["tile_ids"]) == [0, 4, 8]
        assert decoded["called_tile_id"] == 0

    def test_pon_round_trip(self):
        # Pon of 1m (copies 0,1,2), caller=2, from seat 0
        meld = FrozenMeld(
            tiles=(0, 1, 2),
            meld_type=FrozenMeld.PON,
            opened=True,
            called_tile=0,
            who=2,
            from_who=0,
        )
        compact = frozen_meld_to_compact(meld)
        decoded = decode_meld_compact(compact)
        assert decoded["meld_type"] == "pon"
        assert decoded["caller_seat"] == 2
        assert decoded["from_seat"] == 0
        assert sorted(decoded["tile_ids"]) == [0, 1, 2]
        assert decoded["called_tile_id"] == 0

    def test_open_kan_round_trip(self):
        # Open kan of 1m (all 4 copies), caller=3, from seat 1
        meld = FrozenMeld(
            tiles=(0, 1, 2, 3),
            meld_type=FrozenMeld.KAN,
            opened=True,
            called_tile=0,
            who=3,
            from_who=1,
        )
        compact = frozen_meld_to_compact(meld)
        decoded = decode_meld_compact(compact)
        assert decoded["meld_type"] == "open_kan"
        assert decoded["caller_seat"] == 3
        assert decoded["from_seat"] == 1
        assert sorted(decoded["tile_ids"]) == [0, 1, 2, 3]
        assert decoded["called_tile_id"] == 0

    def test_closed_kan_round_trip(self):
        # Closed kan of 2m (tile_34=1, copies 4,5,6,7), caller=0
        meld = FrozenMeld(
            tiles=(4, 5, 6, 7),
            meld_type=FrozenMeld.KAN,
            opened=False,
            who=0,
            from_who=None,
            called_tile=None,
        )
        compact = frozen_meld_to_compact(meld)
        decoded = decode_meld_compact(compact)
        assert decoded["meld_type"] == "closed_kan"
        assert decoded["caller_seat"] == 0
        assert decoded["from_seat"] is None
        assert sorted(decoded["tile_ids"]) == [4, 5, 6, 7]
        assert decoded["called_tile_id"] is None

    def test_shouminkan_round_trip(self):
        # Added kan (shouminkan) of 1m, caller=1, from seat 3
        meld = FrozenMeld(
            tiles=(0, 1, 2, 3),
            meld_type=FrozenMeld.SHOUMINKAN,
            opened=True,
            called_tile=0,
            who=1,
            from_who=3,
        )
        compact = frozen_meld_to_compact(meld)
        decoded = decode_meld_compact(compact)
        assert decoded["meld_type"] == "added_kan"
        assert decoded["caller_seat"] == 1
        assert decoded["from_seat"] == 3
        assert sorted(decoded["tile_ids"]) == [0, 1, 2, 3]
        assert decoded["called_tile_id"] == 0

    def test_chankan_round_trip(self):
        # Chankan uses same wire type as shouminkan (added_kan)
        meld = FrozenMeld(
            tiles=(0, 1, 2, 3),
            meld_type=FrozenMeld.CHANKAN,
            opened=True,
            called_tile=1,
            who=2,
            from_who=0,
        )
        compact = frozen_meld_to_compact(meld)
        decoded = decode_meld_compact(compact)
        assert decoded["meld_type"] == "added_kan"
        assert decoded["caller_seat"] == 2
        assert decoded["from_seat"] == 0
        assert decoded["called_tile_id"] == 1

    def test_all_four_seats_produce_distinct_values(self):
        # Same pon from different seats should produce different IMME values
        compacts = set()
        for seat in range(4):
            from_seat = (seat + 1) % 4
            meld = FrozenMeld(
                tiles=(0, 1, 2),
                meld_type=FrozenMeld.PON,
                opened=True,
                called_tile=0,
                who=seat,
                from_who=from_seat,
            )
            compacts.add(frozen_meld_to_compact(meld))
        assert len(compacts) == 4


class TestMeldEventRoundTrip:
    """Encode MeldEvent -> IMME int -> decode and verify fields."""

    def test_chi_event_round_trip(self):
        event = MeldEvent(
            meld_type=MeldViewType.CHI,
            caller_seat=2,
            from_seat=1,
            tile_ids=[36, 40, 44],
            called_tile_id=36,
        )
        compact = meld_event_to_compact(event)
        decoded = decode_meld_compact(compact)
        assert decoded["meld_type"] == "chi"
        assert decoded["caller_seat"] == 2
        assert decoded["from_seat"] == 1
        assert sorted(decoded["tile_ids"]) == [36, 40, 44]

    def test_pon_event_round_trip(self):
        event = MeldEvent(
            meld_type=MeldViewType.PON,
            caller_seat=0,
            from_seat=3,
            tile_ids=[0, 1, 2],
            called_tile_id=2,
        )
        compact = meld_event_to_compact(event)
        decoded = decode_meld_compact(compact)
        assert decoded["meld_type"] == "pon"
        assert decoded["caller_seat"] == 0
        assert decoded["from_seat"] == 3
        assert decoded["called_tile_id"] == 2

    def test_open_kan_event_round_trip(self):
        event = MeldEvent(
            meld_type=MeldViewType.OPEN_KAN,
            caller_seat=1,
            from_seat=2,
            tile_ids=[8, 9, 10, 11],
            called_tile_id=9,
        )
        compact = meld_event_to_compact(event)
        decoded = decode_meld_compact(compact)
        assert decoded["meld_type"] == "open_kan"
        assert decoded["caller_seat"] == 1
        assert decoded["called_tile_id"] == 9

    def test_closed_kan_event_round_trip(self):
        event = MeldEvent(
            meld_type=MeldViewType.CLOSED_KAN,
            caller_seat=3,
            from_seat=None,
            tile_ids=[120, 121, 122, 123],
            called_tile_id=None,
        )
        compact = meld_event_to_compact(event)
        decoded = decode_meld_compact(compact)
        assert decoded["meld_type"] == "closed_kan"
        assert decoded["caller_seat"] == 3
        assert decoded["from_seat"] is None
        assert decoded["called_tile_id"] is None

    def test_added_kan_event_round_trip(self):
        event = MeldEvent(
            meld_type=MeldViewType.ADDED_KAN,
            caller_seat=0,
            from_seat=2,
            tile_ids=[0, 1, 2, 3],
            called_tile_id=0,
        )
        compact = meld_event_to_compact(event)
        decoded = decode_meld_compact(compact)
        assert decoded["meld_type"] == "added_kan"
        assert decoded["caller_seat"] == 0
        assert decoded["from_seat"] == 2
