"""Compact meld encoding/decoding using IMME (Integer-Mapped Meld Encoding).

Encode each meld as a single integer. The encoding is lossless: decode(encode(meld))
reproduces every field of the original MeldData.

No external dependencies — this module can be used standalone in any project
that communicates with the protocol.

Tile representation
-------------------
Mahjong uses 136 physical tiles: 34 tile types x 4 copies each.

    tile_id  = tile_34 * 4 + copy        (136-format, 0-135)
    tile_34  = tile_id // 4              (34-format,  0-33)
    copy     = tile_id % 4               (physical copy, 0-3)

Tile types in 34-format:
    Man (characters): 0-8, Pin (circles): 9-17, Sou (bamboo): 18-26
    Honors: E=27, S=28, W=29, N=30, Haku=31, Hatsu=32, Chun=33

Integer layout
--------------
Every IMME value is structured as:

    value = meld_index * 4 + caller_seat

caller_seat (0-3) is always in the lowest 2 bits. meld_index falls into
one of five contiguous ranges that determine the meld type:

    Type         Offset   Count   Range
    ----         ------   -----   -----
    Chi             0     4032       0 ..  4031
    Pon          4032     1224    4032 ..  5255
    Shouminkan   5256      408    5256 ..  5663
    Daiminkan    5664      408    5664 ..  6071
    Ankan        6072       34    6072 ..  6105

Total: 6106 meld indices x 4 seats = 24424 values (fits in 15 bits).

Per-type encoding formulas
--------------------------
Chi (3 consecutive numbered tiles, called from kamicha):

    base_index  = suit_index * 7 + start_in_suit     (0-20: 3 suits x 7 sequences)
    copy_index  = copy_lo * 16 + copy_mid * 4 + copy_hi   (0-63: 4^3 copy combos)
    called_pos  = 0-2  (which of the 3 sorted tiles was the called discard)
    meld_index  = (base_index * 64 + copy_index) * 3 + called_pos

Pon (3 identical tiles, called from any opponent):

    tile_34      = 0-33
    missing_copy = 0-3  (which of the 4 physical copies is absent)
    called_pos   = 0-2  (index of the called tile in sorted tile_ids)
    from_offset  = (from_seat - caller_seat) % 4 - 1   (0-2)
    pon_index    = ((tile_34 * 4 + missing_copy) * 3 + called_pos) * 3 + from_offset
    meld_index   = PON_OFFSET + pon_index

Shouminkan / Daiminkan (open kan, all 4 copies):

    tile_34      = 0-33
    called_copy  = 0-3  (which physical copy was the called discard)
    from_offset  = 0-2  (same as pon)
    local_index  = (tile_34 * 4 + called_copy) * 3 + from_offset
    meld_index   = <TYPE_OFFSET> + local_index

Ankan (closed kan, all 4 copies from hand, no opponent):

    tile_34      = 0-33
    meld_index   = ANKAN_OFFSET + tile_34

Game event envelope
-------------------
For network transport, the IMME integer is wrapped in a dict:

    {"t": 0, "m": <imme_int>}

"t" is the event type (0 = meld). "m" is the IMME-encoded integer.
"""

from typing import Literal, TypedDict

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

type MeldType = Literal["chi", "pon", "added_kan", "open_kan", "closed_kan"]


class MeldData(TypedDict):
    """Wire-format representation of a mahjong meld.

    Attributes:
        type: Always ``"meld"``.
        meld_type: Meld category.
        caller_seat: Seat index (0-3) of the player declaring the meld.
        from_seat: Seat of the opponent whose discard was claimed.
            ``None`` for closed kan (all tiles drawn from hand).
        tile_ids: Tile IDs in 136-format (``tile_34 * 4 + copy``).
        called_tile_id: The specific tile claimed from the opponent's discard.
            ``None`` for closed kan. For added kan this is the original pon's
            called tile, not the added 4th tile.
    """

    type: Literal["meld"]
    meld_type: MeldType
    caller_seat: int
    from_seat: int | None
    tile_ids: list[int]
    called_tile_id: int | None


# ---------------------------------------------------------------------------
# IMME offset ranges
# ---------------------------------------------------------------------------

