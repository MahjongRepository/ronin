"""User account and session models for authentication."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, model_validator


class AccountType(StrEnum):
    HUMAN = "human"
    BOT = "bot"


class User(BaseModel, frozen=True):
    """User account stored in the user repository."""

    user_id: str
    username: str
    password_hash: str  # bcrypt hash for humans, "!" sentinel for bots
    account_type: AccountType = AccountType.HUMAN
    api_key_hash: str | None = None  # SHA-256 hash of API key, only for bots

    @model_validator(mode="after")
    def _validate_account_fields(self) -> Self:
        if self.account_type == AccountType.HUMAN and not self.password_hash:
            raise ValueError("Human accounts must have a password hash")
        if self.account_type == AccountType.BOT and not self.api_key_hash:
            raise ValueError("Bot accounts must have an api_key_hash")
        return self


@dataclass
class AuthSession:
    """Server-side session for authenticated users."""

    session_id: str  # UUID, stored in cookie
    user_id: str
    username: str
    created_at: float  # time.time()
    expires_at: float  # time.time() + TTL
