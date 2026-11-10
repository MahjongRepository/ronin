import {
    type SessionInput,
    type SessionState,
    endReasonOf,
    sessionDeadline,
    startSession,
    stepSession,
    takesMessages,
} from "@/entities/session";
import {
    DesyncError,
    type TableEvent,
    type TableState,
    applyEvent,
    chankanKanDeclared,
    createInitialTableState,
} from "@/entities/table";
import { assertNever } from "@/shared/lib";
import { CALL_TYPE, type ParsedServerMessage, parseServerMessage } from "@/shared/protocol";
import { type GameSessionData } from "@/shared/session";

import { callsAt, liveCalls } from "./calls";
import {
    type DecisionContext,
    expireDecision,
    followDecision,
    isAnsweredWait,
    openDecision,
} from "./decision";
import {
    desyncDeadline,
    desyncStep,
    isSnapshotPayload,
    recoveryFailedStep,
    refusesResyncRequest,
    requestAfterDropped,
    resynced,
    settleDesync,
    takesWhileDesynced,
    withPacing,
} from "./desync";
import {
    automaticStep,
    canAnswer,
    decisionIntentStep,
    discardAutomaticDrawStep,
    settleAutomaticDiscard,
    toggleKeepAutoWinStep,
    toggleSwitchStep,
} from "./intents";
import { keptNotice, submittedWaitId, withNotice } from "./notices";
import { confirmOpeningStep, openingAt, openingDeadline, withOpening } from "./opening";
import {
    decisionOf,
    pendingOf,
    replaceDecision,
    replaceRoundConfirm,
    settledPending,
    withPending,
} from "./pending";
import { SWITCHES_OFF, snapshotLeftHand, switchesForNewHand, unseenWait } from "./play-switches";
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
    type LiveClient,
    type LiveEvent,
    type LocalIntent,
    type Pending,
    type TracedStep,
} from "./types";

function untraced(step: ClientStep<LiveClient>): TracedStep<LiveClient> {
    return { ...step, parsed: null };
}

