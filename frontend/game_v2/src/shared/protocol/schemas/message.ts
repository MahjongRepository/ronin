import { type z } from "zod/mini";

import { EVENT_TYPE, SESSION_MESSAGE_TYPE } from "@/shared/protocol/constants";

import { type CallPromptEvent, parseCallPrompt } from "./call-prompt";
import {
    discardSchema,
    doraRevealedSchema,
    drawNoticeSchema,
    drawSchema,
    errorEventSchema,
    furitenSchema,
    gameEndSchema,
    gameStartedSchema,
    meldSchema,
    riichiDeclaredSchema,
    roundStartedSchema,
    turnSchema,
} from "./events";
import { type GameReconnectedEvent, gameReconnectedSchema } from "./reconnect";
import { type RoundEndEvent, parseRoundEnd } from "./round-results";
import { type SessionMessage, parseSessionMessage } from "./session";

// --- Union types ---

export type GameEvent =
    | z.output<typeof gameStartedSchema>
    | z.output<typeof roundStartedSchema>
    | z.output<typeof drawSchema>
    | z.output<typeof drawNoticeSchema>
    | z.output<typeof discardSchema>
    | z.output<typeof meldSchema>
    | z.output<typeof riichiDeclaredSchema>
    | z.output<typeof doraRevealedSchema>
    | z.output<typeof errorEventSchema>
    | z.output<typeof furitenSchema>
    | z.output<typeof gameEndSchema>
    | z.output<typeof turnSchema>
    | CallPromptEvent
    | RoundEndEvent;

export type ParsedServerMessage = GameEvent | SessionMessage | GameReconnectedEvent;

// --- Result tuple type ---

export type ParseResult = [Error, null] | [null, ParsedServerMessage];

// --- Internal game event dispatcher ---

function parseGameEvent(raw: Record<string, unknown>, t: number): GameEvent {
    switch (t) {
        case EVENT_TYPE.MELD: {
            return meldSchema.parse(raw);
        }
        case EVENT_TYPE.DRAW: {
            return drawSchema.parse(raw);
        }
        case EVENT_TYPE.DISCARD: {
            return discardSchema.parse(raw);
        }
        case EVENT_TYPE.CALL_PROMPT: {
            return parseCallPrompt(raw);
        }
        case EVENT_TYPE.ROUND_END: {
            return parseRoundEnd(raw);
        }
        case EVENT_TYPE.RIICHI_DECLARED: {
            return riichiDeclaredSchema.parse(raw);
        }
        case EVENT_TYPE.DORA_REVEALED: {
            return doraRevealedSchema.parse(raw);
        }
        case EVENT_TYPE.ERROR: {
            return errorEventSchema.parse(raw);
        }
        case EVENT_TYPE.GAME_STARTED: {
            return gameStartedSchema.parse(raw);
        }
        case EVENT_TYPE.ROUND_STARTED: {
            return roundStartedSchema.parse(raw);
        }
        case EVENT_TYPE.GAME_END: {
            return gameEndSchema.parse(raw);
        }
        case EVENT_TYPE.FURITEN: {
            return furitenSchema.parse(raw);
        }
        case EVENT_TYPE.TURN: {
            return turnSchema.parse(raw);
        }
        case EVENT_TYPE.DRAW_NOTICE: {
            return drawNoticeSchema.parse(raw);
        }
        default: {
            throw new Error(`Unknown game event type: t=${String(t)}`);
        }
    }
}

// --- Try-parse wrapper ---

function tryParse(raw: Record<string, unknown>): ParsedServerMessage {
    if (typeof raw.type === "string") {
        if (raw.type === SESSION_MESSAGE_TYPE.GAME_RECONNECTED) {
            return gameReconnectedSchema.parse(raw);
        }
        return parseSessionMessage(raw);
    }
    if (typeof raw.t === "number") {
        return parseGameEvent(raw, raw.t);
    }
    throw new Error("Message has neither 'type' (string) nor 't' (number) field");
}

function wrapParseError(raw: Record<string, unknown>, err: unknown): Error {
    const message = err instanceof Error ? err.message : String(err);
    if (typeof raw.t === "number") {
        return new Error(`Failed to parse game event t=${raw.t}: ${message}`, { cause: err });
    }
    if (typeof raw.type === "string") {
        return new Error(`Failed to parse session message type=${raw.type}: ${message}`, {
            cause: err,
        });
    }
    return err instanceof Error ? err : new Error(message);
}

/**
 * The fields the live socket stamps on a message for its recipient alone, by wire key, as parsed: a game start's
 * viewer seat and timer settings, a deal's viewer seat and private hand, and the wait id of a turn or call prompt
 * opening, each with its bank. A replay records none of them.
 */
function liveStamps(message: ParsedServerMessage): readonly (readonly [string, unknown])[] {
    switch (message.type) {
        case "game_started": {
            return [
                ["s", message.seat],
                ["tm", message.timer],
            ];
        }
        case "round_started": {
            return [
                ["s", message.seat],
                ["mt", message.myTiles],
            ];
        }
        case "draw":
        case "call_prompt":
        case "turn": {
            return [
                ["wi", message.waitId],
                ["bk", message.bankSeconds],
            ];
        }
        default: {
            return [];
        }
    }
}

function parseLiveMessage(raw: Record<string, unknown>): ParsedServerMessage {
    const message = tryParse(raw);
    const missing = liveStamps(message).find(([, value]) => value === null);
    if (missing !== undefined) {
        throw new Error(`the live message has no ${missing[0]}, which the server always stamps`);
    }
    return message;
}

function parseResult(
    raw: Record<string, unknown>,
    parse: (raw: Record<string, unknown>) => ParsedServerMessage,
): ParseResult {
    try {
        return [null, parse(raw)];
    } catch (error) {
        return [wrapParseError(raw, error), null];
    }
}

/** Parse a message the live socket sent, complete with what the server stamps for its recipient. */
export function parseServerMessage(raw: Record<string, unknown>): ParseResult {
    return parseResult(raw, parseLiveMessage);
}

/** Parse a message a replay file records, which carries none of the live socket's stamps (`parseReplayLine`). */
export function parseRecordedMessage(raw: Record<string, unknown>): ParseResult {
    return parseResult(raw, tryParse);
}
