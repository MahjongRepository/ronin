import { z } from "zod/mini";

import { assertNever } from "@/shared/lib";
import {
    CLIENT_MESSAGE_TYPE,
    CLOSE_CODE,
    type ClientMessage,
    EVENT_TYPE,
    GAME_ACTION,
    KAN_TYPE,
    NUM_PLAYERS,
    NUM_TILES,
} from "@/shared/protocol";
import { type GameSessionData } from "@/shared/session";

import { nextDeadline, startGameClient, stepGameClient } from "./dispatch";
import { type ScenarioStep, type SeatScenario } from "./scenario";
import { type ClientEffect, type LiveClient, type LocalIntent, type Offer } from "./types";

/** What a transcript writes for the game ticket of a JOIN_GAME or RECONNECT, which the lobby's handoff holds. */
const GAME_TICKET_PLACEHOLDER = "<game ticket>";

/**
 * The closes after which the client must not reconnect, as `docs/architecture.md` (Game client contract) names
 * them: kept here apart from the session's own policy, so a scenario checks the session against the contract.
 */
const TERMINAL_CLOSE_CODES: ReadonlySet<number> = new Set([
    CLOSE_CODE.INVALID_GAME_ACTION,
    CLOSE_CODE.REPLACED_BY_NEW_CONNECTION,
]);

const tileIdSchema = z.int().check(z.gte(0), z.lte(NUM_TILES - 1));
const actionBase = {
    t: z.literal(CLIENT_MESSAGE_TYPE.GAME_ACTION),
    wi: z.int().check(z.gte(0)),
};

/**
 * A game action exactly as the seat sent it: strict, so a key the client's builders never write fails the parse,
 * and each shape is one of the builders' `ClientMessage` shapes.
 */
const sentActionSchema = z.discriminatedUnion("a", [
    z.strictObject({ ...actionBase, a: z.literal(GAME_ACTION.DISCARD), ti: tileIdSchema }),
    z.strictObject({ ...actionBase, a: z.literal(GAME_ACTION.DECLARE_RIICHI), ti: tileIdSchema }),
    z.strictObject({ ...actionBase, a: z.literal(GAME_ACTION.DECLARE_TSUMO) }),
    z.strictObject({ ...actionBase, a: z.literal(GAME_ACTION.CALL_RON) }),
    z.strictObject({ ...actionBase, a: z.literal(GAME_ACTION.CALL_PON), ti: tileIdSchema }),
    z.strictObject({
        ...actionBase,
        a: z.literal(GAME_ACTION.CALL_CHI),
        sequence_tiles: z.tuple([tileIdSchema, tileIdSchema]),
        ti: tileIdSchema,
    }),
    z.strictObject({
        ...actionBase,
        a: z.literal(GAME_ACTION.CALL_KAN),
        kan_type: z.enum([KAN_TYPE.ADDED, KAN_TYPE.CLOSED, KAN_TYPE.OPEN]),
        ti: tileIdSchema,
    }),
    z.strictObject({ ...actionBase, a: z.literal(GAME_ACTION.CALL_KYUUSHU) }),
    z.strictObject({ ...actionBase, a: z.literal(GAME_ACTION.PASS) }),
    z.strictObject({ ...actionBase, a: z.literal(GAME_ACTION.CONFIRM_ROUND) }),
]);

const ticketSchema = z.literal(GAME_TICKET_PLACEHOLDER);

/** A JOIN_GAME or RECONNECT exactly as the seat sent it, its ticket replaced by the placeholder. */
const sentIdentitySchema = z.discriminatedUnion("t", [
    z.strictObject({ game_ticket: ticketSchema, t: z.literal(CLIENT_MESSAGE_TYPE.JOIN_GAME) }),
    z.strictObject({ game_ticket: ticketSchema, t: z.literal(CLIENT_MESSAGE_TYPE.RECONNECT) }),
]);

type SentAction = z.output<typeof sentActionSchema>;
type SentIdentity = z.output<typeof sentIdentitySchema>;

