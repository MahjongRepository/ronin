from game.session.models import SessionData
from game.session.session_store import SessionStore


class TestSessionData:
    def test_defaults(self):
        sd = SessionData(session_token="tok", player_name="Alice", game_id="g1")
        assert sd.seat is None
        assert sd.disconnected_at is None

    def test_all_fields(self):
        sd = SessionData(
            session_token="tok",
            player_name="Bob",
            game_id="g2",
            seat=1,
            disconnected_at=100.0,
        )
        assert sd.session_token == "tok"
        assert sd.player_name == "Bob"
        assert sd.game_id == "g2"
        assert sd.seat == 1
        assert sd.disconnected_at == 100.0


class TestSessionStore:
    def test_create_session_returns_unique_tokens(self):
        store = SessionStore()
        s1 = store.create_session("Alice", "g1")
        s2 = store.create_session("Bob", "g1")
        assert s1.session_token != s2.session_token

    def test_create_session_stores_player_name_and_game_id(self):
        store = SessionStore()
        session = store.create_session("Alice", "g1")
        assert session.player_name == "Alice"
        assert session.game_id == "g1"
        assert session.seat is None
        assert session.disconnected_at is None

    def test_get_session_returns_none_for_unknown_token(self):
        store = SessionStore()
        assert store.get_session("nonexistent") is None

    def test_get_session_returns_created_session(self):
        store = SessionStore()
        created = store.create_session("Alice", "g1")
        fetched = store.get_session(created.session_token)
        assert fetched is created

    def test_bind_seat_updates_session(self):
        store = SessionStore()
        session = store.create_session("Alice", "g1")
        store.bind_seat(session.session_token, 2)
        assert session.seat == 2

    def test_bind_seat_ignores_unknown_token(self):
        store = SessionStore()
        store.bind_seat("nonexistent", 0)  # should not raise
        assert store.get_session("nonexistent") is None

    def test_mark_disconnected_sets_timestamp(self):
        store = SessionStore()
        session = store.create_session("Alice", "g1")
        assert session.disconnected_at is None
        store.mark_disconnected(session.session_token)
        assert session.disconnected_at is not None
        assert isinstance(session.disconnected_at, float)

    def test_mark_disconnected_ignores_unknown_token(self):
        store = SessionStore()
        store.mark_disconnected("nonexistent")  # should not raise
        assert store.get_session("nonexistent") is None

    def test_remove_session_deletes_entry(self):
        store = SessionStore()
        session = store.create_session("Alice", "g1")
        store.remove_session(session.session_token)
        assert store.get_session(session.session_token) is None

    def test_remove_session_ignores_unknown_token(self):
        store = SessionStore()
        store.remove_session("nonexistent")  # should not raise

    def test_cleanup_game_removes_all_sessions_for_game(self):
        store = SessionStore()
        s1 = store.create_session("Alice", "g1")
        s2 = store.create_session("Bob", "g1")
        store.cleanup_game("g1")
        assert store.get_session(s1.session_token) is None
        assert store.get_session(s2.session_token) is None

    def test_cleanup_game_preserves_sessions_for_other_games(self):
        store = SessionStore()
        s1 = store.create_session("Alice", "g1")
        s2 = store.create_session("Bob", "g2")
        store.cleanup_game("g1")
        assert store.get_session(s1.session_token) is None
        assert store.get_session(s2.session_token) is not None
