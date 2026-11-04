import { describe, expect, expectTypeOf, it } from "vitest";

import { WIRE_KEY, parseReplayLine } from "@/shared/protocol";
import { EVENT_TYPE, GAME_TYPE } from "@/shared/protocol/constants";
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
    turnSchema,
} from "@/shared/protocol/schemas/events";

const SEATS = [0, 1, 2, 3] as const;

interface WirePlayer {
    readonly [WIRE_KEY.AI_PLAYER]: number;
    readonly [WIRE_KEY.NAME]: string;
    readonly [WIRE_KEY.SEAT]: number;
}

interface WirePlayerView {
    readonly [WIRE_KEY.SEAT]: number;
    readonly [WIRE_KEY.SCORE]: number;
    readonly [WIRE_KEY.TILES]?: readonly number[];
}

/** A game start's four seats in seat order: `named` at its own seat, a plain player at each other. */
function fourPlayers(named: WirePlayer): WirePlayer[] {
    return SEATS.map((seat) =>
        seat === named[WIRE_KEY.SEAT]
            ? named
            : { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: `P${seat}`, [WIRE_KEY.SEAT]: seat },
    );
}

/** A deal's four seats in seat order: `shown` at its own seat, the starting score at each other. */
function fourViews(shown: WirePlayerView): WirePlayerView[] {
    return SEATS.map((seat) =>
        seat === shown[WIRE_KEY.SEAT] ? shown : { [WIRE_KEY.SEAT]: seat, [WIRE_KEY.SCORE]: 250 },
    );
}

