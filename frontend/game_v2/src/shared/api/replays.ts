/** A replay file's text, or the HTTP status the server refused it with. */
export type ReplayFetch =
    | { readonly ok: true; readonly text: string }
    | { readonly ok: false; readonly status: number };

/** Fetch a replay; rejects on a network failure, and with an `AbortError` once `signal` aborts. */
export type LoadReplay = (gameId: string, signal: AbortSignal) => Promise<ReplayFetch>;

export async function fetchReplay(gameId: string, signal: AbortSignal): Promise<ReplayFetch> {
    const response = await fetch(`/api/replays/${encodeURIComponent(gameId)}`, { signal });
    if (!response.ok) {
        return { ok: false, status: response.status };
    }
    return { ok: true, text: await response.text() };
}

export function isAbortError(error: unknown): boolean {
    return error instanceof DOMException && error.name === "AbortError";
}
