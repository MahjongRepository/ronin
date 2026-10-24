const DEFAULT_LOBBY_URL = "/";

/** Lobby server URL — from Vite env in dev, falls back to "/" in production (same origin). */
export function getLobbyUrl(): string {
    return import.meta.env.VITE_LOBBY_URL || DEFAULT_LOBBY_URL;
}