describe("gameStartedSchema", () => {
    it("parses realistic wire payload with 4 players", () => {
        const wire = {
            [WIRE_KEY.DEALER_DICE]: [
                [3, 5],
                [2, 4],
            ],
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.GAME_ID]: "game-abc-123",
            [WIRE_KEY.GAME_TYPE]: GAME_TYPE.HANCHAN,
            [WIRE_KEY.PLAYERS]: [
                { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: "Alice", [WIRE_KEY.SEAT]: 0 },
                { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: "Bob", [WIRE_KEY.SEAT]: 1 },
                { [WIRE_KEY.AI_PLAYER]: 1, [WIRE_KEY.NAME]: "Charlie", [WIRE_KEY.SEAT]: 2 },
                { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: "Diana", [WIRE_KEY.SEAT]: 3 },
            ],
            [WIRE_KEY.RIICHI_STICK_VALUE]: 10,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.GAME_STARTED,
        };
        const result = gameStartedSchema.parse(wire);
        expect(result.type).toBe("game_started");
        expect(result.gameId).toBe("game-abc-123");
        expect(result.dealerSeat).toBe(0);
        expect(result.riichiStickValue).toBe(1000);
        expect(result.dealerDice).toEqual([
            [3, 5],
            [2, 4],
        ]);
        expect(result.players).toHaveLength(4);
        expect(result.players[0]).toEqual({
            aiStandIn: null,
            isAiPlayer: false,
            name: "Alice",
            seat: 0,
        });
        expect(result.players[2].isAiPlayer).toBe(true);
    });

    it("converts ai integer to boolean (0 = false, 1 = true)", () => {
        const wire = {
            [WIRE_KEY.DEALER_DICE]: [
                [1, 1],
                [1, 1],
            ],
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.GAME_ID]: "g1",
            [WIRE_KEY.GAME_TYPE]: GAME_TYPE.TONPUSEN,
            [WIRE_KEY.PLAYERS]: fourPlayers({
                [WIRE_KEY.AI_PLAYER]: 1,
                [WIRE_KEY.NAME]: "Bot",
                [WIRE_KEY.SEAT]: 0,
            }),
            [WIRE_KEY.RIICHI_STICK_VALUE]: 10,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.GAME_STARTED,
        };
        const result = gameStartedSchema.parse(wire);
        expect(result.players[0].isAiPlayer).toBe(true);
    });

    it("reads the live copy's viewer seat and timer settings, null in a replay", () => {
        const wire = {
            [WIRE_KEY.DEALER_DICE]: [
                [1, 1],
                [1, 1],
            ],
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.GAME_ID]: "g1",
            [WIRE_KEY.GAME_TYPE]: GAME_TYPE.TONPUSEN,
            [WIRE_KEY.PLAYERS]: fourPlayers({
                [WIRE_KEY.AI_PLAYER]: 0,
                [WIRE_KEY.NAME]: "Alice",
                [WIRE_KEY.SEAT]: 2,
            }),
            [WIRE_KEY.RIICHI_STICK_VALUE]: 10,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.GAME_STARTED,
        };
        const timer = {
            [WIRE_KEY.BANK_SECONDS]: 20,
            [WIRE_KEY.GAME_START_PAUSE]: 3,
            [WIRE_KEY.MAX_BANK_SECONDS]: 20,
            [WIRE_KEY.ROUND_ADVANCE_TIMEOUT]: 15,
            [WIRE_KEY.BASE_TURN_SECONDS]: 5,
        };
        const live = gameStartedSchema.parse({
            ...wire,
            [WIRE_KEY.SEAT]: 2,
            [WIRE_KEY.TIMER_SETTINGS]: timer,
        });
        const replay = gameStartedSchema.parse(wire);
        expect(live.gameType).toBe(GAME_TYPE.TONPUSEN);
        expect(live.seat).toBe(2);
        expect(live.timer).toEqual({
            bankSeconds: 20,
            baseTurnSeconds: 5,
            gameStartPauseSeconds: 3,
            maxBankSeconds: 20,
            roundAdvanceTimeoutSeconds: 15,
        });
        expect(replay.seat).toBeNull();
        expect(replay.timer).toBeNull();
    });

    it("rejects missing required fields", () => {
        const wire = { [WIRE_KEY.GAME_ID]: "g1", [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.GAME_STARTED };
        expect(() => gameStartedSchema.parse(wire)).toThrow();
    });

    it("refuses a riichi stick value that is not a whole number of wire units", () => {
        const wire = {
            [WIRE_KEY.DEALER_DICE]: [
                [1, 1],
                [1, 1],
            ],
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.GAME_ID]: "g1",
            [WIRE_KEY.GAME_TYPE]: GAME_TYPE.TONPUSEN,
            [WIRE_KEY.PLAYERS]: fourPlayers({
                [WIRE_KEY.AI_PLAYER]: 0,
                [WIRE_KEY.NAME]: "Alice",
                [WIRE_KEY.SEAT]: 0,
            }),
            [WIRE_KEY.RIICHI_STICK_VALUE]: 15.5,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.GAME_STARTED,
        };
        expect(() => gameStartedSchema.parse(wire)).toThrow();
        expect(
            gameStartedSchema.parse({ ...wire, [WIRE_KEY.RIICHI_STICK_VALUE]: 15 })
                .riichiStickValue,
        ).toBe(1500);
    });

    it("refuses a game start or a deal that does not list each of the four seats once, in seat order", () => {
        const players = fourPlayers({
            [WIRE_KEY.AI_PLAYER]: 0,
            [WIRE_KEY.NAME]: "Alice",
            [WIRE_KEY.SEAT]: 0,
        });
        const views = fourViews({ [WIRE_KEY.SEAT]: 0, [WIRE_KEY.SCORE]: 250 });
        const start = {
            [WIRE_KEY.DEALER_DICE]: [
                [1, 1],
                [1, 1],
            ],
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.GAME_ID]: "g1",
            [WIRE_KEY.GAME_TYPE]: GAME_TYPE.HANCHAN,
            [WIRE_KEY.PLAYERS]: players,
            [WIRE_KEY.RIICHI_STICK_VALUE]: 10,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.GAME_STARTED,
        };
        const deal = {
            [WIRE_KEY.CURRENT_PLAYER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [10],
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.HONBA]: 0,
            [WIRE_KEY.ROUND_NUMBER]: 0,
            [WIRE_KEY.PLAYERS]: views,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.ROUND_IN_WIND]: 1,
            [WIRE_KEY.EVENT_TYPE]: 9,
            [WIRE_KEY.TILES_REMAINING]: 70,
            [WIRE_KEY.WIND]: 0,
        };

        for (const p of [players.slice(0, 3), [players[1], players[0], ...players.slice(2)]]) {
            expect(() => gameStartedSchema.parse({ ...start, [WIRE_KEY.PLAYERS]: p })).toThrow(
                "the game start does not seat each of the four seats once, in seat order",
            );
        }
        expect(() =>
            roundStartedSchema.parse({ ...deal, [WIRE_KEY.PLAYERS]: views.slice(1) }),
        ).toThrow("the deal does not list each of the four seats once, in seat order");
    });
});

