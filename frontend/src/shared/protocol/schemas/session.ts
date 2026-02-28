// Zod schemas for session messages (string `type` field).
// Six variants: session_error, pong, player_reconnected, chat, player_left, game_left.
// Manual dispatch via parseSessionMessage() since session messages don't share
// a numeric discriminant like game events.

import { z } from "zod";

import { SESSION_MESSAGE_TYPE } from "../constants";

// --- Session Error ---

const sessionErrorSchema = z
    .object({
        code: z.string(),
        message: z.string(),
        type: z.literal(SESSION_MESSAGE_TYPE.ERROR),
    })
    .transform((raw) => ({
        code: raw.code,
        message: raw.message,
        type: "session_error" as const,
    }));

// --- Pong ---

const pongSchema = z
    .object({
        type: z.literal(SESSION_MESSAGE_TYPE.PONG),
    })
    .transform(() => ({
        type: "pong" as const,
    }));

// --- Player Reconnected ---

const playerReconnectedSchema = z
    .object({
        player_name: z.string(),
        type: z.literal(SESSION_MESSAGE_TYPE.PLAYER_RECONNECTED),
    })
    .transform((raw) => ({
        playerName: raw.player_name,
        type: "player_reconnected" as const,
    }));

// --- Chat ---

const sessionChatSchema = z
    .object({
        player_name: z.string(),
        text: z.string(),
        type: z.literal(SESSION_MESSAGE_TYPE.CHAT),
    })
    .transform((raw) => ({
        playerName: raw.player_name,
        text: raw.text,
        type: "chat" as const,
    }));

// --- Player Left ---

const playerLeftSchema = z
    .object({
        player_name: z.string(),
        type: z.literal(SESSION_MESSAGE_TYPE.PLAYER_LEFT),
    })
    .transform((raw) => ({
        playerName: raw.player_name,
        type: "player_left" as const,
    }));

// --- Game Left ---

const gameLeftSchema = z
    .object({
        type: z.literal(SESSION_MESSAGE_TYPE.GAME_LEFT),
    })
    .transform(() => ({
        type: "game_left" as const,
    }));

// --- Dispatch ---

export type SessionErrorMessage = z.output<typeof sessionErrorSchema>;
export type PongMessage = z.output<typeof pongSchema>;
export type PlayerReconnectedMessage = z.output<typeof playerReconnectedSchema>;
export type SessionChatMessage = z.output<typeof sessionChatSchema>;
export type PlayerLeftMessage = z.output<typeof playerLeftSchema>;
export type GameLeftMessage = z.output<typeof gameLeftSchema>;

export type SessionMessage =
    | SessionErrorMessage
    | PongMessage
    | PlayerReconnectedMessage
    | SessionChatMessage
    | PlayerLeftMessage
    | GameLeftMessage;

export function parseSessionMessage(raw: Record<string, unknown>): SessionMessage {
    const { type } = raw;
    switch (type) {
        case SESSION_MESSAGE_TYPE.ERROR:
            return sessionErrorSchema.parse(raw);
        case SESSION_MESSAGE_TYPE.PONG:
            return pongSchema.parse(raw);
        case SESSION_MESSAGE_TYPE.PLAYER_RECONNECTED:
            return playerReconnectedSchema.parse(raw);
        case SESSION_MESSAGE_TYPE.CHAT:
            return sessionChatSchema.parse(raw);
        case SESSION_MESSAGE_TYPE.PLAYER_LEFT:
            return playerLeftSchema.parse(raw);
        case SESSION_MESSAGE_TYPE.GAME_LEFT:
            return gameLeftSchema.parse(raw);
        default:
            throw new Error(`Unknown session message type: type=${String(type)}`);
    }
}
