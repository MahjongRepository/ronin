import {
    type SessionInput,
    type SessionState,
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
    refusesResyncRequest,
    resynced,
    settleDesync,
    takesServerMessages,
    takesWhileDesynced,
} from "./desync";
import { keptNotice, submittedWaitId, withNotice } from "./notices";
import {
    decisionOf,
    pendingOf,
    replaceDecision,
    replaceRoundConfirm,
    settledPending,
    withPending,
} from "./pending";
import { SWITCHES_OFF, snapshotLeftHand, switchAnswer, unseenWait } from "./play-switches";
import {
    confirmStep,
    followRoundConfirm,
    openedRoundConfirm,
    reopenResultStep,
    showsLastResultAfter,
} from "./round-confirm";
import {
    type ClientEvent,
    type ClientStep,
    type Decision,
    type DecisionIntent,
    type LiveClient,
    type LiveEvent,
    type LocalIntent,
    type Pending,
    type PlayIntent,
    type PlaySwitch,
    type ReplayClient,
    type ReplayLineEvent,
    type ShownCalls,
    type TracedStep,
} from "./types";

const MS_PER_SECOND = 1000;

function untraced(step: ClientStep<LiveClient>): TracedStep<LiveClient> {
    return { ...step, parsed: null, partial: false };
}

function reportProtocolFailure(state: ReplayClient, detail: string): TracedStep<ReplayClient> {
    return {
        effects: [{ detail, type: "report_protocol_failure" }],
        parsed: null,
        partial: false,
        state,
    };
}

/**
 * Whether the client may answer what its seat owes: its session holds the seat. Out of step the seat owes nothing,
 * so it answers nothing.
 */
function canAnswer(state: LiveClient): boolean {
    return canSend(state.session);
}

/** Whether the session ended other than by the game's end: it failed, or the player left. */
function endedEarly(session: SessionState): boolean {
    return session.status === "ended" && session.reason.kind !== "game_ended";
}

/**
 * Step the session, then drop what it outdates: the notices, and the calls shown once it failed or the player left,
 * so nothing is left pending. The game's end keeps the calls, so its last win shows its call, and only their time ends
 * them. What the seat owes goes at the step's end once the session holds no seat (`settledPending`).
 */