describe("roundStartedSchema (live)", () => {
    it("parses live format with seat and myTiles", () => {
        const wire = {
            [WIRE_KEY.CURRENT_PLAYER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [10],
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.HONBA]: 0,
            [WIRE_KEY.MY_TILES]: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48],
            [WIRE_KEY.ROUND_NUMBER]: 1,
            [WIRE_KEY.PLAYERS]: [
                { [WIRE_KEY.SEAT]: 0, [WIRE_KEY.SCORE]: 250 },
                { [WIRE_KEY.SEAT]: 1, [WIRE_KEY.SCORE]: 250 },
                { [WIRE_KEY.SEAT]: 2, [WIRE_KEY.SCORE]: 250 },
                { [WIRE_KEY.SEAT]: 3, [WIRE_KEY.SCORE]: 250 },
            ],
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.ROUND_IN_WIND]: 1,
            [WIRE_KEY.SEAT]: 0,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_STARTED,
            [WIRE_KEY.TILES_REMAINING]: 70,
            [WIRE_KEY.WIND]: 0,
        };
        const result = roundStartedSchema.parse(wire);
        expect(result.type).toBe("round_started");
        expect(result.seat).toBe(0);
        expect(result.myTiles).toHaveLength(13);
        expect(result.wind).toBe(0);
        expect(result.roundNumber).toBe(1);
    });

    it("refuses a deal that names no round within its wind, or no live wall", () => {
        const deal = {
            [WIRE_KEY.CURRENT_PLAYER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [10],
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.HONBA]: 0,
            [WIRE_KEY.MY_TILES]: [0],
            [WIRE_KEY.ROUND_NUMBER]: 1,
            [WIRE_KEY.PLAYERS]: fourViews({ [WIRE_KEY.SEAT]: 0, [WIRE_KEY.SCORE]: 250 }),
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.ROUND_IN_WIND]: 1,
            [WIRE_KEY.SEAT]: 0,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_STARTED,
            [WIRE_KEY.TILES_REMAINING]: 70,
            [WIRE_KEY.WIND]: 0,
        };
        const { [WIRE_KEY.ROUND_IN_WIND]: _roundInWind, ...unnamedRound } = deal;
        const { [WIRE_KEY.TILES_REMAINING]: _tilesRemaining, ...uncountedWall } = deal;

        expect(roundStartedSchema.parse(deal)).toMatchObject({
            roundInWind: 1,
            tilesRemaining: 70,
        });
        expect(() => roundStartedSchema.parse(unnamedRound)).toThrow();
        expect(() => roundStartedSchema.parse(uncountedWall)).toThrow();
    });

    it("decodes wire scores (250 -> 25000)", () => {
        const wire = {
            [WIRE_KEY.CURRENT_PLAYER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [10],
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.HONBA]: 0,
            [WIRE_KEY.MY_TILES]: [0],
            [WIRE_KEY.ROUND_NUMBER]: 1,
            [WIRE_KEY.PLAYERS]: fourViews({ [WIRE_KEY.SEAT]: 0, [WIRE_KEY.SCORE]: 250 }),
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.ROUND_IN_WIND]: 1,
            [WIRE_KEY.SEAT]: 0,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_STARTED,
            [WIRE_KEY.TILES_REMAINING]: 70,
            [WIRE_KEY.WIND]: 0,
        };
        const result = roundStartedSchema.parse(wire);
        expect(result.players[0].score).toBe(25_000);
    });

    it("live format player tiles default to null", () => {
        const wire = {
            [WIRE_KEY.CURRENT_PLAYER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [10],
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.HONBA]: 0,
            [WIRE_KEY.MY_TILES]: [0],
            [WIRE_KEY.ROUND_NUMBER]: 1,
            [WIRE_KEY.PLAYERS]: fourViews({ [WIRE_KEY.SEAT]: 0, [WIRE_KEY.SCORE]: 250 }),
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.ROUND_IN_WIND]: 1,
            [WIRE_KEY.SEAT]: 0,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_STARTED,
            [WIRE_KEY.TILES_REMAINING]: 70,
            [WIRE_KEY.WIND]: 0,
        };
        const result = roundStartedSchema.parse(wire);
        expect(result.players[0].tiles).toBeNull();
    });
});

