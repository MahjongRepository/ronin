import { type ClientMessage, type ParsedServerMessage } from "@/shared/protocol";
import { type GameSessionData } from "@/shared/session";

/**
 * Why a retry waits: `transport` reopens a dropped socket, `session` resends RECONNECT on the open socket after
 * the server answered `reconnect_retry_later`. Each has its own attempt budget.
 */
export type RetryKind = "transport" | "session";

/** The socket as the session knows it; `down` means none is open or opening. */
export type LinkState = "connecting" | "open" | "down";

export interface PendingRetry {
    readonly kind: RetryKind;
    readonly dueAt: number;
}

export interface RetryAttempts {
    readonly transport: number;
    readonly session: number;
}

/**
 * A session still working for its seat. `joining` has never been admitted, so it identifies with JOIN_GAME;
 * `reconnecting` was, or was told the game already started, so it identifies with RECONNECT; `playing` holds its
 * seat on the open socket.
 */
export interface ActiveSession {
    readonly status: "joining" | "playing" | "reconnecting";
    readonly gameId: string;
    readonly handoff: GameSessionData;
    readonly link: LinkState;
    readonly retry: PendingRetry | null;
    readonly attempts: RetryAttempts;
}

export type EndReason =
    | { readonly kind: "game_ended" }
    | { readonly kind: "no_handoff" }
    | { readonly kind: "left" }
    | { readonly kind: "closed"; readonly code: number; readonly reason: string }
    | { readonly kind: "refused"; readonly code: string }
    | { readonly kind: "retries_exhausted"; readonly retry: RetryKind }
    | { readonly kind: "failed"; readonly detail: string };

/**
 * A session that will never act again on its own: every later input leaves it as it is and emits nothing,
 * except that leaving still takes the player to the lobby from an end that stayed on the page.
 */
export interface EndedSession {
    readonly status: "ended";
    readonly gameId: string;
    readonly reason: EndReason;
}

export type SessionState = ActiveSession | EndedSession;

/** What the session is driven by; `at` is the logical time the driver stamped from its clock. */
export type SessionInput =
    | { readonly kind: "message"; readonly at: number; readonly message: ParsedServerMessage }
    | { readonly kind: "transport_opened"; readonly at: number }
    | {
          readonly kind: "transport_closed";
          readonly at: number;
          readonly code: number;
          readonly reason: string;
      }
    | { readonly kind: "tick"; readonly at: number }
    | { readonly kind: "leave"; readonly at: number };

/**
 * A description of IO for the live driver to run in order; the transition never runs one. Timers are not
 * effects: the driver derives the next deadline from the state after each step and answers it with a tick.
 */
export type SessionEffect =
    | { readonly type: "open_socket"; readonly url: string }
    | { readonly type: "close_socket" }
    | { readonly type: "send"; readonly message: ClientMessage }
    | { readonly type: "clear_handoff"; readonly gameId: string }
    | { readonly type: "redirect_to_lobby" };

export interface SessionStep {
    readonly state: SessionState;
    readonly effects: readonly SessionEffect[];
}