CHI_OFFSET = 0
CHI_COUNT = 4032  # 21 * 64 * 3
PON_OFFSET = CHI_OFFSET + CHI_COUNT  # 4032
PON_COUNT = 1224  # 34 * 4 * 3 * 3
SHOUMINKAN_OFFSET = PON_OFFSET + PON_COUNT  # 5256
SHOUMINKAN_COUNT = 408  # 34 * 4 * 3
DAIMINKAN_OFFSET = SHOUMINKAN_OFFSET + SHOUMINKAN_COUNT  # 5664
DAIMINKAN_COUNT = 408  # 34 * 4 * 3
ANKAN_OFFSET = DAIMINKAN_OFFSET + DAIMINKAN_COUNT  # 6072
ANKAN_COUNT = 34

EVENT_TYPE_MELD = 0

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def encode_meld_compact(meld: MeldData) -> int:
    """Encode a meld as a single IMME integer (no event envelope)."""
    caller_seat = meld.get("caller_seat")
    if not _is_strict_int(caller_seat) or caller_seat not in _VALID_SEATS:
        msg = f"caller_seat must be an integer 0-3, got {caller_seat!r}"
        raise ValueError(msg)

    encoder = _ENCODERS.get(meld["meld_type"])
    if encoder is None:
        msg = f"Unknown meld type: {meld['meld_type']}"
        raise ValueError(msg)
    return encoder(meld)


def decode_meld_compact(value: int) -> MeldData:
    """Decode an IMME integer back to a MeldData dict."""
    if not _is_strict_int(value):
        msg = f"Expected integer, got {type(value).__name__}"
        raise TypeError(msg)
    if value < 0:
        msg = f"Compact integer {value} is negative"
        raise ValueError(msg)

    caller_seat = value % 4
    meld_index = value // 4

    if meld_index < PON_OFFSET:
        return _decode_chi(meld_index - CHI_OFFSET, caller_seat)

    if meld_index < SHOUMINKAN_OFFSET:
        return _decode_pon(meld_index - PON_OFFSET, caller_seat)

    if meld_index < DAIMINKAN_OFFSET:
        return _decode_shouminkan(meld_index - SHOUMINKAN_OFFSET, caller_seat)

    if meld_index < ANKAN_OFFSET:
        return _decode_daiminkan(meld_index - DAIMINKAN_OFFSET, caller_seat)

    if meld_index < ANKAN_OFFSET + ANKAN_COUNT:
        return _decode_ankan(meld_index - ANKAN_OFFSET, caller_seat)

    msg = f"Compact integer {value} (meld_index={meld_index}) out of range"
    raise ValueError(msg)


def encode_game_event(meld: MeldData) -> dict[str, int]:
    """Encode a meld as a game event: ``{"t": 0, "m": <IMME_int>}``."""
    return {"t": EVENT_TYPE_MELD, "m": encode_meld_compact(meld)}


def decode_game_event(event: dict[str, int]) -> MeldData:
    """Decode a game event ``{"t": int, "m": int}`` back to a MeldData."""
    event_type = event["t"]
    if event_type != EVENT_TYPE_MELD:
        msg = f"Unsupported event type: {event_type}"
        raise ValueError(msg)
    payload = event["m"]
    if not _is_strict_int(payload):
        msg = f"Expected integer payload, got {type(payload).__name__}"
        raise TypeError(msg)
    return decode_meld_compact(payload)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_CHI_SEQS_PER_SUIT = 7
_SUITED_TILE_KINDS = 3  # man, pin, sou (suit_index 0-2, honors start at 3)
_VALID_SEATS = {0, 1, 2, 3}
_MISSING_COPIES = 4
_CALLED_POSITIONS = 3
_FROM_OFFSETS = 3
_CALLED_COPIES = 4


