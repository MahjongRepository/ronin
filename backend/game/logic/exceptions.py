from typing import ClassVar

from game.logic.enums import GameErrorCode


class GameRuleError(Exception):
    """
    A rule judgment refused the acting seat's action: one the wire offered, refused by a rule of the discard (kuikae, a
    riichi player's tsumogiri, a riichi discard that breaks tenpai). The client is told these rules, but a discard it
    gets wrong is only refused, never kicked: the decision stays open.

    Raised only while validating an action, before anything changes. The action handler turns it into a Refusal carrying
    `code`, which the service answers with an ErrorEvent to the acting seat; the turn and its timer continue. Any other
    exception the engine raises is either structural input (ImpossibleActionError) or a server fault. Each judgment is a
    subclass with its own code; the base answers with the generic INVALID_ACTION.
    """

    code: ClassVar[GameErrorCode] = GameErrorCode.INVALID_ACTION


class InvalidDiscardError(GameRuleError):
    """
    The tile is in hand but not a legal discard (kuikae, or a riichi player discarding other than the drawn tile).
    """

    code = GameErrorCode.INVALID_DISCARD


class InvalidRiichiError(GameRuleError):
    """
    The riichi discard would leave the hand not tenpai.
    """

    code = GameErrorCode.INVALID_RIICHI


class ImpossibleActionError(Exception):
    """
    Structurally impossible input: a tile not in hand, or an action or tile the wire did not offer the seat.

    A correct client never sends it. The action handler validating the acting seat's input turns it into
    InvalidGameActionError; raised anywhere else (call resolution executes responses already validated on submit), it is
    a server fault.
    """


class InvalidMeldError(ImpossibleActionError):
    """
    The meld does not match the hand or what was offered (tiles missing, kan not offered, chi shape invalid).
    """


class ScoringError(Exception):
    """
    The scoring library failed on a hand the engine had already judged a win: a server fault, never a rule judgment.
    """


class TileOwnershipError(Exception):
    """
    A committed game state does not own each of the 136 tiles exactly once: a server fault, never a player's.
    """


class UnsupportedSettingsError(Exception):
    """
    Game settings contain unsupported values that cannot be silently ignored.
    """


class GeneratedActionError(Exception):
    """
    The engine refused an action the server made on a seat's behalf (an AI decision or a timeout default).

    The server generated it, so the refusal is a server fault that ends the game, never the seat's fault.
    """


class InvalidGameActionError(Exception):
    """
    A human client sent structurally impossible input for its own seat (modified client, bug, or attack).

    Raised by an action handler only for the acting seat, before anything changes. The session disconnects that player
    (1008) and seats an AI player.

    Attributes:
        action: The game action that was attempted (e.g. "discard", "declare_riichi").
        seat: The acting seat.
        reason: Human-readable explanation of why the action is invalid.
    """

    def __init__(self, *, action: str, seat: int, reason: str) -> None:
        self.action = action
        self.seat = seat
        self.reason = reason
        super().__init__(f"invalid {action} from seat {seat}: {reason}")
