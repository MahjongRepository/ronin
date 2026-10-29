import { type SessionEffect, type SessionState } from "@/entities/session";
import { type KanDeclaredEvent, type TableState } from "@/entities/table";
import { type HandoffRecovery } from "@/shared/api";
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

/** A local user intent: leave for the lobby, answer the open decision, or confirm the round result read. */
export type LocalIntent =
    | { readonly type: "leave" }
    | { readonly type: "discard"; readonly tileId: number }
    | { readonly type: "choose"; readonly offer: Offer }
    | { readonly type: "pass" }
    | { readonly type: "confirm_result" };

/** An intent that answers the open decision. */
export type DecisionIntent = Exclude<LocalIntent, { readonly type: "leave" | "confirm_result" }>;

/** An intent the board offers: an answer to the open decision, or the round result's confirm. */
export type PlayIntent = Exclude<LocalIntent, { readonly type: "leave" }>;

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
    | { readonly kind: "intent"; readonly at: number; readonly intent: LocalIntent }
    | {
          readonly kind: "handoff_recovered";
          readonly at: number;
          readonly recovery: HandoffRecovery;
      };

/**
 * A short-lived notice to the viewer, shown until `until` in logical time: its seat is back after a reconnect, or the
 * server refused its last move (by the game's error code, or the socket's rate limit) while the move stays open.
 */
export type TimedNotice =
    | { readonly kind: "reconnected"; readonly until: number }
    | { readonly kind: "refused"; readonly code: string; readonly until: number };

/**
 * Where the viewer stands with the round result it reads before the next deal. Owed: the server waits on the seat's
 * confirm by this wait id until the round's one advance deadline, the timeout times the result's pages, when the
 * client can estimate it (logical time, backdated by a snapshot's elapsed time; null when unknown). It is for display
 * only: the server's timeout advances the game, and the client never confirms on its own. Sent: the player confirmed
 * it once and waits for the others, unless the rate limit reopens it as owed. Confirmed: a reconnect's snapshot owes
 * no confirm, so the seat waits too. Final: the game's last result, which the game end follows at once; the player
 * dismisses it to read the standings, which sends nothing.
 */
export type RoundConfirm =
    | { readonly kind: "owed"; readonly waitId: number; readonly deadline: number | null }
    | { readonly kind: "sent"; readonly waitId: number; readonly deadline: number | null }
    | { readonly kind: "confirmed" }
    | { readonly kind: "final" };

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
    readonly roundConfirm: RoundConfirm | null;
    /** The latest short-lived notice, until it expires or a newer one replaces it. */
    readonly notice: TimedNotice | null;
    /** How many server messages the client could not read: the table may be wrong from the first. */
    readonly unreadMessages: number;
}

/** The session's IO plus a report of a message or replay line the client could not parse, for the driver to show. */
export type ClientEffect =
    | SessionEffect
    | { readonly type: "report_parse_error"; readonly detail: string };

export interface ClientStep {
    readonly state: GameClientState;
    readonly effects: readonly ClientEffect[];
}

/**
 * A step plus what it took of its event, as parsed: a server message or replay line, the kan a replay's round end
 * robbed as declared, or null for any other. A partial step took only part of its event: the dispatcher steps the
 * same event again for the rest.
 */
export interface TracedStep extends ClientStep {
    readonly parsed: ReplayLine | KanDeclaredEvent | null;
    readonly partial: boolean;
}
