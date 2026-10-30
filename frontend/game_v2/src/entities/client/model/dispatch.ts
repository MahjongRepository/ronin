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
    roundEndPages,
} from "@/entities/table";
import { assertNever } from "@/shared/lib";
import {
    CALL_TYPE,
    type ClientMessage,
    type ParsedServerMessage,
    type ReplayLine,
    SESSION_ERROR_CODE,
    buildConfirmRoundAction,
    parseReplayLine,
    parseServerMessage,
} from "@/shared/protocol";
import { type GameSessionData } from "@/shared/session";

import {
    answerDecision,
    expireDecision,
    followDecision,
    openDecision,
    refusesSubmission,
} from "./decision";
import {
    type ClientEvent,
    type ClientStep,
    type DecisionIntent,
    type GameClientState,
    type LocalIntent,
    type PlayIntent,
    type RoundConfirm,
    type TimedNotice,
    type TracedStep,
} from "./types";

const MS_PER_SECOND = 1000;
const CONFIRMED: RoundConfirm = { kind: "confirmed" };
const FINAL: RoundConfirm = { kind: "final" };
const RECONNECTED_NOTICE_MS = 3000;
const REFUSED_NOTICE_MS = 4000;

function untraced(step: ClientStep): TracedStep {
    return { ...step, parsed: null, partial: false };
}