const atSchema = z.int().check(z.gte(0));
const labelSchema = z.optional(z.string().check(z.minLength(1)));
const payloadSchema = z.record(z.string(), z.unknown());
const sentMessageSchema = z.union([sentIdentitySchema, sentActionSchema]);

const transcriptEventSchema = z.discriminatedUnion("kind", [
    z.strictObject({ at: atSchema, kind: z.literal("opened"), label: labelSchema }),
    z.strictObject({
        at: atSchema,
        code: z.int(),
        kind: z.literal("closed"),
        label: labelSchema,
        reason: z.string(),
    }),
    z.strictObject({
        at: atSchema,
        kind: z.literal("received"),
        label: labelSchema,
        payload: payloadSchema,
    }),
    z.strictObject({
        at: atSchema,
        kind: z.literal("sent"),
        label: labelSchema,
        message: sentMessageSchema,
    }),
]);

type TranscriptEvent = z.output<typeof transcriptEventSchema>;

function inTimeOrder(events: readonly { readonly at: number }[]): boolean {
    return events.every((event, index) => index === 0 || event.at >= events[index - 1].at);
}

const transcriptEventsSchema = z
    .array(transcriptEventSchema)
    .check(z.refine(inTimeOrder, "a transcript's times never go back"));

const nameSchema = z.string().check(z.minLength(1));
const seatSchema = z.int().check(z.gte(0), z.lte(NUM_PLAYERS - 1));

const seatTranscriptSchema = z.pipe(
    z.strictObject({
        events: transcriptEventsSchema,
        game_id: nameSchema,
        scenario: nameSchema,
        seat: seatSchema,
    }),
    z.transform(({ events, game_id: gameId, scenario, seat }) => ({
        events,
        gameId,
        scenario,
        seat,
    })),
);

/**
 * What the server met of one seat's client in a scenario the backend generated (`make generate-seat-scenarios`),
 * in order with logical times in milliseconds: the sockets it opened, each message its socket received as raw wire
 * payload, each message it sent (its JOIN_GAME and RECONNECT with the ticket left out), and each close it saw.
 */
export type SeatTranscript = z.output<typeof seatTranscriptSchema>;

/** Parse a seat transcript at the boundary it arrives at, as JSON. */
export function parseSeatTranscript(raw: unknown): [Error, null] | [null, SeatTranscript] {
    const result = seatTranscriptSchema.safeParse(raw);
    return result.success ? [null, result.data] : [result.error, null];
}

function isIdentity(message: SentIdentity | SentAction): message is SentIdentity {
    return message.t !== CLIENT_MESSAGE_TYPE.GAME_ACTION;
}

type ChosenAction = Exclude<
    SentAction,
    { a: typeof GAME_ACTION.DISCARD | typeof GAME_ACTION.PASS | typeof GAME_ACTION.CONFIRM_ROUND }
>;

/** The offer whose choice sends `action`. */
function chosenOffer(action: ChosenAction): Offer {
    switch (action.a) {
        case GAME_ACTION.DECLARE_RIICHI: {
            return { kind: "riichi", tileId: action.ti };
        }
        case GAME_ACTION.DECLARE_TSUMO: {
            return { kind: "tsumo" };
        }
        case GAME_ACTION.CALL_RON: {
            return { kind: "ron" };
        }
        case GAME_ACTION.CALL_PON: {
            return { kind: "pon", tileId: action.ti };
        }
        case GAME_ACTION.CALL_CHI: {
            return { kind: "chi", sequence: action.sequence_tiles, tileId: action.ti };
        }
        case GAME_ACTION.CALL_KAN: {
            return { kanType: action.kan_type, kind: "kan", tileId: action.ti };
        }
        case GAME_ACTION.CALL_KYUUSHU: {
            return { kind: "kyuushu" };
        }
        default: {
            return assertNever(action);
        }
    }
}

