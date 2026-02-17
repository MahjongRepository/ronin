const DEFAULT_LOBBY_URL = "http://localhost:8710";

/** Lobby server URL from env.js, with localhost fallback. */
export function getLobbyUrl(): string {
    return (window as unknown as Record<string, string>).__LOBBY_URL__ || DEFAULT_LOBBY_URL;
}
