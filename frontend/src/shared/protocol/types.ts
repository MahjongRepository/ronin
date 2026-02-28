// Re-exports of Zod-inferred types from all schema files.

import { type z } from "zod";

import {
    type discardSchema,
    type doraRevealedSchema,
    type drawSchema,
    type errorEventSchema,
    type furitenSchema,
    type gameEndSchema,
    type gameStartedSchema,
    type meldSchema,
    type riichiDeclaredSchema,
    type roundStartedSchema,
} from "./schemas/events";

// --- Game event types ---

export type GameStartedEvent = z.output<typeof gameStartedSchema>;
export type RoundStartedEvent = z.output<typeof roundStartedSchema>;
export type DrawEvent = z.output<typeof drawSchema>;
export type DiscardEvent = z.output<typeof discardSchema>;
export type MeldEvent = z.output<typeof meldSchema>;
export type RiichiDeclaredEvent = z.output<typeof riichiDeclaredSchema>;
export type DoraRevealedEvent = z.output<typeof doraRevealedSchema>;
export type ErrorEvent = z.output<typeof errorEventSchema>;
export type FuritenEvent = z.output<typeof furitenSchema>;
export type GameEndEvent = z.output<typeof gameEndSchema>;

// --- Call prompt types ---

export type {
    CallPromptEvent,
    ChankanPromptEvent,
    MeldPromptEvent,
    RonPromptEvent,
} from "./schemas/call-prompt";

// --- Round end types ---

export type {
    AbortiveDrawRoundEnd,
    DoubleRonRoundEnd,
    ExhaustiveDrawRoundEnd,
    NagashiManganRoundEnd,
    RonRoundEnd,
    RoundEndEvent,
    TsumoRoundEnd,
} from "./schemas/round-results";

// --- Session message types ---

export type {
    GameLeftMessage,
    PlayerLeftMessage,
    PlayerReconnectedMessage,
    PongMessage,
    SessionChatMessage,
    SessionErrorMessage,
    SessionMessage,
} from "./schemas/session";

// --- Reconnection types ---

export type { GameReconnectedEvent } from "./schemas/reconnect";

// --- Aggregate types ---

export type { GameEvent, ParsedServerMessage, ParseResult } from "./schemas/message";
