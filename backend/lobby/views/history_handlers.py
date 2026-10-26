from __future__ import annotations

from typing import TYPE_CHECKING

from lobby.views.assets import render_page

if TYPE_CHECKING:
    from datetime import datetime

    from starlette.requests import Request
    from starlette.responses import Response

    from shared.dal.models import PlayedGame

SECONDS_PER_HOUR = 3600
SECONDS_PER_MINUTE = 60


def _format_duration(started_at: datetime, ended_at: datetime) -> str:
    """
    Format game duration as a human-readable string (e.g. '5m 30s', '1h 12m', '45s').
    """
    seconds = max(int((ended_at - started_at).total_seconds()), 0)
    if seconds >= SECONDS_PER_HOUR:
        h = seconds // SECONDS_PER_HOUR
        m = (seconds % SECONDS_PER_HOUR) // SECONDS_PER_MINUTE
        return f"{h}h {m}m"

    if seconds >= SECONDS_PER_MINUTE:
        m = seconds // SECONDS_PER_MINUTE
        s = seconds % SECONDS_PER_MINUTE
        return f"{m}m {s}s"

    return f"{seconds}s"


def _prepare_history_for_display(games: list[PlayedGame]) -> list[dict]:
    """
    Transform played games into template-friendly view models.
    """
    result = []
    for game in games:
        has_scores = game.standings and game.standings[0].final_score is not None
        players = [
            {
                "name": s.name,
                "score": s.score,
                "final_score": s.final_score,
                "is_winner": has_scores and i == 0,
            }
            for i, s in enumerate(game.standings)
        ]

        duration_label = None
        if game.ended_at:
            duration_label = _format_duration(game.started_at, game.ended_at)

        result.append(
            {
                "game": game,
                "players": players,
                "duration_label": duration_label,
                "game_type_label": (
                    "南" if game.game_type == "hanchan" else "東" if game.game_type == "tonpusen" else ""
                ),
            },
        )

    return result


async def history_page(request: Request) -> Response:
    """GET /history - render the history page with recent played games."""
    game_repo = request.app.state.game_repo
    games = await game_repo.get_recent_completed_games(limit=20)
    display_games = _prepare_history_for_display(games)
    return render_page(
        request, template_name="history.html", context={"games": display_games, "username": request.user.username}
    )