describe("roundStartedSchema (replay)", () => {
    it("parses replay format without s and mt, with player tiles", () => {
        const wire = {
            [WIRE_KEY.CURRENT_PLAYER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [10],
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.HONBA]: 0,
            [WIRE_KEY.ROUND_NUMBER]: 1,
            [WIRE_KEY.PLAYERS]: [
                {
                    [WIRE_KEY.SEAT]: 0,
                    [WIRE_KEY.SCORE]: 250,
                    [WIRE_KEY.TILES]: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48],
                },
                {
                    [WIRE_KEY.SEAT]: 1,
                    [WIRE_KEY.SCORE]: 250,
                    [WIRE_KEY.TILES]: [1, 5, 9, 13, 17, 21, 25, 29, 33, 37, 41, 45, 49],
                },
                {
                    [WIRE_KEY.SEAT]: 2,
                    [WIRE_KEY.SCORE]: 250,
                    [WIRE_KEY.TILES]: [2, 6, 10, 14, 18, 22, 26, 30, 34, 38, 42, 46, 50],
                },
                {
                    [WIRE_KEY.SEAT]: 3,
                    [WIRE_KEY.SCORE]: 250,
                    [WIRE_KEY.TILES]: [3, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43, 47, 51],
                },
            ],
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.ROUND_IN_WIND]: 1,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_STARTED,
            [WIRE_KEY.TILES_REMAINING]: 70,
            [WIRE_KEY.WIND]: 0,
        };
        const result = roundStartedSchema.parse(wire);
        expect(result.seat).toBeNull();
        expect(result.myTiles).toBeNull();
        expect(result.players[0].tiles).toHaveLength(13);
        expect(result.players[1].tiles).toHaveLength(13);
    });

    it("preserves round metadata in replay format", () => {
        const wire = {
            [WIRE_KEY.CURRENT_PLAYER]: 2,
            [WIRE_KEY.DORA_INDICATORS]: [10, 42],
            [WIRE_KEY.DEALER]: 1,
            [WIRE_KEY.HONBA]: 3,
            [WIRE_KEY.ROUND_NUMBER]: 5,
            [WIRE_KEY.PLAYERS]: fourViews({
                [WIRE_KEY.SEAT]: 0,
                [WIRE_KEY.SCORE]: 300,
                [WIRE_KEY.TILES]: [0],
            }),
            [WIRE_KEY.RIICHI_STICKS]: 2,
            [WIRE_KEY.ROUND_IN_WIND]: 2,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_STARTED,
            [WIRE_KEY.TILES_REMAINING]: 70,
            [WIRE_KEY.WIND]: 1,
        };
        const result = roundStartedSchema.parse(wire);
        expect(result.wind).toBe(1);
        expect(result.roundNumber).toBe(5);
        expect([result.roundInWind, result.tilesRemaining]).toEqual([2, 70]);
        expect(result.dealerSeat).toBe(1);
        expect(result.currentPlayerSeat).toBe(2);
        expect(result.doraIndicators).toEqual([10, 42]);
        expect(result.honbaSticks).toBe(3);
        expect(result.riichiSticks).toBe(2);
    });
});