/** The intent that sends `action`: the answer to a decision, or the player's confirm of a round result. */
function answeringIntent(action: SentAction): LocalIntent {
    switch (action.a) {
        case GAME_ACTION.DISCARD: {
            return { tileId: action.ti, type: "discard" };
        }
        case GAME_ACTION.PASS: {
            return { type: "pass" };
        }
        case GAME_ACTION.CONFIRM_ROUND: {
            return { type: "confirm_result" };
        }
        default: {
            return { offer: chosenOffer(action), type: "choose" };
        }
    }
}

/** A sent message as the client sends it: a JOIN_GAME or RECONNECT with the handoff's ticket. */
function sentEffect(message: SentIdentity | SentAction, handoff: GameSessionData): ClientEffect {
    const sent: ClientMessage = isIdentity(message)
        ? { ...message, game_ticket: handoff.gameTicket }
        : message;
    return { message: sent, type: "send" };
}

/**
 * A sent message as the step that makes the client send it: the intent choosing it (an answer, a round confirm), or,
 * for a message the client sends on its own (a JOIN_GAME or RECONNECT resent on its open socket), the tick at its
 * recorded time.
 */
function sentStep(
    { at, label, message }: Extract<TranscriptEvent, { kind: "sent" }>,
    handoff: GameSessionData,
): ScenarioStep {
    const effects = [sentEffect(message, handoff)];
    if (isIdentity(message)) {
        return { effects, event: { at, kind: "tick" }, label };
    }
    return { effects, event: { at, intent: answeringIntent(message), kind: "intent" }, label };
}

/**
 * A close as the step the client takes it in: after one the contract makes terminal the client stops reconnecting and
 * forgets the handoff, staying on the page to say why.
 */
function closedStep(
    { at, code, label, reason }: Extract<TranscriptEvent, { kind: "closed" }>,
    gameId: string,
): ScenarioStep {
    const effects: ClientEffect[] = TERMINAL_CLOSE_CODES.has(code)
        ? [{ gameId, type: "clear_handoff" }]
        : [];
    return { effects, event: { at, code, kind: "transport_closed", reason }, label };
}

/**
 * A server message as the step the client takes it in: after the game's end the seat's ticket will never hold it
 * again, so the client forgets the handoff and a return to the page joins with no dead ticket.
 */
function receivedStep(
    { at, label, payload }: Extract<TranscriptEvent, { kind: "received" }>,
    gameId: string,
): ScenarioStep {
    const effects: ClientEffect[] =
        payload.t === EVENT_TYPE.GAME_END ? [{ gameId, type: "clear_handoff" }] : [];
    return { effects, event: { at, kind: "server_message", raw: payload }, label };
}

/** Where the converter is in a transcript: its events and the index of the next one to take. */
interface Cursor {
    readonly events: readonly TranscriptEvent[];
    readonly index: number;
}

interface DriveContext {
    readonly gameId: string;
    readonly handoff: GameSessionData;
    /** Whether a socket was opened before, so the next open is the client's own reopen. */
    readonly reopen: boolean;
}

/** The steps a transcript event is taken in, and how many events they cover. */
interface Taken {
    readonly steps: readonly ScenarioStep[];
    readonly covered: number;
}

/**
 * A socket's open as the steps the client takes it in, with how many transcript events they cover: a socket opened
 * after the first is the client's own reopen, so a tick at its recorded time must ask to open it; the open then
 * sends the JOIN_GAME or RECONNECT the transcript records right after it.
 */
function openedSteps({ events, index }: Cursor, { handoff, reopen }: DriveContext): Taken {
    const { at, label } = events[index];
    const next = events.at(index + 1);
    const identity =
        next?.kind === "sent" && next.at === at && isIdentity(next.message) ? next : null;
    const opening: ScenarioStep = {
        effects: identity === null ? [] : [sentEffect(identity.message, handoff)],
        event: { at, kind: "transport_opened" },
        label: label ?? identity?.label,
    };
    const reopening: ScenarioStep[] = reopen
        ? [{ effects: [{ type: "open_socket", url: handoff.wsUrl }], event: { at, kind: "tick" } }]
        : [];
    return { covered: identity === null ? 1 : 2, steps: [...reopening, opening] };
}

