class FakeReplayStorage:
    def __init__(self) -> None:
        self.saved: dict[str, str] = {}

    def save_replay(self, game_id: str, content: str) -> None:
        self.saved[game_id] = content


class FailingReplayStorage:
    def save_replay(self, game_id: str, content: str) -> None:
        raise OSError("disk full")
