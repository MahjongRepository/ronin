import { type SessionEffect, type SessionState } from "@/entities/session";

/**
 * A local user intent. Only leaving exists yet; the table's intents (a tile tapped, a call chosen) join this
 * union when the live game's decisions arrive.
 */
export interface LocalIntent {
    readonly type: "leave";
}

/**
 * The one input of the game client's dispatcher, from any source: the live socket, a scripted scenario, or later
 * replay lines. Each is stamped with the logical time `at` the source's clock gave it; a `tick` only advances
 * time. A server message carries the raw wire payload, parsed inside the dispatcher.
 */
export type ClientEvent =
    | {
          readonly kind: "server_message";
          readonly at: number;
          readonly raw: Readonly<Record<string, unknown>>;
      }
    | { readonly kind: "transport_opened"; readonly at: number }
    | {
          readonly kind: "transport_closed";
          readonly at: number;
          readonly code: number;
          readonly reason: string;
      }
    | { readonly kind: "transport_error"; readonly at: number; readonly detail: string }
    | { readonly kind: "tick"; readonly at: number }
    | { readonly kind: "intent"; readonly at: number; readonly intent: LocalIntent };

/** A round end the client confirms by itself once `dueAt` passes, standing in for the result screen. */
export interface PendingConfirm {
    readonly waitId: number;
    readonly dueAt: number;
}

/**
 * The game client's state at logical time `now`, the `at` of the last event it took, so a state kept at a
 * historical cursor keeps the time it was taken at.
 */
export interface GameClientState {
    readonly now: number;
    readonly session: SessionState;
    readonly pendingConfirm: PendingConfirm | null;
}

/** The session's IO plus a report of a server message the client could not parse, for the driver to show. */
export type ClientEffect =
    | SessionEffect
    | { readonly type: "report_parse_error"; readonly detail: string };

export interface ClientStep {
    readonly state: GameClientState;
    readonly effects: readonly ClientEffect[];
}
