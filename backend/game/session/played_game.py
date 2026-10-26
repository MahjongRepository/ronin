from typing import TYPE_CHECKING

from shared.dal.models import PlayedGameStanding

if TYPE_CHECKING:
    from datetime import datetime

    from game.logic.events import GameEndedEvent
    from shared.dal.models import GameEndReason, PlayedGame


def build_finish_record(
    start: PlayedGame,
    *,
    end_reason: GameEndReason,
    ended_at: datetime,
    game_ended_event: GameEndedEvent | None,
) -> PlayedGame:
    """
    Build a game's whole finish record from its start record, never from engine or connection state at the end.

    A completed game lists the end event's standings in its placement order (tiebreaks by seat distance to the dealer
    included, so never re-sorted), each seat's name and user_id taken from the start record; without the event (an
    abandoned or failed game) the start record's seat-order standings stay, with no scores.
    """
    if game_ended_event is None:
        return start.model_copy(update={"ended_at": ended_at, "end_reason": end_reason})

    participants = {standing.seat: standing for standing in start.standings}
    standings = [
        PlayedGameStanding(
            name=participants[s.seat].name,
            seat=s.seat,
            user_id=participants[s.seat].user_id,
            score=s.score,
            final_score=s.final_score,
        )
        for s in game_ended_event.standings
    ]
    return start.model_copy(
        update={
            "ended_at": ended_at,
            "end_reason": end_reason,
            "num_rounds_played": game_ended_event.num_rounds,
            "standings": standings,
        },
    )