def _is_strict_int(value: object) -> bool:
    """Return True if value is an int but not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_from_offset(from_seat: int, caller_seat: int) -> int:
    """Compute and validate from_offset for open melds.

    from_offset encodes the relative seat distance (1, 2, or 3 steps clockwise)
    as 0, 1, or 2. A player cannot call their own discard, so from_seat must
    differ from caller_seat. Both seats must be in range 0-3.
    """
    if not _is_strict_int(from_seat) or from_seat not in _VALID_SEATS:
        msg = f"from_seat must be an integer 0-3, got {from_seat!r}"
        raise ValueError(msg)
    from_offset = (from_seat - caller_seat) % 4 - 1
    if from_offset not in (0, 1, 2):
        msg = (
            f"Invalid from_seat/caller_seat: from_seat={from_seat}, "
            f"caller_seat={caller_seat} produces from_offset={from_offset}"
        )
        raise ValueError(msg)
    return from_offset


# --- Chi ---


def _encode_chi(meld: MeldData) -> int:
    tile_ids = sorted(meld["tile_ids"])
    caller_seat = meld["caller_seat"]
    called_tile_id = meld["called_tile_id"]
    if called_tile_id is None:
        msg = "Chi meld requires called_tile_id"
        raise ValueError(msg)
    from_seat = meld.get("from_seat")
    expected_from = (caller_seat + 3) % 4
    if not _is_strict_int(from_seat) or from_seat not in _VALID_SEATS:
        msg = f"from_seat must be an integer 0-3, got {from_seat!r}"
        raise ValueError(msg)
    if from_seat != expected_from:
        msg = f"Chi from_seat must be kamicha ({expected_from}), got {from_seat}"
        raise ValueError(msg)

    tile34_lo = tile_ids[0] // 4
    copy_lo = tile_ids[0] % 4
    copy_mid = tile_ids[1] % 4
    copy_hi = tile_ids[2] % 4

    suit_index = tile34_lo // 9
    if suit_index >= _SUITED_TILE_KINDS:
        msg = f"Chi tiles must be suited (man/pin/sou), got tile_34={tile34_lo}"
        raise ValueError(msg)
    start_in_suit = tile34_lo % 9
    if start_in_suit >= _CHI_SEQS_PER_SUIT:
        msg = f"Chi sequence cannot start at position {start_in_suit} in suit (max {_CHI_SEQS_PER_SUIT - 1})"
        raise ValueError(msg)
    base_index = suit_index * _CHI_SEQS_PER_SUIT + start_in_suit

    copy_index = copy_lo * 16 + copy_mid * 4 + copy_hi
    called_pos = tile_ids.index(called_tile_id)

    meld_index = (base_index * 64 + copy_index) * 3 + called_pos
    return meld_index * 4 + caller_seat


def _decode_chi(meld_index: int, caller_seat: int) -> MeldData:
    called_pos = meld_index % 3
    remainder = meld_index // 3
    copy_index = remainder % 64
    base_index = remainder // 64

    suit_index = base_index // _CHI_SEQS_PER_SUIT
    start_in_suit = base_index % _CHI_SEQS_PER_SUIT
    tile34_lo = suit_index * 9 + start_in_suit

    copy_lo = copy_index // 16
    copy_mid = (copy_index // 4) % 4
    copy_hi = copy_index % 4

    tile_ids = [
        tile34_lo * 4 + copy_lo,
        (tile34_lo + 1) * 4 + copy_mid,
        (tile34_lo + 2) * 4 + copy_hi,
    ]

    return MeldData(
        type="meld",
        meld_type="chi",
        caller_seat=caller_seat,
        from_seat=(caller_seat + 3) % 4,
        tile_ids=tile_ids,
        called_tile_id=tile_ids[called_pos],
    )


# --- Pon ---


def _encode_pon(meld: MeldData) -> int:
    tile_ids = sorted(meld["tile_ids"])
    caller_seat = meld["caller_seat"]
    called_tile_id = meld["called_tile_id"]
    from_seat = meld["from_seat"]
    if called_tile_id is None:
        msg = "Pon meld requires called_tile_id"
        raise ValueError(msg)
    if from_seat is None:
        msg = "Pon meld requires from_seat"
        raise ValueError(msg)

    tile_34 = tile_ids[0] // 4
    used_copies = {tid % 4 for tid in tile_ids}
    missing_copy = ({0, 1, 2, 3} - used_copies).pop()
    called_pos = tile_ids.index(called_tile_id)
    from_offset = _validate_from_offset(from_seat, caller_seat)

    pon_index = (
        (tile_34 * _MISSING_COPIES + missing_copy) * _CALLED_POSITIONS + called_pos
    ) * _FROM_OFFSETS + from_offset
    meld_index = PON_OFFSET + pon_index
    return meld_index * 4 + caller_seat


def _decode_pon(pon_index: int, caller_seat: int) -> MeldData:
    from_offset = pon_index % _FROM_OFFSETS
    remainder = pon_index // _FROM_OFFSETS
    called_pos = remainder % _CALLED_POSITIONS
    remainder = remainder // _CALLED_POSITIONS
    missing_copy = remainder % _MISSING_COPIES
    tile_34 = remainder // _MISSING_COPIES

    tile_ids = [tile_34 * 4 + c for c in range(4) if c != missing_copy]

    return MeldData(
        type="meld",
        meld_type="pon",
        caller_seat=caller_seat,
        from_seat=(caller_seat + from_offset + 1) % 4,
        tile_ids=tile_ids,
        called_tile_id=tile_ids[called_pos],
    )


# --- Shouminkan / Daiminkan (open kan) ---


def _encode_open_kan(meld: MeldData, type_offset: int) -> int:
    caller_seat = meld["caller_seat"]
    called_tile_id = meld["called_tile_id"]
    from_seat = meld["from_seat"]
    if called_tile_id is None:
        msg = "Open kan meld requires called_tile_id"
        raise ValueError(msg)
    if from_seat is None:
        msg = "Open kan meld requires from_seat"
        raise ValueError(msg)

    tile_34 = meld["tile_ids"][0] // 4
    called_copy = called_tile_id % 4
    from_offset = _validate_from_offset(from_seat, caller_seat)

    local_index = (tile_34 * _CALLED_COPIES + called_copy) * _FROM_OFFSETS + from_offset
    meld_index = type_offset + local_index
    return meld_index * 4 + caller_seat


def _decode_open_kan(local_index: int, caller_seat: int, meld_type: MeldType) -> MeldData:
    from_offset = local_index % _FROM_OFFSETS
    remainder = local_index // _FROM_OFFSETS
    called_copy = remainder % _CALLED_COPIES
    tile_34 = remainder // _CALLED_COPIES

    return MeldData(
        type="meld",
        meld_type=meld_type,
        caller_seat=caller_seat,
        from_seat=(caller_seat + from_offset + 1) % 4,
        tile_ids=[tile_34 * 4 + c for c in range(4)],
        called_tile_id=tile_34 * 4 + called_copy,
    )


def _encode_shouminkan(meld: MeldData) -> int:
    return _encode_open_kan(meld, SHOUMINKAN_OFFSET)


def _decode_shouminkan(local_index: int, caller_seat: int) -> MeldData:
    return _decode_open_kan(local_index, caller_seat, "added_kan")


def _encode_daiminkan(meld: MeldData) -> int:
    return _encode_open_kan(meld, DAIMINKAN_OFFSET)


def _decode_daiminkan(local_index: int, caller_seat: int) -> MeldData:
    return _decode_open_kan(local_index, caller_seat, "open_kan")


# --- Ankan (closed kan) ---


def _encode_ankan(meld: MeldData) -> int:
    caller_seat = meld["caller_seat"]
    tile_34 = meld["tile_ids"][0] // 4
    meld_index = ANKAN_OFFSET + tile_34
    return meld_index * 4 + caller_seat


def _decode_ankan(local_index: int, caller_seat: int) -> MeldData:
    tile_34 = local_index
    return MeldData(
        type="meld",
        meld_type="closed_kan",
        caller_seat=caller_seat,
        from_seat=None,
        tile_ids=[tile_34 * 4 + c for c in range(4)],
        called_tile_id=None,
    )


# --- Encoder dispatch ---

_ENCODERS = {
    "chi": _encode_chi,
    "pon": _encode_pon,
    "added_kan": _encode_shouminkan,
    "open_kan": _encode_daiminkan,
    "closed_kan": _encode_ankan,
}
