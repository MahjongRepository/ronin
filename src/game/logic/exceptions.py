"""Typed domain exceptions for game rule violations.

All domain-level rule violations use subclasses of GameRuleError
rather than raw ValueError. This enables consistent catch-and-convert
at the service boundary while preserving the broad fatal-error
containment in MessageRouter for unexpected exceptions.
"""


class GameRuleError(Exception):
    """Base exception for game rule violations.

    Raised by domain logic (turn.py, melds.py, round.py) when a player
    action violates game rules. Caught at the service boundary
    (action_handlers.py) and converted to ErrorEvent responses.
    """


class InvalidDiscardError(GameRuleError):
    """Tile cannot be discarded (not in hand, kuikae restriction, etc.)."""


class InvalidMeldError(GameRuleError):
    """Meld call is invalid (wrong tiles, already called, etc.)."""


class InvalidRiichiError(GameRuleError):
    """Riichi declaration conditions not met."""


class InvalidWinError(GameRuleError):
    """Win declaration (tsumo/ron) conditions not met or calculation error."""


class InvalidActionError(GameRuleError):
    """Action is not valid in the current game state."""


class UnsupportedSettingsError(GameRuleError):
    """Game settings contain unsupported values that cannot be silently ignored."""


class InvalidGameActionError(Exception):
    """Raised when a player sends a provably invalid game action.

    Indicates the client is sending fabricated data (modified client, bug, or attack).
    The player should be disconnected and replaced with a bot.

    Attributes:
        action: The game action that was attempted (e.g. "discard", "declare_riichi").
        seat: The seat number of the player.
        reason: Human-readable explanation of why the action is invalid.

    """

    def __init__(self, *, action: str, seat: int, reason: str) -> None:
        self.action = action
        self.seat = seat
        self.reason = reason
        super().__init__(f"invalid {action} from seat {seat}: {reason}")