describe("drawSchema", () => {
    it("decodes a live draw without a wall count", () => {
        // d = seat * 136 + tileId = 1 * 136 + 42 = 178
        const wire = {
            [WIRE_KEY.PACKED_MOVE]: 178,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DRAW,
        };
        const result = drawSchema.parse(wire);
        expect(result).toMatchObject({
            availableActions: [],
            seat: 1,
            source: "live",
            tileId: 42,
            type: "draw",
        });
        expectTypeOf(result.source).toEqualTypeOf<"live">();
        expect(result).not.toHaveProperty("tilesRemaining");

        const [missingCount] = parseReplayLine(wire);
        expect(missingCount).toBeInstanceOf(Error);

        const [replayError, recorded] = parseReplayLine({
            ...wire,
            [WIRE_KEY.TILES_REMAINING]: 66,
        });
        expect(replayError).toBeNull();
        expect(recorded).toMatchObject({ source: "replay", tileId: 42, tilesRemaining: 66 });
    });

    it("parses available actions array", () => {
        const wire = {
            [WIRE_KEY.AVAILABLE_ACTIONS]: [
                { [WIRE_KEY.ACTION]: 1, [WIRE_KEY.TILES]: [5, 10, 15] },
                { [WIRE_KEY.ACTION]: 2 },
                { [WIRE_KEY.ACTION]: 4, [WIRE_KEY.TILES]: [9] },
            ],
            [WIRE_KEY.PACKED_MOVE]: 5,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DRAW,
        };
        const result = drawSchema.parse(wire);
        expect(result.availableActions).toEqual([
            { action: 1, tileIds: [5, 10, 15] },
            { action: 2 },
            { action: 4, tileTypes: [9] },
        ]);
    });

    it.each([
        {
            [WIRE_KEY.AVAILABLE_ACTIONS]: [{ [WIRE_KEY.ACTION]: 0 }],
            name: "a discard, which the server never offers",
        },
        {
            [WIRE_KEY.AVAILABLE_ACTIONS]: [{ [WIRE_KEY.ACTION]: 3, [WIRE_KEY.TILES]: [40] }],
            name: "a kan of a tile id, not a tile type",
        },
        {
            [WIRE_KEY.AVAILABLE_ACTIONS]: [{ [WIRE_KEY.ACTION]: 4, [WIRE_KEY.TILES]: [] }],
            name: "an added kan with no tile type",
        },
    ])("refuses an offer of $name", ({ [WIRE_KEY.AVAILABLE_ACTIONS]: aa }) => {
        expect(() =>
            drawSchema.parse({
                [WIRE_KEY.AVAILABLE_ACTIONS]: aa,
                [WIRE_KEY.PACKED_MOVE]: 5,
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DRAW,
            }),
        ).toThrow();
    });

    it("defaults available actions to empty array when aa is absent", () => {
        const wire = {
            [WIRE_KEY.PACKED_MOVE]: 0,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DRAW,
        };
        const result = drawSchema.parse(wire);
        expect(result.availableActions).toEqual([]);
    });

    it("reads the turn's bank and a re-send's elapsed seconds, null without them", () => {
        const opening = drawSchema.parse({
            [WIRE_KEY.BANK_SECONDS]: 12.5,
            [WIRE_KEY.PACKED_MOVE]: 0,
            [WIRE_KEY.WAIT_ELAPSED]: 3.2,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DRAW,

            [WIRE_KEY.WAIT_ID]: 4,
        });
        const plain = drawSchema.parse({
            [WIRE_KEY.PACKED_MOVE]: 0,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DRAW,
        });
        expect(opening.bankSeconds).toBe(12.5);
        expect(opening.elapsedSeconds).toBe(3.2);
        expect(opening.waitId).toBe(4);
        expect(plain.bankSeconds).toBeNull();
        expect(plain.elapsedSeconds).toBeNull();
    });
});

describe("turnSchema", () => {
    it("reads the kuikae tile types and the turn's wait", () => {
        const result = turnSchema.parse({
            [WIRE_KEY.BANK_SECONDS]: 20,
            [WIRE_KEY.KUIKAE_TILES]: [4, 7],
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.TURN,
            [WIRE_KEY.WAIT_ID]: 9,
        });
        expect(result).toEqual({
            bankSeconds: 20,
            elapsedSeconds: null,
            kuikaeTileTypes: [4, 7],
            type: "turn",
            waitId: 9,
        });
    });

    it("rejects a kuikae tile outside the 34 types", () => {
        expect(() =>
            turnSchema.parse({
                [WIRE_KEY.KUIKAE_TILES]: [34],
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.TURN,
            }),
        ).toThrow();
    });
});

