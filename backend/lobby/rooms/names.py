from __future__ import annotations

import itertools
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Collection

_ADJECTIVES = (
    "Amber",
    "Autumn",
    "Azure",
    "Bright",
    "Copper",
    "Crimson",
    "Golden",
    "Hidden",
    "Indigo",
    "Ivory",
    "Jade",
    "Lucky",
    "Misty",
    "Moonlit",
    "Quiet",
    "Scarlet",
    "Shining",
    "Silent",
    "Silver",
    "Spring",
    "Starry",
    "Summer",
    "Sunny",
    "Winter",
)
_NOUNS = (
    "Bonsai",
    "Daruma",
    "Dojo",
    "Fuji",
    "Haiku",
    "Izakaya",
    "Kappa",
    "Kimono",
    "Kitsune",
    "Koi",
    "Kotatsu",
    "Matsuri",
    "Mochi",
    "Onsen",
    "Origami",
    "Ryokan",
    "Sakura",
    "Shiba",
    "Taiko",
    "Tanuki",
    "Tatami",
    "Tengu",
    "Torii",
    "Yuzu",
)
ROOM_NAMES = tuple(f"{adjective} {noun}" for adjective, noun in itertools.product(_ADJECTIVES, _NOUNS))


def pick_room_name(taken: Collection[str]) -> str:
    """
    Pick a random room name that no open room holds, or any name once all are held.

    A name only labels a room for players; the room id identifies it, so a repeat is harmless.
    """
    free = [name for name in ROOM_NAMES if name not in taken]
    return secrets.choice(free or ROOM_NAMES)
