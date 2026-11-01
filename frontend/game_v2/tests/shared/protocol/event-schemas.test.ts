import { describe, expect, it } from "vitest";

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
    readonly ai: number;
    readonly nm: string;
    readonly s: number;
}

interface WirePlayerView {
    readonly s: number;
    readonly sc: number;
    readonly tl?: readonly number[];
}

/** A game start's four seats in seat order: `named` at its own seat, a plain player at each other. */
function fourPlayers(named: WirePlayer): WirePlayer[] {
    return SEATS.map((seat) => (seat === named.s ? named : { ai: 0, nm: `P${seat}`, s: seat }));
}

/** A deal's four seats in seat order: `shown` at its own seat, the starting score at each other. */
function fourViews(shown: WirePlayerView): WirePlayerView[] {
    return SEATS.map((seat) => (seat === shown.s ? shown : { s: seat, sc: 250 }));
}

describe("gameStartedSchema", () => {
    it("parses realistic wire payload with 4 players", () => {
        const wire = {
            dd: [
                [3, 5],
                [2, 4],
            ],
            dl: 0,
            gid: "game-abc-123",
            gt: GAME_TYPE.HANCHAN,
            p: [
                { ai: 0, nm: "Alice", s: 0 },
                { ai: 0, nm: "Bob", s: 1 },
                { ai: 1, nm: "Charlie", s: 2 },
                { ai: 0, nm: "Diana", s: 3 },
            ],
            rsv: 10,
            t: EVENT_TYPE.GAME_STARTED,
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
            dd: [
                [1, 1],
                [1, 1],
            ],
            dl: 0,
            gid: "g1",
            gt: GAME_TYPE.TONPUSEN,
            p: fourPlayers({ ai: 1, nm: "Bot", s: 0 }),
            rsv: 10,
            t: EVENT_TYPE.GAME_STARTED,
        };
        const result = gameStartedSchema.parse(wire);
        expect(result.players[0].isAiPlayer).toBe(true);
    });

    it("reads the live copy's viewer seat and timer settings, null in a replay", () => {
        const wire = {
            dd: [
                [1, 1],
                [1, 1],
            ],
            dl: 0,
            gid: "g1",
            gt: GAME_TYPE.TONPUSEN,
            p: fourPlayers({ ai: 0, nm: "Alice", s: 2 }),
            rsv: 10,
            t: EVENT_TYPE.GAME_STARTED,
        };
        const timer = { bk: 20, gp: 3, mb: 60, md: 5, ra: 15, rb: 10, tb: 5 };
        const live = gameStartedSchema.parse({ ...wire, s: 2, tm: timer });
        const replay = gameStartedSchema.parse(wire);
        expect(live.gameType).toBe(GAME_TYPE.TONPUSEN);
        expect(live.seat).toBe(2);
        expect(live.timer).toEqual({
            bankSeconds: 20,
            baseTurnSeconds: 5,
            gameStartPauseSeconds: 3,
            maxBankSeconds: 60,
            meldDecisionSeconds: 5,
            roundAdvanceTimeoutSeconds: 15,
            roundBonusSeconds: 10,
        });
        expect(replay.seat).toBeNull();
        expect(replay.timer).toBeNull();
    });

    it("rejects missing required fields", () => {
        const wire = { gid: "g1", t: EVENT_TYPE.GAME_STARTED };
        expect(() => gameStartedSchema.parse(wire)).toThrow();
    });

    it("refuses a riichi stick value that is not a whole number of wire units", () => {
        const wire = {
            dd: [
                [1, 1],
                [1, 1],
            ],
            dl: 0,
            gid: "g1",
            gt: GAME_TYPE.TONPUSEN,
            p: fourPlayers({ ai: 0, nm: "Alice", s: 0 }),
            rsv: 15.5,
            t: EVENT_TYPE.GAME_STARTED,
        };
        expect(() => gameStartedSchema.parse(wire)).toThrow();
        expect(gameStartedSchema.parse({ ...wire, rsv: 15 }).riichiStickValue).toBe(1500);
    });

    it("refuses a game start or a deal that does not list each of the four seats once, in seat order", () => {
        const players = fourPlayers({ ai: 0, nm: "Alice", s: 0 });
        const views = fourViews({ s: 0, sc: 250 });
        const start = {
            dd: [
                [1, 1],
                [1, 1],
            ],
            dl: 0,
            gid: "g1",
            gt: GAME_TYPE.HANCHAN,
            p: players,
            rsv: 10,
            t: EVENT_TYPE.GAME_STARTED,
        };
        const deal = {
            cp: 0,
            di: [10],
            dl: 0,
            h: 0,
            n: 0,
            p: views,
            r: 0,
            rw: 1,
            t: 9,
            tr: 70,
            w: 0,
        };

        for (const p of [players.slice(0, 3), [players[1], players[0], ...players.slice(2)]]) {
            expect(() => gameStartedSchema.parse({ ...start, p })).toThrow(
                "the game start does not seat each of the four seats once, in seat order",
            );
        }
        expect(() => roundStartedSchema.parse({ ...deal, p: views.slice(1) })).toThrow(
            "the deal does not list each of the four seats once, in seat order",
        );
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
            rw: 1,
            s: 0,
            t: EVENT_TYPE.ROUND_STARTED,
            tr: 70,
            w: 0,
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
            cp: 0,
            di: [10],
            dl: 0,
            h: 0,
            mt: [0],
            n: 1,
            p: fourViews({ s: 0, sc: 250 }),
            r: 0,
            rw: 1,
            s: 0,
            t: EVENT_TYPE.ROUND_STARTED,
            tr: 70,
            w: 0,
        };
        const { rw: _roundInWind, ...unnamedRound } = deal;
        const { tr: _tilesRemaining, ...uncountedWall } = deal;

        expect(roundStartedSchema.parse(deal)).toMatchObject({
            roundInWind: 1,
            tilesRemaining: 70,
        });
        expect(() => roundStartedSchema.parse(unnamedRound)).toThrow();
        expect(() => roundStartedSchema.parse(uncountedWall)).toThrow();
    });

    it("decodes wire scores (250 -> 25000)", () => {
        const wire = {
            cp: 0,
            di: [10],
            dl: 0,
            h: 0,
            mt: [0],
            n: 1,
            p: fourViews({ s: 0, sc: 250 }),
            r: 0,
            rw: 1,
            s: 0,
            t: EVENT_TYPE.ROUND_STARTED,
            tr: 70,
            w: 0,
        };
        const result = roundStartedSchema.parse(wire);
        expect(result.players[0].score).toBe(25_000);
    });

    it("live format player tiles default to null", () => {
        const wire = {
            cp: 0,
            di: [10],
            dl: 0,
            h: 0,
            mt: [0],
            n: 1,
            p: fourViews({ s: 0, sc: 250 }),
            r: 0,
            rw: 1,
            s: 0,
            t: EVENT_TYPE.ROUND_STARTED,
            tr: 70,
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
                { s: 2, sc: 250, tl: [2, 6, 10, 14, 18, 22, 26, 30, 34, 38, 42, 46, 50] },
                { s: 3, sc: 250, tl: [3, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43, 47, 51] },
            ],
            r: 0,
            rw: 1,
            t: EVENT_TYPE.ROUND_STARTED,
            tr: 70,
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
            p: fourViews({ s: 0, sc: 300, tl: [0] }),
            r: 2,
            rw: 2,
            t: EVENT_TYPE.ROUND_STARTED,
            tr: 70,
            w: 1,
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
    it("decodes packed integer to seat + tileId beside the live wall left, refusing a draw that names no wall", () => {
        // d = seat * 136 + tileId = 1 * 136 + 42 = 178
        const wire = { d: 178, t: EVENT_TYPE.DRAW, tr: 69 };
        const { tr: _tilesRemaining, ...uncountedWall } = wire;
        const result = drawSchema.parse(wire);
        expect(() => drawSchema.parse(uncountedWall)).toThrow();
        expect(result.type).toBe("draw");
        expect(result.seat).toBe(1);
        expect(result.tileId).toBe(42);
        expect(result.tilesRemaining).toBe(69);
        expect(result.availableActions).toEqual([]);
    });

    it("parses available actions array", () => {
        const wire = {
            aa: [{ a: 1, tl: [5, 10, 15] }, { a: 2 }, { a: 4, tl: [9] }],
            d: 5,
            t: EVENT_TYPE.DRAW,
            tr: 69,
        };
        const result = drawSchema.parse(wire);
        expect(result.availableActions).toEqual([
            { action: 1, tileIds: [5, 10, 15] },
            { action: 2 },
            { action: 4, tileTypes: [9] },
        ]);
    });

    it.each([
        { aa: [{ a: 0 }], name: "a discard, which the server never offers" },
        { aa: [{ a: 3, tl: [40] }], name: "a kan of a tile id, not a tile type" },
        { aa: [{ a: 4, tl: [] }], name: "an added kan with no tile type" },
    ])("refuses an offer of $name", ({ aa }) => {
        expect(() => drawSchema.parse({ aa, d: 5, t: EVENT_TYPE.DRAW, tr: 69 })).toThrow();
    });

    it("defaults available actions to empty array when aa is absent", () => {
        const wire = { d: 0, t: EVENT_TYPE.DRAW, tr: 69 };
        const result = drawSchema.parse(wire);
        expect(result.availableActions).toEqual([]);
    });

    it("reads the turn's bank and a re-send's elapsed seconds, null without them", () => {
        const opening = drawSchema.parse({
            bk: 12.5,
            d: 0,
            el: 3.2,
            t: EVENT_TYPE.DRAW,
            tr: 69,
            wi: 4,
        });
        const plain = drawSchema.parse({ d: 0, t: EVENT_TYPE.DRAW, tr: 69 });
        expect(opening.bankSeconds).toBe(12.5);
        expect(opening.elapsedSeconds).toBe(3.2);
        expect(opening.waitId).toBe(4);
        expect(plain.bankSeconds).toBeNull();
        expect(plain.elapsedSeconds).toBeNull();
    });
});

describe("turnSchema", () => {
    it("reads the kuikae tile types and the turn's wait", () => {
        const result = turnSchema.parse({ bk: 20, kt: [4, 7], t: EVENT_TYPE.TURN, wi: 9 });
        expect(result).toEqual({
            bankSeconds: 20,
            elapsedSeconds: null,
            kuikaeTileTypes: [4, 7],
            type: "turn",
            waitId: 9,
        });
    });

    it("rejects a kuikae tile outside the 34 types", () => {
        expect(() => turnSchema.parse({ kt: [34], t: EVENT_TYPE.TURN })).toThrow();
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
        // meld_index = 6888 + 0 = 6888, value = 6888 * 4 + 0 = 27552
        const wire = { m: 27_552, t: EVENT_TYPE.MELD };
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
        const wire = { r: 2, s: 2, sc: 240, t: EVENT_TYPE.RIICHI_DECLARED };
        const result = riichiDeclaredSchema.parse(wire);
        expect(result).toEqual({
            riichiSticks: 2,
            score: 24_000,
            seat: 2,
            type: "riichi_declared",
        });
        expect(() => riichiDeclaredSchema.parse({ s: 2, t: EVENT_TYPE.RIICHI_DECLARED })).toThrow();
    });

    it("rejects invalid seat", () => {
        const wire = { r: 1, s: 5, sc: 240, t: EVENT_TYPE.RIICHI_DECLARED };
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
    it("parses valid wire payload, with the wait id the refused action echoed", () => {
        const wire = { cd: "not_your_turn", msg: "It's not your turn", t: EVENT_TYPE.ERROR, wi: 4 };
        const result = errorEventSchema.parse(wire);
        expect(result).toEqual({
            code: "not_your_turn",
            message: "It's not your turn",
            type: "error",
            waitId: 4,
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

function standing(seat: number): Record<string, number> {
    return { fs: 0, s: seat, sc: 250 };
}

describe("gameEndSchema", () => {
    it("parses valid wire payload with standings", () => {
        const wire = {
            ec: "target_reached",
            lb: 20,
            lr: 2,
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
        expect([result.numRounds, result.endCause]).toEqual([8, "target_reached"]);
        expect([result.leftoverRiichiBonus, result.leftoverRiichiSticks]).toEqual([2000, 2]);
        expect(result.standings[0]).toEqual({ finalScore: 42, score: 35_000, seat: 0 });
        expect(result.standings[3]).toEqual({ finalScore: -36, score: 20_000, seat: 3 });
    });

    it("refuses standings that rank a seat twice, in whatever order the server ranks them", () => {
        const wire = { ec: "length", lb: 0, lr: 0, nr: 8, t: EVENT_TYPE.GAME_END, ws: 1 };

        expect(gameEndSchema.parse({ ...wire, st: [1, 2, 3, 0].map(standing) }).winnerSeat).toBe(1);
        expect(() => gameEndSchema.parse({ ...wire, st: [1, 2, 3, 1].map(standing) })).toThrow(
            "rank each of the four seats once",
        );
    });
});
