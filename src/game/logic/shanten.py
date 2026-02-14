"""Shanten calculation using xiangting (Rust)."""

from xiangting import PlayerCount, calculate_replacement_number

AGARI_STATE: int = -1

# Xiangting requires tile count to be 3n+1 or 3n+2.
# Other counts (empty hands, test fixtures with unusual sizes) can't be tenpai.
_NOT_TENPAI: int = 8


def calculate_shanten(tiles_34: list[int]) -> int:
    """Calculate the minimum shanten number across all hand patterns (regular, chiitoitsu, kokushi).

    Used by is_tempai() which must detect tenpai for all hand types.
    """
    total = sum(tiles_34)
    if total == 0 or total % 3 not in (1, 2):
        return _NOT_TENPAI
    return calculate_replacement_number(tiles_34, PlayerCount.FOUR) - 1
