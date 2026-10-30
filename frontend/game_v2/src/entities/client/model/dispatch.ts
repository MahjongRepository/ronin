import {
    type SessionInput,
    type SessionState,
    hasSocket,
    sessionDeadline,
    startSession,
    stepSession,
} from "@/entities/session";
import {
    CALLOUT_MS,
    type Call,
    DesyncError,
    type TableEvent,
    type TableState,
    applyEvent,
    callsShownKan,
    chankanKanDeclared,
    createInitialTableState,
    eventCalls,
    replayLineTableEvent,
    robbedKanDeclared,
} from "@/entities/table";
import { assertNever } from "@/shared/lib";
import {
    CALL_TYPE,
    type ClientMessage,
    type ParsedServerMessage,
    type ReplayLine,
    parseReplayLine,
    parseServerMessage,
} from "@/shared/protocol";
import { type GameSessionData } from "@/shared/session";

import {
    type DecisionContext,
    answerDecision,
    expireDecision,
    followDecision,
    isAnsweredWait,
    openDecision,
} from "./decision";
import {
    canSend,
    deferredUntilDeal,
    desyncDeadline,
    desyncStep,
    isSnapshotPayload,
    recoveryFailedStep,
    resynced,
    settleDesync,
    takesServerMessages,
    takesWhileDesynced,
} from "./desync";
import { keptNotice, submittedWaitId, withNotice } from "./notices";
import { SWITCHES_OFF, snapshotLeftHand, switchAnswer, unseenWait } from "./play-switches";
import { confirmStep, reopenResultStep, withRoundConfirm } from "./round-confirm";
import {
    type ClientEvent,
    type ClientStep,
    type DecisionIntent,
    type GameClientState,
    type LocalIntent,
    type PlayIntent,
    type PlaySwitch,
    type ShownCalls,
    type TracedStep,
} from "./types";

const MS_PER_SECOND = 1000;

function untraced(step: ClientStep): TracedStep {
    return { ...step, parsed: null, partial: false };
}

function reportProtocolFailure(state: GameClientState, detail: string): TracedStep {
    return {
        effects: [{ detail, type: "report_protocol_failure" }],
        parsed: null,
        partial: false,
        state,
    };
}

/** Whether the client may answer: it can send, and it is in step with the server, since out of step it answers nothing. */
function canAnswer(state: GameClientState): boolean {
    return canSend(state.session) && state.desync === null;
}

/** Whether the session ended other than by the game's end: it failed, or the player left. */
function endedEarly(session: SessionState): boolean {
    return session.status === "ended" && session.reason.kind !== "game_ended";
}

/**
 * Step the session, then drop what the session can no longer send: a round confirm (but the game's last result, which
 * sends nothing), and the open decision once the socket drops, since the reconnect re-sends any wait the server still
 * owes the seat and its snapshot says whether the round confirm is still owed; the notices it outdates; and the calls
 * shown once it failed or the player left, so nothing is left pending. The game's end keeps them, so its last win
 * shows its call, and only their time ends them. A replay has no session.
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
            calls: endedEarly(step.state) ? null : state.calls,
            decision: hasSocket(step.state) ? state.decision : null,
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
        case "draw_notice":
        case "discard":
        case "meld":
        case "riichi_declared":
        case "dora_revealed":
        case "round_end":
        case "game_end":
        case "game_reconnected":
        case "ai_replacement":
        case "human_return": {
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
            const { timer } = message;
            return {
                ...state,
                firstDealDue:
                    timer === null ? null : state.now + timer.gameStartPauseSeconds * MS_PER_SECOND,
                timer: timer ?? state.timer,
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

/**
 * The play switches after a message, from the table it found (`before`): a deal turns them off, as does a reconnect's
 * snapshot of another hand or of a round result pending. Any other message leaves them, a snapshot of the same hand
 * included. A table of another game forgets the highest wait id opened, which belongs to its game.
 */
function withSwitches(
    state: GameClientState,
    before: TableState,
    message: ParsedServerMessage,
): GameClientState {
    const leaves =
        message.type === "round_started" ||
        (message.type === "game_reconnected" && snapshotLeftHand(before, state.table));
    const switched = leaves ? { ...state, switches: SWITCHES_OFF } : state;
    return state.table.gameId === before.gameId
        ? switched
        : { ...switched, highestOpenedWaitId: null };
}

function decisionContext(state: GameClientState): DecisionContext {
    const { now, table, timer, viewerSeat } = state;
    const viewer = table.players.find((player) => player.seat === viewerSeat);
    return { at: now, hand: viewer?.tiles ?? [], melds: viewer?.melds ?? [], timer, viewerSeat };
}

