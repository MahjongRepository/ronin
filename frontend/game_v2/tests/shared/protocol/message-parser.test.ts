import { describe, expect, it } from "vitest";

import { WIRE_KEY } from "@/shared/protocol";
import { EVENT_TYPE, SESSION_MESSAGE_TYPE } from "@/shared/protocol/constants";
import { parseServerMessage } from "@/shared/protocol/schemas/message";

const LIVE_GAME_STARTED = {
    [WIRE_KEY.DEALER_DICE]: [
        [1, 2],
        [3, 4],
    ],
    [WIRE_KEY.DEALER]: 0,
    [WIRE_KEY.GAME_ID]: "g-abc",
    [WIRE_KEY.GAME_TYPE]: 0,
    [WIRE_KEY.PLAYERS]: [0, 1, 2, 3].map((seat) => ({
        [WIRE_KEY.AI_PLAYER]: 0,
        [WIRE_KEY.NAME]: `P${seat}`,
        [WIRE_KEY.SEAT]: seat,
    })),
    [WIRE_KEY.RIICHI_STICK_VALUE]: 10,
    [WIRE_KEY.SEAT]: 0,
    [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.GAME_STARTED,
    [WIRE_KEY.TIMER_SETTINGS]: {
        [WIRE_KEY.BANK_SECONDS]: 20,
        [WIRE_KEY.GAME_START_PAUSE]: 3,
        [WIRE_KEY.MAX_BANK_SECONDS]: 20,
        [WIRE_KEY.ROUND_ADVANCE_TIMEOUT]: 15,
        [WIRE_KEY.BASE_TURN_SECONDS]: 5,
    },
};

const LIVE_ROUND_STARTED = {
    [WIRE_KEY.CURRENT_PLAYER]: 0,
    [WIRE_KEY.DORA_INDICATORS]: [10],
    [WIRE_KEY.DEALER]: 0,
    [WIRE_KEY.HONBA]: 0,
    [WIRE_KEY.MY_TILES]: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    [WIRE_KEY.ROUND_NUMBER]: 0,
    [WIRE_KEY.PLAYERS]: [0, 1, 2, 3].map((seat) => ({
        [WIRE_KEY.SEAT]: seat,
        [WIRE_KEY.SCORE]: 250,
    })),
    [WIRE_KEY.RIICHI_STICKS]: 0,
    [WIRE_KEY.ROUND_IN_WIND]: 1,
    [WIRE_KEY.SEAT]: 0,
    [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_STARTED,
    [WIRE_KEY.TILES_REMAINING]: 70,
    [WIRE_KEY.WIND]: 0,
};

describe("parseServerMessage", () => {
    describe("session messages (string type field)", () => {
        it("parses a session error message", () => {
            const raw = {
                [WIRE_KEY.SESSION_ERROR_CODE]: "invalid_ticket",
                [WIRE_KEY.SESSION_ERROR_MESSAGE]: "Ticket expired",
                [WIRE_KEY.SESSION_TYPE]: SESSION_MESSAGE_TYPE.ERROR,
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({
                code: "invalid_ticket",
                message: "Ticket expired",
                type: "session_error",
                waitId: null,
            });
        });

        it("parses a game_reconnected message", () => {
            const raw = {
                [WIRE_KEY.CURRENT_PLAYER]: 2,
                [WIRE_KEY.DICE]: [3, 5],
                [WIRE_KEY.DEALER_DICE]: [
                    [3, 5],
                    [2, 4],
                ],
                [WIRE_KEY.DORA_INDICATORS]: [10],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.FURITEN]: false,
                [WIRE_KEY.FIRST_DEALER]: 0,
                [WIRE_KEY.GAME_ID]: "game-123",
                [WIRE_KEY.HONBA]: 0,
                [WIRE_KEY.MY_TILES]: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                [WIRE_KEY.ROUND_NUMBER]: 0,
                [WIRE_KEY.PLAYERS]: [
                    { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: "Alice", [WIRE_KEY.SEAT]: 0 },
                    { [WIRE_KEY.AI_PLAYER]: 1, [WIRE_KEY.NAME]: "Bot1", [WIRE_KEY.SEAT]: 1 },
                    { [WIRE_KEY.AI_PLAYER]: 1, [WIRE_KEY.NAME]: "Bot2", [WIRE_KEY.SEAT]: 2 },
                    { [WIRE_KEY.AI_PLAYER]: 1, [WIRE_KEY.NAME]: "Bot3", [WIRE_KEY.SEAT]: 3 },
                ],
                [WIRE_KEY.PLAYER_STATES]: [
                    {
                        [WIRE_KEY.DISCARDS]: [],
                        [WIRE_KEY.MELDS]: [],
                        [WIRE_KEY.IS_RIICHI]: false,
                        [WIRE_KEY.SEAT]: 0,
                        [WIRE_KEY.SCORE]: 250,
                        [WIRE_KEY.TILE_COUNT]: 13,
                    },
                    {
                        [WIRE_KEY.DISCARDS]: [
                            { [WIRE_KEY.TSUMOGIRI]: true, [WIRE_KEY.TILE_ID]: 50 },
                        ],
                        [WIRE_KEY.MELDS]: [101],
                        [WIRE_KEY.IS_RIICHI]: false,
                        [WIRE_KEY.SEAT]: 1,
                        [WIRE_KEY.SCORE]: 250,
                        [WIRE_KEY.TILE_COUNT]: 10,
                    },
                    {
                        [WIRE_KEY.DISCARDS]: [],
                        [WIRE_KEY.MELDS]: [],
                        [WIRE_KEY.IS_RIICHI]: false,
                        [WIRE_KEY.SEAT]: 2,
                        [WIRE_KEY.SCORE]: 250,
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
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.ROUND_HISTORY]: [],
                [WIRE_KEY.RIICHI_STICK_VALUE]: 10,
                [WIRE_KEY.ROUND_IN_WIND]: 1,
                [WIRE_KEY.SEAT]: 0,
                [WIRE_KEY.TIMER_SETTINGS]: {
                    [WIRE_KEY.BANK_SECONDS]: 20,
                    [WIRE_KEY.GAME_START_PAUSE]: 3,
                    [WIRE_KEY.MAX_BANK_SECONDS]: 20,
                    [WIRE_KEY.ROUND_ADVANCE_TIMEOUT]: 15,
                    [WIRE_KEY.BASE_TURN_SECONDS]: 5,
                },
                [WIRE_KEY.TILES_REMAINING]: 60,
                [WIRE_KEY.SESSION_TYPE]: SESSION_MESSAGE_TYPE.GAME_RECONNECTED,
                [WIRE_KEY.WIND]: 0,
                [WIRE_KEY.WAIT_ID]: 12,
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed!.type).toBe("game_reconnected");
        });
    });

    describe("game events (integer t field)", () => {
        it("parses a draw event", () => {
            // seat=0, tileId=5 -> d = 0*136 + 5 = 5
            const raw = {
                [WIRE_KEY.BANK_SECONDS]: 20,
                [WIRE_KEY.PACKED_MOVE]: 5,
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DRAW,
                [WIRE_KEY.WAIT_ID]: 3,
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({
                availableActions: [],
                bankSeconds: 20,
                elapsedSeconds: null,
                seat: 0,
                source: "live",
                tileId: 5,
                type: "draw",
                waitId: 3,
            });
        });

        it("parses a turn event", () => {
            const raw = {
                [WIRE_KEY.BANK_SECONDS]: 20,
                [WIRE_KEY.KUIKAE_TILES]: [3],
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.TURN,
                [WIRE_KEY.WAIT_ID]: 5,
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toMatchObject({ kuikaeTileTypes: [3], type: "turn", waitId: 5 });
        });

        it("parses a discard event", () => {
            // plain discard: seat=1, tileId=10 -> d = 0*544 + 1*136 + 10 = 146
            const raw = { [WIRE_KEY.PACKED_MOVE]: 146, [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DISCARD };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({
                isRiichi: false,
                isTsumogiri: false,
                seat: 1,
                tileId: 10,
                type: "discard",
            });
        });

        it("parses a game_started event", () => {
            const raw = {
                [WIRE_KEY.DEALER_DICE]: [
                    [1, 2],
                    [3, 4],
                ],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.GAME_ID]: "g-abc",
                [WIRE_KEY.GAME_TYPE]: 0,
                [WIRE_KEY.PLAYERS]: [
                    { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: "Alice", [WIRE_KEY.SEAT]: 0 },
                    { [WIRE_KEY.AI_PLAYER]: 1, [WIRE_KEY.NAME]: "Bot", [WIRE_KEY.SEAT]: 1 },
                    { [WIRE_KEY.AI_PLAYER]: 1, [WIRE_KEY.NAME]: "Bot2", [WIRE_KEY.SEAT]: 2 },
                    { [WIRE_KEY.AI_PLAYER]: 1, [WIRE_KEY.NAME]: "Bot3", [WIRE_KEY.SEAT]: 3 },
                ],
                [WIRE_KEY.RIICHI_STICK_VALUE]: 10,
                [WIRE_KEY.SEAT]: 0,
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.GAME_STARTED,
                [WIRE_KEY.TIMER_SETTINGS]: {
                    [WIRE_KEY.BANK_SECONDS]: 20,
                    [WIRE_KEY.GAME_START_PAUSE]: 3,
                    [WIRE_KEY.MAX_BANK_SECONDS]: 20,
                    [WIRE_KEY.ROUND_ADVANCE_TIMEOUT]: 15,
                    [WIRE_KEY.BASE_TURN_SECONDS]: 5,
                },
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed!.type).toBe("game_started");
        });

        it("parses a call_prompt event (ron)", () => {
            const raw = {
                [WIRE_KEY.BANK_SECONDS]: 17,
                [WIRE_KEY.CALL_TYPE]: 0,
                [WIRE_KEY.CALLER_SEAT]: 2,
                [WIRE_KEY.FROM_SEAT]: 1,
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.CALL_PROMPT,
                [WIRE_KEY.TILE_ID]: 50,
                [WIRE_KEY.WAIT_ID]: 4,
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({
                availableCalls: [],
                bankSeconds: 17,
                callType: 0,
                callerSeat: 2,
                elapsedSeconds: null,
                fromSeat: 1,
                tileId: 50,
                type: "call_prompt",
                waitId: 4,
            });
        });

        it("parses a round_end event (tsumo)", () => {
            const raw = {
                [WIRE_KEY.CLOSED_TILES]: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.HONBA_BONUS]: 0,
                [WIRE_KEY.HAND_RESULT]: {
                    [WIRE_KEY.FU]: 30,
                    [WIRE_KEY.HAN]: 3,
                    [WIRE_KEY.HAND_LIMIT]: "none",
                    [WIRE_KEY.POINTS]: 39,
                    [WIRE_KEY.YAKU]: [
                        {
                            [WIRE_KEY.HAN]: 1,
                            [WIRE_KEY.YAKU_ID]: 0,
                            [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                        },
                    ],
                },
                [WIRE_KEY.MELDS]: [],
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.RIICHI_COLLECTED]: 1,
                [WIRE_KEY.RESULT_TYPE]: 0,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 50, "1": -20, "2": -20, "3": -10 },
                [WIRE_KEY.SCORES]: { "0": 300, "1": 250, "2": 250, "3": 200 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
                [WIRE_KEY.WINNER_SEAT]: 0,
                [WIRE_KEY.WINNING_TILE]: 10,
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed!.type).toBe("round_end");
        });

        it("parses a furiten event", () => {
            const raw = { [WIRE_KEY.FURITEN]: true, [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.FURITEN };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({ isFuriten: true, type: "furiten" });
        });

        it("parses a riichi_declared event", () => {
            const raw = {
                [WIRE_KEY.RIICHI_STICKS]: 1,
                [WIRE_KEY.SEAT]: 2,
                [WIRE_KEY.SCORE]: 240,
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.RIICHI_DECLARED,
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({
                riichiSticks: 1,
                score: 24_000,
                seat: 2,
                type: "riichi_declared",
            });
        });

        it("parses a dora_revealed event", () => {
            const raw = {
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DORA_REVEALED,
                [WIRE_KEY.TILE_ID]: 100,
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({ tileId: 100, type: "dora_revealed" });
        });

        it("parses an error event", () => {
            const raw = {
                [WIRE_KEY.GAME_ERROR_CODE]: "not_your_turn",
                [WIRE_KEY.GAME_ERROR_MESSAGE]: "not your turn",
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ERROR,
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({
                code: "not_your_turn",
                message: "not your turn",
                type: "error",
                waitId: null,
            });
        });
    });

    describe("error handling", () => {
        it("returns error when message has neither type nor t field", () => {
            const raw = { data: "something" };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeInstanceOf(Error);
            expect(err!.message).toContain("neither");
            expect(parsed).toBeNull();
        });

        it("returns error with descriptive message for unknown string type", () => {
            const raw = { [WIRE_KEY.SESSION_TYPE]: "nonexistent_type" };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeInstanceOf(Error);
            expect(err!.message).toContain("SESSION_TYPE=nonexistent_type");
            expect(parsed).toBeNull();
        });

        it("returns error with descriptive message for unknown integer t", () => {
            const raw = { [WIRE_KEY.EVENT_TYPE]: 99 };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeInstanceOf(Error);
            expect(err!.message).toContain("EVENT_TYPE=99");
            expect(parsed).toBeNull();
        });

        it("returns error when valid t but malformed payload", () => {
            // draw event needs a `d` field
            const raw = { [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DRAW, wrong_field: 5 };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeInstanceOf(Error);
            expect(err!.message).toContain("EVENT_TYPE=1");
            expect(err!.message).toContain("expected number, received undefined");
            expect(parsed).toBeNull();
        });

        it.each([
            [
                "game start without its viewer seat",
                { ...LIVE_GAME_STARTED, [WIRE_KEY.SEAT]: undefined },
                WIRE_KEY.SEAT,
            ],
            [
                "game start without its timer settings",
                { ...LIVE_GAME_STARTED, [WIRE_KEY.TIMER_SETTINGS]: undefined },
                WIRE_KEY.TIMER_SETTINGS,
            ],
            [
                "deal without the viewer's hand",
                { ...LIVE_ROUND_STARTED, [WIRE_KEY.MY_TILES]: undefined },
                WIRE_KEY.MY_TILES,
            ],
            [
                "deal without its viewer seat",
                { ...LIVE_ROUND_STARTED, [WIRE_KEY.SEAT]: undefined },
                WIRE_KEY.SEAT,
            ],
            [
                "draw without its wait id",
                {
                    [WIRE_KEY.BANK_SECONDS]: 20,
                    [WIRE_KEY.PACKED_MOVE]: 5,
                    [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DRAW,
                },
                WIRE_KEY.WAIT_ID,
            ],
            [
                "turn without its bank",
                {
                    [WIRE_KEY.KUIKAE_TILES]: [],
                    [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.TURN,
                    [WIRE_KEY.WAIT_ID]: 5,
                },
                WIRE_KEY.BANK_SECONDS,
            ],
            [
                "call prompt without its wait id",
                {
                    [WIRE_KEY.BANK_SECONDS]: 20,
                    [WIRE_KEY.CALL_TYPE]: 0,
                    [WIRE_KEY.CALLER_SEAT]: 2,
                    [WIRE_KEY.FROM_SEAT]: 1,
                    [WIRE_KEY.EVENT_TYPE]: 3,
                    [WIRE_KEY.TILE_ID]: 50,
                },
                WIRE_KEY.WAIT_ID,
            ],
            [
                "call prompt without its bank",
                {
                    [WIRE_KEY.CALL_TYPE]: 0,
                    [WIRE_KEY.CALLER_SEAT]: 2,
                    [WIRE_KEY.FROM_SEAT]: 1,
                    [WIRE_KEY.EVENT_TYPE]: 3,
                    [WIRE_KEY.TILE_ID]: 50,
                    [WIRE_KEY.WAIT_ID]: 4,
                },
                WIRE_KEY.BANK_SECONDS,
            ],
        ])("refuses a %s, which the live socket always stamps", (_name, raw, key) => {
            const [err, parsed] = parseServerMessage(raw);
            expect([err?.message, parsed]).toEqual([expect.stringContaining(`no ${key},`), null]);
        });

        it("returns error when valid type but malformed payload", () => {
            // session_error needs code and message fields
            const raw = { [WIRE_KEY.SESSION_TYPE]: SESSION_MESSAGE_TYPE.ERROR };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeInstanceOf(Error);
            expect(err!.message).toContain("SESSION_TYPE=session_error");
            expect(parsed).toBeNull();
        });
    });
});