/**
 * The ticks the live driver takes before `at`: one at each deadline the client holds that falls due earlier, each
 * expected to describe no effect, since everything the client sent on its own is in the transcript at its time.
 */
function ticksBefore(
    state: LiveClient,
    at: number,
): { readonly state: LiveClient; readonly steps: ScenarioStep[] } {
    const steps: ScenarioStep[] = [];
    let current = state;
    for (let due = nextDeadline(current); due !== null && due < at; due = nextDeadline(current)) {
        const step: ScenarioStep = { event: { at: due, kind: "tick" } };
        current = stepGameClient(current, step.event).state;
        if (nextDeadline(current) === due) {
            throw new Error(`A tick at ${due} left the client's deadline where it was`);
        }
        steps.push(step);
    }
    return { state: current, steps };
}

function advance(state: LiveClient, steps: readonly ScenarioStep[]): LiveClient {
    return steps.reduce((current, step) => stepGameClient(current, step.event).state, state);
}

/** The steps the transcript event at the cursor is taken in. */
function eventSteps(cursor: Cursor, context: DriveContext): Taken {
    const event = cursor.events[cursor.index];
    switch (event.kind) {
        case "opened": {
            return openedSteps(cursor, context);
        }
        case "received": {
            return { covered: 1, steps: [receivedStep(event, context.gameId)] };
        }
        case "sent": {
            return { covered: 1, steps: [sentStep(event, context.handoff)] };
        }
        case "closed": {
            return { covered: 1, steps: [closedStep(event, context.gameId)] };
        }
        default: {
            return assertNever(event);
        }
    }
}

interface Driven extends Taken {
    readonly state: LiveClient;
}

/** Drive the client to the transcript event at `index` and through it: the ticks due before it, then its steps. */
function driveEvent(state: LiveClient, cursor: Cursor, context: DriveContext): Driven {
    const ticks = ticksBefore(state, cursor.events[cursor.index].at);
    const taken = eventSteps(cursor, context);
    return {
        covered: taken.covered,
        state: advance(ticks.state, taken.steps),
        steps: [...ticks.steps, ...taken.steps],
    };
}

/** Drive the client through the transcript from its start, returning the steps it is taken in. */
function drivenSteps(transcript: SeatTranscript, handoff: GameSessionData): ScenarioStep[] {
    const { events, gameId } = transcript;
    let { state } = startGameClient(gameId, handoff, events[0]?.at ?? 0);
    const steps: ScenarioStep[] = [];
    for (let index = 0; index < events.length;) {
        const reopen = events.slice(0, index).some((event) => event.kind === "opened");
        const driven = driveEvent(state, { events, index }, { gameId, handoff, reopen });
        ({ state } = driven);
        steps.push(...driven.steps);
        index += driven.covered;
    }
    return steps;
}

/**
 * The seat scenario a transcript describes. The converter drives the client as the live driver does, ticking at
 * each deadline the client holds before the transcript's next event; the effects it expects come only from the
 * transcript and the contract, never from the client under test: every message the transcript records sent, at its
 * recorded time (an answer or a round confirm as the intent choosing it, a message the client sends on its own as a
 * tick then, a JOIN_GAME or RECONNECT as the effect of the open before it), a socket reopened at its recorded open,
 * the handoff forgotten after a terminal close, and nothing else. An automatic send the client makes early, late or never is a
 * mismatch.
 */
export function seatScenarioFromTranscript(
    transcript: SeatTranscript,
    handoff: GameSessionData,
): SeatScenario {
    const { events, gameId, scenario, seat } = transcript;
    return {
        gameId,
        handoff,
        name: `${scenario} (seat ${seat})`,
        seat,
        startAt: events[0]?.at ?? 0,
        startEffects: [{ type: "open_socket", url: handoff.wsUrl }],
        steps: drivenSteps(transcript, handoff),
    };
}
