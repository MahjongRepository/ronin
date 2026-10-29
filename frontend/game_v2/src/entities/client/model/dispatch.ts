import {
    type SessionInput,
    type SessionState,
    failSession,
    sessionDeadline,
    startSession,
    stepSession,
} from "@/entities/session";
import {
    type TableEvent,
    applyEvent,
    chankanKanDeclared,
    createInitialTableState,
    replayLineTableEvent,
    robbedKanDeclared,
} from "@/entities/table";
import { assertNever } from "@/shared/lib";
import {
    CALL_TYPE,
    type ClientMessage,
    type ParsedServerMessage,
    type ReplayLine,
    buildConfirmRoundAction,
    parseReplayLine,
    parseServerMessage,
} from "@/shared/protocol";
import { type GameSessionData } from "@/shared/session";

import { answerDecision, expireDecision, followDecision, openDecision } from "./decision";
import {
    type ClientEvent,
    type ClientStep,
    type DecisionIntent,
    type GameClientState,
    type LocalIntent,
    type TracedStep,
} from "./types";

const ROUND_CONFIRM_DELAY_MS = 1000;

function untraced(step: ClientStep): TracedStep {
    return { ...step, parsed: null, partial: false };
}

function reportParseError(state: GameClientState, detail: string): TracedStep {
    return {
        effects: [{ detail, type: "report_parse_error" }],
        parsed: null,
        partial: false,
        state,
    };
}

function canSend(session: SessionState | null): boolean {
    return session !== null && session.status === "playing" && session.link === "open";
}

/** Whether a message shows the server moved past the round advance a pending confirm answers. */
function supersedesRoundAdvance(message: ParsedServerMessage): boolean {
    return (
        message.type !== "session_error" &&
        message.type !== "player_left" &&
        message.type !== "player_reconnected"
    );
}

/**
 * Step the session, then drop what the session can no longer send: a pending confirm, and the open decision once
 * the socket drops, since the reconnect re-sends any wait the server still owes the seat. A replay has no session.
 */
function withSession(state: GameClientState, input: SessionInput): ClientStep {
    if (state.session === null) {
        return { effects: [], state };
    }
    const step = stepSession(state.session, input);
    const sendable = canSend(step.state);
    const linked = step.state.status !== "ended" && step.state.link !== "down";
    return {
        effects: step.effects,
        state: {
            ...state,
            decision: linked ? state.decision : null,
            pendingConfirm: sendable ? state.pendingConfirm : null,
            session: step.state,
        },
    };
}

/**
 * The table change a server message carries, or null for one that only speaks to the seat or the session. A chankan
 * prompt shows the kan it offers to rob as declared.
 */
function serverTableEvent(message: ParsedServerMessage): TableEvent | null {
    switch (message.type) {
        case "game_started":
        case "round_started":
        case "draw":
        case "discard":
        case "meld":
        case "riichi_declared":
        case "dora_revealed":
        case "round_end":
        case "game_end":
        case "game_reconnected":
        case "player_left":
        case "player_reconnected": {
            return message;
        }
        case "call_prompt": {
            return message.callType === CALL_TYPE.CHANKAN ? chankanKanDeclared(message) : null;
        }
        case "turn":
        case "furiten":
        case "error":
        case "session_error": {
            return null;
        }
        default: {
            return assertNever(message);
        }
    }
}

/** The viewer's own facts a message carries: its seat, its timer settings, its furiten. */
function withViewer(state: GameClientState, message: ParsedServerMessage): GameClientState {
    switch (message.type) {
        case "game_started": {
            return {
                ...state,
                timer: message.timer ?? state.timer,
                viewerSeat: message.seat ?? state.viewerSeat,
            };
        }
        case "round_started": {
            return { ...state, furiten: false, viewerSeat: message.seat ?? state.viewerSeat };
        }
        case "game_reconnected": {
            const { isFuriten, seat, timer } = message;
            return { ...state, furiten: isFuriten, timer, viewerSeat: seat };
        }
        case "furiten": {
            return { ...state, furiten: message.isFuriten };
        }
        default: {
            return state;
        }
    }
}

function withDecision(state: GameClientState, message: ParsedServerMessage): GameClientState {
    const { now, table, timer, viewerSeat } = state;
    const hand = table.players.find((player) => player.seat === viewerSeat)?.tiles ?? [];
    const opened = openDecision(message, { at: now, hand, timer, viewerSeat });
    if (opened !== null) {
        return { ...state, decision: opened };
    }
    const decision = state.decision === null ? null : followDecision(state.decision, message);
    return { ...state, decision };
}