/** Whether the session ended other than by the game's end: it failed, or the player left. */
function endedEarly(session: SessionState): boolean {
    const reason = endReasonOf(session);
    return reason !== null && reason.kind !== "game_ended";
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

/** The viewer's own facts a message carries: its seat, its timer settings, its furiten, its pending game's wait. */
function withViewer(state: LiveClient, message: ParsedServerMessage): LiveClient {
    switch (message.type) {
        case "game_started": {
            return { ...withPacing(state, message), viewerSeat: message.seat ?? state.viewerSeat };
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
        case "game_joined": {
            return withPacing(state, message);
        }
        default: {
            return state;
        }
    }
}

/**
 * The play switches after a message, from the table it found (`before`): a deal turns them off, as does a reconnect's
 * snapshot of another hand or of a round result pending, except an Auto win the player keeps between rounds. Any other
 * message leaves them, a snapshot of the same hand included. A table of another game forgets the highest wait id
 * opened, which belongs to its game.
 */
function withSwitches(
    state: LiveClient,
    before: TableState,
    message: ParsedServerMessage,
): LiveClient {
    const leaves =
        message.type === "round_started" ||
        (message.type === "game_reconnected" && snapshotLeftHand(before, state.table));
    const switched = leaves
        ? { ...state, switches: switchesForNewHand(state.switches, state.keepAutoWin) }
        : state;
    return state.table.gameId === before.gameId
        ? switched
        : { ...switched, highestOpenedWaitId: null };
}

function decisionContext(state: LiveClient): DecisionContext {
    const { now, table, timer, viewerSeat } = state;
    const viewer = table.players.find((player) => player.seat === viewerSeat);
    return {
        at: now,
        hand: viewer?.tiles ?? [],
        melds: viewer?.melds ?? [],
        phase: table.phase,
        timer,
        viewerSeat,
    };
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
    if (confirm.kind === "replaced") {
        return replaceRoundConfirm(state, confirm.confirm);
    }
    return withPending(state, followedPending(pendingOf(state), message));
}

function repeatedCallPrompt(state: LiveClient, message: TracedStep["parsed"]): boolean {
    return (
        message?.type === "call_prompt" &&
        message.waitId !== null &&
        !unseenWait(message.waitId, state.highestOpenedWaitId)
    );
}

function applyMessageTable(state: LiveClient, message: ParsedServerMessage): LiveClient {
    const event = serverTableEvent(message);
    if (event === null) {
        return state;
    }
    const table = applyEvent(state.table, event);
    const calls = repeatedCallPrompt(state, message) ? state.calls : liveCalls(state, event, table);
    return { ...state, calls, table };
}

/**
 * The client after a server message the session took (`stepped`, from `before`): the table event it carries and its
 * calls, the viewer's facts, the play switches, what the seat owes, the game's last result, the notices and the
 * opening screen, then the automatic answer to a decision it opened on an unseen wait.
 */
function takeMessage(
    before: LiveClient,
    stepped: LiveClient,
    message: ParsedServerMessage,
): ClientStep<LiveClient> {
    const tabled = applyMessageTable(stepped, message);
    const viewed = withSwitches(withViewer(tabled, message), before.table, message);
    const owed = withPendingAfter(viewed, message);
    const shown = { ...owed, showsLastResult: showsLastResultAfter(owed, message) };
    const noticeBefore = { session: before.session, submitted: submittedWaitId(viewed) };
    const noticed = withNotice(noticeBefore, shown, message);
    return automaticStep(withOpening(noticed, message), viewed.highestOpenedWaitId);
}

/**
 * A game's end its in-step table refused, the first sign the client missed the round end before it, taken once more
 * by the client that loss put out of step (`lost`), since its final scores are the server's whatever the table missed. A
 * table out of step takes any game end, so this take cannot refuse it again.
 */
function gameEndOutOfStep(
    before: LiveClient,
    lost: ClientStep<LiveClient>,
    message: ParsedServerMessage,
): ClientStep<LiveClient> {
    const ended = takeMessage(before, lost.state, message);
    return { effects: [...lost.effects, ...ended.effects], state: ended.state };
}

/**
 * Take a server message the session took, as `takeMessage` does, where a `DesyncError` (a message the table or the
 * decision cannot take) is a protocol failure rather than a bug: it puts the client out of step, and it ends the page
 * for a snapshot, since no snapshot can rebuild the client then; a game's end in step is taken once more out of step
 * (`gameEndOutOfStep`), and out of step, the game's last round end it cannot take is one more message dropped. A
 * snapshot puts the client back in step before it is taken, so what it says the seat owes is owed in step. Any other
 * error is the client's own and propagates.
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
        if (message.type === "game_reconnected") {
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
    const { sync } = state;
    if (sync.kind === "out_of_step" && !takesWhileDesynced(message)) {
        const paced = withPacing(step.state, message);
        return { effects: step.effects, state: requestAfterDropped(paced, sync, message) };
    }
    const taken = takeMessageInStep(state, step.state, message);
    return { effects: [...step.effects, ...taken.effects], state: taken.state };
}

/**
 * A server message, on a session that takes them: one that does not parse puts the client out of step (a snapshot
 * that does not parse ends the page).
 */
function onServerMessage(state: LiveClient, raw: Record<string, unknown>): TracedStep<LiveClient> {
    if (!takesMessages(state.session)) {
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
    return { ...takeParsedMessage(state, message), parsed: message };
}

function onTick(state: LiveClient): ClientStep<LiveClient> {
    const session = withSession(state, { at: state.now, kind: "tick" });
    const discarded = discardAutomaticDrawStep(session.state);
    return { effects: [...session.effects, ...discarded.effects], state: discarded.state };
}

function onIntent(state: LiveClient, intent: LocalIntent): ClientStep<LiveClient> {
    switch (intent.type) {
        case "leave": {
            return withSession(state, { at: state.now, kind: "leave" });
        }
        case "discard":
        case "choose":
        case "pass": {
            return decisionIntentStep(state, intent, null);
        }
        case "toggle_switch": {
            return toggleSwitchStep(state, intent.playSwitch) ?? { effects: [], state };
        }
        case "toggle_keep_auto_win": {
            return toggleKeepAutoWinStep(state);
        }
        case "confirm_result": {
            return confirmStep(state, canAnswer(state)) ?? { effects: [], state };
        }
        case "show_last_result": {
            return reopenResultStep(state) ?? { effects: [], state };
        }
        case "confirm_opening": {
            return confirmOpeningStep(state, canAnswer(state)) ?? { effects: [], state };
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
                takesMessages(timed.session)
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
        automaticDiscard: null,
        boardMotion: { mode: "reset", sequence: 0 },
        calls: null,
        furiten: false,
        highestOpenedWaitId: null,
        keepAutoWin: false,
        kind: "live",
        notice: null,
        now: at,
        opening: { kind: "unseen" },
        pendingGameSeconds: null,
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

/**
 * When the client next needs a tick: the earliest of its session's deadline, its open decision's, its notice's, its
 * calls' and its resume screen's expiry, and when its resync request counts as unanswered, or null. A round confirm's
 * deadline needs none: the client never confirms on its own, and its countdown reads `now`.
 */
export function nextDeadline(state: LiveClient): number | null {
    const { calls, notice, session } = state;
    const decision = decisionOf(state);
    const decisionDue = decision?.status.kind === "open" ? decision.deadline : null;
    const deadlines = [
        sessionDeadline(session),
        desyncDeadline(state),
        decisionDue,
        state.automaticDiscard?.due ?? null,
        notice?.until ?? null,
        calls?.until ?? null,
        openingDeadline(state),
    ].filter((deadline) => deadline !== null);
    return deadlines.length === 0 ? null : Math.min(...deadlines);
}

/**
 * The state at logical time `at`: an open decision past its deadline expired, a notice, calls or the resume screen
 * past their time gone.
 */
function expireAt(state: LiveClient, at: number): LiveClient {
    const { calls, notice, opening } = state;
    const decision = decisionOf(state);
    const current = decision === null ? null : expireDecision(decision, at);
    const shown = notice !== null && at >= notice.until ? null : notice;
    const called = callsAt(calls, at);
    const opened = openingAt(opening, at);
    if (current === decision && shown === notice && called === calls && opened === opening) {
        return state;
    }
    const expired = { ...state, calls: called, notice: shown, opening: opened };
    return current === decision ? expired : replaceDecision(expired, current);
}

/**
 * The live dispatcher's step with what it took of its event, as parsed, for a timeline to index by: the event, then
 * what the seat owes settled on the session it left, the resync settlement and the expiry every event runs. A live
 * event is always one step. Logical time never runs back: an event stamped before the state's `now` (a wall clock
 * stepped back) is taken at `now`.
 */
export function traceLiveClient(state: LiveClient, stamped: LiveEvent): TracedStep<LiveClient> {
    const event = { ...stamped, at: Math.max(state.now, stamped.at) };
    const step = stepLiveEvent({ ...state, now: event.at }, event);
    const settled = settleDesync({ ...step, state: settledPending(step.state) });
    const expired = expireAt(settled.state, event.at);
    const next = settleAutomaticDiscard(expired);
    const changed = next.table !== state.table;
    const reset =
        step.parsed?.type === "game_reconnected" ||
        repeatedCallPrompt(state, step.parsed) ||
        !next.table.inStep;
    const boardMotion = changed
        ? {
              mode: reset ? ("reset" as const) : ("step" as const),
              sequence: state.boardMotion.sequence + 1,
          }
        : state.boardMotion;
    return { ...step, effects: settled.effects, state: { ...next, boardMotion } };
}

/**
 * The game client's dispatcher: a pure `(state, event) → { state, effects }` over client events, composing the
 * session transition, the table transition and the viewer's decision. Nothing in it runs IO, reads a clock or
 * starts a timer; the effects are descriptions only a live driver executes, and the time is the event's `at`.
 */
export function stepGameClient(state: LiveClient, event: LiveEvent): ClientStep<LiveClient> {
    const { effects, state: next } = traceLiveClient(state, event);
    return { effects, state: next };
}
