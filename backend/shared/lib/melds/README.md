# IMME: Integer-Mapped Meld Encoding

Standalone, lossless compression library for Riichi Mahjong melds. Each meld is encoded as a single integer (15 bits) — no string parsing, no dict construction at encode time, pure arithmetic.

Zero external dependencies. Uses only Python's `typing` module.

## Quick Start

```python
from shared.lib.melds import (
    MeldData,
    encode_meld_compact,
    decode_meld_compact,
    encode_game_event,
    decode_game_event,
)

# Encode a pon meld to a single integer.
meld = MeldData(
    type="meld",
    meld_type="pon",
    caller_seat=1,
    from_seat=0,
    tile_ids=[8, 9, 10],
    called_tile_id=8,
)

value = encode_meld_compact(meld)   # e.g. 16181
decoded = decode_meld_compact(value) # reproduces all fields

# Wrap in a game event envelope for network transport.
event = encode_game_event(meld)      # {"t": 0, "m": 16181}
decoded = decode_game_event(event)   # back to MeldData
```

## MeldData Format

`MeldData` is a `TypedDict` with these fields:

| Field            | Type                  | Description                                                                                 |
|------------------|-----------------------|---------------------------------------------------------------------------------------------|
| `type`           | `Literal["meld"]`     | Always `"meld"`.                                                                            |
| `meld_type`      | `MeldType`            | Meld category (see below).                                                                  |
| `caller_seat`    | `int`                 | Seat index (0-3) of the player declaring the meld.                                          |
| `from_seat`      | `int \| None`         | Seat of the opponent whose discard was claimed. `None` for closed kan.                      |
| `tile_ids`       | `list[int]`           | Tile IDs in 136-format (`tile_34 * 4 + copy`).                                              |
| `called_tile_id` | `int \| None`         | The specific tile claimed from the opponent's discard. `None` for closed kan.               |

## MeldType Values

| Value          | Description                                                          |
|----------------|----------------------------------------------------------------------|
| `"chi"`        | Sequence of 3 consecutive numbered tiles, called from kamicha (left) |
| `"pon"`        | Triplet of 3 identical tiles, called from any opponent               |
| `"open_kan"`   | Open quad (daiminkan), called from an opponent's discard             |
| `"closed_kan"` | Closed quad (ankan), all 4 tiles drawn from hand                     |
| `"added_kan"`  | Added quad (shouminkan/chankan), extending a pon to a kan            |

## Tile Representation

Mahjong uses 136 physical tiles: 34 tile types, 4 copies each.

```
tile_id = tile_34 * 4 + copy     (136-format, 0-135)
tile_34 = tile_id // 4           (34-format,  0-33)
copy    = tile_id % 4            (physical copy, 0-3)
```

Tile types in 34-format:

| Range | Suit / Category       | Tiles                                        |
|-------|-----------------------|----------------------------------------------|
| 0-8   | Man (characters)      | 1m, 2m, 3m, 4m, 5m, 6m, 7m, 8m, 9m         |
| 9-17  | Pin (circles)         | 1p, 2p, 3p, 4p, 5p, 6p, 7p, 8p, 9p         |
| 18-26 | Sou (bamboo)          | 1s, 2s, 3s, 4s, 5s, 6s, 7s, 8s, 9s         |
| 27-30 | Winds                 | East, South, West, North                     |
| 31-33 | Dragons               | Haku (white), Hatsu (green), Chun (red)      |

## IMME Encoding

Every IMME value is structured as:

```
value = meld_index * 4 + caller_seat
```

`caller_seat` (0-3) occupies the lowest 2 bits. `meld_index` falls into one of five contiguous ranges that determine the meld type:

### Encoding Ranges

| Type       | Offset | Count | Range        |
|------------|--------|-------|--------------|
| Chi        |      0 |  4032 |    0 -  4031 |
| Pon        |   4032 |  1224 | 4032 -  5255 |
| Shouminkan |   5256 |   408 | 5256 -  5663 |
| Daiminkan  |   5664 |   408 | 5664 -  6071 |
| Ankan      |   6072 |    34 | 6072 -  6105 |

Total: 6106 meld indices x 4 seats = 24424 values (fits in 15 bits).

### Per-Type Encoding Formulas

**Chi** (3 consecutive numbered tiles, called from kamicha):

```
base_index = suit_index * 7 + start_in_suit    (0-20: 3 suits x 7 sequences)
copy_index = copy_lo * 16 + copy_mid * 4 + copy_hi  (0-63: 4^3 copy combos)
called_pos = 0-2  (which of the 3 sorted tiles was the called discard)
meld_index = (base_index * 64 + copy_index) * 3 + called_pos
```

**Pon** (3 identical tiles, called from any opponent):

```
tile_34      = 0-33
missing_copy = 0-3  (which of the 4 physical copies is absent)
called_pos   = 0-2  (index of the called tile in sorted tile_ids)
from_offset  = (from_seat - caller_seat) % 4 - 1   (0-2)
pon_index    = ((tile_34 * 4 + missing_copy) * 3 + called_pos) * 3 + from_offset
meld_index   = PON_OFFSET + pon_index
```