function withDecision(state: GameClientState, message: ParsedServerMessage): GameClientState {
    const { highestOpenedWaitId } = state;
    if (state.decision !== null && isAnsweredWait(state.decision, message)) {
        return state;
    }
    const opened = openDecision(message, decisionContext(state));
    if (opened !== null) {
        const highest = Math.max(opened.waitId, highestOpenedWaitId ?? opened.waitId);
        return { ...state, decision: opened, highestOpenedWaitId: highest };
    }
    const decision = state.decision === null ? null : followDecision(state.decision, message);
    return { ...state, decision };
}

function shownCalls(calls: readonly Call[], at: number): ShownCalls {
    return { at, calls, until: at + CALLOUT_MS };
}

/**
 * The calls a live board shows after a server message's table event, from the table it found (`state`'s) to the one it
 * left: the calls the event makes, but a kan the calls still showing call already (the declaration a reconnect's re-sent prompt repeats); else
 * those still showing, which only their time ends, since a move that calls nothing may follow a call at once (an AI
 * player's discard after its pon, the viewer's own draw after a riichi). A deal, or a snapshot that leaves the hand,
 * starts a new board, which shows none of the hand before, however soon it follows that hand's last call.
 */
function liveCalls(
    state: GameClientState,
    event: TableEvent,
    table: TableState,
): ShownCalls | null {
    const newBoard =
        event.type === "round_started" ||
        (event.type === "game_reconnected" && snapshotLeftHand(state.table, table));
    if (newBoard) {
        return null;
    }
    const shown = state.calls;
    const live = shown !== null && shown.until > state.now ? shown.calls : [];
    const calls = (eventCalls(event, state.table, table) ?? []).filter(
        (call) => !callsShownKan(live, call),
    );
    return calls.length === 0 ? shown : shownCalls(calls, state.now);
}

/**
 * The calls a replay's board shows after a line's table event: the calls a move makes, none for a move that makes
 * none, and those of the move before for its bookkeeping and annotations, so each stop shows its own move's calls.
 */
function replayCalls(
    state: GameClientState,
    event: TableEvent,
    table: TableState,
): ShownCalls | null {
    const calls = eventCalls(event, state.table, table);
    if (calls === null) {
        return state.calls;
    }
    return calls.length === 0 ? null : shownCalls(calls, state.now);
}

/**
 * The client after a server message the session took (`stepped`, from `before`): the table event it carries and its
 * calls, the viewer's facts, the play switches, the decision it opens or follows, the round confirm and the notices,
 * then the switches' answer to a decision it opened on an unseen wait.
 */
function takeMessage(
    before: GameClientState,
    stepped: GameClientState,
    message: ParsedServerMessage,
): ClientStep {
    const tableEvent = serverTableEvent(message);
    const table = tableEvent === null ? stepped.table : applyEvent(stepped.table, tableEvent);
    const tabled =
        tableEvent === null
            ? stepped
            : { ...stepped, calls: liveCalls(stepped, tableEvent, table), table };
    const viewed = withSwitches(withViewer(tabled, message), before.table, message);
    const decided = withDecision(viewed, message);
    const noticeBefore = { session: before.session, submitted: submittedWaitId(viewed) };
    const noticed = withNotice(noticeBefore, withRoundConfirm(decided, message), message);
    return switchStep(noticed, viewed.highestOpenedWaitId);
}

/** Whether a message the client cannot take ends the page: a snapshot, or a game's end out of step already. */
function failsRecovery(stepped: GameClientState, message: ParsedServerMessage): boolean {
    return (
        message.type === "game_reconnected" ||
        (message.type === "game_end" && stepped.desync !== null)
    );
}

/**
 * A game's end its in-step table refused, the first sign the client missed the round end before it, taken once more
 * by the client that loss put out of step (`lost`), since its standings are the server's whatever the table missed.
 */
function gameEndOutOfStep(
    before: GameClientState,
    lost: ClientStep,
    message: ParsedServerMessage,
): ClientStep {
    const ended = takeMessageInStep(before, lost.state, message);
    return { effects: [...lost.effects, ...ended.effects], state: ended.state };
}

/**
 * Take a server message the session took, as `takeMessage` does, where a `DesyncError` (a message the table or the
 * decision cannot take) is a protocol failure rather than a bug: it puts the client out of step, and it ends the page
 * for a snapshot or a game's end out of step already, since no snapshot can rebuild the client then; a game's end in
 * step is taken once more out of step (`gameEndOutOfStep`), and out of step, the game's last round end it cannot take
 * is one more message dropped. A snapshot it takes puts it back in step. Any other error is the client's own and
 * propagates.
 */
