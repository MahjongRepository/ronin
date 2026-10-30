import { type HandoffRecovery } from "@/shared/api";
import { type ClientMessage, type ParsedServerMessage } from "@/shared/protocol";
import { type GameSessionData } from "@/shared/session";

/**
 * Why a retry waits: `transport` reopens a dropped socket, `session` resends the identity message on the open socket
 * after a rate limit or `reconnect_retry_later`. Each has its own attempt budget.
 */
export type RetryKind = "transport" | "session";

export interface RetryAttempts {
    readonly transport: number;
    readonly session: number;
}

/**
 * How a session seeking its seat claims it: JOIN_GAME until it is admitted, RECONNECT once it was or the server said
 * the game already started. `lostSeat`: this page held the seat and lost it to a drop, what the player sees as lost.
 */
export type Identity =
    | { readonly kind: "join" }
    | { readonly kind: "reconnect"; readonly lostSeat: boolean };

/** What every active session knows: its game and the lobby's handoff. */
interface SessionBase {
    readonly gameId: string;
    readonly handoff: GameSessionData;
}

/** What a session seeking its seat adds: how it claims it, and the retries it spent since it last held it. */
interface SeekingBase extends SessionBase {
    readonly identity: Identity;
    readonly attempts: RetryAttempts;
}

/** A socket asked for and not open yet; past `connectDeadline` the attempt counts as a failed connection. */
export interface ConnectingSession extends SeekingBase {
    readonly status: "connecting";
    readonly connectDeadline: number;
}

/**
 * An open socket that sent its identity message and awaits the admission, or, refused for now (a rate limit, a
 * `reconnect_retry_later`), resends it at `sessionRetryAt`.
 */
export interface IdentifyingSession extends SeekingBase {
    readonly status: "identifying";
    readonly sessionRetryAt: number | null;
}

/** The seat held on the open socket. */
export interface PlayingSession extends SessionBase {
    readonly status: "playing";
}

/** No socket since a drop: its transport retry opens one at `dueAt`. */
export interface AwaitingRetrySession extends SeekingBase {
    readonly status: "awaiting_retry";
    readonly dueAt: number;
}

/** A session working for its seat: connecting, identifying or awaiting a transport retry. */
export type SeekingSession = ConnectingSession | IdentifyingSession | AwaitingRetrySession;

/** A session holding or working for its seat; only `playing` holds it, and only it may send game messages. */
export type ActiveSession = SeekingSession | PlayingSession;

/**
 * A page whose tab held no handoff, asking the lobby for the player's game before it can join: the lookup is in
 * flight, or, after `failedLookups` failed, waits until `retryAt` to ask again.
 */
export interface RecoveringSession {
    readonly status: "recovering";
    readonly gameId: string;
    readonly failedLookups: number;
    readonly retryAt: number | null;
}

export type EndReason =
    | { readonly kind: "game_ended" }
    | { readonly kind: "no_handoff" }
    | { readonly kind: "recovery_failed"; readonly detail: string }
    | { readonly kind: "moved"; readonly gameId: string }
    | { readonly kind: "left" }
    | { readonly kind: "closed"; readonly code: number; readonly reason: string }
    | { readonly kind: "refused"; readonly code: string }
    | {
          readonly kind: "retries_exhausted";
          readonly retry: RetryKind;
          /** The game had started with the seat (the session was reconnecting), so an AI plays it meanwhile. */
          readonly gameStarted: boolean;
      }
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

export type SessionState = RecoveringSession | ActiveSession | EndedSession;

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
    | { readonly kind: "leave"; readonly at: number }
    | {
          readonly kind: "handoff_recovered";
          readonly at: number;
          readonly recovery: HandoffRecovery;
      };

/**
 * A description of IO for the live driver to run in order; the transition never runs one. Timers are not
 * effects: the driver derives the next deadline from the state after each step and answers it with a tick.
 */
export type SessionEffect =
    | { readonly type: "open_socket"; readonly url: string }
    | { readonly type: "close_socket" }
    | { readonly type: "send"; readonly message: ClientMessage }
    | { readonly type: "clear_handoff"; readonly gameId: string }
    | { readonly type: "redirect_to_lobby" }
    | { readonly type: "recover_handoff" }
    | { readonly type: "store_handoff"; readonly gameId: string; readonly handoff: GameSessionData }
    | {
          readonly type: "redirect_to_game";
          readonly gameId: string;
          readonly gameClientUrl: string;
      };

export interface SessionStep {
    readonly state: SessionState;
    readonly effects: readonly SessionEffect[];
}