**Shouminkan / Daiminkan** (open kan, all 4 copies):

```
tile_34      = 0-33
called_copy  = 0-3  (which physical copy was the called discard)
from_offset  = 0-2  (same as pon)
local_index  = (tile_34 * 4 + called_copy) * 3 + from_offset
meld_index   = <TYPE_OFFSET> + local_index
```

**Ankan** (closed kan, all 4 copies from hand, no opponent):

```
tile_34    = 0-33
meld_index = ANKAN_OFFSET + tile_34
```

## Game Event Envelope

For network transport, the IMME integer is wrapped in a minimal dict:

```json
{"t": 0, "m": 12345}
```

- `"t"` is the event type (`0` = meld, defined as `EVENT_TYPE_MELD`)
- `"m"` is the IMME-encoded integer

Use `encode_game_event()` and `decode_game_event()` for this format.

## Integration Guide

The library knows nothing about game-specific models. To use it in a game:

1. Convert your game meld objects to `MeldData` dicts at the boundary.
2. Call `encode_meld_compact()` to get the integer.
3. On the receiving side, call `decode_meld_compact()` to recover all fields.

Example bridge for a game `FrozenMeld` object:

```python
from shared.lib.melds import MeldData, encode_meld_compact

def frozen_meld_to_compact(meld) -> int:
    data = MeldData(
        type="meld",
        meld_type=map_game_type_to_wire_type(meld),
        caller_seat=meld.who,
        from_seat=meld.from_who,
        tile_ids=list(meld.tiles),
        called_tile_id=meld.called_tile,
    )
    return encode_meld_compact(data)
```

## Public API

| Function               | Signature                           | Description                                    |
|------------------------|-------------------------------------|------------------------------------------------|
| `encode_meld_compact`  | `(MeldData) -> int`                 | Encode a meld as a single IMME integer         |
| `decode_meld_compact`  | `(int) -> MeldData`                 | Decode an IMME integer back to a MeldData dict |
| `encode_game_event`    | `(MeldData) -> dict[str, int]`      | Encode as `{"t": 0, "m": <int>}`              |
| `decode_game_event`    | `(dict[str, int]) -> MeldData`      | Decode a game event back to MeldData           |

| Constant          | Value | Description                     |
|-------------------|-------|---------------------------------|
| `EVENT_TYPE_MELD` |   0   | Integer event type for melds    |

| Type       | Description                                         |
|------------|-----------------------------------------------------|
| `MeldData` | TypedDict for wire-format meld representation       |
| `MeldType` | Literal type alias for valid meld type strings      |

## Examples

### Chi (sequence)

```python
# Player 2 calls chi on 3m from player 1 (kamicha).
# Tiles: 1m(copy 0), 2m(copy 1), 3m(copy 2). Called tile: 3m(copy 2).
chi = MeldData(
    type="meld",
    meld_type="chi",
    caller_seat=2,
    from_seat=1,
    tile_ids=[0, 5, 10],
    called_tile_id=10,
)
value = encode_meld_compact(chi)
assert decode_meld_compact(value) == chi
```

### Pon (triplet)

```python
# Player 0 calls pon on East wind from player 2.
# Tiles: East(copy 0), East(copy 1), East(copy 3). Called: East(copy 3).
pon = MeldData(
    type="meld",
    meld_type="pon",
    caller_seat=0,
    from_seat=2,
    tile_ids=[108, 109, 111],
    called_tile_id=111,
)
value = encode_meld_compact(pon)
assert decode_meld_compact(value) == pon
```

### Open Kan (daiminkan)

```python
# Player 3 calls open kan on Haku from player 1. All 4 copies.
open_kan = MeldData(
    type="meld",
    meld_type="open_kan",
    caller_seat=3,
    from_seat=1,
    tile_ids=[124, 125, 126, 127],
    called_tile_id=125,
)
value = encode_meld_compact(open_kan)
assert decode_meld_compact(value) == open_kan
```

### Closed Kan (ankan)

```python
# Player 1 declares closed kan on 5p. All 4 copies, no opponent involved.
closed_kan = MeldData(
    type="meld",
    meld_type="closed_kan",
    caller_seat=1,
    from_seat=None,
    tile_ids=[52, 53, 54, 55],
    called_tile_id=None,
)
value = encode_meld_compact(closed_kan)
assert decode_meld_compact(value) == closed_kan
```

### Added Kan (shouminkan)

```python
# Player 0 adds 4th tile to existing pon of Chun. Called from player 3.
added_kan = MeldData(
    type="meld",
    meld_type="added_kan",
    caller_seat=0,
    from_seat=3,
    tile_ids=[132, 133, 134, 135],
    called_tile_id=133,
)
value = encode_meld_compact(added_kan)
assert decode_meld_compact(value) == added_kan
```