function withSession(state: LiveClient, input: SessionInput): ClientStep<LiveClient> {
    const step = stepSession(state.session, input);
    return {
        effects: step.effects,
        state: {
            ...state,
            calls: endedEarly(step.state) ? null : state.calls,
            notice: keptNotice(state.notice, step.state),
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
        case "session_error":
        case "game_joined": {
            return null;
        }
        default: {
            return assertNever(message);
        }
    }
}

/** The viewer's own facts a message carries: its seat, its timer settings, its furiten. */
function withViewer(state: LiveClient, message: ParsedServerMessage): LiveClient {
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
    state: LiveClient,
    before: TableState,
    message: ParsedServerMessage,
): LiveClient {
    const leaves =
        message.type === "round_started" ||
        (message.type === "game_reconnected" && snapshotLeftHand(before, state.table));
    const switched = leaves ? { ...state, switches: SWITCHES_OFF } : state;
    return state.table.gameId === before.gameId
        ? switched
        : { ...switched, highestOpenedWaitId: null };
}

function decisionContext(state: LiveClient): DecisionContext {
    const { now, table, timer, viewerSeat } = state;
    const viewer = table.players.find((player) => player.seat === viewerSeat);
    return { at: now, hand: viewer?.tiles ?? [], melds: viewer?.melds ?? [], timer, viewerSeat };
}

/** What the seat owed before a message, as the message leaves it when it opens nothing. */
function followedPending(pending: Pending | null, message: ParsedServerMessage): Pending | null {
    if (pending === null) {
        return null;
    }
    if (pending.kind === "decision") {
        const decision = followDecision(pending.decision, message);
        return decision === null ? null : { decision, kind: "decision" };
    }
    const confirm = followRoundConfirm(pending.confirm, message);
    return confirm === null ? null : { confirm, kind: "round_confirm" };
}

/** The client owing a decision a message opened, in place of whatever it owed, its wait the highest opened if above. */
function withOpenedDecision(state: LiveClient, opened: Decision): LiveClient {
    const highest = Math.max(opened.waitId, state.highestOpenedWaitId ?? opened.waitId);
    return { ...replaceDecision(state, opened), highestOpenedWaitId: highest };
}

/**
 * What the seat owes after a message: what it owed when the message only repeats the wait it answered; else the
 * decision the message opens, raising the highest wait id opened, or the round confirm it opens or closes, either in
 * place of whatever the seat owed; else what it owed as the message leaves it.
 */
function withPendingAfter(state: LiveClient, message: ParsedServerMessage): LiveClient {
    const decision = decisionOf(state);
    if (decision !== null && isAnsweredWait(decision, message)) {
        return state;
    }
    const opened = openDecision(message, decisionContext(state));
    if (opened !== null) {
        return withOpenedDecision(state, opened);
    }
    const confirm = openedRoundConfirm(state, message);
    if (confirm !== undefined) {
        return replaceRoundConfirm(state, confirm);
    }
    return withPending(state, followedPending(pendingOf(state), message));
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
function liveCalls(state: LiveClient, event: TableEvent, table: TableState): ShownCalls | null {
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
function replayCalls(state: ReplayClient, event: TableEvent, table: TableState): ShownCalls | null {
    const calls = eventCalls(event, state.table, table);
    if (calls === null) {
        return state.calls;
    }
    return calls.length === 0 ? null : shownCalls(calls, state.now);
}

/**
 * The client after a server message the session took (`stepped`, from `before`): the table event it carries and its
 * calls, the viewer's facts, the play switches, what the seat owes, the game's last result and the notices, then the
 * switches' answer to a decision it opened on an unseen wait.
 */
function takeMessage(
    before: LiveClient,
    stepped: LiveClient,
    message: ParsedServerMessage,
): ClientStep<LiveClient> {
    const tableEvent = serverTableEvent(message);
    const table = tableEvent === null ? stepped.table : applyEvent(stepped.table, tableEvent);
    const tabled =
        tableEvent === null
            ? stepped
            : { ...stepped, calls: liveCalls(stepped, tableEvent, table), table };
    const viewed = withSwitches(withViewer(tabled, message), before.table, message);
    const owed = withPendingAfter(viewed, message);
    const shown = { ...owed, showsLastResult: showsLastResultAfter(owed, message) };
    const noticeBefore = { session: before.session, submitted: submittedWaitId(viewed) };
    const noticed = withNotice(noticeBefore, shown, message);
    return switchStep(noticed, viewed.highestOpenedWaitId);
}

/** Whether a message the client cannot take ends the page: a snapshot, or a game's end out of step already. */
function failsRecovery(stepped: LiveClient, message: ParsedServerMessage): boolean {
    return (
        message.type === "game_reconnected" ||
        (message.type === "game_end" && stepped.sync.kind === "out_of_step")
    );
}

/**
 * A game's end its in-step table refused, the first sign the client missed the round end before it, taken once more
 * by the client that loss put out of step (`lost`), since its standings are the server's whatever the table missed.
 */
function gameEndOutOfStep(
    before: LiveClient,
    lost: ClientStep<LiveClient>,
    message: ParsedServerMessage,
): ClientStep<LiveClient> {
    const ended = takeMessageInStep(before, lost.state, message);
    return { effects: [...lost.effects, ...ended.effects], state: ended.state };
}

/**
 * Take a server message the session took, as `takeMessage` does, where a `DesyncError` (a message the table or the
 * decision cannot take) is a protocol failure rather than a bug: it puts the client out of step, and it ends the page
 * for a snapshot or a game's end out of step already, since no snapshot can rebuild the client then; a game's end in
 * step is taken once more out of step (`gameEndOutOfStep`), and out of step, the game's last round end it cannot take
 * is one more message dropped. A snapshot puts the client back in step before it is taken, so what it says the seat
 * owes is owed in step. Any other error is the client's own and propagates.
 */
function takeMessageInStep(
    before: LiveClient,
    stepped: LiveClient,
    message: ParsedServerMessage,
): ClientStep<LiveClient> {
    try {
        const taking = message.type === "game_reconnected" ? resynced(stepped) : stepped;
        return takeMessage(before, taking, message);
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
function takeParsedMessage(
    state: LiveClient,
    message: ParsedServerMessage,
): ClientStep<LiveClient> {
    if (refusesResyncRequest(state, message)) {
        return { effects: [], state };
    }
    const step = withSession(state, { at: state.now, kind: "message", message });
    if (state.sync.kind === "out_of_step" && !takesWhileDesynced(message)) {
        return { effects: step.effects, state: deferredUntilDeal(step.state, message) };
    }
    const taken = takeMessageInStep(state, step.state, message);
    return { effects: [...step.effects, ...taken.effects], state: taken.state };
}

/**
 * A server message, on a session that takes them: one that does not parse puts the client out of step (a snapshot
 * that does not parse ends the page).
 */
function onServerMessage(state: LiveClient, raw: Record<string, unknown>): TracedStep<LiveClient> {
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
function robbedKanPart(state: ReplayClient, line: ReplayLine): TracedStep<ReplayClient> | null {
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
function replayLineStep(
    state: ReplayClient,
    line: ReplayLine,
    event: TableEvent,
): TracedStep<ReplayClient> {
    const table = applyEvent(state.table, event);
    const calls = replayCalls(state, event, table);
    return { effects: [], parsed: line, partial: false, state: { ...state, calls, table } };
}

/**
 * A replay file's line: a replay event or seat control line moves the table; any other is reported. A round end that
 * robbed a kan is taken in two parts, the kan declared and then the result, so a replay stops on the kan.
 */
function onReplayLine(state: ReplayClient, raw: Record<string, unknown>): TracedStep<ReplayClient> {
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

function onTick(state: LiveClient): ClientStep<LiveClient> {
    return withSession(state, { at: state.now, kind: "tick" });
}

/** The action `intent` sends now: the open decision's answer, on a socket the client can send on; or null. */
function decisionAnswer(state: LiveClient, intent: DecisionIntent): ClientMessage | null {
    const { table, viewerSeat } = state;
    const decision = decisionOf(state);
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
export function takesIntent(state: LiveClient, intent: PlayIntent): boolean {
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
    state: LiveClient,
    intent: DecisionIntent,
    bySwitch: PlaySwitch | null,
): ClientStep<LiveClient> {
    const decision = decisionOf(state);
    const message = decisionAnswer(state, intent);
    if (decision === null || message === null) {
        return { effects: [], state };
    }
    const status = { at: state.now, bySwitch, intent, kind: "submitted" } as const;
    return {
        effects: [{ message, type: "send" }],
        state: replaceDecision(state, { ...decision, status }),
    };
}

/**
 * The play switches' standing answer to a decision a message opened on a wait above the highest the game opened before
 * it (`highestBefore`), taken exactly where the player's press would be; nothing for a decision already open, re-sent after
 * a reconnect or reopened by a refusal, which stay the player's.
 */
function switchStep(state: LiveClient, highestBefore: number | null): ClientStep<LiveClient> {
    const decision = decisionOf(state);
    if (decision?.status.kind !== "open" || !unseenWait(decision.waitId, highestBefore)) {
        return { effects: [], state };
    }
    const answer = switchAnswer(decision, state.switches);
    return answer === null
        ? { effects: [], state }
        : onDecisionIntent(state, answer.intent, answer.bySwitch);
}

/** Whether the player may turn a play switch on or off now: on a live seat while a round plays. */
function takesSwitch(state: LiveClient): boolean {
    const { session, table, viewerSeat } = state;
    return session.status !== "ended" && viewerSeat !== null && table.phase === "in_round";
}

/** Turn a play switch on or off, sending nothing: it answers the waits the client sees from then on. */
function toggleSwitchStep(
    state: LiveClient,
    playSwitch: PlaySwitch,
): ClientStep<LiveClient> | null {
    if (!takesSwitch(state)) {
        return null;
    }
    const switches = { ...state.switches, [playSwitch]: !state.switches[playSwitch] };
    return { effects: [], state: { ...state, switches } };
}

function onIntent(state: LiveClient, intent: LocalIntent): ClientStep<LiveClient> {
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

function stepLiveEvent(timed: LiveClient, event: LiveEvent): TracedStep<LiveClient> {
    switch (event.kind) {
        case "server_message": {
            return onServerMessage(timed, event.raw);
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

/**
 * Begin the game client at logical time `at` from the lobby's handoff, or, when the tab holds none, by asking the
 * lobby for it.
 */
export function startGameClient(
    gameId: string,
    handoff: GameSessionData | null,
    at: number,
): ClientStep<LiveClient> {
    const step = startSession(gameId, handoff, at);
    const state: LiveClient = {
        calls: null,
        firstDealDue: null,
        furiten: false,
        highestOpenedWaitId: null,
        kind: "live",
        notice: null,
        now: at,
        resyncRequests: 0,
        session: step.state,
        showsLastResult: false,
        switches: SWITCHES_OFF,
        sync: { kind: "in_step", pending: null },
        table: createInitialTableState(),
        timer: null,
        viewerSeat: null,
    };
    return { effects: step.effects, state };
}

/** Begin a replay's client at logical time `at`: no session, no viewer, nothing it could send. */
export function startReplayClient(at: number): ReplayClient {
    return { calls: null, kind: "replay", now: at, table: createInitialTableState() };
}

/**
 * When the client next needs a tick: the earliest of its session's deadline, its open decision's, its notice's and its
 * calls' expiry, and when its resync request counts as unanswered, or null. A round confirm's deadline needs none: the
 * client never confirms on its own, and its countdown reads `now`.
 */
export function nextDeadline(state: LiveClient): number | null {
    const { calls, notice, session } = state;
    const decision = decisionOf(state);
    const decisionDue = decision?.status.kind === "open" ? decision.deadline : null;
    const deadlines = [
        sessionDeadline(session),
        desyncDeadline(state),
        decisionDue,
        notice?.until ?? null,
        calls?.until ?? null,
    ].filter((deadline) => deadline !== null);
    return deadlines.length === 0 ? null : Math.min(...deadlines);
}

/** The calls shown at logical time `at`: none once their time is past. */
function callsAt(calls: ShownCalls | null, at: number): ShownCalls | null {
    return calls !== null && at >= calls.until ? null : calls;
}

/** The state at logical time `at`: an open decision past its deadline expired, a notice or calls past their time gone. */
function expireAt(state: LiveClient, at: number): LiveClient {
    const { calls, notice } = state;
    const decision = decisionOf(state);
    const current = decision === null ? null : expireDecision(decision, at);
    const shown = notice !== null && at >= notice.until ? null : notice;
    const called = callsAt(calls, at);
    if (current === decision && shown === notice && called === calls) {
        return state;
    }
    const expired = { ...state, calls: called, notice: shown };
    return current === decision ? expired : replaceDecision(expired, current);
}

/**
 * One part of the live dispatcher's step with what it took of its event, as parsed: the event, then what the seat
 * owes settled on the session it left, the resync settlement and the expiry every event runs.
 */
function traceLivePart(state: LiveClient, event: LiveEvent): TracedStep<LiveClient> {
    const step = stepLiveEvent({ ...state, now: event.at }, event);
    const settled = settleDesync({ ...step, state: settledPending(step.state) });
    const expired = expireAt(settled.state, event.at);
    return { ...step, effects: settled.effects, state: expired };
}

/**
 * The live dispatcher's step as the parts it took, each with what it took of the event, as parsed, for a timeline to
 * index by: one part, but two for a replay's round end that robbed a kan (the kan declared, then the result). The
 * second part finds the kan shown, so the parts always end.
 */
export function traceLiveClient(
    state: LiveClient,
    event: LiveEvent,
): readonly TracedStep<LiveClient>[] {
    const step = traceLivePart(state, event);
    return step.partial ? [step, ...traceLiveClient(step.state, event)] : [step];
}

/**
 * A replay's step over one line of its file, as the parts it took, as `traceLiveClient` takes them: the line's table
 * event and the calls it makes, a replay having nothing else to take.
 */
export function traceReplayClient(
    state: ReplayClient,
    event: ReplayLineEvent,
): readonly TracedStep<ReplayClient>[] {
    const step = onReplayLine({ ...state, now: event.at }, event.raw);
    const part = { ...step, state: { ...step.state, calls: callsAt(step.state.calls, event.at) } };
    return part.partial ? [part, ...traceReplayClient(part.state, event)] : [part];
}

/**
 * The game client's dispatcher: a pure `(state, event) → { state, effects }` over client events, composing the
 * session transition, the table transition and the viewer's decision. Nothing in it runs IO, reads a clock or
 * starts a timer; the effects are descriptions only a live driver executes, and the time is the event's `at`.
 */
export function stepGameClient(state: LiveClient, event: LiveEvent): ClientStep<LiveClient> {
    const parts = traceLiveClient(state, event);
    return {
        effects: parts.flatMap((part) => part.effects),
        state: parts.at(-1)?.state ?? state,
    };
}
