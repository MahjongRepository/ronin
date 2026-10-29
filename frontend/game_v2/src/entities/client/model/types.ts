import { type SessionEffect, type SessionState } from "@/entities/session";
import { type TableState } from "@/entities/table";
import {
    type CallType,
    type ClientMessage,
    type KanType,
    type ReplayLine,
    type TimerSettings,
} from "@/shared/protocol";

/**
 * A choice the server offered at a decision, resolved to what answering it sends: a turn's tsumo, riichi with one
 * of its tenpai-keeping discards, a closed or added kan, kyuushu; a call prompt's ron, pon, chi with one of its
 * pairs, or open kan. A discard and a pass are not offers: a turn always takes a discard, a call prompt a pass.
 */
export type Offer =
    | { readonly kind: "tsumo" }
    | { readonly kind: "riichi"; readonly tileId: number }
    | { readonly kind: "kan"; readonly kanType: KanType; readonly tileId: number }
    | { readonly kind: "kyuushu" }
    | { readonly kind: "ron" }
    | { readonly kind: "pon"; readonly tileId: number }
    | {
          readonly kind: "chi";
          readonly tileId: number;
          readonly sequence: readonly [number, number];
      };

/**
 * Where a decision stands: open for an answer, answered with the action sent, or past its deadline in logical
 * time. Expired is for display: it still takes one answer, which the server judges by its wait id, and the client
 * never sends one on its own.
 */
export type DecisionStatus =
    | { readonly kind: "open" }
    | { readonly kind: "submitted"; readonly at: number; readonly message: ClientMessage }
    | { readonly kind: "expired" };

interface DecisionBase {
    readonly waitId: number;
    readonly offers: readonly Offer[];
    readonly openedAt: number;
    /**
     * When the server's timer for the wait likely runs out, in logical time: an estimate for the countdown, never a
     * gate. Null without the timer settings, or for a turn whose opening message names no bank.
     */
    readonly deadline: number | null;
    readonly status: DecisionStatus;
}

/** The seat's own turn, opened by its draw, or by the `turn` event after its own pon or chi. */
export interface TurnDecision extends DecisionBase {
    readonly kind: "turn";
    /** The tile types kuikae forbids discarding on the turn after the seat's own pon or chi. */
    readonly kuikaeTileTypes: readonly number[];
}

/** A call prompt on another seat's discard, or on a kan it may rob. */
export interface CallDecision extends DecisionBase {
    readonly kind: "call";
    readonly callType: CallType;
    readonly tileId: number;
    readonly fromSeat: number;
}

export type Decision = TurnDecision | CallDecision;

/** A local user intent: leave for the lobby, or answer the open decision. */
export type LocalIntent =
    | { readonly type: "leave" }
    | { readonly type: "discard"; readonly tileId: number }
    | { readonly type: "choose"; readonly offer: Offer }
    | { readonly type: "pass" };

/**
 * The one input of the game client's dispatcher, from any source: the live socket, a scripted scenario, or a
 * replay file. Each is stamped with the logical time `at` the source's clock gave it; a `tick` only advances
 * time. A server message carries the raw wire payload, parsed inside the dispatcher; a replay line carries a
 * replay file's event line, parsed as one.
 */
export type ClientEvent =
    | {
          readonly kind: "server_message";
          readonly at: number;
          readonly raw: Readonly<Record<string, unknown>>;
      }
    | {
          readonly kind: "replay_line";
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
 * historical cursor keeps the time it was taken at. A replay has no session: no socket drives it and it sends
 * nothing. The table holds what the source showed: one seat's view for a live seat (`viewerSeat`), every hand for
 * a replay, whose viewer is null.
 */
export interface GameClientState {
    readonly now: number;
    readonly session: SessionState | null;
    readonly table: TableState;
    readonly viewerSeat: number | null;
    readonly decision: Decision | null;
    /** The furiten the server last reported to the viewer's seat; a new deal clears it. */
    readonly furiten: boolean;
    readonly timer: TimerSettings | null;
    readonly pendingConfirm: PendingConfirm | null;
}

/** The session's IO plus a report of a message or replay line the client could not parse, for the driver to show. */
export type ClientEffect =
    | SessionEffect
    | { readonly type: "report_parse_error"; readonly detail: string };

export interface ClientStep {
    readonly state: GameClientState;
    readonly effects: readonly ClientEffect[];
}

/** A step plus what its event carried, as parsed: a server message or replay line, or null for any other. */
export interface TracedStep extends ClientStep {
    readonly parsed: ReplayLine | null;
}
