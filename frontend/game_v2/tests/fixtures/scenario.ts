import { vi } from "vitest";

import { type WirePayload } from "#tests/fixtures/wire";
import {
    type ClientEffect,
    type LiveClient,
    type LiveEvent,
    startGameClient,
    stepGameClient,
} from "@/entities/client";
import {
    type SessionEffect,
    type SessionInput,
    type SessionState,
    startSession,
    stepSession,
} from "@/entities/session";
import { type HandoffRecovery } from "@/shared/api";
import { type ParsedServerMessage, parseServerMessage } from "@/shared/protocol";
import { type GameSessionData } from "@/shared/session";

export const GAME_ID = "g1";
export const HANDOFF = { gameTicket: "ticket-1", wsUrl: "ws://game/ws/g1" } as const;

interface Step<State, Effect> {
    readonly state: State;
    readonly effects: readonly Effect[];
}

/** Steps a pure transition one input at a time, keeping the state and returning each step's effects. */
export class Scenario<State, Input, Effect> {
    readonly startEffects: readonly Effect[];
    private current: State;
    private readonly transition: (state: State, input: Input) => Step<State, Effect>;

    constructor(
        start: Step<State, Effect>,
        transition: (state: State, input: Input) => Step<State, Effect>,
    ) {
        this.current = start.state;
        this.startEffects = start.effects;
        this.transition = transition;
    }

    get state(): State {
        return this.current;
    }

    step(input: Input): readonly Effect[] {
        const next = this.transition(this.current, input);
        this.current = next.state;
        return next.effects;
    }
}

/** A session begun at 0 from the lobby's handoff, or from none when `handoff` is null. */
export function sessionScenario(
    handoff: GameSessionData | null = HANDOFF,
): Scenario<SessionState, SessionInput, SessionEffect> {
    return new Scenario(startSession(GAME_ID, handoff, 0), stepSession);
}

/** A client begun at 0 from the lobby's handoff, or from none when `handoff` is null. */
export function clientScenario(
    handoff: GameSessionData | null = HANDOFF,
): Scenario<LiveClient, LiveEvent, ClientEffect> {
    return new Scenario(startGameClient(GAME_ID, handoff, 0), stepGameClient);
}

function parsed(raw: WirePayload): ParsedServerMessage {
    const [error, message] = parseServerMessage(raw);
    if (error) {
        throw error;
    }
    return message;
}

export const sessionInput = {
    closed: (at: number, code: number): SessionInput => ({
        at,
        code,
        kind: "transport_closed",
        reason: "",
    }),
    leave: (at: number): SessionInput => ({ at, kind: "leave" }),
    message: (at: number, raw: WirePayload): SessionInput => ({
        at,
        kind: "message",
        message: parsed(raw),
    }),
    opened: (at: number): SessionInput => ({ at, kind: "transport_opened" }),
    recovered: (at: number, recovery: HandoffRecovery): SessionInput => ({
        at,
        kind: "handoff_recovered",
        recovery,
    }),
    tick: (at: number): SessionInput => ({ at, kind: "tick" }),
};

export const clientEvent = {
    closed: (at: number, code: number): LiveEvent => ({
        at,
        code,
        kind: "transport_closed",
        reason: "",
    }),
    confirm: (at: number): LiveEvent => ({
        at,
        intent: { type: "confirm_result" },
        kind: "intent",
    }),
    confirmOpening: (at: number): LiveEvent => ({
        at,
        intent: { type: "confirm_opening" },
        kind: "intent",
    }),
    leave: (at: number): LiveEvent => ({ at, intent: { type: "leave" }, kind: "intent" }),
    message: (at: number, raw: WirePayload): LiveEvent => ({ at, kind: "server_message", raw }),
    opened: (at: number): LiveEvent => ({ at, kind: "transport_opened" }),
    tick: (at: number): LiveEvent => ({ at, kind: "tick" }),
};

function forbidIo(): never {
    throw new Error("the dispatcher ran IO");
}

/**
 * Run `work` with the socket and fetch globals throwing, and the timer, storage and clock functions spied on,
 * the clocks throwing too; return its result and how often each spy was called.
 */
export function forbiddingIo<Result>(work: () => Result): { calls: number[]; result: Result } {
    vi.stubGlobal("WebSocket", forbidIo);
    vi.stubGlobal("fetch", forbidIo);
    const spies = [
        vi.spyOn(globalThis, "setTimeout"),
        vi.spyOn(Storage.prototype, "removeItem"),
        vi.spyOn(Date, "now").mockImplementation(forbidIo),
        vi.spyOn(performance, "now").mockImplementation(forbidIo),
    ];
    try {
        const result = work();
        return { calls: spies.map((spy) => spy.mock.calls.length), result };
    } finally {
        vi.restoreAllMocks();
        vi.unstubAllGlobals();
    }
}