function takeMessageInStep(
    before: GameClientState,
    stepped: GameClientState,
    message: ParsedServerMessage,
): ClientStep {
    try {
        const taken = takeMessage(before, stepped, message);
        return message.type === "game_reconnected"
            ? { ...taken, state: resynced(taken.state) }
            : taken;
    } catch (error: unknown) {
        if (!(error instanceof DesyncError)) {
            throw error;
        }
        if (failsRecovery(stepped, message)) {
            return recoveryFailedStep(stepped, "impossible_state", error.message);
        }
        const lost = desyncStep(stepped, "impossible_state", error.message);
        return message.type === "game_end" ? gameEndOutOfStep(before, lost, message) : lost;
    }
}

/**
 * A parsed server message: the session takes every one; out of step, only the snapshot and the game's end with its
 * last round end reach the table, any other dropped.
 */
function takeParsedMessage(state: GameClientState, message: ParsedServerMessage): ClientStep {
    const step = withSession(state, { at: state.now, kind: "message", message });
    if (state.desync !== null && !takesWhileDesynced(message)) {
        return { effects: step.effects, state: deferredUntilDeal(step.state, message) };
    }
    const taken = takeMessageInStep(state, step.state, message);
    return { effects: [...step.effects, ...taken.effects], state: taken.state };
}

/**
 * A server message, on a session that takes them: one that does not parse puts the client out of step (a snapshot
 * that does not parse ends the page).
 */
function onServerMessage(state: GameClientState, raw: Record<string, unknown>): TracedStep {
    if (!takesServerMessages(state.session)) {
        return untraced({ effects: [], state });
    }
    const [error, message] = parseServerMessage(raw);
    if (error) {
        return untraced(
            isSnapshotPayload(raw)
                ? recoveryFailedStep(state, "unreadable_message", error.message)
                : desyncStep(state, "unreadable_message", error.message),
        );
    }
    return { ...takeParsedMessage(state, message), parsed: message, partial: false };
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
    const calls = replayCalls(state, declared, table);
    return { effects: [], parsed: declared, partial: true, state: { ...state, calls, table } };
}

/** A replay line's whole step: its table event applied, and the calls the move makes. */
function replayLineStep(state: GameClientState, line: ReplayLine, event: TableEvent): TracedStep {
    const table = applyEvent(state.table, event);
    const calls = replayCalls(state, event, table);
    return { effects: [], parsed: line, partial: false, state: { ...state, calls, table } };
}

/**
 * A replay file's line: a replay event or seat control line moves the table; any other is reported. A round end that
 * robbed a kan is taken in two parts, the kan declared and then the result, so a replay stops on the kan.
 */
function onReplayLine(state: GameClientState, raw: Record<string, unknown>): TracedStep {
    const [error, line] = parseReplayLine(raw);
    if (error) {
        return reportProtocolFailure(state, `Parse error: ${error.message}`);
    }
    const tableEvent = replayLineTableEvent(line);
    if (tableEvent === null) {
        return reportProtocolFailure(state, `Non-replay event type: ${line.type}`);
    }
    return robbedKanPart(state, line) ?? replayLineStep(state, line, tableEvent);
}

function onTick(state: GameClientState): ClientStep {
    return withSession(state, { at: state.now, kind: "tick" });
}

/** The action `intent` sends now: the open decision's answer, on a socket the client can send on; or null. */
function decisionAnswer(state: GameClientState, intent: DecisionIntent): ClientMessage | null {
    const { decision, table, viewerSeat } = state;
    if (decision === null || !canAnswer(state)) {
        return null;
    }
    const viewer = table.players.find((player) => player.seat === viewerSeat);
    return answerDecision(decision, intent, viewer);
}

/**
 * Whether stepping `intent` now would answer the open decision, confirm the round result, reopen the game's last
 * one or turn a play switch: the one test of what the client may play, so the board offers exactly the intents the dispatcher takes.
 */
export function takesIntent(state: GameClientState, intent: PlayIntent): boolean {
    if (intent.type === "confirm_result") {
        return confirmStep(state, canAnswer(state)) !== null;
    }
    if (intent.type === "show_last_result") {
        return reopenResultStep(state) !== null;
    }
    if (intent.type === "toggle_switch") {
        return takesSwitch(state);
    }
    return decisionAnswer(state, intent) !== null;
}

/**
 * Answer the open decision, by the player's press or by the play switch `bySwitch`: send the action it takes and mark
 * it submitted, or change nothing.
 */
