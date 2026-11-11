from lobby.tournaments.hub import CHAT_HISTORY_MAX_AGE_SECONDS, CHAT_HISTORY_MAX_LINES, TournamentHub


def _texts(hub, tournament_id):
    return [line["text"] for line in hub.chat_history(tournament_id)]


def test_tournament_hub_add_chat_line__when_lines_age_past_a_day_or_overflow_the_cap__should_keep_newest_recent():
    now = 1_794_393_000.0
    hub = TournamentHub(clock=lambda: now)
    hub.add_chat_line("cup", "alice", "yesterday")
    hub.add_chat_line("league", "bob", "abandoned")
    now += CHAT_HISTORY_MAX_AGE_SECONDS + 1

    hub.add_chat_line("cup", "carol", "today")

    assert hub.chat_history("cup") == [{"player_name": "carol", "text": "today", "time": now}]
    assert hub.chat_history("league") == []

    overflow = [f"line {index}" for index in range(CHAT_HISTORY_MAX_LINES)]
    for text in overflow:
        hub.add_chat_line("cup", "carol", text)

    assert _texts(hub, "cup") == overflow