function reportUnreadMessage(state: GameClientState, detail: string): TracedStep {
    return reportParseError({ ...state, unreadMessages: state.unreadMessages + 1 }, detail);
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

function isLinked(session: SessionState): boolean {
    return session.status !== "ended" && session.status !== "recovering" && session.link !== "down";
}

/**
 * The timed notice a session keeps: none once it ended, and the seat's return only while the seat is held, so a
 * second drop replaces it with its own notice.
 */
function keptNotice(notice: TimedNotice | null, session: SessionState): TimedNotice | null {
    if (session.status === "ended") {
        return null;
    }
    return notice?.kind === "reconnected" && session.status !== "playing" ? null : notice;
}

/**
 * Step the session, then drop what the session can no longer send: a round confirm (but the game's last result, which
 * sends nothing), and the open decision once the socket drops, since the reconnect re-sends any wait the server still
 * owes the seat and its snapshot says whether the round confirm is still owed; and the notices it outdates. A replay
 * has no session.
 */
function withSession(state: GameClientState, input: SessionInput): ClientStep {
    if (state.session === null) {
        return { effects: [], state };
    }
    const step = stepSession(state.session, input);
    const sendable = canSend(step.state);
    return {
        effects: step.effects,
        state: {
            ...state,
            decision: isLinked(step.state) ? state.decision : null,
            notice: keptNotice(state.notice, step.state),
            roundConfirm:
                sendable || state.roundConfirm?.kind === "final" ? state.roundConfirm : null,
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

/**
 * When the server's round advance timer for the table's result likely runs out, in logical time: one deadline per
 * round, the round advance timeout times the result's pages (the server's `results_shown`, a double ron's winners),
 * armed at the round end, less the time the timer has run already.
 */
function roundAdvanceDeadline(state: GameClientState, elapsedSeconds: number): number | null {
    const { now, table, timer } = state;
    if (timer === null || table.roundEndResult === null) {
        return null;
    }
    const seconds = timer.roundAdvanceTimeoutSeconds * roundEndPages(table.roundEndResult).length;
    return now + Math.max(0, seconds - elapsedSeconds) * MS_PER_SECOND;
}

/**
 * The round confirm a reconnect's snapshot names: none outside a round advance; owed, with a deadline only when the
 * snapshot says how long its timer has run, never a fresh full timeout; or confirmed already.
 */
function reconnectRoundConfirm(
    state: GameClientState,
    snapshot: Extract<ParsedServerMessage, { type: "game_reconnected" }>,
): RoundConfirm | null {
    const { confirmationOwed, elapsedSeconds, waitId } = snapshot;
    if (state.table.roundEndResult === null) {
        return null;
    }
    if (!confirmationOwed) {
        return CONFIRMED;
    }
    const deadline = elapsedSeconds === null ? null : roundAdvanceDeadline(state, elapsedSeconds);
    return { deadline, kind: "owed", waitId };
}

/**
 * The round confirm a message opens, from the table it left: a round end's wait, a reconnect's snapshot of a round
 * advance, or the game's last result when the game end follows a round end. Null for a round end with no wait;
 * undefined for any other message.
 */
function openedRoundConfirm(
    state: GameClientState,
    message: ParsedServerMessage,
): RoundConfirm | null | undefined {
    switch (message.type) {
        case "round_end": {
            const { waitId } = message;
            const deadline = roundAdvanceDeadline(state, 0);
            return waitId === null ? null : { deadline, kind: "owed", waitId };
        }
        case "game_reconnected": {
            return reconnectRoundConfirm(state, message);
        }
        case "game_end": {
            return state.table.roundEndResult === null ? null : FINAL;
        }
        default: {
            return undefined;
        }
    }
}

/**
 * The round confirm after a message that opens none: closed by the next deal alone, and a sent one reopened as owed
 * by the socket's rate limit alone. A game error never answers it: a late reply to an earlier move names no wait,
 * and the confirm's own stale reply follows the deal that closed it already.
 */
function followRoundConfirm(
    confirm: RoundConfirm,
    message: ParsedServerMessage,
): RoundConfirm | null {
    if (message.type === "round_started" && confirm.kind !== "final") {
        return null;
    }
    const rateLimited =
        message.type === "session_error" && message.code === SESSION_ERROR_CODE.RATE_LIMITED;
    if (confirm.kind === "sent" && rateLimited) {
        return { deadline: confirm.deadline, kind: "owed", waitId: confirm.waitId };
    }
    return confirm;
}

function withRoundConfirm(state: GameClientState, message: ParsedServerMessage): GameClientState {
    const opened = openedRoundConfirm(state, message);
    const { roundConfirm } = state;
    if (opened !== undefined) {
        return { ...state, roundConfirm: opened };
    }
    if (roundConfirm === null) {
        return state;
    }
    return { ...state, roundConfirm: followRoundConfirm(roundConfirm, message) };
}

/**
 * The notice a message raises, from the session it found (`before`) and the one it left (`state`'s): the seat is back
 * after a reconnect's snapshot, when this page lost it to a drop; a move refused while the seat plays, as the
 * decision reads a refusal. Null for any other message.
 */
function messageNotice(
    before: SessionState | null,
    state: GameClientState,
    message: ParsedServerMessage,
): TimedNotice | null {
    const { now, session } = state;
    if (message.type === "game_reconnected") {
        const lostSeat = before?.status === "reconnecting" && before.lostSeat;
        return lostSeat ? { kind: "reconnected", until: now + RECONNECTED_NOTICE_MS } : null;
    }
    if (session?.status !== "playing" || !refusesSubmission(message)) {
        return null;
    }
    return { code: message.code, kind: "refused", until: now + REFUSED_NOTICE_MS };
}

/**
 * The notices a message leaves: the one it raises, if any; and a snapshot rebuilds the table, so the messages read
 * wrong before it no longer count.
 */
function withNotice(
    before: SessionState | null,
    state: GameClientState,
    message: ParsedServerMessage,
): GameClientState {
    const notice = messageNotice(before, state, message);
    const unreadMessages = message.type === "game_reconnected" ? 0 : state.unreadMessages;
    return { ...state, notice: notice ?? state.notice, unreadMessages };
}

function onServerMessage(state: GameClientState, raw: Record<string, unknown>): TracedStep {
    const [error, message] = parseServerMessage(raw);
    if (error) {
        return reportUnreadMessage(state, error.message);
    }
    const step = withSession(state, { at: state.now, kind: "message", message });
    const tableEvent = serverTableEvent(message);
    const tabled =
        tableEvent === null
            ? step.state
            : { ...step.state, table: applyEvent(step.state.table, tableEvent) };
    const decided = withDecision(withViewer(tabled, message), message);
    const next = withNotice(state.session, withRoundConfirm(decided, message), message);
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
    return withSession(state, { at: state.now, kind: "tick" });
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
 * Confirm the round result: send the owed confirm by its wait id once, on a socket the client can send on, and wait
 * for the others; or dismiss the game's last result for the standings, sending nothing. Null when there is nothing
 * to confirm.
 */
function confirmStep(state: GameClientState): ClientStep | null {
    const { roundConfirm } = state;
    if (roundConfirm?.kind === "final") {
        return { effects: [], state: { ...state, roundConfirm: null } };
    }
    if (roundConfirm?.kind !== "owed" || !canSend(state.session)) {
        return null;
    }
    const { deadline, waitId } = roundConfirm;
    return {
        effects: [{ message: buildConfirmRoundAction(waitId), type: "send" }],
        state: { ...state, roundConfirm: { deadline, kind: "sent", waitId } },
    };
}

/**
 * Reopen the game's last result over the standings it was dismissed for, sending nothing. Null unless the game ended on
 * a result the standings show.
 */
function reopenResultStep(state: GameClientState): ClientStep | null {
    const { roundConfirm, table } = state;
    if (table.phase !== "game_ended" || table.roundEndResult === null || roundConfirm !== null) {
        return null;
    }
    return { effects: [], state: { ...state, roundConfirm: FINAL } };
}

/**
 * Whether stepping `intent` now would answer the open decision, confirm the round result or reopen the game's last
 * one: the one test of what the client may play, so the board offers exactly the intents the dispatcher takes.
 */
export function takesIntent(state: GameClientState, intent: PlayIntent): boolean {
    if (intent.type === "confirm_result") {
        return confirmStep(state) !== null;
    }
    if (intent.type === "show_last_result") {
        return reopenResultStep(state) !== null;
    }
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
        case "confirm_result": {
            return confirmStep(state) ?? { effects: [], state };
        }
        case "show_last_result": {
            return reopenResultStep(state) ?? { effects: [], state };
        }
        default: {
            return assertNever(intent);
        }
    }
}

/** The session's own input a transport event or the lobby's answer for the handoff is. */
function sessionInput(
    event: Extract<
        ClientEvent,
        { kind: "transport_opened" | "transport_closed" | "handoff_recovered" }
    >,
): SessionInput {
    switch (event.kind) {
        case "transport_opened": {
            return { at: event.at, kind: "transport_opened" };
        }
        case "transport_closed": {
            const { at, code, reason } = event;
            return { at, code, kind: "transport_closed", reason };
        }
        case "handoff_recovered": {
            return { at: event.at, kind: "handoff_recovered", recovery: event.recovery };
        }
        default: {
            return assertNever(event);
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
        case "transport_opened":
        case "transport_closed":
        case "handoff_recovered": {
            return untraced(withSession(timed, sessionInput(event)));
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
        notice: null,
        now: at,
        roundConfirm: null,
        session,
        table: createInitialTableState(),
        timer: null,
        unreadMessages: 0,
        viewerSeat: null,
    };
}

/**
 * Begin the game client at logical time `at` from the lobby's handoff, or, when the tab holds none, by asking the
 * lobby for it.
 */
export function startGameClient(
    gameId: string,
    handoff: GameSessionData | null,
    at: number,
): ClientStep {
    const step = startSession(gameId, handoff, at);
    return { effects: step.effects, state: emptyClient(at, step.state) };
}

/** Begin a replay's client at logical time `at`: no session, no viewer, nothing it could send. */
export function startReplayClient(at: number): GameClientState {
    return emptyClient(at, null);
}

/**
 * When the client next needs a tick: the earliest of its session's deadline, its open decision's and its notice's
 * expiry, or null. A round confirm's deadline needs none: the client never confirms on its own, and its countdown
 * reads `now`.
 */
export function nextDeadline(state: GameClientState): number | null {
    const { decision, notice, session } = state;
    const decisionDue = decision?.status.kind === "open" ? decision.deadline : null;
    const deadlines = [
        session === null ? null : sessionDeadline(session),
        decisionDue,
        notice?.until ?? null,
    ].filter((deadline) => deadline !== null);
    return deadlines.length === 0 ? null : Math.min(...deadlines);
}

/** End the client because its driver failed while stepping it; nothing is pending afterwards. */
export function failGameClient(state: GameClientState, detail: string): GameClientState {
    const session = state.session === null ? null : failSession(state.session, detail);
    return { ...state, decision: null, notice: null, roundConfirm: null, session };
}

/** The state at logical time `at`: an open decision past its deadline expired, a notice past its time gone. */
function expireAt(state: GameClientState, at: number): GameClientState {
    const { decision, notice } = state;
    const current = decision === null ? null : expireDecision(decision, at);
    const shown = notice !== null && at >= notice.until ? null : notice;
    return current === decision && shown === notice
        ? state
        : { ...state, decision: current, notice: shown };
}

/** One part of the dispatcher's step with what it took of its event, as parsed. */
function traceGameClientPart(state: GameClientState, event: ClientEvent): TracedStep {
    const step = stepEvent({ ...state, now: event.at }, event);
    const expired = expireAt(step.state, event.at);
    return expired === step.state ? step : { ...step, state: expired };
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
