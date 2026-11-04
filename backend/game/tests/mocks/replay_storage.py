class FakeReplayStorage:
    def __init__(self) -> None:
        self.saved: dict[str, bytes] = {}

    def save_replay(self, game_id: str, content: bytes) -> None:
        self.saved[game_id] = content


class FailingReplayStorage:
    def save_replay(self, game_id: str, content: bytes) -> None:
        raise OSError("disk full")
