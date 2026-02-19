"""Meld fixtures: ~250 melds in wire format covering all meld types.

Wire format matches MeldEvent sent to client:
{'type': 'meld', 'meld_type': '...', 'caller_seat': N, 'from_seat': N, 'tile_ids': [...], 'called_tile_id': N}
"""

from shared.lib.melds.compact import MeldData, MeldType

# 136-format: tile_34 * 4 gives first copy, +1/+2/+3 for other copies
# Suits in 34-format: man 0-8, pin 9-17, sou 18-26
# Honors in 34-format: E=27 S=28 W=29 N=30 Haku=31 Hatsu=32 Chun=33

MAN_34 = 0
PIN_34 = 9
SOU_34 = 18
SUITS_34 = (MAN_34, PIN_34, SOU_34)
HONORS_34 = (27, 28, 29, 30, 31, 32, 33)


def _id(tile_34: int, copy: int = 0) -> int:  # deadcode: ignore
    """Return a specific copy (0-3) of a tile type in 136-format."""
    return tile_34 * 4 + copy


def _meld(  # deadcode: ignore
    meld_type: MeldType,
    tile_ids: list[int],
    caller_seat: int,
    from_seat: int | None = None,
    called_tile_id: int | None = None,
) -> MeldData:
    """Build a meld in wire format."""
    return MeldData(
        type="meld",
        meld_type=meld_type,
        caller_seat=caller_seat,
        from_seat=from_seat,
        tile_ids=tile_ids,
        called_tile_id=called_tile_id,
    )


def _build_chi_fixtures() -> list[MeldData]:  # deadcode: ignore
    """Chi melds with game-realistic variety (~105 total).

    Chi can only be called from the left player: from_seat = (caller_seat + 3) % 4.
    The called tile (the discard) can be low, mid, or high in the sequence.
    Covers all sequences x all caller seats x varied called positions and tile copies.
    """
    melds: list[MeldData] = []

    # for each suit: all 7 sequences x 4 caller seats, rotating called position and copies
    copy_rotations = [
        # (copy_lo, copy_mid, copy_hi) — different combinations of tile copies
        (0, 1, 2),
        (1, 0, 3),
        (2, 3, 0),
        (3, 2, 1),
    ]

    for suit in SUITS_34:
        for start in range(7):
            lo34, mid34, hi34 = suit + start, suit + start + 1, suit + start + 2
            for caller in range(4):
                from_seat = (caller + 3) % 4
                c_lo, c_mid, c_hi = copy_rotations[caller]
                # called position cycles: low → mid → high across suits
                called_pos = (start + caller) % 3
                tiles_34 = [lo34, mid34, hi34]
                copies = [c_lo, c_mid, c_hi]
                melds.append(
                    _meld(
                        meld_type="chi",
                        tile_ids=[_id(lo34, c_lo), _id(mid34, c_mid), _id(hi34, c_hi)],
                        caller_seat=caller,
                        from_seat=from_seat,
                        called_tile_id=_id(tiles_34[called_pos], copies[called_pos]),
                    ),
                )

    # terminal-edge sequences: 1-2-3 and 7-8-9 are common in tanyao-denying hands
    # add extra with less common copy combos
    for suit in SUITS_34:
        for start, caller in [(0, 1), (0, 3), (4, 0), (4, 2), (6, 0), (6, 2)]:
            lo34, mid34, hi34 = suit + start, suit + start + 1, suit + start + 2
            from_seat = (caller + 3) % 4
            melds.append(
                _meld(
                    meld_type="chi",
                    tile_ids=[_id(lo34, 3), _id(mid34, 2), _id(hi34, 1)],
                    caller_seat=caller,
                    from_seat=from_seat,
                    called_tile_id=_id(mid34, 2),
                ),
            )

    return melds


def _build_pon_fixtures() -> list[MeldData]:  # deadcode: ignore
    """Pon melds with game-realistic variety (~80 total).

    Pon can be called from any of the other 3 players (shimocha/toimen/kamicha).
    Covers all 34 tile types with multiple caller/from combinations.
    """
    melds: list[MeldData] = []

    # all suit tiles: each tile type x 2 caller/from combos (shimocha and toimen calls)
    for suit in SUITS_34:
        for val in range(9):
            t34 = suit + val
            # combo 1: caller=0, from rotates based on tile value
            from_seat = (val % 3) + 1
            melds.append(
                _meld(
                    meld_type="pon",
                    tile_ids=[_id(t34, 0), _id(t34, 1), _id(t34, 3)],
                    caller_seat=0,
                    from_seat=from_seat,
                    called_tile_id=_id(t34, 3),
                ),
            )

            # combo 2: different caller, different copies
            caller = (val % 3) + 1
            from_seat2 = (caller + 1 + val % 2) % 4
            melds.append(
                _meld(
                    meld_type="pon",
                    tile_ids=[_id(t34, 1), _id(t34, 2), _id(t34, 0)],
                    caller_seat=caller,
                    from_seat=from_seat2,
                    called_tile_id=_id(t34, 0),
                ),
            )

    # honors: all 7 x 3 caller/from combos (honors are called more often)
    for t34 in HONORS_34:
        for j, (caller, frm) in enumerate([(0, 1), (1, 3), (2, 0)]):
            copies = [(0, 1, 2), (0, 2, 3), (1, 2, 3)][j]
            called_idx = 2
            melds.append(
                _meld(
                    meld_type="pon",
                    tile_ids=[_id(t34, copies[0]), _id(t34, copies[1]), _id(t34, copies[2])],
                    caller_seat=caller,
                    from_seat=frm,
                    called_tile_id=_id(t34, copies[called_idx]),
                ),
            )

    return melds


