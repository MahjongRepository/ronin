from game.session.session_store import SessionStore


class TestSessionStore:
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
