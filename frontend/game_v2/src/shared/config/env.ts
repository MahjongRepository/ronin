const DEFAULT_LOBBY_URL = "/";

/** Lobby server URL — from Vite env in dev, falls back to "/" in production (same origin). */
export function getLobbyUrl(): string {
    return import.meta.env.VITE_LOBBY_URL || DEFAULT_LOBBY_URL;
}

function lobbyPageUrl(path: string): string {
    return `${getLobbyUrl().replace(/\/+$/, "")}${path}`;
}

/** The lobby's game history page, where a replay page sends a reader back. */
export function getLobbyHistoryUrl(): string {
    return lobbyPageUrl("/history");
}

/**
 * A game's replay page, shown from `seat` (none: the recorded first dealer's), with this page's client version (`v`),
 * so the v2 client opens it too.
 */
export function replayPageUrl(gameId: string, seat: number | null, search: string): string {
    const params = new URLSearchParams();
    const version = new URLSearchParams(search).get("v");
    if (version !== null) {
        params.set("v", version);
    }
    if (seat !== null) {
        params.set("seat", String(seat));
    }
    const query = params.toString();
    return lobbyPageUrl(
        `/play/history/${encodeURIComponent(gameId)}${query === "" ? "" : `?${query}`}`,
    );
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
