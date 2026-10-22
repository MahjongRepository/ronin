from shared.lib.melds.compact import MeldData, MeldType

MAN_34 = 0
PIN_34 = 9
SOU_34 = 18
SUITS_34 = (MAN_34, PIN_34, SOU_34)
HONORS_34 = (27, 28, 29, 30, 31, 32, 33)


def _id(tile_34: int, copy: int = 0) -> int:
    return tile_34 * 4 + copy


def _meld(
    meld_type: MeldType,
    tile_ids: list[int],
    caller_seat: int,
    from_seat: int | None = None,
    called_tile_id: int | None = None,
) -> MeldData:
    return MeldData(
        type="meld",
        meld_type=meld_type,
        caller_seat=caller_seat,
        from_seat=from_seat,
        tile_ids=tile_ids,
        called_tile_id=called_tile_id,
    )


def _build_chi_fixtures() -> list[MeldData]:
    melds: list[MeldData] = []

    copy_rotations = [
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


def _build_pon_fixtures() -> list[MeldData]:
    melds: list[MeldData] = []

    for suit in SUITS_34:
        for val in range(9):
            t34 = suit + val
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


def _build_open_kan_fixtures() -> list[MeldData]:
    melds: list[MeldData] = []

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


def _build_closed_kan_fixtures() -> list[MeldData]:
    melds: list[MeldData] = []

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

    for i, t34 in enumerate(HONORS_34):
        melds.append(
            _meld(
                meld_type="closed_kan",
                tile_ids=[_id(t34, 0), _id(t34, 1), _id(t34, 2), _id(t34, 3)],
                caller_seat=i % 4,
            ),
        )

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


def _build_added_kan_fixtures() -> list[MeldData]:
    melds: list[MeldData] = []

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


def build_all_fixtures() -> list[MeldData]:
    return (
        _build_chi_fixtures()
        + _build_pon_fixtures()
        + _build_open_kan_fixtures()
        + _build_closed_kan_fixtures()
        + _build_added_kan_fixtures()
    )
