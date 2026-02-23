from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlayerSpec(BaseModel):
    """Player info for direct game creation. The game_ticket field is the signed
    game ticket string -- the game server uses it as the session token in SessionStore,
    so clients can later present the same ticket in JOIN_GAME to match their session."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=50)
    user_id: str = Field(min_length=1, max_length=100)
    game_ticket: str = Field(min_length=1, max_length=2000)


class CreateGameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_id: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    num_ai_players: int = Field(default=3, ge=0, le=3, strict=True)
    players: list[PlayerSpec] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def _validate_players(self) -> Self:
        expected = 4 - self.num_ai_players
        if len(self.players) != expected:
            raise ValueError(f"Expected {expected} players for {self.num_ai_players} AI, got {len(self.players)}")
        _check_unique([p.game_ticket for p in self.players], "game_ticket")
        _check_unique([p.name for p in self.players], "player name")
        _check_unique([p.user_id for p in self.players], "user_id")
        return self


def _check_unique(values: list[str], label: str) -> None:
    """Raise ValueError if the list contains duplicate values."""
    if len(set(values)) != len(values):
        raise ValueError(f"Duplicate {label} in player list")
