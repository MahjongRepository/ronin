import { describe, expect, it } from "vitest";

import {
    ABORTIVE_DRAW_TYPE,
    ROUND_RESULT_TYPE,
    SESSION_MESSAGE_TYPE,
} from "@/shared/protocol/constants";
import { gameReconnectedSchema } from "@/shared/protocol/schemas/reconnect";

const FINISHED_ROUND = {
    dl: 0,
    h: 0,
    ps: [],
    rs: [],
    rt: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
    sch: { "0": 0, "1": 0, "2": 0, "3": 0 },
    w: 0,
    ws: [],
};

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
        f: true,
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
                tc: 13,
            },
            {
                dsc: [{ rd: true, tg: false, ti: 100 }],
                ml: [6081],
                ri: true,
                s: 1,
                sc: 240,
                tc: 10,
            },
            {
                dsc: [],
                ml: [],
                ri: false,
                s: 2,
                sc: 260,
                tc: 13,
            },
            {
                dsc: [],
                ml: [],
                ri: false,
                s: 3,
                sc: 250,
                tc: 13,
            },
        ],
        r: 1,
        rc: 20,
        rh: [FINISHED_ROUND, FINISHED_ROUND],
        rsv: 15,
        s: 0,
        tm: { bk: 20, gp: 3, mb: 60, md: 5, ra: 15, rb: 10, tb: 5 },
        tr: 52,
        type: SESSION_MESSAGE_TYPE.GAME_RECONNECTED,
        w: 0,
        wi: 9,
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
        expect(result.waitId).toBe(9);
        expect(result.roundResult).toBeNull();
        expect(result.confirmationOwed).toBe(false);
    });

    it("parses sticks, the riichi cost and stick value, tiles remaining, seat info and the seat's furiten", () => {
        const result = parsePayload();

        expect(result.honbaSticks).toBe(1);
        expect(result.riichiSticks).toBe(1);
        expect([result.riichiCost, result.riichiStickValue]).toEqual([2000, 1500]);
        expect(result.tilesRemaining).toBe(52);
        expect(result.seat).toBe(0);
        expect(result.myTiles).toHaveLength(13);
        expect(result.isFuriten).toBe(true);
        expect(result.playerStates.map((state) => state.tileCount)).toEqual([13, 10, 13, 13]);
        expect(result.timer.bankSeconds).toBe(20);
    });

    it("reads a round advance's result, owed confirmation and the finished rounds' ledger", () => {
        const result = parsePayload({
            el: 4.5,
            n: 1,
            oc: true,
            re: {
                rn: ABORTIVE_DRAW_TYPE.FOUR_WINDS,
                rt: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
                sch: { "0": 0, "1": 0, "2": 0, "3": 0 },
                scs: { "0": 250, "1": 240, "2": 260, "3": 250 },
            },
            rh: [
                {
                    dl: 0,
                    h: 0,
                    ls: 2,
                    ps: [3],
                    rs: [1],
                    rt: 1,
                    sch: { "0": 39, "1": 0, "2": -39, "3": 0 },
                    w: 0,
                    ws: [0],
                },
                {
                    dl: 1,
                    h: 0,
                    ps: [],
                    rn: "four_winds",
                    rs: [],
                    rt: 4,
                    sch: { "0": 0, "1": 0, "2": 0, "3": 0 },
                    w: 0,
                    ws: [],
                },
            ],
        });

        expect(result.confirmationOwed).toBe(true);
        expect(result.elapsedSeconds).toBe(4.5);
        expect(result.roundResult).toMatchObject({
            reason: ABORTIVE_DRAW_TYPE.FOUR_WINDS,
            resultType: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
            type: "round_end",
        });
        expect(result.roundHistory).toEqual([
            {
                abortiveReason: null,
                dealerSeat: 0,
                honbaSticks: 0,
                loserSeat: 2,
                paoSeats: [3],
                resultType: ROUND_RESULT_TYPE.RON,
                riichiSeats: [1],
                scoreChanges: { "0": 3900, "1": 0, "2": -3900, "3": 0 },
                tenpaiSeats: null,
                wind: 0,
                winnerSeats: [0],
            },
            {
                abortiveReason: ABORTIVE_DRAW_TYPE.FOUR_WINDS,
                dealerSeat: 1,
                honbaSticks: 0,
                loserSeat: null,
                paoSeats: [],
                resultType: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
                riichiSeats: [],
                scoreChanges: { "0": 0, "1": 0, "2": 0, "3": 0 },
                tenpaiSeats: null,
                wind: 0,
                winnerSeats: [],
            },
        ]);
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

        expect(s0.score).toBe(25_000);
        expect(s1.score).toBe(24_000);
        expect(s2.score).toBe(26_000);
    });

    it("parses player info with ai integer to boolean conversion", () => {
        const { players } = parsePayload();
        const [human, , ai] = players;

        expect(players).toHaveLength(4);
        expect(human).toEqual({ aiStandIn: null, isAiPlayer: false, name: "Alice", seat: 0 });
        expect(ai).toEqual({ aiStandIn: null, isAiPlayer: true, name: "CPU-1", seat: 2 });
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
        expect(state1.melds).toEqual([6081]);
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

describe("gameReconnectedSchema - latest discard", () => {
    it("reads the latest discard's seat, none when ld is absent, and refuses a null the server never sends", () => {
        expect(parsePayload({ ld: 1 }).latestDiscardSeat).toBe(1);
        expect(parsePayload().latestDiscardSeat).toBeNull();
        expect(() => parsePayload({ ld: null })).toThrow();
    });
});
