from dataclasses import dataclass, field

SERVER_CLOSE_CODES = (1000, 1008, 1011, 4001, 4002, 4004)


@dataclass
class SocketStats:
    """
    Count the game sockets' traffic since the process started, process-wide and never per user.

    Out traffic is counted when queued for send, so it overstates what reached clients while sockets are overloaded.
    """

    connections: int = 0
    connections_accepted: int = 0
    messages_in: int = 0
    bytes_in: int = 0
    messages_out: int = 0
    bytes_out: int = 0
    handling_seconds: float = 0.0
    handled_messages: int = 0
    malformed_messages: int = 0
    rate_limited_messages: int = 0
    closes: dict[int, int] = field(default_factory=lambda: dict.fromkeys(SERVER_CLOSE_CODES, 0))

    def count_close(self, code: int) -> None:
        """
        Count a close the server requested; a code outside the fixed set gets its own key rather than going unseen.
        """
        self.closes[code] = self.closes.get(code, 0) + 1

    @property
    def snapshot(self) -> dict[str, int | float]:
        """
        Return the totals and gauges as the flat `/status` keys, one `closes_<code>` key per close code.
        """
        return {
            "connections": self.connections,
            "connections_accepted": self.connections_accepted,
            "messages_in": self.messages_in,
            "bytes_in": self.bytes_in,
            "messages_out": self.messages_out,
            "bytes_out": self.bytes_out,
            "handling_seconds": self.handling_seconds,
            "handled_messages": self.handled_messages,
            "malformed_messages": self.malformed_messages,
            "rate_limited_messages": self.rate_limited_messages,
            **{f"closes_{code}": count for code, count in self.closes.items()},
        }