describe("discardSchema", () => {
    it("decodes plain discard (no flags)", () => {
        // flag=0, seat=0, tile=10 => d = 0 * 544 + 0 * 136 + 10 = 10
        const wire = { [WIRE_KEY.PACKED_MOVE]: 10, [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DISCARD };
        const result = discardSchema.parse(wire);
        expect(result.type).toBe("discard");
        expect(result.seat).toBe(0);
        expect(result.tileId).toBe(10);
        expect(result.isTsumogiri).toBe(false);
        expect(result.isRiichi).toBe(false);
    });

    it("decodes tsumogiri discard", () => {
        // flag=1 (tsumogiri), seat=2, tile=50 => d = 1 * 544 + 2 * 136 + 50 = 866
        const wire = { [WIRE_KEY.PACKED_MOVE]: 866, [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DISCARD };
        const result = discardSchema.parse(wire);
        expect(result.isTsumogiri).toBe(true);
        expect(result.isRiichi).toBe(false);
        expect(result.seat).toBe(2);
        expect(result.tileId).toBe(50);
    });

    it("decodes riichi discard", () => {
        // flag=2 (riichi), seat=1, tile=0 => d = 2 * 544 + 1 * 136 + 0 = 1224
        const wire = { [WIRE_KEY.PACKED_MOVE]: 1224, [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DISCARD };
        const result = discardSchema.parse(wire);
        expect(result.isRiichi).toBe(true);
        expect(result.isTsumogiri).toBe(false);
    });

    it("decodes riichi + tsumogiri discard", () => {
        // flag=3, seat=0, tile=0 => d = 3 * 544 + 0 = 1632
        const wire = { [WIRE_KEY.PACKED_MOVE]: 1632, [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DISCARD };
        const result = discardSchema.parse(wire);
        expect(result.isRiichi).toBe(true);
        expect(result.isTsumogiri).toBe(true);
    });
});

describe("meldSchema", () => {
    it("decodes IMME integer to full meld structure (ankan)", () => {
        // Ankan (closed kan) for tile_34=0 by seat 0:
        // meld_index = 6888 + 0 = 6888, value = 6888 * 4 + 0 = 27552
        const wire = { [WIRE_KEY.PACKED_MELD]: 27_552, [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.MELD };
        const result = meldSchema.parse(wire);
        expect(result.type).toBe("meld");
        expect(result.meldType).toBe("closed_kan");
        expect(result.callerSeat).toBe(0);
        expect(result.fromSeat).toBeNull();
        expect(result.tileIds).toEqual([0, 1, 2, 3]);
        expect(result.calledTileId).toBeNull();
    });
});

describe("riichiDeclaredSchema", () => {
    it("reads the declarer's score after its deposit and the table's sticks, refusing a riichi that names neither", () => {
        const wire = {
            [WIRE_KEY.RIICHI_STICKS]: 2,
            [WIRE_KEY.SEAT]: 2,
            [WIRE_KEY.SCORE]: 240,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.RIICHI_DECLARED,
        };
        const result = riichiDeclaredSchema.parse(wire);
        expect(result).toEqual({
            riichiSticks: 2,
            score: 24_000,
            seat: 2,
            type: "riichi_declared",
        });
        expect(() =>
            riichiDeclaredSchema.parse({
                [WIRE_KEY.SEAT]: 2,
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.RIICHI_DECLARED,
            }),
        ).toThrow();
    });

    it("rejects invalid seat", () => {
        const wire = {
            [WIRE_KEY.RIICHI_STICKS]: 1,
            [WIRE_KEY.SEAT]: 5,
            [WIRE_KEY.SCORE]: 240,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.RIICHI_DECLARED,
        };
        expect(() => riichiDeclaredSchema.parse(wire)).toThrow();
    });
});

describe("doraRevealedSchema", () => {
    it("parses valid wire payload", () => {
        const wire = { [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DORA_REVEALED, [WIRE_KEY.TILE_ID]: 42 };
        const result = doraRevealedSchema.parse(wire);
        expect(result).toEqual({ tileId: 42, type: "dora_revealed" });
    });

    it("rejects tile ID out of range", () => {
        const wire = { [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DORA_REVEALED, [WIRE_KEY.TILE_ID]: 136 };
        expect(() => doraRevealedSchema.parse(wire)).toThrow();
    });
});

describe("errorEventSchema", () => {
    it("parses valid wire payload, with the wait id the refused action echoed", () => {
        const wire = {
            [WIRE_KEY.GAME_ERROR_CODE]: "not_your_turn",
            [WIRE_KEY.GAME_ERROR_MESSAGE]: "It's not your turn",
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ERROR,
            [WIRE_KEY.WAIT_ID]: 4,
        };
        const result = errorEventSchema.parse(wire);
        expect(result).toEqual({
            code: "not_your_turn",
            message: "It's not your turn",
            type: "error",
            waitId: 4,
        });
    });

    it("rejects missing message field", () => {
        const wire = {
            [WIRE_KEY.GAME_ERROR_CODE]: "some_code",
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ERROR,
        };
        expect(() => errorEventSchema.parse(wire)).toThrow();
    });
});

describe("furitenSchema", () => {
    it("parses furiten true", () => {
        const wire = { [WIRE_KEY.FURITEN]: true, [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.FURITEN };
        const result = furitenSchema.parse(wire);
        expect(result).toEqual({ isFuriten: true, type: "furiten" });
    });

    it("parses furiten false", () => {
        const wire = { [WIRE_KEY.FURITEN]: false, [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.FURITEN };
        const result = furitenSchema.parse(wire);
        expect(result).toEqual({ isFuriten: false, type: "furiten" });
    });

    it("rejects wrong type for f field", () => {
        const wire = { [WIRE_KEY.FURITEN]: 1, [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.FURITEN };
        expect(() => furitenSchema.parse(wire)).toThrow();
    });
});

function standing(seat: number): Record<string, number> {
    return { [WIRE_KEY.FINAL_SCORE]: 0, [WIRE_KEY.SEAT]: seat, [WIRE_KEY.SCORE]: 250 };
}

describe("gameEndSchema", () => {
    it("parses valid wire payload with standings", () => {
        const wire = {
            [WIRE_KEY.END_CAUSE]: "target_reached",
            [WIRE_KEY.LEFTOVER_BONUS]: 20,
            [WIRE_KEY.LEFTOVER_RIICHI]: 2,
            [WIRE_KEY.ROUND_COUNT]: 8,
            [WIRE_KEY.STANDINGS]: [
                { [WIRE_KEY.FINAL_SCORE]: 42, [WIRE_KEY.SEAT]: 0, [WIRE_KEY.SCORE]: 350 },
                { [WIRE_KEY.FINAL_SCORE]: 12, [WIRE_KEY.SEAT]: 1, [WIRE_KEY.SCORE]: 250 },
                { [WIRE_KEY.FINAL_SCORE]: -18, [WIRE_KEY.SEAT]: 2, [WIRE_KEY.SCORE]: 200 },
                { [WIRE_KEY.FINAL_SCORE]: -36, [WIRE_KEY.SEAT]: 3, [WIRE_KEY.SCORE]: 200 },
            ],
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.GAME_END,
            [WIRE_KEY.WINNER_SEAT]: 0,
        };
        const result = gameEndSchema.parse(wire);
        expect(result.type).toBe("game_end");
        expect(result.winnerSeat).toBe(0);
        expect([result.numRounds, result.endCause]).toEqual([8, "target_reached"]);
        expect([result.leftoverRiichiBonus, result.leftoverRiichiSticks]).toEqual([2000, 2]);
        expect(result.standings[0]).toEqual({ finalScore: 42, score: 35_000, seat: 0 });
        expect(result.standings[3]).toEqual({ finalScore: -36, score: 20_000, seat: 3 });
    });

    it("refuses standings that rank a seat twice, in whatever order the server ranks them", () => {
        const wire = {
            [WIRE_KEY.END_CAUSE]: "length",
            [WIRE_KEY.LEFTOVER_BONUS]: 0,
            [WIRE_KEY.LEFTOVER_RIICHI]: 0,
            [WIRE_KEY.ROUND_COUNT]: 8,
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.GAME_END,
            [WIRE_KEY.WINNER_SEAT]: 1,
        };

        expect(
            gameEndSchema.parse({ ...wire, [WIRE_KEY.STANDINGS]: [1, 2, 3, 0].map(standing) })
                .winnerSeat,
        ).toBe(1);
        expect(() =>
            gameEndSchema.parse({ ...wire, [WIRE_KEY.STANDINGS]: [1, 2, 3, 1].map(standing) }),
        ).toThrow("rank each of the four seats once");
    });
});
