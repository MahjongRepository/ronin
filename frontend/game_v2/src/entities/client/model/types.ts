import { type SessionEffect, type SessionState } from "@/entities/session";
import { type Call, type KanDeclaredEvent, type TableState } from "@/entities/table";
import { type HandoffRecovery } from "@/shared/api";
import {
    type CallType,
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
 * A play switch: a standing answer the player turns on for the rest of the hand. Auto win takes a tsumo or ron offer,
 * No calls passes a call prompt that offers chi, pon or open kan and no ron, Auto discard discards the drawn tile on a
 * turn that offers nothing else.
 */
export type PlaySwitch = "auto_win" | "no_calls" | "auto_discard";

/** Which play switches are on. */
export type PlaySwitches = Readonly<Record<PlaySwitch, boolean>>;

/**
 * Where a decision stands: open for an answer, answered with the intent the dispatcher took and sent (by the player's
 * press, or by the play switch that answered it, `bySwitch`), or past its deadline in logical time. Expired is for display: it still takes
 * one answer, which the server judges by its wait id, and the client never sends one without the player's
 * instruction.
 */
export type DecisionStatus =
    | { readonly kind: "open" }
    | {
          readonly kind: "submitted";
          readonly at: number;
          readonly intent: DecisionIntent;
          readonly bySwitch: PlaySwitch | null;
      }
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
    /**
     * When the turn's base time likely runs out and its bank starts to drain, in logical time: the server's base time
     * from the opening, less what a re-sent wait says has run. Null when the turn has no deadline.
     */
    readonly baseDeadline: number | null;
    /** The tile types kuikae forbids discarding on the turn after the seat's own pon or chi. */
    readonly kuikaeTileTypes: readonly number[];
    /** The tile the turn's draw drew; null on the turn after the seat's own pon or chi, which draws none. */
    readonly drawnTileId: number | null;
}

/** A call prompt on another seat's discard, or on a kan it may rob. */
export interface CallDecision extends DecisionBase {
    readonly kind: "call";
    readonly callType: CallType;
    readonly tileId: number;
    readonly fromSeat: number;
}

export type Decision = TurnDecision | CallDecision;

/**
 * A local user intent: leave for the lobby, answer the open decision, confirm the round result read, reopen the
 * game's last result from the standings, or turn a play switch on or off, which sends nothing itself.
 */
export type LocalIntent =
    | { readonly type: "leave" }
    | { readonly type: "discard"; readonly tileId: number }
    | { readonly type: "choose"; readonly offer: Offer }
    | { readonly type: "pass" }
    | { readonly type: "confirm_result" }
    | { readonly type: "show_last_result" }
    | { readonly type: "toggle_switch"; readonly playSwitch: PlaySwitch };

/** An intent that answers the open decision. */
export type DecisionIntent = Exclude<
    LocalIntent,
    { readonly type: "leave" | "confirm_result" | "show_last_result" | "toggle_switch" }
>;

/** An intent the board offers: an answer to the open decision, the round result's confirm, or a play switch. */
export type PlayIntent = Exclude<LocalIntent, { readonly type: "leave" }>;

/**
 * The one input of the game client's dispatcher, from any source: the live socket, a scripted scenario, or a
 * replay file. Each is stamped with the logical time `at` the source's clock gave it; a `tick` only advances
 * time. A server message carries the raw wire payload, parsed inside the dispatcher; a replay line carries a
 * replay file's event line, parsed as one. A transport error is the browser's socket error, which its close follows;
 * an undecodable frame is a server frame the socket could not decode into a message (not binary, not MessagePack, not
 * an object), a message the client missed.
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
    | { readonly kind: "frame_undecodable"; readonly at: number; readonly detail: string }
    | { readonly kind: "tick"; readonly at: number }
    | { readonly kind: "intent"; readonly at: number; readonly intent: LocalIntent }
    | {
          readonly kind: "handoff_recovered";
          readonly at: number;
          readonly recovery: HandoffRecovery;
      };

/** An event a live seat's client takes: any but a replay line. */
export type LiveEvent = Exclude<ClientEvent, { readonly kind: "replay_line" }>;

/** The one event a replay's client takes: a line of its file. */
export type ReplayLineEvent = Extract<ClientEvent, { readonly kind: "replay_line" }>;

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
 * no confirm, so the seat waits too.
 */
export type RoundConfirm =
    | { readonly kind: "owed"; readonly waitId: number; readonly deadline: number | null }
    | { readonly kind: "sent"; readonly waitId: number; readonly deadline: number | null }
    | { readonly kind: "confirmed" };

/**
 * What the seat owes the server, one at a time: its open decision, or the round result it reads before the next deal.
 * The server never waits on both, since a round end closes every decision and only the next deal opens one.
 */
export type Pending =
    | { readonly kind: "decision"; readonly decision: Decision }
    | { readonly kind: "round_confirm"; readonly confirm: RoundConfirm };

/**
 * The protocol failure that put the client out of step with the server: a server message that does not parse, a frame
 * that does not decode, or a message its table or decision cannot take (`DesyncError`).
 */
export type DesyncCause = "unreadable_message" | "undecodable_frame" | "impossible_state";

/**
 * A client in step with the server, and what its seat owes while the session holds the seat; null while it owes
 * nothing or holds no seat.
 */
export interface InStep {
    readonly kind: "in_step";
    readonly pending: Pending | null;
}

