// Top-level message parser that routes incoming wire messages
// to the correct schema based on discriminator fields.
// String `type` field -> session/reconnect messages.
// Integer `t` field -> game events.

import { type z } from "zod";

import { EVENT_TYPE, SESSION_MESSAGE_TYPE } from "../constants";
import { type CallPromptEvent, parseCallPrompt } from "./call-prompt";
import {
    discardSchema,
    doraRevealedSchema,
    drawSchema,
    errorEventSchema,
    furitenSchema,
    gameEndSchema,
    gameStartedSchema,
    meldSchema,
    riichiDeclaredSchema,
    roundStartedSchema,
} from "./events";
import { type GameReconnectedEvent, gameReconnectedSchema } from "./reconnect";
import { type RoundEndEvent, parseRoundEnd } from "./round-results";
import { type SessionMessage, parseSessionMessage } from "./session";

// --- Union types ---

export type GameEvent =
    | z.output<typeof gameStartedSchema>
    | z.output<typeof roundStartedSchema>
    | z.output<typeof drawSchema>
    | z.output<typeof discardSchema>
    | z.output<typeof meldSchema>
    | z.output<typeof riichiDeclaredSchema>
    | z.output<typeof doraRevealedSchema>
    | z.output<typeof errorEventSchema>
    | z.output<typeof furitenSchema>
    | z.output<typeof gameEndSchema>
    | CallPromptEvent
    | RoundEndEvent;

export type ParsedServerMessage = GameEvent | SessionMessage | GameReconnectedEvent;

// --- Result tuple type ---

export type ParseResult = [Error, null] | [null, ParsedServerMessage];

// --- Internal game event dispatcher ---

function parseGameEvent(raw: Record<string, unknown>): GameEvent {
    const t = raw.t as number;
    switch (t) {
        case EVENT_TYPE.MELD:
            return meldSchema.parse(raw);
        case EVENT_TYPE.DRAW:
            return drawSchema.parse(raw);
        case EVENT_TYPE.DISCARD:
            return discardSchema.parse(raw);
        case EVENT_TYPE.CALL_PROMPT:
            return parseCallPrompt(raw);
        case EVENT_TYPE.ROUND_END:
            return parseRoundEnd(raw);
        case EVENT_TYPE.RIICHI_DECLARED:
            return riichiDeclaredSchema.parse(raw);
        case EVENT_TYPE.DORA_REVEALED:
            return doraRevealedSchema.parse(raw);
        case EVENT_TYPE.ERROR:
            return errorEventSchema.parse(raw);
        case EVENT_TYPE.GAME_STARTED:
            return gameStartedSchema.parse(raw);
        case EVENT_TYPE.ROUND_STARTED:
            return roundStartedSchema.parse(raw);
        case EVENT_TYPE.GAME_END:
            return gameEndSchema.parse(raw);
        case EVENT_TYPE.FURITEN:
            return furitenSchema.parse(raw);
        default:
            throw new Error(`Unknown game event type: t=${String(t)}`);
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
        return parseGameEvent(raw);
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

// --- Public API ---

export function parseServerMessage(raw: Record<string, unknown>): ParseResult {
    try {
        return [null, tryParse(raw)];
    } catch (err) {
        return [wrapParseError(raw, err), null];
    }
}
