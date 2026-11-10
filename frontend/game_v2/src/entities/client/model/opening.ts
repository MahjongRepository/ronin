import { assertNever } from "@/shared/lib";
import { type ParsedServerMessage } from "@/shared/protocol";

import { startConfirmOf } from "./pending";
import { sendConfirmStep } from "./round-confirm";
import { type ClientStep, type LiveClient, type OpeningScreen } from "./types";

/** How long the opening screen shows for a page that joined a game in play. */
export const OPENING_SCREEN_MS = 5000;

const CLOSED: OpeningScreen = { kind: "closed" };
const START: OpeningScreen = { cause: "start", kind: "showing" };

/**
 * Whether a message the client took left the seat owing the start confirm: the first deal's, or a snapshot's of the
 * game's start. It shows the start screen whatever the page showed, since only its OK sends the confirm.
 */
function owesStartAfter(state: LiveClient, message: ParsedServerMessage): boolean {
    return (
        (message.type === "round_started" || message.type === "game_reconnected") &&
        startConfirmOf(state)?.kind === "owed"
    );
}

/**
 * The opening screen a message opens on a page that has shown none: the game start's at its first deal, so the seating
 * first shows scored and with its OK, never growing them a moment after the game start; a snapshot's of the game's start
 * before its first draw, as the start's, or of a round in play, for `OPENING_SCREEN_MS`, while one of a round's result
 * pending opens none, since the result's own panel shows the round and the scores. Any other message opens none yet.
 */
function openedBy(state: LiveClient, message: ParsedServerMessage): OpeningScreen {
    const { now, table } = state;
    if (message.type === "round_started") {
        return START;
    }
    if (message.type === "game_reconnected") {
        if (startConfirmOf(state) !== null) {
            return START;
        }
        return table.phase === "in_round"
            ? { cause: "resume", kind: "showing", until: now + OPENING_SCREEN_MS }
            : CLOSED;
    }
    return state.opening;
}

/**
 * Whether a message closes the opening screen showing: a round's end or the game's end, whose panels take its place,
 * and for the game's start, the first draw, which starts play once the server has every seat's start confirm or its
 * timeout ran out.
 */
function closesShowing(
    cause: "start" | "resume",
    state: LiveClient,
    message: ParsedServerMessage,
): boolean {
    const { phase } = state.table;
    if (phase === "round_ended" || phase === "game_ended") {
        return true;
    }
    return cause === "start" && (message.type === "draw" || message.type === "draw_notice");
}

/** The client with the opening screen a message the table took leaves: opened, closed, or as it was. */
export function withOpening(state: LiveClient, message: ParsedServerMessage): LiveClient {
    const { opening } = state;
    if (owesStartAfter(state, message)) {
        return opening.kind === "showing" && opening.cause === "start"
            ? state
            : { ...state, opening: START };
    }
    switch (opening.kind) {
        case "unseen": {
            const opened = openedBy(state, message);
            return opened === opening ? state : { ...state, opening: opened };
        }
        case "showing": {
            return closesShowing(opening.cause, state, message)
                ? { ...state, opening: CLOSED }
                : state;
        }
        case "closed": {
            return state;
        }
        default: {
            return assertNever(opening);
        }
    }
}

/** The opening screen at logical time `at`: the resume screen closed once its time ran out. */
export function openingAt(opening: OpeningScreen, at: number): OpeningScreen {
    return opening.kind === "showing" && opening.cause === "resume" && at >= opening.until
        ? CLOSED
        : opening;
}

/**
 * When the opening screen showing closes on its own: the resume screen's time; null for the start screen, which play's
 * start closes, the server timing the start confirm out, and while none shows.
 */
export function openingDeadline(state: LiveClient): number | null {
    const { opening } = state;
    return opening.kind === "showing" && opening.cause === "resume" ? opening.until : null;
}

/**
 * The opening screen's OK: send the start confirm the seat owes (`sendConfirmStep`), the screen showing on until play
 * starts; else, with no start confirm (the resume screen, a seat the server does not await, or a socket that dropped
 * it), close the screen, sending nothing. Null while none shows, and while the seat waits for the others on a start
 * confirm it sent or a snapshot found in.
 */
export function confirmOpeningStep(
    state: LiveClient,
    sendable: boolean,
): ClientStep<LiveClient> | null {
    if (state.opening.kind !== "showing") {
        return null;
    }
    return startConfirmOf(state) === null
        ? { effects: [], state: { ...state, opening: CLOSED } }
        : sendConfirmStep(state, sendable);
}
