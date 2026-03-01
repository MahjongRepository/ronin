import { describe, expect, it } from "vitest";

import { EVENT_TYPE } from "@/shared/protocol/constants";
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
} from "@/shared/protocol/schemas/events";

describe("gameStartedSchema", () => {
    it("parses realistic wire payload with 4 players", () => {
        const wire = {
            dd: [
                [3, 5],
                [2, 4],
            ],
            dl: 0,
            gid: "game-abc-123",
            p: [
                { ai: 0, nm: "Alice", s: 0 },
                { ai: 0, nm: "Bob", s: 1 },
                { ai: 1, nm: "Charlie", s: 2 },
                { ai: 0, nm: "Diana", s: 3 },
            ],
            t: EVENT_TYPE.GAME_STARTED,
        };
        const result = gameStartedSchema.parse(wire);
        expect(result.type).toBe("game_started");
        expect(result.gameId).toBe("game-abc-123");
        expect(result.dealerSeat).toBe(0);
        expect(result.dealerDice).toEqual([
            [3, 5],
            [2, 4],
        ]);
        expect(result.players).toHaveLength(4);
        expect(result.players[0]).toEqual({ isAiPlayer: false, name: "Alice", seat: 0 });
        expect(result.players[2].isAiPlayer).toBe(true);
    });

    it("converts ai integer to boolean (0 = false, 1 = true)", () => {
        const wire = {
            dd: [
                [1, 1],
                [1, 1],
            ],
            dl: 0,
            gid: "g1",
            p: [{ ai: 1, nm: "Bot", s: 0 }],
            t: EVENT_TYPE.GAME_STARTED,
        };
        const result = gameStartedSchema.parse(wire);
        expect(result.players[0].isAiPlayer).toBe(true);
    });

    it("rejects missing required fields", () => {
        const wire = { gid: "g1", t: EVENT_TYPE.GAME_STARTED };
        expect(() => gameStartedSchema.parse(wire)).toThrow();
    });
});

describe("roundStartedSchema (live)", () => {
    it("parses live format with seat and myTiles", () => {
        const wire = {
            cp: 0,
            di: [10],
            dl: 0,
            h: 0,
            mt: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48],
            n: 1,
            p: [
                { s: 0, sc: 250 },
                { s: 1, sc: 250 },
                { s: 2, sc: 250 },
                { s: 3, sc: 250 },
            ],
            r: 0,
            s: 0,
            t: EVENT_TYPE.ROUND_STARTED,
            w: 0,
        };
        const result = roundStartedSchema.parse(wire);
        expect(result.type).toBe("round_started");
        expect(result.seat).toBe(0);
        expect(result.myTiles).toHaveLength(13);
        expect(result.wind).toBe(0);
        expect(result.roundNumber).toBe(1);
    });

    it("decodes wire scores (250 -> 25000)", () => {
        const wire = {
            cp: 0,
            di: [10],
            dl: 0,
            h: 0,
            mt: [0],
            n: 1,
            p: [{ s: 0, sc: 250 }],
            r: 0,
            s: 0,
            t: EVENT_TYPE.ROUND_STARTED,
            w: 0,
        };
        const result = roundStartedSchema.parse(wire);
        expect(result.players[0].score).toBe(25000);
    });

    it("defaults dice to [1, 1] when dc is absent", () => {
        const wire = {
            cp: 0,
            di: [10],
            dl: 0,
            h: 0,
            mt: [0],
            n: 1,
            p: [{ s: 0, sc: 250 }],
            r: 0,
            s: 0,
            t: EVENT_TYPE.ROUND_STARTED,
            w: 0,
        };
        const result = roundStartedSchema.parse(wire);
        expect(result.dice).toEqual([1, 1]);
    });

    it("uses provided dice when dc is present", () => {
        const wire = {
            cp: 0,
            dc: [3, 5] as [number, number],
            di: [10],
            dl: 0,
            h: 0,
            mt: [0],
            n: 1,
            p: [{ s: 0, sc: 250 }],
            r: 0,
            s: 0,
            t: EVENT_TYPE.ROUND_STARTED,
            w: 0,
        };
        const result = roundStartedSchema.parse(wire);
        expect(result.dice).toEqual([3, 5]);
    });

    it("live format player tiles default to null", () => {
        const wire = {
            cp: 0,
            di: [10],
            dl: 0,
            h: 0,
            mt: [0],
            n: 1,
            p: [{ s: 0, sc: 250 }],
            r: 0,
            s: 0,
            t: EVENT_TYPE.ROUND_STARTED,
            w: 0,
        };
        const result = roundStartedSchema.parse(wire);
        expect(result.players[0].tiles).toBeNull();
    });
});

