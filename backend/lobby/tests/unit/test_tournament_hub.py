from app.tournaments.hub import HISTORY_MAX_AGE_SECONDS, HISTORY_MAX_ENTRIES, TournamentHub


def _chat(text):
    return {"type": "chat", "player_name": "alice", "text": text}


def _texts(hub, tournament_id):
    return [entry["text"] for entry in hub.history(tournament_id)]


def test_tournament_hub_record__when_entries_age_past_a_day_or_overflow_the_cap__should_keep_newest_recent():
    now = 1_794_393_000.0
    hub = TournamentHub(clock=lambda: now)
    hub.record("cup", _chat("yesterday"))
    hub.record("league", _chat("abandoned"))
    now += HISTORY_MAX_AGE_SECONDS / 2
    hub.record("cup", _chat("last night"))
    now += HISTORY_MAX_AGE_SECONDS / 2 + 1

    kept = hub.record("cup", _chat("today"))

    assert kept == {**_chat("today"), "time": now}
    assert _texts(hub, "cup") == ["last night", "today"]
    assert hub.history("league") == []

    overflow = [f"line {index}" for index in range(HISTORY_MAX_ENTRIES)]
    for text in overflow:
        hub.record("cup", _chat(text))

    assert _texts(hub, "cup") == overflow
