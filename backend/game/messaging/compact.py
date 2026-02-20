"""Compact integer encoding for draw and discard events.

Packs draw/discard events into single integers to reduce wire and replay
payload size. Used by both WebSocket broadcasts and replay collection.

Draw encoding
-------------
    d = seat * 136 + tile_id

Valid range: 0..543 (4 seats x 136 tiles).

Discard encoding
----------------
    flag = (is_riichi << 1) | is_tsumogiri
    d = flag * 544 + seat * 136 + tile_id

Bit 0 = tsumogiri, Bit 1 = riichi.
Valid range: 0..2175 (4 flag combos x 4 seats x 136 tiles).
"""

from game.logic.settings import NUM_PLAYERS
from game.logic.tiles import NUM_TILES

_SEAT_TILE_SPACE = NUM_PLAYERS * NUM_TILES  # 544
_NUM_DISCARD_FLAGS = 4  # 2 bits: is_tsumogiri | is_riichi

_MAX_DRAW = _SEAT_TILE_SPACE - 1  # 543
_MAX_DISCARD = _NUM_DISCARD_FLAGS * _SEAT_TILE_SPACE - 1  # 2175


def _is_strict_int(value: object) -> bool:
    """Return True if value is an int but not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def encode_draw(seat: int, tile_id: int) -> int:
    """Encode a draw event as a single integer.

    Args:
        seat: Player seat index (0-3).
        tile_id: Tile ID in 136-format (0-135).

    Returns:
        Packed integer in range 0..543.
    """
    if not _is_strict_int(seat):
        msg = f"seat must be an integer, got {type(seat).__name__}"
        raise TypeError(msg)
    if not _is_strict_int(tile_id):
        msg = f"tile_id must be an integer, got {type(tile_id).__name__}"
        raise TypeError(msg)
    if seat < 0 or seat >= NUM_PLAYERS:
        msg = f"seat must be 0-{NUM_PLAYERS - 1}, got {seat}"
        raise ValueError(msg)
    if tile_id < 0 or tile_id >= NUM_TILES:
        msg = f"tile_id must be 0-{NUM_TILES - 1}, got {tile_id}"
        raise ValueError(msg)
    return seat * NUM_TILES + tile_id


def decode_draw(d: int) -> tuple[int, int]:  # deadcode: ignore
    """Decode a packed draw integer back to (seat, tile_id).

    Args:
        d: Packed draw integer (0..543).

    Returns:
        Tuple of (seat, tile_id).
    """
    if not _is_strict_int(d):
        msg = f"Expected integer, got {type(d).__name__}"
        raise TypeError(msg)
    if d < 0 or d > _MAX_DRAW:
        msg = f"Draw packed value must be 0-{_MAX_DRAW}, got {d}"
        raise ValueError(msg)
    seat, tile_id = divmod(d, NUM_TILES)
    return seat, tile_id


def encode_discard(seat: int, tile_id: int, *, is_tsumogiri: bool, is_riichi: bool) -> int:
    """Encode a discard event as a single integer.

    Args:
        seat: Player seat index (0-3).
        tile_id: Tile ID in 136-format (0-135).
        is_tsumogiri: Whether the discarded tile was just drawn.
        is_riichi: Whether the discard declares riichi.

    Returns:
        Packed integer in range 0..2175.
    """
    if not _is_strict_int(seat):
        msg = f"seat must be an integer, got {type(seat).__name__}"
        raise TypeError(msg)
    if not _is_strict_int(tile_id):
        msg = f"tile_id must be an integer, got {type(tile_id).__name__}"
        raise TypeError(msg)
    if seat < 0 or seat >= NUM_PLAYERS:
        msg = f"seat must be 0-{NUM_PLAYERS - 1}, got {seat}"
        raise ValueError(msg)
    if tile_id < 0 or tile_id >= NUM_TILES:
        msg = f"tile_id must be 0-{NUM_TILES - 1}, got {tile_id}"
        raise ValueError(msg)
    flag = (int(is_riichi) << 1) | int(is_tsumogiri)
    return flag * _SEAT_TILE_SPACE + seat * NUM_TILES + tile_id


def decode_discard(d: int) -> tuple[int, int, bool, bool]:
    """Decode a packed discard integer back to (seat, tile_id, is_tsumogiri, is_riichi).

    Args:
        d: Packed discard integer (0..2175).

    Returns:
        Tuple of (seat, tile_id, is_tsumogiri, is_riichi).
    """
    if not _is_strict_int(d):
        msg = f"Expected integer, got {type(d).__name__}"
        raise TypeError(msg)
    if d < 0 or d > _MAX_DISCARD:
        msg = f"Discard packed value must be 0-{_MAX_DISCARD}, got {d}"
        raise ValueError(msg)
    flag, remainder = divmod(d, _SEAT_TILE_SPACE)
    seat, tile_id = divmod(remainder, NUM_TILES)
    is_tsumogiri = bool(flag & 0b01)
    is_riichi = bool(flag & 0b10)
    return seat, tile_id, is_tsumogiri, is_riichi
