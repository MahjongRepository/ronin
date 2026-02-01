"""
Pydantic models for the session layer.
"""

from pydantic import BaseModel


class GameInfo(BaseModel):
    """Game information for lobby listing."""

    game_id: str
    player_count: int
    max_players: int
    num_bots: int
    started: bool
