import { describe, expect, it } from "vitest";

import { WIRE_KEY } from "@/shared/protocol";
import {
    ABORTIVE_DRAW_TYPE,
    ROUND_RESULT_TYPE,
    SESSION_MESSAGE_TYPE,
} from "@/shared/protocol/constants";
import { gameReconnectedSchema } from "@/shared/protocol/schemas/reconnect";

/** Seat 1's added kan of 1p from seat 3: 38 called, 39 added from hand. */
const ADDED_KAN_OF_1P = 22_457;

const FINISHED_ROUND = {
    [WIRE_KEY.DEALER]: 0,
    [WIRE_KEY.HONBA]: 0,
    [WIRE_KEY.PAO_SEAT]: [],
    [WIRE_KEY.RIICHI_SEATS]: [],
    [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
    [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 0, "3": 0 },
    [WIRE_KEY.WIND]: 0,
    [WIRE_KEY.WINNER_SEAT]: [],
};

function makeReconnectPayload(overrides?: Record<string, unknown>): Record<string, unknown> {
    return {
        [WIRE_KEY.CURRENT_PLAYER]: 2,
        [WIRE_KEY.DICE]: [3, 5],
        [WIRE_KEY.DEALER_DICE]: [
            [1, 4],
            [2, 6],
        ],
        [WIRE_KEY.DORA_INDICATORS]: [45, 67],
        [WIRE_KEY.DEALER]: 0,
        [WIRE_KEY.FURITEN]: true,
        [WIRE_KEY.FIRST_DEALER]: 3,
        [WIRE_KEY.GAME_ID]: "game-abc-123",
        [WIRE_KEY.HONBA]: 1,
        [WIRE_KEY.MY_TILES]: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48],
        [WIRE_KEY.ROUND_NUMBER]: 2,
        [WIRE_KEY.PLAYERS]: [
            { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: "Alice", [WIRE_KEY.SEAT]: 0 },
            { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: "Bob", [WIRE_KEY.SEAT]: 1 },
            { [WIRE_KEY.AI_PLAYER]: 1, [WIRE_KEY.NAME]: "CPU-1", [WIRE_KEY.SEAT]: 2 },
            { [WIRE_KEY.AI_PLAYER]: 1, [WIRE_KEY.NAME]: "CPU-2", [WIRE_KEY.SEAT]: 3 },
        ],
        [WIRE_KEY.PLAYER_STATES]: [
            {
                [WIRE_KEY.DISCARDS]: [
                    {
                        [WIRE_KEY.RIICHI_DISCARD]: false,
                        [WIRE_KEY.TSUMOGIRI]: true,
                        [WIRE_KEY.TILE_ID]: 50,
                    },
                    { [WIRE_KEY.TILE_ID]: 55 },
                ],
                [WIRE_KEY.MELDS]: [],
                [WIRE_KEY.IS_RIICHI]: false,
                [WIRE_KEY.SEAT]: 0,
                [WIRE_KEY.SCORE]: 250,
                [WIRE_KEY.TILE_COUNT]: 13,
            },
            {
                [WIRE_KEY.DISCARDS]: [
                    {
                        [WIRE_KEY.RIICHI_DISCARD]: true,
                        [WIRE_KEY.TSUMOGIRI]: false,
                        [WIRE_KEY.TILE_ID]: 100,
                    },
                ],
                [WIRE_KEY.MELDS]: [ADDED_KAN_OF_1P],
                [WIRE_KEY.IS_RIICHI]: true,
                [WIRE_KEY.SEAT]: 1,
                [WIRE_KEY.SCORE]: 240,
                [WIRE_KEY.TILE_COUNT]: 10,
            },
            {
                [WIRE_KEY.DISCARDS]: [],
                [WIRE_KEY.MELDS]: [],
                [WIRE_KEY.IS_RIICHI]: false,
                [WIRE_KEY.SEAT]: 2,
                [WIRE_KEY.SCORE]: 260,
                [WIRE_KEY.TILE_COUNT]: 13,
            },
            {
                [WIRE_KEY.DISCARDS]: [],
                [WIRE_KEY.MELDS]: [],
                [WIRE_KEY.IS_RIICHI]: false,
                [WIRE_KEY.SEAT]: 3,
                [WIRE_KEY.SCORE]: 250,
                [WIRE_KEY.TILE_COUNT]: 13,
            },
        ],
        [WIRE_KEY.RIICHI_STICKS]: 1,
        [WIRE_KEY.ROUND_HISTORY]: [FINISHED_ROUND, FINISHED_ROUND],
        [WIRE_KEY.RIICHI_STICK_VALUE]: 15,
        [WIRE_KEY.ROUND_IN_WIND]: 2,
        [WIRE_KEY.SEAT]: 0,
        [WIRE_KEY.TIMER_SETTINGS]: {
            [WIRE_KEY.BANK_SECONDS]: 20,
            [WIRE_KEY.GAME_START_PAUSE]: 3,
            [WIRE_KEY.MAX_BANK_SECONDS]: 20,
            [WIRE_KEY.ROUND_ADVANCE_TIMEOUT]: 15,
            [WIRE_KEY.BASE_TURN_SECONDS]: 5,
        },
        [WIRE_KEY.TILES_REMAINING]: 52,
        [WIRE_KEY.SESSION_TYPE]: SESSION_MESSAGE_TYPE.GAME_RECONNECTED,
        [WIRE_KEY.WIND]: 0,
        [WIRE_KEY.WAIT_ID]: 9,
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
        expect([result.wind, result.roundInWind, result.firstDealerSeat]).toEqual([0, 2, 3]);
        expect(result.waitId).toBe(9);
        expect(result.roundResult).toBeNull();
        expect(result.confirmationOwed).toBe(false);
    });

    it("parses sticks, the riichi stick value, tiles remaining, seat info and the seat's furiten", () => {
        const result = parsePayload();

        expect(result.honbaSticks).toBe(1);
        expect(result.riichiSticks).toBe(1);
        expect(result.riichiStickValue).toBe(1500);
        expect(result.tilesRemaining).toBe(52);
        expect(result.seat).toBe(0);
        expect(result.myTiles).toHaveLength(13);
        expect(result.isFuriten).toBe(true);
        expect(result.playerStates.map((state) => state.tileCount)).toEqual([13, 10, 13, 13]);
        expect(result.timer.bankSeconds).toBe(20);
    });

    it("reads a round advance's result, owed confirmation, its timer and the finished rounds' ledger", () => {
        const result = parsePayload({
            [WIRE_KEY.ROUND_ADVANCE_SECONDS]: 20,
            [WIRE_KEY.WAIT_ELAPSED]: 4.5,
            [WIRE_KEY.ROUND_NUMBER]: 1,
            [WIRE_KEY.CONFIRMATION_OWED]: true,
            [WIRE_KEY.ROUND_RESULT]: {
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 1,
                [WIRE_KEY.RIICHI_STICKS]: 1,
                [WIRE_KEY.ABORTIVE_REASON]: ABORTIVE_DRAW_TYPE.FOUR_WINDS,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 0, "3": 0 },
                [WIRE_KEY.SCORES]: { "0": 250, "1": 240, "2": 260, "3": 250 },
            },
            [WIRE_KEY.ROUND_HISTORY]: [
                {
                    [WIRE_KEY.DEALER]: 0,
                    [WIRE_KEY.HONBA]: 0,
                    [WIRE_KEY.LOSER_SEAT]: 2,
                    [WIRE_KEY.PAO_SEAT]: [3],
                    [WIRE_KEY.RIICHI_SEATS]: [1],
                    [WIRE_KEY.RESULT_TYPE]: 1,
                    [WIRE_KEY.SCORE_CHANGES]: { "0": 39, "1": 0, "2": -39, "3": 0 },
                    [WIRE_KEY.WIND]: 0,
                    [WIRE_KEY.WINNER_SEAT]: [0],
                },
                {
                    [WIRE_KEY.DEALER]: 1,
                    [WIRE_KEY.HONBA]: 0,
                    [WIRE_KEY.PAO_SEAT]: [],
                    [WIRE_KEY.ABORTIVE_REASON]: "four_winds",
                    [WIRE_KEY.RIICHI_SEATS]: [],
                    [WIRE_KEY.RESULT_TYPE]: 4,
                    [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 0, "3": 0 },
                    [WIRE_KEY.WIND]: 0,
                    [WIRE_KEY.WINNER_SEAT]: [],
                },
            ],
        });

        expect(result.confirmationOwed).toBe(true);
        expect(result.advanceTimer).toEqual({ elapsedSeconds: 4.5, seconds: 20 });
        expect(result.roundResult).toMatchObject({
            reason: ABORTIVE_DRAW_TYPE.FOUR_WINDS,
            resultType: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
            riichiSticks: 1,
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

    it("parses the dealer dice and dora indicators", () => {
        const result = parsePayload();

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
        expect(state1.melds).toEqual([
            {
                addedTileId: 39,
                calledTileId: 38,
                callerSeat: 1,
                fromSeat: 3,
                meldType: "added_kan",
                tileIds: [36, 37, 38, 39],
            },
        ]);
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
        expect(parsePayload({ [WIRE_KEY.LATEST_DISCARD_SEAT]: 1 }).latestDiscardSeat).toBe(1);
        expect(parsePayload().latestDiscardSeat).toBeNull();
        expect(() => parsePayload({ [WIRE_KEY.LATEST_DISCARD_SEAT]: null })).toThrow();
    });
});
