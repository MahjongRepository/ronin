from __future__ import annotations

from pydantic import TypeAdapter

from app.chat_messages import LobbyChatMessage, decode_client_frame

TournamentClientMessage = LobbyChatMessage

_tournament_message_adapter: TypeAdapter[TournamentClientMessage] = TypeAdapter(TournamentClientMessage)


def parse_tournament_message(raw: str) -> TournamentClientMessage:
    """
    Parse and validate a raw JSON string into a typed tournament message; chat is the only one.

    Raise ``json.JSONDecodeError`` for malformed JSON, ``ValidationError`` for an invalid message and a plain
    ``ValueError`` for one over the size limit.
    """
    return _tournament_message_adapter.validate_python(decode_client_frame(raw))