describe("roundStartedSchema (replay)", () => {
    it("parses replay format without s and mt, with player tiles", () => {
        const wire = {
            cp: 0,
            di: [10],
            dl: 0,
            h: 0,
            n: 1,
            p: [
                { s: 0, sc: 250, tl: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48] },
                { s: 1, sc: 250, tl: [1, 5, 9, 13, 17, 21, 25, 29, 33, 37, 41, 45, 49] },
            ],
            r: 0,
            t: EVENT_TYPE.ROUND_STARTED,
            w: 0,
        };
        const result = roundStartedSchema.parse(wire);
        expect(result.seat).toBeNull();
        expect(result.myTiles).toBeNull();
        expect(result.players[0].tiles).toHaveLength(13);
        expect(result.players[1].tiles).toHaveLength(13);
    });

    it("preserves round metadata in replay format", () => {
        const wire = {
            cp: 2,
            di: [10, 42],
            dl: 1,
            h: 3,
            n: 5,
            p: [{ s: 0, sc: 300, tl: [0] }],
            r: 2,
            t: EVENT_TYPE.ROUND_STARTED,
            w: 1,
        };
        const result = roundStartedSchema.parse(wire);
        expect(result.wind).toBe(1);
        expect(result.roundNumber).toBe(5);
        expect(result.dealerSeat).toBe(1);
        expect(result.currentPlayerSeat).toBe(2);
        expect(result.doraIndicators).toEqual([10, 42]);
        expect(result.honbaSticks).toBe(3);
        expect(result.riichiSticks).toBe(2);
    });
});

describe("drawSchema", () => {
    it("decodes packed integer to seat + tileId", () => {
        // d = seat * 136 + tileId = 1 * 136 + 42 = 178
        const wire = { d: 178, t: EVENT_TYPE.DRAW };
        const result = drawSchema.parse(wire);
        expect(result.type).toBe("draw");
        expect(result.seat).toBe(1);
        expect(result.tileId).toBe(42);
        expect(result.availableActions).toEqual([]);
    });

    it("parses available actions array", () => {
        const wire = {
            aa: [{ a: 0, tl: [5, 10, 15] }, { a: 2 }],
            d: 5,
            t: EVENT_TYPE.DRAW,
        };
        const result = drawSchema.parse(wire);
        expect(result.availableActions).toEqual([
            { action: 0, tiles: [5, 10, 15] },
            { action: 2, tiles: null },
        ]);
    });

    it("defaults available actions to empty array when aa is absent", () => {
        const wire = { d: 0, t: EVENT_TYPE.DRAW };
        const result = drawSchema.parse(wire);
        expect(result.availableActions).toEqual([]);
    });
});

describe("discardSchema", () => {
    it("decodes plain discard (no flags)", () => {
        // flag=0, seat=0, tile=10 => d = 0 * 544 + 0 * 136 + 10 = 10
        const wire = { d: 10, t: EVENT_TYPE.DISCARD };
        const result = discardSchema.parse(wire);
        expect(result.type).toBe("discard");
        expect(result.seat).toBe(0);
        expect(result.tileId).toBe(10);
        expect(result.isTsumogiri).toBe(false);
        expect(result.isRiichi).toBe(false);
    });

    it("decodes tsumogiri discard", () => {
        // flag=1 (tsumogiri), seat=2, tile=50 => d = 1 * 544 + 2 * 136 + 50 = 866
        const wire = { d: 866, t: EVENT_TYPE.DISCARD };
        const result = discardSchema.parse(wire);
        expect(result.isTsumogiri).toBe(true);
        expect(result.isRiichi).toBe(false);
        expect(result.seat).toBe(2);
        expect(result.tileId).toBe(50);
    });

    it("decodes riichi discard", () => {
        // flag=2 (riichi), seat=1, tile=0 => d = 2 * 544 + 1 * 136 + 0 = 1224
        const wire = { d: 1224, t: EVENT_TYPE.DISCARD };
        const result = discardSchema.parse(wire);
        expect(result.isRiichi).toBe(true);
        expect(result.isTsumogiri).toBe(false);
    });

    it("decodes riichi + tsumogiri discard", () => {
        // flag=3, seat=0, tile=0 => d = 3 * 544 + 0 = 1632
        const wire = { d: 1632, t: EVENT_TYPE.DISCARD };
        const result = discardSchema.parse(wire);
        expect(result.isRiichi).toBe(true);
        expect(result.isTsumogiri).toBe(true);
    });
});

