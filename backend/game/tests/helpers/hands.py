from mahjong.tile import TilesConverter


def tile_copies(
    copy: int,
    *,
    sou: str | None = None,
    pin: str | None = None,
    man: str | None = None,
    honors: str | None = None,
) -> list[int]:
    return [tile + copy for tile in TilesConverter.string_to_136_array(sou=sou, pin=pin, man=man, honors=honors)]


PIN_3_TRIPLE_RON_DISCARD = tile_copies(2, pin="3")[0]
PIN_3_TRIPLE_RON_DEALER_HAND = (
    *tile_copies(0, honors="12347"),
    *tile_copies(1, honors="1234"),
    *tile_copies(2, honors="1234"),
)
PIN_3_TRIPLE_RON_CALLER_HANDS = (
    (*tile_copies(0, man="123456789", pin="12", honors="5"), *tile_copies(1, honors="5")),
    (*tile_copies(0, sou="123456789", pin="45", honors="6"), *tile_copies(1, honors="6")),
    (*tile_copies(1, man="234567", sou="678", pin="345"), *tile_copies(0, pin="6")),
)
