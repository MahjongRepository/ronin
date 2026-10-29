const DEFAULT_LOBBY_URL = "/";

/** Lobby server URL — from Vite env in dev, falls back to "/" in production (same origin). */
export function getLobbyUrl(): string {
    return import.meta.env.VITE_LOBBY_URL || DEFAULT_LOBBY_URL;
}

const DEBUG_OFF_VALUES: ReadonlySet<string> = new Set(["0", "false", "no", "off"]);

/** Whether a page's query asks for its debug view: `?debug` alone or with any value but an off one (`0`, `false`). */
export function isDebugRequested(search: string): boolean {
    const value = new URLSearchParams(search).get("debug");
    return value !== null && !DEBUG_OFF_VALUES.has(value.toLowerCase());
}

/**
 * A game's page under the game client's URL the lobby named, with the current page's query, so the v2 client
 * (`?v=2`) and `?debug` carry over; the router decodes the id back.
 */
export function gamePageUrl(gameClientUrl: string, gameId: string, search: string): string {
    return `${gameClientUrl}/${encodeURIComponent(gameId)}${search}`;
}