/**
 * Where an out-of-step client's resync request stands. Unsent: none is outstanding, so the client asks as soon as its
 * session can (at once while it holds the seat), whether it just lost step, its socket dropped (the reconnect bringing
 * a snapshot of its own) or the game moved while it awaited the deal. Sent: its request is outstanding on the open
 * socket until `due`, when it counts as unanswered and is sent again; a rate limit meanwhile answers it, never the
 * session's identity message. Awaiting the snapshot: the socket identifies with RECONNECT, whose own snapshot is the
 * answer, asked for only once it goes unanswered at `due`. At the deal: the server said the game has not dealt yet, or
 * the socket identifies with JOIN_GAME (answered by `game_joined`, never a snapshot, and only before the deal), so the
 * client asks again at the first deal's time `due`. On a game message: the same with no deal time ahead, so the
 * client asks again only once the server's next game message says the game moved.
 */
export type ResyncRequest =
    | { readonly kind: "unsent" }
    | { readonly kind: "sent"; readonly due: number }
    | { readonly kind: "awaiting_snapshot"; readonly due: number }
    | { readonly kind: "at_deal"; readonly due: number }
    | { readonly kind: "on_game_message" };

/**
 * A client out of step with the server since logical time `since`: it owes and answers nothing and drops every server
 * message but a snapshot, the game's end and the round end before it (the game's last) until a snapshot rebuilds it,
 * which its resync request asks for. `unreadMessages`: the protocol failures it met since it lost step, the first
 * included, so the board says its table may be wrong.
 */
export interface Desync {
    readonly kind: "out_of_step";
    readonly cause: DesyncCause;
    readonly detail: string;
    readonly since: number;
    readonly request: ResyncRequest;
    readonly unreadMessages: number;
}

/** Whether the client is in step with the server, which a snapshot alone restores. */
export type Sync = InStep | Desync;

/**
 * The calls the board shows, made aloud by one move at logical time `at`. A live server message's last until `until`
 * or a newer call; a replay line's until the next move, since a replay's stop is a move and its time never runs.
 */
export interface ShownCalls {
    readonly calls: readonly Call[];
    readonly at: number;
    readonly until: number;
}

/**
 * What every client holds at logical time `now`, the `at` of the last event it took, so a state kept at a historical
 * cursor keeps the time it was taken at: the table as its source showed it, and the calls its board shows by their
 * seats, or null.
 */
interface ClientBase {
    readonly now: number;
    readonly table: TableState;
    readonly calls: ShownCalls | null;
}

/**
 * A replay's client: every hand the file records, and nothing else. No socket drives it, it has no viewer and it
 * sends nothing, so it owes, answers and loses step with nothing.
 */
export interface ReplayClient extends ClientBase {
    readonly kind: "replay";
}

/** A live seat's client: its session, the table as the seat sees it, and the seat's own facts and obligations. */
export interface LiveClient extends ClientBase {
    readonly kind: "live";
    readonly session: SessionState;
    /** The seat the server named the viewer's, or null before it did. */
    readonly viewerSeat: number | null;
    /** The furiten the server last reported to the viewer's seat; a new deal clears it. */
    readonly furiten: boolean;
    readonly timer: TimerSettings | null;
    /**
     * How long the server holds the pending game the seat joined for its players before it starts, from its
     * `game_joined`, in seconds; null before the server said so.
     */
    readonly pendingGameSeconds: number | null;
    /** Whether the client is in step with the server, and what the seat owes it while it is. */
    readonly sync: Sync;
    /**
     * The game's last result shown over the standings: the game end follows it at once, the player dismisses it to
     * read the standings and may reopen it from them, none of which sends anything. Out of step too, since that result
     * and the standings are the server's.
     */
    readonly showsLastResult: boolean;
    /** The latest short-lived notice, until it expires or a newer one replaces it. */
    readonly notice: TimedNotice | null;
    /**
     * How many resync requests this page has sent, never reset, so a client that loses step again and again ends
     * however often its snapshots arrive.
     */
    readonly resyncRequests: number;
    /**
     * When the server's game start pause likely ends with the first deal, in logical time, from the game start's timer
     * settings; null without them.
     */
    readonly firstDealDue: number | null;
    /** The play switches the player turned on for this hand; a deal turns them off. */
    readonly switches: PlaySwitches;
    /**
     * The highest wait id a decision of this game opened, or null before the first, whether or not a switch was on:
     * kept across a dropped socket, a refusal and a deal, never lowered and never taken from a snapshot, so a switch
     * answers a wait only the first time the client sees it, never one re-sent after a reconnect or reopened by a
     * refusal.
     */
    readonly highestOpenedWaitId: number | null;
}

/** The game client's state: a replay's, or a live seat's. */
export type GameClientState = ReplayClient | LiveClient;

/**
 * The session's IO plus a report of a protocol failure for the driver to show: a message or replay line the client
 * could not parse, a frame it could not decode, or a message it could not take (`DesyncCause`).
 */
export type ClientEffect =
    | SessionEffect
    | { readonly type: "report_protocol_failure"; readonly detail: string };

export interface ClientStep<State extends GameClientState = GameClientState> {
    readonly state: State;
    readonly effects: readonly ClientEffect[];
}

/**
 * A step plus what it took of its event, as parsed: a server message or replay line, the kan a replay's round end
 * robbed as declared, or null for any other.
 */
export interface TracedStep<
    State extends GameClientState = GameClientState,
> extends ClientStep<State> {
    readonly parsed: ReplayLine | KanDeclaredEvent | null;
}