describe("meldSchema", () => {
    it("decodes IMME integer to full meld structure (ankan)", () => {
        // Ankan (closed kan) for tile_34=0 by seat 0:
        // meld_index = 6072 + 0 = 6072, value = 6072 * 4 + 0 = 24288
        const wire = { m: 24288, t: EVENT_TYPE.MELD };
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
    it("parses valid wire payload", () => {
        const wire = { s: 2, t: EVENT_TYPE.RIICHI_DECLARED };
        const result = riichiDeclaredSchema.parse(wire);
        expect(result).toEqual({ seat: 2, type: "riichi_declared" });
    });

    it("rejects invalid seat", () => {
        const wire = { s: 5, t: EVENT_TYPE.RIICHI_DECLARED };
        expect(() => riichiDeclaredSchema.parse(wire)).toThrow();
    });
});

describe("doraRevealedSchema", () => {
    it("parses valid wire payload", () => {
        const wire = { t: EVENT_TYPE.DORA_REVEALED, ti: 42 };
        const result = doraRevealedSchema.parse(wire);
        expect(result).toEqual({ tileId: 42, type: "dora_revealed" });
    });

    it("rejects tile ID out of range", () => {
        const wire = { t: EVENT_TYPE.DORA_REVEALED, ti: 136 };
        expect(() => doraRevealedSchema.parse(wire)).toThrow();
    });
});

describe("errorEventSchema", () => {
    it("parses valid wire payload", () => {
        const wire = { cd: "not_your_turn", msg: "It's not your turn", t: EVENT_TYPE.ERROR };
        const result = errorEventSchema.parse(wire);
        expect(result).toEqual({
            code: "not_your_turn",
            message: "It's not your turn",
            type: "error",
        });
    });

    it("rejects missing message field", () => {
        const wire = { cd: "some_code", t: EVENT_TYPE.ERROR };
        expect(() => errorEventSchema.parse(wire)).toThrow();
    });
});

describe("furitenSchema", () => {
    it("parses furiten true", () => {
        const wire = { f: true, t: EVENT_TYPE.FURITEN };
        const result = furitenSchema.parse(wire);
        expect(result).toEqual({ isFuriten: true, type: "furiten" });
    });

    it("parses furiten false", () => {
        const wire = { f: false, t: EVENT_TYPE.FURITEN };
        const result = furitenSchema.parse(wire);
        expect(result).toEqual({ isFuriten: false, type: "furiten" });
    });

    it("rejects wrong type for f field", () => {
        const wire = { f: 1, t: EVENT_TYPE.FURITEN };
        expect(() => furitenSchema.parse(wire)).toThrow();
    });
});

describe("gameEndSchema", () => {
    it("parses valid wire payload with standings", () => {
        const wire = {
            nr: 8,
            st: [
                { fs: 42, s: 0, sc: 350 },
                { fs: 12, s: 1, sc: 250 },
                { fs: -18, s: 2, sc: 200 },
                { fs: -36, s: 3, sc: 200 },
            ],
            t: EVENT_TYPE.GAME_END,
            ws: 0,
        };
        const result = gameEndSchema.parse(wire);
        expect(result.type).toBe("game_end");
        expect(result.winnerSeat).toBe(0);
        expect(result.numRounds).toBe(8);
        expect(result.standings[0]).toEqual({ finalScore: 42, score: 35000, seat: 0 });
        expect(result.standings[3]).toEqual({ finalScore: -36, score: 20000, seat: 3 });
    });

    it("defaults numRounds to 0 when nr is absent", () => {
        const wire = {
            st: [{ fs: 0, s: 0, sc: 250 }],
            t: EVENT_TYPE.GAME_END,
            ws: 1,
        };
        const result = gameEndSchema.parse(wire);
        expect(result.numRounds).toBe(0);
    });
});
