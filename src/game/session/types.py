"""
Pydantic models for the session layer.
"""

from pydantic import BaseModel


class RoomInfo(BaseModel):
    """Room information for lobby listing."""

    room_id: str
    human_player_count: int
    humans_needed: int
    total_seats: int
    num_bots: int
    players: list[str]
