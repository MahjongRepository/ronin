import { describe, expect, it } from "vitest";

import { SESSION_MESSAGE_TYPE } from "@/shared/protocol/constants";
import { gameReconnectedSchema } from "@/shared/protocol/schemas/reconnect";

// Realistic reconnection payload matching the wire format from
// backend/game/session/manager.py:642-644 (ReconnectionSnapshot with aliases + injected type).
function makeReconnectPayload(overrides?: Record<string, unknown>): Record<string, unknown> {
    return {
        cp: 2,
        dc: [3, 5],
        dd: [
            [1, 4],
            [2, 6],
        ],
        di: [45, 67],
        dl: 0,
        gid: "game-abc-123",
        h: 1,
        mt: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48],
        n: 2,
        p: [
            { ai: 0, nm: "Alice", s: 0 },
            { ai: 0, nm: "Bob", s: 1 },
            { ai: 1, nm: "CPU-1", s: 2 },
            { ai: 1, nm: "CPU-2", s: 3 },
        ],
        pst: [
            {
                dsc: [{ rd: false, tg: true, ti: 50 }, { ti: 55 }],
                ml: [],
                ri: false,
                s: 0,
                sc: 250,
            },
            {
                dsc: [{ rd: true, tg: false, ti: 100 }],
                ml: [6080],
                ri: true,
                s: 1,
                sc: 240,
            },
            {
                dsc: [],
                ml: [],
                ri: false,
                s: 2,
                sc: 260,
            },
            {
                dsc: [],
                ml: [],
                ri: false,
                s: 3,
                sc: 250,
            },
        ],
        r: 1,
        s: 0,
        tr: 52,
        type: SESSION_MESSAGE_TYPE.GAME_RECONNECTED,
        w: 0,
        ...overrides,
    };
}

function parsePayload(overrides?: Record<string, unknown>) {
    return gameReconnectedSchema.parse(makeReconnectPayload(overrides));
}

describe("gameReconnectedSchema", () => {
    it("parses game and round metadata", () => {
        const result = parsePayload();

        expect(result.type).toBe("game_reconnected");
        expect(result.gameId).toBe("game-abc-123");
        expect(result.currentPlayerSeat).toBe(2);
        expect(result.dealerSeat).toBe(0);
        expect(result.roundNumber).toBe(2);
        expect(result.wind).toBe(0);
    });

    it("parses sticks, tiles remaining, and seat info", () => {
        const result = parsePayload();

        expect(result.honbaSticks).toBe(1);
        expect(result.riichiSticks).toBe(1);
        expect(result.tilesRemaining).toBe(52);
        expect(result.seat).toBe(0);
        expect(result.myTiles).toHaveLength(13);
    });

    it("parses dice and dora indicators", () => {
        const result = parsePayload();

        expect(result.dice).toEqual([3, 5]);
        expect(result.dealerDice).toEqual([
            [1, 4],
            [2, 6],
        ]);
        expect(result.doraIndicators).toEqual([45, 67]);
    });

    it("transforms wire scores (divide by 100 reversed)", () => {
        const { playerStates } = parsePayload();
        const [s0, s1, s2] = playerStates;

        expect(s0.score).toBe(25000);
        expect(s1.score).toBe(24000);
        expect(s2.score).toBe(26000);
    });

    it("parses player info with ai integer to boolean conversion", () => {
        const { players } = parsePayload();
        const [human, , ai] = players;

        expect(players).toHaveLength(4);
        expect(human).toEqual({ isAiPlayer: false, name: "Alice", seat: 0 });
        expect(ai).toEqual({ isAiPlayer: true, name: "CPU-1", seat: 2 });
    });

    it("parses player 0 state with discards (not riichi)", () => {
        const { playerStates } = parsePayload();
        const [state0] = playerStates;

        expect(state0.seat).toBe(0);
        expect(state0.isRiichi).toBe(false);
        expect(state0.melds).toEqual([]);
        expect(state0.discards).toEqual([
            { isRiichiDiscard: false, isTsumogiri: true, tileId: 50 },
            { isRiichiDiscard: false, isTsumogiri: false, tileId: 55 },
        ]);
    });

    it("parses player 1 state with riichi and meld", () => {
        const { playerStates } = parsePayload();
        const [, state1] = playerStates;

        expect(state1.seat).toBe(1);
        expect(state1.isRiichi).toBe(true);
        expect(state1.melds).toEqual([6080]);
        expect(state1.discards).toEqual([
            { isRiichiDiscard: true, isTsumogiri: false, tileId: 100 },
        ]);
    });

    it("defaults discard booleans to false when omitted", () => {
        const { playerStates } = parsePayload();
        const [{ discards }] = playerStates;
        const [, secondDiscard] = discards;

        expect(secondDiscard.isRiichiDiscard).toBe(false);
        expect(secondDiscard.isTsumogiri).toBe(false);
    });

    it("parses empty player states (no discards, no melds)", () => {
        const { playerStates } = parsePayload();
        const [, , state2] = playerStates;

        expect(state2.discards).toEqual([]);
        expect(state2.melds).toEqual([]);
        expect(state2.isRiichi).toBe(false);
    });
});
