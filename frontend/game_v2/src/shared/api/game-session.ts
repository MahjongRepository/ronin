import { z } from "zod";

import { type GameSessionData } from "@/shared/session";

const GAME_SESSION_URL = "/api/game-session";
const HTTP_UNAUTHORIZED = 401;
const HTTP_NOT_FOUND = 404;

/** The lobby's answer (`docs/architecture.md`, Game client contract): the game the player plays and its handoff. */
const handoffSchema = z.object({
    game_client_url: z.string().min(1),
    game_id: z.string().min(1),
    game_ticket: z.string().min(1),
    ws_url: z.string().min(1),
});

/**
 * What asking the lobby for the player's game found: the handoff of the game they play (which may be another game
 * than the page's), that they play none (or are not logged in), or that the lookup failed.
 */
export type HandoffRecovery =
    | {
          readonly kind: "found";
          readonly gameId: string;
          readonly gameClientUrl: string;
          readonly handoff: GameSessionData;
      }
    | { readonly kind: "missing" }
    | { readonly kind: "failed"; readonly detail: string };

/** Ask the lobby for the handoff; rejects on a network failure, and with an `AbortError` once `signal` aborts. */
export type RecoverHandoff = (signal: AbortSignal) => Promise<HandoffRecovery>;

export async function fetchGameHandoff(signal: AbortSignal): Promise<HandoffRecovery> {
    const response = await fetch(GAME_SESSION_URL, {
        cache: "no-store",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        signal,
    });
    if (response.status === HTTP_NOT_FOUND || response.status === HTTP_UNAUTHORIZED) {
        return { kind: "missing" };
    }
    if (!response.ok) {
        return { detail: `HTTP ${response.status}`, kind: "failed" };
    }
    const parsed = handoffSchema.safeParse(await response.json());
    if (!parsed.success) {
        return { detail: "malformed game session", kind: "failed" };
    }
    const { game_client_url: gameClientUrl, game_id: gameId, game_ticket, ws_url } = parsed.data;
    return {
        gameClientUrl,
        gameId,
        handoff: { gameTicket: game_ticket, wsUrl: ws_url },
        kind: "found",
    };
}