def _build_open_kan_fixtures() -> list[MeldData]:  # deadcode: ignore
    """Open kan (daiminkan): rare in real games (~25 total).

    Spread across terminals, honors, and select middle tiles.
    """
    melds: list[MeldData] = []

    # terminals in each suit (1 and 9) — kans are most common with terminals/honors
    for suit in SUITS_34:
        for val in (0, 8):
            t34 = suit + val
            for caller, frm in [(0, 1), (2, 3)]:
                melds.append(
                    _meld(
                        meld_type="open_kan",
                        tile_ids=[_id(t34, 0), _id(t34, 1), _id(t34, 2), _id(t34, 3)],
                        caller_seat=caller,
                        from_seat=frm,
                        called_tile_id=_id(t34, 3),
                    ),
                )

    # all 7 honors — honor kans are most realistic
    for i, t34 in enumerate(HONORS_34):
        caller = i % 4
        frm = (caller + 1 + i % 2) % 4
        melds.append(
            _meld(
                meld_type="open_kan",
                tile_ids=[_id(t34, 0), _id(t34, 1), _id(t34, 2), _id(t34, 3)],
                caller_seat=caller,
                from_seat=frm,
                called_tile_id=_id(t34, 3),
            ),
        )

    # a few middle tiles (rare but possible)
    for suit, val, caller, frm in [(MAN_34, 4, 1, 0), (PIN_34, 4, 3, 2), (SOU_34, 4, 0, 3)]:
        t34 = suit + val
        melds.append(
            _meld(
                meld_type="open_kan",
                tile_ids=[_id(t34, 0), _id(t34, 1), _id(t34, 2), _id(t34, 3)],
                caller_seat=caller,
                from_seat=frm,
                called_tile_id=_id(t34, 3),
            ),
        )

    return melds


def _build_closed_kan_fixtures() -> list[MeldData]:  # deadcode: ignore
    """Closed kan (ankan): no from_seat or called_tile (~20 total).

    All 4 tiles come from the player's hand.
    """
    melds: list[MeldData] = []

    # terminals
    for suit in SUITS_34:
        for val in (0, 8):
            t34 = suit + val
            caller = (suit // 9 + val) % 4
            melds.append(
                _meld(
                    meld_type="closed_kan",
                    tile_ids=[_id(t34, 0), _id(t34, 1), _id(t34, 2), _id(t34, 3)],
                    caller_seat=caller,
                ),
            )

    # all honors
    for i, t34 in enumerate(HONORS_34):
        melds.append(
            _meld(
                meld_type="closed_kan",
                tile_ids=[_id(t34, 0), _id(t34, 1), _id(t34, 2), _id(t34, 3)],
                caller_seat=i % 4,
            ),
        )

    # select middle tiles — closed kan of 5s is common in tsumo-oriented play
    for suit, val, caller in [
        (MAN_34, 4, 0),
        (PIN_34, 4, 1),
        (SOU_34, 4, 2),
        (MAN_34, 3, 3),
        (PIN_34, 6, 0),
        (SOU_34, 2, 1),
    ]:
        t34 = suit + val
        melds.append(
            _meld(
                meld_type="closed_kan",
                tile_ids=[_id(t34, 0), _id(t34, 1), _id(t34, 2), _id(t34, 3)],
                caller_seat=caller,
            ),
        )

    return melds


def _build_added_kan_fixtures() -> list[MeldData]:  # deadcode: ignore
    """Added kan (shouminkan): upgrade an existing pon (~20 total).

    Keeps from_seat from the original pon call.
    Convention: tile_ids has the added tile last; called_tile_id is the
    original pon's called tile (the discard claimed from an opponent).
    """
    melds: list[MeldData] = []

    # terminals — pon copies (0, 1, 3), called copy 1, added copy 2
    for suit in SUITS_34:
        for val in (0, 8):
            t34 = suit + val
            caller = (suit // 9) % 4
            frm = (caller + 1 + val % 2) % 4
            melds.append(
                _meld(
                    meld_type="added_kan",
                    tile_ids=[_id(t34, 0), _id(t34, 1), _id(t34, 3), _id(t34, 2)],
                    caller_seat=caller,
                    from_seat=frm,
                    called_tile_id=_id(t34, 1),
                ),
            )

    # all honors — pon copies (0, 1, 2), called copy 0, added copy 3
    for i, t34 in enumerate(HONORS_34):
        caller = i % 4
        frm = (caller + 2) % 4
        melds.append(
            _meld(
                meld_type="added_kan",
                tile_ids=[_id(t34, 0), _id(t34, 1), _id(t34, 2), _id(t34, 3)],
                caller_seat=caller,
                from_seat=frm,
                called_tile_id=_id(t34, 0),
            ),
        )

    # middle tiles — pon copies (0, 2, 3), called copy 2, added copy 1
    for suit, val, caller, frm in [
        (MAN_34, 4, 1, 3),
        (PIN_34, 4, 2, 0),
        (SOU_34, 4, 3, 1),
        (MAN_34, 2, 0, 2),
        (PIN_34, 7, 1, 0),
        (SOU_34, 6, 2, 3),
    ]:
        t34 = suit + val
        melds.append(
            _meld(
                meld_type="added_kan",
                tile_ids=[_id(t34, 0), _id(t34, 2), _id(t34, 3), _id(t34, 1)],
                caller_seat=caller,
                from_seat=frm,
                called_tile_id=_id(t34, 2),
            ),
        )

    return melds


def build_all_fixtures() -> list[MeldData]:  # deadcode: ignore
    """Build ~250 meld fixtures covering every type with game-realistic variety."""
    return (
        _build_chi_fixtures()
        + _build_pon_fixtures()
        + _build_open_kan_fixtures()
        + _build_closed_kan_fixtures()
        + _build_added_kan_fixtures()
    )
