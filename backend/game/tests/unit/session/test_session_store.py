from game.session.session_store import SessionStore


class TestSessionStore:
    def test_create_session_returns_unique_tokens(self):
        store = SessionStore()
        s1 = store.create_session("Alice", "g1")
        s2 = store.create_session("Bob", "g1")
        assert s1.session_token != s2.session_token

    def test_bind_seat_updates_session(self):
        store = SessionStore()
        session = store.create_session("Alice", "g1")
        store.bind_seat(session.session_token, 2)
        assert session.seat == 2

    def test_bind_seat_ignores_unknown_token(self):
        store = SessionStore()
        store.bind_seat("nonexistent", 0)  # should not raise
        assert store._sessions.get("nonexistent") is None

    def test_mark_disconnected_sets_timestamp(self):
        store = SessionStore()
        session = store.create_session("Alice", "g1")
        assert session.disconnected_at is None
        store.mark_disconnected(session.session_token)
        assert session.disconnected_at is not None

    def test_mark_disconnected_ignores_unknown_token(self):
        store = SessionStore()
        store.mark_disconnected("nonexistent")  # should not raise
        assert store._sessions.get("nonexistent") is None

    def test_remove_session_deletes_entry(self):
        store = SessionStore()
        session = store.create_session("Alice", "g1")
        store.remove_session(session.session_token)
        assert store._sessions.get(session.session_token) is None

    def test_remove_session_ignores_unknown_token(self):
        store = SessionStore()
        store.remove_session("nonexistent")  # should not raise

    def test_cleanup_game_removes_all_sessions_for_game(self):
        store = SessionStore()
        s1 = store.create_session("Alice", "g1")
        s2 = store.create_session("Bob", "g1")
        store.cleanup_game("g1")
        assert store._sessions.get(s1.session_token) is None
        assert store._sessions.get(s2.session_token) is None

    def test_cleanup_game_preserves_sessions_for_other_games(self):
        store = SessionStore()
        s1 = store.create_session("Alice", "g1")
        s2 = store.create_session("Bob", "g2")
        store.cleanup_game("g1")
        assert store._sessions.get(s1.session_token) is None
        assert store._sessions.get(s2.session_token) is not None

    def test_get_session_returns_session_by_token(self):
        store = SessionStore()
        session = store.create_session("Alice", "g1")
        result = store.get_session(session.session_token)
        assert result is session

    def test_get_session_returns_none_for_unknown_token(self):
        store = SessionStore()
        assert store.get_session("nonexistent") is None

    def test_mark_reconnected_clears_disconnect_state(self):
        store = SessionStore()
        session = store.create_session("Alice", "g1")
        store.mark_disconnected(session.session_token)
        assert session.disconnected_at is not None
        store.mark_reconnected(session.session_token)
        assert session.disconnected_at is None

    def test_mark_reconnected_ignores_unknown_token(self):
        store = SessionStore()
        store.mark_reconnected("nonexistent")  # should not raise
