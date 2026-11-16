from typing import ClassVar

from game.logic.refusal import RefusalCode


class GameRuleError(Exception):
    """
    A rule judgment refused the acting seat's action: one the wire offered, refused by a rule of the discard (kuikae, a
    riichi player's tsumogiri, a riichi discard that breaks tenpai). The client is told these rules, but a discard it
    gets wrong is a rule judgment, not structural input.

    Raised only while validating an action, before anything changes. The action handler turns it into a RULE Refusal
    carrying `code`. Any other exception the engine raises is either structural input (ImpossibleActionError) or a
    server fault. Each judgment is a subclass with its own code.
    """

    code: ClassVar[RefusalCode]


class InvalidDiscardError(GameRuleError):
    """
    The tile is in hand but not a legal discard: kuikae forbids it, or a riichi player discards other than the drawn
    tile (each its own subclass).
    """


class KuikaeDiscardError(InvalidDiscardError):
    """
    Kuikae forbids discarding the tile right after the seat's own pon or chi.
    """

    code = RefusalCode.KUIKAE


class RiichiTsumogiriError(InvalidDiscardError):
    """
    A riichi player may discard only the tile it drew.
    """

    code = RefusalCode.RIICHI_DRAWN_TILE_ONLY


class InvalidRiichiError(GameRuleError):
    """
    The riichi discard would leave the hand not tenpai.
    """

    code = RefusalCode.RIICHI_BREAKS_TENPAI


class ImpossibleActionError(Exception):
    """
    Structurally impossible input: a tile not in hand, or an action or tile the wire did not offer the seat.

    A correct client never sends it. The action handler validating the acting seat's input turns it into a NOT_OFFERED
    Refusal carrying `code`; raised anywhere else (call resolution executes responses already validated on submit), it
    is a server fault.
    """

    code: ClassVar[RefusalCode] = RefusalCode.NOT_OFFERED


class TileNotHeldError(ImpossibleActionError):
    """
    The action names a tile the seat does not hold.
    """

    code = RefusalCode.TILE_NOT_HELD


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


class DiscardHistoryError(Exception):
    """
    The round's discard history and its rivers disagree: a server fault, never a player's.
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
