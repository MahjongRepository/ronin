import { type z } from "zod/mini";

import { type timerSettingsSchema } from "./schemas/common";
import {
    type discardSchema,
    type doraRevealedSchema,
    type drawNoticeSchema,
    type drawSchema,
    type errorEventSchema,
    type furitenSchema,
    type gameEndSchema,
    type gameStartedSchema,
    type meldSchema,
    type riichiDeclaredSchema,
    type roundStartedSchema,
    type turnSchema,
} from "./schemas/events";

// --- Game event types ---

export type GameStartedEvent = z.output<typeof gameStartedSchema>;
export type RoundStartedEvent = z.output<typeof roundStartedSchema>;
export type DrawEvent = z.output<typeof drawSchema>;
export type DrawNoticeEvent = z.output<typeof drawNoticeSchema>;
export type DiscardEvent = z.output<typeof discardSchema>;
export type MeldEvent = z.output<typeof meldSchema>;
/** A meld on another seat's tile, which names that seat and tile: every meld but a closed kan. */
export type ClaimedMeldEvent = Exclude<MeldEvent, { meldType: "closed_kan" }>;
export type RiichiDeclaredEvent = z.output<typeof riichiDeclaredSchema>;
export type DoraRevealedEvent = z.output<typeof doraRevealedSchema>;
export type ErrorEvent = z.output<typeof errorEventSchema>;
export type FuritenEvent = z.output<typeof furitenSchema>;
export type GameEndEvent = z.output<typeof gameEndSchema>;
export type TurnEvent = z.output<typeof turnSchema>;
export type TimerSettings = z.output<typeof timerSettingsSchema>;

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
    PaoLiability,
    RonRoundEnd,
    RoundEndEvent,
    TsumoRoundEnd,
} from "./schemas/round-results";

// --- Session message types ---

export type { SeatControlMessage, SessionErrorMessage, SessionMessage } from "./schemas/session";

// --- Reconnection types ---

export type { GameReconnectedEvent } from "./schemas/reconnect";

// --- Aggregate types ---

export type { GameEvent, ParsedServerMessage, ParseResult } from "./schemas/message";