/** The round advance the seat owes: a round end's wait, or a reconnect into one whose confirmation is still owed. */
function owedConfirmWaitId(message: ParsedServerMessage): number | null {
    if (message.type === "round_end") {
        return message.waitId;
    }
    if (message.type === "game_reconnected" && message.confirmationOwed) {
        return message.waitId;
    }
    return null;
}

function withPendingConfirm(state: GameClientState, message: ParsedServerMessage): GameClientState {
    const moved = supersedesRoundAdvance(message) ? { ...state, pendingConfirm: null } : state;
    const waitId = owedConfirmWaitId(message);
    if (waitId === null || !canSend(moved.session)) {
        return moved;
    }
    return { ...moved, pendingConfirm: { dueAt: state.now + ROUND_CONFIRM_DELAY_MS, waitId } };
}

function onServerMessage(state: GameClientState, raw: Record<string, unknown>): TracedStep {
    const [error, message] = parseServerMessage(raw);
    if (error) {
        return reportParseError(state, error.message);
    }
    const step = withSession(state, { at: state.now, kind: "message", message });
    const tableEvent = serverTableEvent(message);
    const tabled =
        tableEvent === null
            ? step.state
            : { ...step.state, table: applyEvent(step.state.table, tableEvent) };
    const next = withPendingConfirm(withDecision(withViewer(tabled, message), message), message);
    return { effects: step.effects, parsed: message, partial: false, state: next };
}

/**
 * The first part of a replay's round end that robbed a kan the table does not show yet: the kan declared, as a part
 * of its own, since the replay records no line for the declaration. Null for any other line.
 */
function robbedKanPart(state: GameClientState, line: ReplayLine): TracedStep | null {
    const declared = line.type === "round_end" ? robbedKanDeclared(line) : null;
    if (declared === null) {
        return null;
    }
    const table = applyEvent(state.table, declared);
    if (table === state.table) {
        return null;
    }
    return { effects: [], parsed: declared, partial: true, state: { ...state, table } };
}

/**
 * A replay file's line: a replay event or seat control line moves the table; any other is reported. A round end that
 * robbed a kan is taken in two parts, the kan declared and then the result, so a replay stops on the kan.
 */
function onReplayLine(state: GameClientState, raw: Record<string, unknown>): TracedStep {
    const [error, line] = parseReplayLine(raw);
    if (error) {
        return reportParseError(state, `Parse error: ${error.message}`);
    }
    const tableEvent = replayLineTableEvent(line);
    if (tableEvent === null) {
        return reportParseError(state, `Non-replay event type: ${line.type}`);
    }
    return (
        robbedKanPart(state, line) ?? {
            effects: [],
            parsed: line,
            partial: false,
            state: { ...state, table: applyEvent(state.table, tableEvent) },
        }
    );
}

function onTick(state: GameClientState): ClientStep {
    const step = withSession(state, { at: state.now, kind: "tick" });
    const confirm = step.state.pendingConfirm;
    if (confirm === null || state.now < confirm.dueAt) {
        return step;
    }
    return {
        effects: [
            ...step.effects,
            { message: buildConfirmRoundAction(confirm.waitId), type: "send" },
        ],
        state: { ...step.state, pendingConfirm: null },
    };
}

/** The action `intent` sends now: the open decision's answer, on a socket the client can send on; or null. */
function decisionAnswer(state: GameClientState, intent: DecisionIntent): ClientMessage | null {
    const { decision, table, viewerSeat } = state;
    if (decision === null || !canSend(state.session)) {
        return null;
    }
    const viewer = table.players.find((player) => player.seat === viewerSeat);
    return answerDecision(decision, intent, viewer);
}

/**
 * Whether stepping `intent` now would answer the open decision: the one test of what the client may play, so the
 * board offers exactly the intents the dispatcher takes.
 */
export function takesIntent(state: GameClientState, intent: DecisionIntent): boolean {
    return decisionAnswer(state, intent) !== null;
}

/** Answer the open decision: send the action it takes and mark it submitted, or change nothing. */
function onDecisionIntent(state: GameClientState, intent: DecisionIntent): ClientStep {
    const { decision } = state;
    const message = decisionAnswer(state, intent);
    if (decision === null || message === null) {
        return { effects: [], state };
    }
    const status = { at: state.now, kind: "submitted", message } as const;
    return {
        effects: [{ message, type: "send" }],
        state: { ...state, decision: { ...decision, status } },
    };
}

