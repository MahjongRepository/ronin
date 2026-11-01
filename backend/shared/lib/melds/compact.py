from typing import Literal, TypedDict

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

type MeldType = Literal["chi", "pon", "added_kan", "open_kan", "closed_kan"]


class MeldData(TypedDict):
    """
    Wire-format representation of a mahjong meld.

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
        added_tile_id: For added kan, the 4th tile added from hand to the pon;
            ``None`` for every other meld type.
    """

    type: Literal["meld"]
    meld_type: MeldType
    caller_seat: int
    from_seat: int | None
    tile_ids: list[int]
    called_tile_id: int | None
    added_tile_id: int | None


# ---------------------------------------------------------------------------
# IMME offset ranges
# ---------------------------------------------------------------------------

CHI_OFFSET = 0
CHI_COUNT = 4032  # 21 * 64 * 3
PON_OFFSET = CHI_OFFSET + CHI_COUNT  # 4032
PON_COUNT = 1224  # 34 * 4 * 3 * 3
SHOUMINKAN_OFFSET = PON_OFFSET + PON_COUNT  # 5256
SHOUMINKAN_COUNT = 1224
DAIMINKAN_OFFSET = SHOUMINKAN_OFFSET + SHOUMINKAN_COUNT
DAIMINKAN_COUNT = 408  # 34 * 4 * 3
ANKAN_OFFSET = DAIMINKAN_OFFSET + DAIMINKAN_COUNT
ANKAN_COUNT = 34

EVENT_TYPE_MELD = 0

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def encode_meld_compact(meld: MeldData) -> int:
    """
    Encode a meld as a single IMME integer (no event envelope).
    """
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
    """
    Decode an IMME integer back to a MeldData dict.
    """
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
    """
    Encode a meld as a game event: ``{"t": 0, "m": <IMME_int>}``.
    """
    return {"t": EVENT_TYPE_MELD, "m": encode_meld_compact(meld)}


def decode_game_event(event: dict[str, int]) -> MeldData:
    """
    Decode a game event ``{"t": int, "m": int}`` back to a MeldData.
    """
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
    """
    Return True if value is an int but not a bool.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_from_offset(from_seat: int, caller_seat: int) -> int:
    """
    Compute and validate from_offset for open melds.

    from_offset encodes the relative seat distance (1, 2, or 3 steps clockwise) as 0, 1, or 2. A player cannot call
    their own discard, so from_seat must differ from caller_seat. Both seats must be in range 0-3.
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
        added_tile_id=None,
    )


# --- Pon ---


def _encode_pon(meld: MeldData) -> int:
    tile_ids = sorted(meld["tile_ids"])
    used_copies = {tid % 4 for tid in tile_ids}
    missing_copy = ({0, 1, 2, 3} - used_copies).pop()
    meld_index = PON_OFFSET + _pon_index(meld, tile_ids, missing_copy)
    return meld_index * 4 + meld["caller_seat"]


def _pon_index(meld: MeldData, pon_tile_ids: list[int], missing_copy: int) -> int:
    """
    Index a pon of the sorted pon_tile_ids, its missing_copy the copy it lacks, within its type's range.
    """
    caller_seat = meld["caller_seat"]
    called_tile_id = meld["called_tile_id"]
    from_seat = meld["from_seat"]
    if called_tile_id is None:
        msg = f"{meld['meld_type']} meld requires called_tile_id"
        raise ValueError(msg)

    if from_seat is None:
        msg = f"{meld['meld_type']} meld requires from_seat"
        raise ValueError(msg)

    tile_34 = pon_tile_ids[0] // 4
    called_pos = pon_tile_ids.index(called_tile_id)
    from_offset = _validate_from_offset(from_seat, caller_seat)

    return ((tile_34 * _MISSING_COPIES + missing_copy) * _CALLED_POSITIONS + called_pos) * _FROM_OFFSETS + from_offset


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
        added_tile_id=None,
    )


def _encode_shouminkan(meld: MeldData) -> int:
    added_tile_id = meld["added_tile_id"]
    if added_tile_id is None:
        msg = "added_kan meld requires added_tile_id"
        raise ValueError(msg)

    if added_tile_id not in meld["tile_ids"] or added_tile_id == meld["called_tile_id"]:
        msg = f"added_tile_id {added_tile_id} must be one of the kan's tiles other than its called tile"
        raise ValueError(msg)

    pon_tile_ids = sorted(tid for tid in meld["tile_ids"] if tid != added_tile_id)
    meld_index = SHOUMINKAN_OFFSET + _pon_index(meld, pon_tile_ids, added_tile_id % 4)
    return meld_index * 4 + meld["caller_seat"]


def _decode_shouminkan(local_index: int, caller_seat: int) -> MeldData:
    pon = _decode_pon(local_index, caller_seat)
    tile_34 = pon["tile_ids"][0] // 4
    (added_tile_id,) = {tile_34 * 4 + c for c in range(4)} - set(pon["tile_ids"])
    return MeldData(
        type="meld",
        meld_type="added_kan",
        caller_seat=caller_seat,
        from_seat=pon["from_seat"],
        tile_ids=sorted([*pon["tile_ids"], added_tile_id]),
        called_tile_id=pon["called_tile_id"],
        added_tile_id=added_tile_id,
    )


def _encode_daiminkan(meld: MeldData) -> int:
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
    meld_index = DAIMINKAN_OFFSET + local_index
    return meld_index * 4 + caller_seat


def _decode_daiminkan(local_index: int, caller_seat: int) -> MeldData:
    from_offset = local_index % _FROM_OFFSETS
    remainder = local_index // _FROM_OFFSETS
    called_copy = remainder % _CALLED_COPIES
    tile_34 = remainder // _CALLED_COPIES

    return MeldData(
        type="meld",
        meld_type="open_kan",
        caller_seat=caller_seat,
        from_seat=(caller_seat + from_offset + 1) % 4,
        tile_ids=[tile_34 * 4 + c for c in range(4)],
        called_tile_id=tile_34 * 4 + called_copy,
        added_tile_id=None,
    )


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
        added_tile_id=None,
    )


# --- Encoder dispatch ---

_ENCODERS = {
    "chi": _encode_chi,
    "pon": _encode_pon,
    "added_kan": _encode_shouminkan,
    "open_kan": _encode_daiminkan,
    "closed_kan": _encode_ankan,
}