function onDecisionIntent(
    state: GameClientState,
    intent: DecisionIntent,
    bySwitch: PlaySwitch | null,
): ClientStep {
    const { decision } = state;
    const message = decisionAnswer(state, intent);
    if (decision === null || message === null) {
        return { effects: [], state };
    }
    const status = { at: state.now, bySwitch, intent, kind: "submitted" } as const;
    return {
        effects: [{ message, type: "send" }],
        state: { ...state, decision: { ...decision, status } },
    };
}

/**
 * The play switches' standing answer to a decision a message opened on a wait above the highest the game opened before
 * it (`highestBefore`), taken exactly where the player's press would be; nothing for a decision already open, re-sent after
 * a reconnect or reopened by a refusal, which stay the player's.
 */
function switchStep(state: GameClientState, highestBefore: number | null): ClientStep {
    const { decision, switches } = state;
    if (decision?.status.kind !== "open" || !unseenWait(decision.waitId, highestBefore)) {
        return { effects: [], state };
    }
    const answer = switchAnswer(decision, switches);
    return answer === null
        ? { effects: [], state }
        : onDecisionIntent(state, answer.intent, answer.bySwitch);
}

/** Whether the player may turn a play switch on or off now: on a live seat while a round plays. */
function takesSwitch(state: GameClientState): boolean {
    const { session, table, viewerSeat } = state;
    return (
        session !== null &&
        session.status !== "ended" &&
        viewerSeat !== null &&
        table.phase === "in_round"
    );
}

/** Turn a play switch on or off, sending nothing: it answers the waits the client sees from then on. */
function toggleSwitchStep(state: GameClientState, playSwitch: PlaySwitch): ClientStep | null {
    if (!takesSwitch(state)) {
        return null;
    }
    const switches = { ...state.switches, [playSwitch]: !state.switches[playSwitch] };
    return { effects: [], state: { ...state, switches } };
}

function onIntent(state: GameClientState, intent: LocalIntent): ClientStep {
    switch (intent.type) {
        case "leave": {
            return withSession(state, { at: state.now, kind: "leave" });
        }
        case "discard":
        case "choose":
        case "pass": {
            return onDecisionIntent(state, intent, null);
        }
        case "toggle_switch": {
            return toggleSwitchStep(state, intent.playSwitch) ?? { effects: [], state };
        }
        case "confirm_result": {
            return confirmStep(state, canAnswer(state)) ?? { effects: [], state };
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
            return untraced({ effects: [], state: timed });
        }
        case "frame_undecodable": {
            return untraced(
                takesServerMessages(timed.session)
                    ? desyncStep(timed, "undecodable_frame", event.detail)
                    : { effects: [], state: timed },
            );
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
        calls: null,
        decision: null,
        desync: null,
        firstDealDue: null,
        furiten: false,
        highestOpenedWaitId: null,
        notice: null,
        now: at,
        resyncRequests: 0,
        roundConfirm: null,
        session,
        switches: SWITCHES_OFF,
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
 * When the client next needs a tick: the earliest of its session's deadline, its open decision's, its notice's and its
 * calls' expiry, and when its resync request counts as unanswered, or null. A round confirm's deadline needs none: the
 * client never confirms on its own, and its countdown reads `now`.
 */
export function nextDeadline(state: GameClientState): number | null {
    const { calls, decision, notice, session } = state;
    const decisionDue = decision?.status.kind === "open" ? decision.deadline : null;
    const deadlines = [
        session === null ? null : sessionDeadline(session),
        desyncDeadline(state),
        decisionDue,
        notice?.until ?? null,
        calls?.until ?? null,
    ].filter((deadline) => deadline !== null);
    return deadlines.length === 0 ? null : Math.min(...deadlines);
}

/** The state at logical time `at`: an open decision past its deadline expired, a notice or calls past their time gone. */
function expireAt(state: GameClientState, at: number): GameClientState {
    const { calls, decision, notice } = state;
    const current = decision === null ? null : expireDecision(decision, at);
    const shown = notice !== null && at >= notice.until ? null : notice;
    const called = calls !== null && at >= calls.until ? null : calls;
    return current === decision && shown === notice && called === calls
        ? state
        : { ...state, calls: called, decision: current, notice: shown };
}

/** One part of the dispatcher's step with what it took of its event, as parsed. */
function traceGameClientPart(state: GameClientState, event: ClientEvent): TracedStep {
    const step = stepEvent({ ...state, now: event.at }, event);
    const settled = settleDesync(step);
    const expired = expireAt(settled.state, event.at);
    return { ...step, effects: settled.effects, state: expired };
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
