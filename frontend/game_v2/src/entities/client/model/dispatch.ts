import {
    type SessionInput,
    type SessionState,
    failSession,
    sessionDeadline,
    startSession,
    stepSession,
} from "@/entities/session";
import { assertNever } from "@/shared/lib";
import {
    type ParsedServerMessage,
    buildConfirmRoundAction,
    parseServerMessage,
} from "@/shared/protocol";
import { type GameSessionData } from "@/shared/session";

import { type ClientEvent, type ClientStep, type GameClientState, type LocalIntent } from "./types";

const ROUND_CONFIRM_DELAY_MS = 1000;

function canSend(session: SessionState): boolean {
    return session.status === "playing" && session.link === "open";
}

/** Whether a message shows the server moved past the round advance a pending confirm answers. */
function supersedesRoundAdvance(message: ParsedServerMessage): boolean {
    return (
        message.type !== "session_error" &&
        message.type !== "player_left" &&
        message.type !== "player_reconnected"
    );
}

/** Step the session, then drop a pending confirm the session can no longer send. */
function withSession(state: GameClientState, input: SessionInput): ClientStep {
    const step = stepSession(state.session, input);
    return {
        effects: step.effects,
        state: {
            ...state,
            pendingConfirm: canSend(step.state) ? state.pendingConfirm : null,
            session: step.state,
        },
    };
}

function confirmLater(state: GameClientState, message: ParsedServerMessage): GameClientState {
    if (message.type !== "round_end" || message.waitId === null || !canSend(state.session)) {
        return state;
    }
    const dueAt = state.now + ROUND_CONFIRM_DELAY_MS;
    return { ...state, pendingConfirm: { dueAt, waitId: message.waitId } };
}

function onServerMessage(state: GameClientState, raw: Record<string, unknown>): ClientStep {
    const [error, message] = parseServerMessage(raw);
    if (error) {
        return { effects: [{ detail: error.message, type: "report_parse_error" }], state };
    }
    const step = withSession(state, { at: state.now, kind: "message", message });
    const moved = supersedesRoundAdvance(message)
        ? { ...step.state, pendingConfirm: null }
        : step.state;
    return { effects: step.effects, state: confirmLater(moved, message) };
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

function onIntent(state: GameClientState, intent: LocalIntent): ClientStep {
    switch (intent.type) {
        case "leave": {
            return withSession(state, { at: state.now, kind: "leave" });
        }
        default: {
            return assertNever(intent.type);
        }
    }
}

/** Begin the game client at logical time `at` from the lobby's handoff, or null when the tab holds none. */
export function startGameClient(
    gameId: string,
    handoff: GameSessionData | null,
    at: number,
): ClientStep {
    const step = startSession(gameId, handoff);
    return { effects: step.effects, state: { now: at, pendingConfirm: null, session: step.state } };
}

/** When the client next needs a tick: the earliest of its pending retry and its pending confirm, or null. */
export function nextDeadline(state: GameClientState): number | null {
    const deadlines = [sessionDeadline(state.session), state.pendingConfirm?.dueAt ?? null].filter(
        (deadline) => deadline !== null,
    );
    return deadlines.length === 0 ? null : Math.min(...deadlines);
}

/** End the client because its driver failed while stepping it; nothing is pending afterwards. */
export function failGameClient(state: GameClientState, detail: string): GameClientState {
    return { ...state, pendingConfirm: null, session: failSession(state.session, detail) };
}

/**
 * The game client's dispatcher: a pure `(state, event) → { state, effects }` over client events, composing the
 * session transition and the round confirm. Nothing in it runs IO, reads a clock or starts a timer; the effects
 * are descriptions only a live driver executes, and the time is the event's `at`.
 */
export function stepGameClient(state: GameClientState, event: ClientEvent): ClientStep {
    const timed: GameClientState = { ...state, now: event.at };
    switch (event.kind) {
        case "server_message": {
            return onServerMessage(timed, event.raw);
        }
        case "transport_opened": {
            return withSession(timed, { at: event.at, kind: "transport_opened" });
        }
        case "transport_closed": {
            const { at, code, reason } = event;
            return withSession(timed, { at, code, kind: "transport_closed", reason });
        }
        case "transport_error": {
            return { effects: [], state: timed };
        }
        case "tick": {
            return onTick(timed);
        }
        case "intent": {
            return onIntent(timed, event.intent);
        }
        default: {
            return assertNever(event);
        }
    }
}
