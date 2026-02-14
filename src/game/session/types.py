"""
Pydantic models for the session layer.
"""

from pydantic import BaseModel


class RoomInfo(BaseModel):
    """Room information for lobby listing."""

    room_id: str
    player_count: int
    players_needed: int
    total_seats: int
    num_ai_players: int
    players: list[str]