function onIntent(state: GameClientState, intent: LocalIntent): ClientStep {
    switch (intent.type) {
        case "leave": {
            return withSession(state, { at: state.now, kind: "leave" });
        }
        case "discard":
        case "choose":
        case "pass": {
            return onDecisionIntent(state, intent);
        }
        default: {
            return assertNever(intent);
        }
    }
}

function stepEvent(timed: GameClientState, event: ClientEvent): TracedStep {
    switch (event.kind) {
        case "server_message": {
            return onServerMessage(timed, event.raw);
        }
        case "replay_line": {
            return onReplayLine(timed, event.raw);
        }
        case "transport_opened": {
            return untraced(withSession(timed, { at: event.at, kind: "transport_opened" }));
        }
        case "transport_closed": {
            const { at, code, reason } = event;
            return untraced(withSession(timed, { at, code, kind: "transport_closed", reason }));
        }
        case "transport_error": {
            return { effects: [], parsed: null, partial: false, state: timed };
        }
        case "tick": {
            return untraced(onTick(timed));
        }
        case "intent": {
            return untraced(onIntent(timed, event.intent));
        }
        default: {
            return assertNever(event);
        }
    }
}

function emptyClient(at: number, session: SessionState | null): GameClientState {
    return {
        decision: null,
        furiten: false,
        now: at,
        pendingConfirm: null,
        session,
        table: createInitialTableState(),
        timer: null,
        viewerSeat: null,
    };
}

/** Begin the game client at logical time `at` from the lobby's handoff, or null when the tab holds none. */
export function startGameClient(
    gameId: string,
    handoff: GameSessionData | null,
    at: number,
): ClientStep {
    const step = startSession(gameId, handoff);
    return { effects: step.effects, state: emptyClient(at, step.state) };
}

/** Begin a replay's client at logical time `at`: no session, no viewer, nothing it could send. */
export function startReplayClient(at: number): GameClientState {
    return emptyClient(at, null);
}

/**
 * When the client next needs a tick: the earliest of its pending retry, its pending confirm and its open
 * decision's deadline, or null.
 */
export function nextDeadline(state: GameClientState): number | null {
    const { decision, pendingConfirm, session } = state;
    const decisionDue = decision?.status.kind === "open" ? decision.deadline : null;
    const deadlines = [
        session === null ? null : sessionDeadline(session),
        pendingConfirm?.dueAt ?? null,
        decisionDue,
    ].filter((deadline) => deadline !== null);
    return deadlines.length === 0 ? null : Math.min(...deadlines);
}

/** End the client because its driver failed while stepping it; nothing is pending afterwards. */
export function failGameClient(state: GameClientState, detail: string): GameClientState {
    const session = state.session === null ? null : failSession(state.session, detail);
    return { ...state, decision: null, pendingConfirm: null, session };
}

/** One part of the dispatcher's step with what it took of its event, as parsed. */
function traceGameClientPart(state: GameClientState, event: ClientEvent): TracedStep {
    const step = stepEvent({ ...state, now: event.at }, event);
    const { decision } = step.state;
    const current = decision === null ? null : expireDecision(decision, event.at);
    return current === decision ? step : { ...step, state: { ...step.state, decision: current } };
}

/**
 * The dispatcher's step as the parts it took, each with what it took of the event, as parsed, for a timeline to
 * index by: one part, but two for a replay's round end that robbed a kan (the kan declared, then the result). The
 * second part finds the kan shown, so the parts always end.
 */
export function traceGameClient(state: GameClientState, event: ClientEvent): readonly TracedStep[] {
    const step = traceGameClientPart(state, event);
    return step.partial ? [step, ...traceGameClient(step.state, event)] : [step];
}

/**
 * The game client's dispatcher: a pure `(state, event) → { state, effects }` over client events, composing the
 * session transition, the table transition and the viewer's decision. Nothing in it runs IO, reads a clock or
 * starts a timer; the effects are descriptions only a live driver executes, and the time is the event's `at`.
 */
export function stepGameClient(state: GameClientState, event: ClientEvent): ClientStep {
    const parts = traceGameClient(state, event);
    return {
        effects: parts.flatMap((part) => part.effects),
        state: parts.at(-1)?.state ?? state,
    };
}
