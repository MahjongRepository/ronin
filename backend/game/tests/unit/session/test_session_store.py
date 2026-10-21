from game.session.session_store import SessionStore


class TestSessionStore:
    def test_session_store__when_game_cleaned_up__should_remove_all_its_sessions(self):
        store = SessionStore()
        s1 = store.create_session("Alice", "g1")
        s2 = store.create_session("Bob", "g1")
        store.cleanup_game("g1")
        assert store._sessions.get(s1.session_token) is None
        assert store._sessions.get(s2.session_token) is None

    def test_session_store__when_game_cleaned_up__should_keep_other_games_sessions(self):
        store = SessionStore()
        s1 = store.create_session("Alice", "g1")
        s2 = store.create_session("Bob", "g2")
        store.cleanup_game("g1")
        assert store._sessions.get(s1.session_token) is None
        assert store._sessions.get(s2.session_token) is not None
