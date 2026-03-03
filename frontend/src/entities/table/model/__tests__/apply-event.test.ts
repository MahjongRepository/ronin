import { describe, expect, test } from "vitest";

import { applyEvent } from "@/entities/table/model/apply-event";
import { createInitialTableState } from "@/entities/table/model/initial-state";
import { type ReplayEvent } from "@/entities/table/model/types";
import {
    type AbortiveDrawRoundEnd,
    type DiscardEvent,
    type DoraRevealedEvent,
    type DoubleRonRoundEnd,
    type DrawEvent,
    type ExhaustiveDrawRoundEnd,
    type GameEndEvent,
    type GameStartedEvent,
    type MeldEvent,
    type NagashiManganRoundEnd,
    ROUND_RESULT_TYPE,
    type RiichiDeclaredEvent,
    type RonRoundEnd,
    type RoundStartedEvent,
    type TsumoRoundEnd,
} from "@/shared/protocol";

function makeGameStartedEvent(overrides?: Partial<GameStartedEvent>): GameStartedEvent {
    return {
        dealerDice: [
            [2, 3],
            [4, 5],
        ],
        dealerSeat: 0,
        gameId: "test-game-1",
        players: [
            { isAiPlayer: false, name: "Alice", seat: 0 },
            { isAiPlayer: true, name: "Bot-1", seat: 1 },
            { isAiPlayer: true, name: "Bot-2", seat: 2 },
            { isAiPlayer: false, name: "Bob", seat: 3 },
        ],
        type: "game_started",
        ...overrides,
    };
}

function makeRoundStartedEvent(overrides?: Partial<RoundStartedEvent>): RoundStartedEvent {
    return {
        currentPlayerSeat: 0,
        dealerSeat: 0,
        dice: [3, 4],
        doraIndicators: [10],
        honbaSticks: 0,
        myTiles: null,
        players: [
            { score: 25000, seat: 0, tiles: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] },
            { score: 25000, seat: 1, tiles: [13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25] },
            { score: 25000, seat: 2, tiles: [26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38] },
            { score: 25000, seat: 3, tiles: [39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51] },
        ],
        riichiSticks: 0,
        roundNumber: 1,
        seat: null,
        type: "round_started",
        wind: 0,
        ...overrides,
    };
}

describe("applyEvent - game_started", () => {
    test("sets phase to pre_game with 4 players at score 0", () => {
        const state = createInitialTableState();
        const event = makeGameStartedEvent();
        const next = applyEvent(state, event);

        expect(next.phase).toBe("pre_game");
        expect(next.players).toHaveLength(4);
        for (const player of next.players) {
            expect(player.score).toBe(0);
        }
    });

    test("sets gameId and dealerSeat from event", () => {
        const state = createInitialTableState();
        const event = makeGameStartedEvent({ dealerSeat: 2, gameId: "abc-123" });
        const next = applyEvent(state, event);

        expect(next.gameId).toBe("abc-123");
        expect(next.dealerSeat).toBe(2);
    });

    test("sets isAiPlayer correctly from the ai flag", () => {
        const state = createInitialTableState();
        const event = makeGameStartedEvent();
        const next = applyEvent(state, event);

        expect(next.players[0].isAiPlayer).toBe(false);
        expect(next.players[1].isAiPlayer).toBe(true);
        expect(next.players[2].isAiPlayer).toBe(true);
        expect(next.players[3].isAiPlayer).toBe(false);
    });

    test("sets player names from event", () => {
        const state = createInitialTableState();
        const event = makeGameStartedEvent();
        const next = applyEvent(state, event);

        expect(next.players[0].name).toBe("Alice");
        expect(next.players[1].name).toBe("Bot-1");
        expect(next.players[3].name).toBe("Bob");
    });

    test("initializes players with empty hands, discards, and melds", () => {
        const state = createInitialTableState();
        const event = makeGameStartedEvent();
        const next = applyEvent(state, event);

        for (const player of next.players) {
            expect(player.tiles).toEqual([]);
            expect(player.discards).toEqual([]);
            expect(player.melds).toEqual([]);
            expect(player.drawnTileId).toBeNull();
            expect(player.isRiichi).toBe(false);
        }
    });

    test("does not mutate the input state", () => {
        const state = createInitialTableState();
        const event = makeGameStartedEvent();
        const next = applyEvent(state, event);

        expect(state.players).toEqual([]);
        expect(state.gameId).toBe("");
        expect(next).not.toBe(state);
    });
});

describe("applyEvent - round_started", () => {
    function stateAfterGameStarted(): ReturnType<typeof applyEvent> {
        return applyEvent(createInitialTableState(), makeGameStartedEvent());
    }

    test("populates tiles from player views and sets phase to in_round", () => {
        const state = stateAfterGameStarted();
        const event = makeRoundStartedEvent();
        const next = applyEvent(state, event);

        expect(next.phase).toBe("in_round");
        expect(next.players[0].tiles).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
        expect(next.players[1].tiles).toEqual([13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]);
    });

    test("sets round-level fields from event", () => {
        const state = stateAfterGameStarted();
        const event = makeRoundStartedEvent({
            doraIndicators: [10, 20],
            honbaSticks: 2,
            riichiSticks: 1,
            roundNumber: 3,
            wind: 1,
        });
        const next = applyEvent(state, event);

        expect(next.roundWind).toBe(1);
        expect(next.roundNumber).toBe(3);
        expect(next.honbaSticks).toBe(2);
        expect(next.riichiSticks).toBe(1);
        expect(next.doraIndicators).toEqual([10, 20]);
    });

    test("updates scores from player views", () => {
        const state = stateAfterGameStarted();
        const event = makeRoundStartedEvent({
            players: [
                { score: 30000, seat: 0, tiles: [0] },
                { score: 22000, seat: 1, tiles: [1] },
                { score: 18000, seat: 2, tiles: [2] },
                { score: 30000, seat: 3, tiles: [3] },
            ],
        });
        const next = applyEvent(state, event);

        expect(next.players[0].score).toBe(30000);
        expect(next.players[1].score).toBe(22000);
        expect(next.players[2].score).toBe(18000);
        expect(next.players[3].score).toBe(30000);
    });

    test("resets previous round state (discards, melds cleared)", () => {
        const state = stateAfterGameStarted();
        // Simulate a player with leftover round state
        const stateWithRoundData = {
            ...state,
            players: state.players.map((p) =>
                p.seat === 0
                    ? {
                          ...p,
                          discards: [{ isRiichi: false, isTsumogiri: false, tileId: 5 }],
                          drawnTileId: 7,
                          isRiichi: true,
                          melds: [
                              {
                                  calledTileId: 10,
                                  callerSeat: 0,
                                  fromSeat: 1,
                                  meldType: "pon" as const,
                                  tileIds: [8, 9, 10],
                              },
                          ],
                      }
                    : p,
            ),
        };

        const event = makeRoundStartedEvent();
        const next = applyEvent(stateWithRoundData, event);

        for (const player of next.players) {
            expect(player.discards).toEqual([]);
            expect(player.melds).toEqual([]);
            expect(player.isRiichi).toBe(false);
            expect(player.drawnTileId).toBeNull();
        }
    });

    test("handles null tiles in player view (null-guard)", () => {
        const state = stateAfterGameStarted();
        const event = makeRoundStartedEvent({
            players: [
                { score: 25000, seat: 0, tiles: null },
                { score: 25000, seat: 1, tiles: [1, 2, 3] },
                { score: 25000, seat: 2, tiles: null },
                { score: 25000, seat: 3, tiles: [4, 5, 6] },
            ],
        });
        const next = applyEvent(state, event);

        expect(next.players[0].tiles).toEqual([]);
        expect(next.players[1].tiles).toEqual([1, 2, 3]);
        expect(next.players[2].tiles).toEqual([]);
        expect(next.players[3].tiles).toEqual([4, 5, 6]);
    });

    test("sets dealerSeat and currentPlayerSeat from event", () => {
        const state = stateAfterGameStarted();
        const event = makeRoundStartedEvent({
            currentPlayerSeat: 2,
            dealerSeat: 2,
        });
        const next = applyEvent(state, event);

        expect(next.dealerSeat).toBe(2);
        expect(next.currentPlayerSeat).toBe(2);
    });

    test("does not mutate the input state", () => {
        const state = stateAfterGameStarted();
        const originalPlayers = state.players.map((p) => ({ ...p, tiles: [...p.tiles] }));
        const event = makeRoundStartedEvent();
        applyEvent(state, event);

        expect(state.players.map((p) => p.tiles)).toEqual(originalPlayers.map((p) => p.tiles));
        expect(state.phase).toBe("pre_game");
    });
});

function stateAfterRoundStarted() {
    const s1 = applyEvent(createInitialTableState(), makeGameStartedEvent());
    return applyEvent(s1, makeRoundStartedEvent());
}

function makeDrawEvent(overrides?: Partial<DrawEvent>): DrawEvent {
    return {
        availableActions: [],
        seat: 0,
        tileId: 52,
        type: "draw",
        ...overrides,
    };
}

function makeDiscardEvent(overrides?: Partial<DiscardEvent>): DiscardEvent {
    return {
        isRiichi: false,
        isTsumogiri: false,
        seat: 0,
        tileId: 52,
        type: "discard",
        ...overrides,
    };
}

describe("applyEvent - draw throws for invalid seat", () => {
    test("throws when no player matches the draw seat", () => {
        const state = stateAfterRoundStarted();
        const event = makeDrawEvent({ seat: 99, tileId: 52 });
        expect(() => applyEvent(state, event)).toThrow("No player found for seat 99");
    });
});

describe("applyEvent - discard throws for invalid seat", () => {
    test("throws when no player matches the discard seat", () => {
        const state = stateAfterRoundStarted();
        const event = makeDiscardEvent({ seat: 99, tileId: 52 });
        expect(() => applyEvent(state, event)).toThrow("No player found for seat 99");
    });
});

describe("applyEvent - draw", () => {
    test("adds tile to player's hand and sets drawnTileId", () => {
        const state = stateAfterRoundStarted();
        const event = makeDrawEvent({ seat: 0, tileId: 52 });
        const next = applyEvent(state, event);

        expect(next.players[0].tiles).toContain(52);
        expect(next.players[0].drawnTileId).toBe(52);
    });

    test("sets currentPlayerSeat to the drawing player", () => {
        const state = stateAfterRoundStarted();
        const event = makeDrawEvent({ seat: 2, tileId: 60 });
        const next = applyEvent(state, event);

        expect(next.currentPlayerSeat).toBe(2);
    });

    test("appends tile to end of existing tiles array", () => {
        const state = stateAfterRoundStarted();
        const originalTileCount = state.players[0].tiles.length;
        const event = makeDrawEvent({ seat: 0, tileId: 52 });
        const next = applyEvent(state, event);

        expect(next.players[0].tiles).toHaveLength(originalTileCount + 1);
        expect(next.players[0].tiles[next.players[0].tiles.length - 1]).toBe(52);
    });

    test("generates description with player name and tile name", () => {
        const state = stateAfterRoundStarted();
        // tileId 52 = red five pin (0p)
        const event = makeDrawEvent({ seat: 0, tileId: 52 });
        const next = applyEvent(state, event);

        expect(next.lastEventDescription).toBe("Alice drew 0p");
    });

    test("does not mutate the input state", () => {
        const state = stateAfterRoundStarted();
        const originalTiles = [...state.players[0].tiles];
        const event = makeDrawEvent({ seat: 0, tileId: 52 });
        applyEvent(state, event);

        expect(state.players[0].tiles).toEqual(originalTiles);
        expect(state.players[0].drawnTileId).toBeNull();
    });
});

describe("applyEvent - discard", () => {
    test("removes tile from player's hand and clears drawnTileId", () => {
        const state = stateAfterRoundStarted();
        // First draw a tile, then discard it
        const afterDraw = applyEvent(state, makeDrawEvent({ seat: 0, tileId: 52 }));
        const event = makeDiscardEvent({ seat: 0, tileId: 52 });
        const next = applyEvent(afterDraw, event);

        expect(next.players[0].tiles).not.toContain(52);
        expect(next.players[0].drawnTileId).toBeNull();
    });

    test("appends to player's discards array", () => {
        const state = stateAfterRoundStarted();
        const event = makeDiscardEvent({ seat: 0, tileId: 0 });
        const next = applyEvent(state, event);

        expect(next.players[0].discards).toHaveLength(1);
        expect(next.players[0].discards[0]).toEqual({
            isRiichi: false,
            isTsumogiri: false,
            tileId: 0,
        });
    });

    test("preserves tsumogiri flag on discard record", () => {
        const state = stateAfterRoundStarted();
        const event = makeDiscardEvent({ isTsumogiri: true, seat: 0, tileId: 0 });
        const next = applyEvent(state, event);

        expect(next.players[0].discards[0].isTsumogiri).toBe(true);
    });

    test("preserves riichi flag on discard record", () => {
        const state = stateAfterRoundStarted();
        const event = makeDiscardEvent({ isRiichi: true, seat: 0, tileId: 0 });
        const next = applyEvent(state, event);

        expect(next.players[0].discards[0].isRiichi).toBe(true);
    });

    test("generates description with player name and tile name", () => {
        const state = stateAfterRoundStarted();
        // tileId 0 = 1m
        const event = makeDiscardEvent({ seat: 0, tileId: 0 });
        const next = applyEvent(state, event);

        expect(next.lastEventDescription).toBe("Alice discarded 1m");
    });

    test("does not mutate the input state", () => {
        const state = stateAfterRoundStarted();
        const originalTiles = [...state.players[0].tiles];
        const originalDiscards = [...state.players[0].discards];
        const event = makeDiscardEvent({ seat: 0, tileId: 0 });
        applyEvent(state, event);

        expect(state.players[0].tiles).toEqual(originalTiles);
        expect(state.players[0].discards).toEqual(originalDiscards);
    });

    test("accumulates multiple discards", () => {
        const state = stateAfterRoundStarted();
        const after1 = applyEvent(state, makeDiscardEvent({ seat: 0, tileId: 0 }));
        const after2 = applyEvent(after1, makeDiscardEvent({ seat: 0, tileId: 1 }));

        expect(after2.players[0].discards).toHaveLength(2);
        expect(after2.players[0].discards[0].tileId).toBe(0);
        expect(after2.players[0].discards[1].tileId).toBe(1);
    });
});

function makeRiichiDeclaredEvent(overrides?: Partial<RiichiDeclaredEvent>): RiichiDeclaredEvent {
    return {
        seat: 0,
        type: "riichi_declared",
        ...overrides,
    };
}

function makeDoraRevealedEvent(overrides?: Partial<DoraRevealedEvent>): DoraRevealedEvent {
    return {
        tileId: 20,
        type: "dora_revealed",
        ...overrides,
    };
}

function makeGameEndEvent(overrides?: Partial<GameEndEvent>): GameEndEvent {
    return {
        numRounds: 8,
        standings: [
            { finalScore: 45.0, score: 35000, seat: 0 },
            { finalScore: 12.0, score: 22000, seat: 1 },
            { finalScore: -8.0, score: 18000, seat: 2 },
            { finalScore: -49.0, score: 25000, seat: 3 },
        ],
        type: "game_end",
        winnerSeat: 0,
        ...overrides,
    };
}

describe("applyEvent - riichi_declared", () => {
    test("marks player as riichi", () => {
        const state = stateAfterRoundStarted();
        expect(state.players[1].isRiichi).toBe(false);

        const next = applyEvent(state, makeRiichiDeclaredEvent({ seat: 1 }));

        expect(next.players[1].isRiichi).toBe(true);
    });

    test("does not affect other players", () => {
        const state = stateAfterRoundStarted();
        const next = applyEvent(state, makeRiichiDeclaredEvent({ seat: 1 }));

        expect(next.players[0].isRiichi).toBe(false);
        expect(next.players[2].isRiichi).toBe(false);
        expect(next.players[3].isRiichi).toBe(false);
    });

    test("generates description with player name", () => {
        const state = stateAfterRoundStarted();
        const next = applyEvent(state, makeRiichiDeclaredEvent({ seat: 0 }));

        expect(next.lastEventDescription).toBe("Alice declared riichi");
    });

    test("does not mutate the input state", () => {
        const state = stateAfterRoundStarted();
        applyEvent(state, makeRiichiDeclaredEvent({ seat: 0 }));

        expect(state.players[0].isRiichi).toBe(false);
    });
});

describe("applyEvent - dora_revealed", () => {
    test("appends tile to dora indicators", () => {
        const state = stateAfterRoundStarted();
        // round_started sets doraIndicators to [10]
        expect(state.doraIndicators).toEqual([10]);

        const next = applyEvent(state, makeDoraRevealedEvent({ tileId: 20 }));

        expect(next.doraIndicators).toEqual([10, 20]);
    });

    test("accumulates multiple dora reveals", () => {
        const state = stateAfterRoundStarted();
        const after1 = applyEvent(state, makeDoraRevealedEvent({ tileId: 20 }));
        const after2 = applyEvent(after1, makeDoraRevealedEvent({ tileId: 30 }));

        expect(after2.doraIndicators).toEqual([10, 20, 30]);
    });

    test("generates description with tile name", () => {
        const state = stateAfterRoundStarted();
        // tileId 20 = 6m (tile 20 / 4 = 5, type index 5 = 6m)
        const next = applyEvent(state, makeDoraRevealedEvent({ tileId: 20 }));

        expect(next.lastEventDescription).toMatch(/New dora indicator: /);
    });

    test("does not mutate the input state", () => {
        const state = stateAfterRoundStarted();
        const originalDora = [...state.doraIndicators];
        applyEvent(state, makeDoraRevealedEvent({ tileId: 20 }));

        expect(state.doraIndicators).toEqual(originalDora);
    });
});

describe("applyEvent - game_end", () => {
    test("sets phase to game_ended", () => {
        const state = stateAfterRoundStarted();
        const next = applyEvent(state, makeGameEndEvent());

        expect(next.phase).toBe("game_ended");
    });

    test("updates scores from standings array", () => {
        const state = stateAfterRoundStarted();
        const next = applyEvent(state, makeGameEndEvent());

        expect(next.players[0].score).toBe(35000);
        expect(next.players[1].score).toBe(22000);
        expect(next.players[2].score).toBe(18000);
        expect(next.players[3].score).toBe(25000);
    });

    test("generates description with winner name", () => {
        const state = stateAfterRoundStarted();
        const next = applyEvent(state, makeGameEndEvent({ winnerSeat: 0 }));

        expect(next.lastEventDescription).toBe("Game over - Winner: Alice");
    });

    test("handles winner at different seat", () => {
        const state = stateAfterRoundStarted();
        const next = applyEvent(state, makeGameEndEvent({ winnerSeat: 3 }));

        expect(next.lastEventDescription).toBe("Game over - Winner: Bob");
    });

    test("does not mutate the input state", () => {
        const state = stateAfterRoundStarted();
        const originalScores = state.players.map((p) => p.score);
        applyEvent(state, makeGameEndEvent());

        expect(state.players.map((p) => p.score)).toEqual(originalScores);
        expect(state.phase).toBe("in_round");
    });
});

// --- round_end helpers and tests ---

function makeTsumoRoundEnd(overrides?: Partial<TsumoRoundEnd>): TsumoRoundEnd {
    return {
        closedTiles: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        handResult: { fu: 30, han: 4, yaku: [{ han: 1, yakuId: 0 }] },
        melds: [],
        paoSeat: null,
        resultType: ROUND_RESULT_TYPE.TSUMO,
        riichiSticksCollected: 0,
        scoreChanges: { "0": 10000, "1": -3000, "2": -3000, "3": -4000 },
        scores: { "0": 35000, "1": 22000, "2": 18000, "3": 25000 },
        type: "round_end",
        uraDoraIndicators: null,
        winnerSeat: 0,
        winningTile: 52,
        ...overrides,
    };
}

function makeRonRoundEnd(overrides?: Partial<RonRoundEnd>): RonRoundEnd {
    return {
        closedTiles: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        handResult: { fu: 30, han: 3, yaku: [{ han: 1, yakuId: 0 }] },
        loserSeat: 1,
        melds: [],
        paoSeat: null,
        resultType: ROUND_RESULT_TYPE.RON,
        riichiSticksCollected: 0,
        scoreChanges: { "0": 8000, "1": -8000, "2": 0, "3": 0 },
        scores: { "0": 33000, "1": 17000, "2": 25000, "3": 25000 },
        type: "round_end",
        uraDoraIndicators: null,
        winnerSeat: 0,
        winningTile: 52,
        ...overrides,
    };
}

function makeDoubleRonRoundEnd(overrides?: Partial<DoubleRonRoundEnd>): DoubleRonRoundEnd {
    return {
        loserSeat: 1,
        resultType: ROUND_RESULT_TYPE.DOUBLE_RON,
        scoreChanges: { "0": 8000, "1": -16000, "2": 8000, "3": 0 },
        scores: { "0": 33000, "1": 9000, "2": 33000, "3": 25000 },
        type: "round_end",
        winners: [
            {
                closedTiles: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                handResult: { fu: 30, han: 3, yaku: [{ han: 1, yakuId: 0 }] },
                melds: [],
                paoSeat: null,
                riichiSticksCollected: 0,
                uraDoraIndicators: null,
                winnerSeat: 0,
            },
            {
                closedTiles: [26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38],
                handResult: { fu: 30, han: 3, yaku: [{ han: 1, yakuId: 0 }] },
                melds: [],
                paoSeat: null,
                riichiSticksCollected: 0,
                uraDoraIndicators: null,
                winnerSeat: 2,
            },
        ],
        winningTile: 52,
        ...overrides,
    };
}

function makeExhaustiveDrawRoundEnd(
    overrides?: Partial<ExhaustiveDrawRoundEnd>,
): ExhaustiveDrawRoundEnd {
    return {
        notenSeats: [1, 3],
        resultType: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
        scoreChanges: { "0": 1500, "1": -1500, "2": 1500, "3": -1500 },
        scores: { "0": 26500, "1": 23500, "2": 26500, "3": 23500 },
        tenpaiHands: [
            { closedTiles: [0, 1, 2], melds: [], seat: 0 },
            { closedTiles: [26, 27, 28], melds: [], seat: 2 },
        ],
        tenpaiSeats: [0, 2],
        type: "round_end",
        ...overrides,
    };
}

function makeAbortiveDrawRoundEnd(overrides?: Partial<AbortiveDrawRoundEnd>): AbortiveDrawRoundEnd {
    return {
        reason: "four_winds",
        resultType: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
        scoreChanges: { "0": 0, "1": 0, "2": 0, "3": 0 },
        scores: { "0": 25000, "1": 25000, "2": 25000, "3": 25000 },
        seat: null,
        type: "round_end",
        ...overrides,
    };
}

function makeNagashiManganRoundEnd(
    overrides?: Partial<NagashiManganRoundEnd>,
): NagashiManganRoundEnd {
    return {
        notenSeats: [1, 2, 3],
        qualifyingSeats: [0],
        resultType: ROUND_RESULT_TYPE.NAGASHI_MANGAN,
        scoreChanges: { "0": 12000, "1": -4000, "2": -4000, "3": -4000 },
        scores: { "0": 37000, "1": 21000, "2": 21000, "3": 21000 },
        tenpaiHands: [{ closedTiles: [0, 1, 2], melds: [], seat: 0 }],
        tenpaiSeats: [0],
        type: "round_end",
        ...overrides,
    };
}

describe("applyEvent - round_end", () => {
    describe("tsumo", () => {
        test("updates scores and sets phase to round_ended", () => {
            const state = stateAfterRoundStarted();
            const event = makeTsumoRoundEnd();
            const next = applyEvent(state, event);

            expect(next.phase).toBe("round_ended");
            expect(next.players[0].score).toBe(35000);
            expect(next.players[1].score).toBe(22000);
            expect(next.players[2].score).toBe(18000);
            expect(next.players[3].score).toBe(25000);
        });

        test("description includes winner name", () => {
            const state = stateAfterRoundStarted();
            const event = makeTsumoRoundEnd({ winnerSeat: 0 });
            const next = applyEvent(state, event);

            expect(next.lastEventDescription).toBe("Tsumo by Alice");
        });
    });

    describe("ron", () => {
        test("description includes winner and loser names", () => {
            const state = stateAfterRoundStarted();
            const event = makeRonRoundEnd({ loserSeat: 1, winnerSeat: 0 });
            const next = applyEvent(state, event);

            expect(next.lastEventDescription).toBe("Ron by Alice from Bot-1");
        });

        test("updates scores from scores map", () => {
            const state = stateAfterRoundStarted();
            const event = makeRonRoundEnd();
            const next = applyEvent(state, event);

            expect(next.players[0].score).toBe(33000);
            expect(next.players[1].score).toBe(17000);
        });
    });

    describe("double_ron", () => {
        test("reads from winners array and includes both names", () => {
            const state = stateAfterRoundStarted();
            const event = makeDoubleRonRoundEnd();
            const next = applyEvent(state, event);

            expect(next.lastEventDescription).toBe("Double ron by Alice and Bot-2");
        });

        test("updates scores correctly", () => {
            const state = stateAfterRoundStarted();
            const event = makeDoubleRonRoundEnd();
            const next = applyEvent(state, event);

            expect(next.players[0].score).toBe(33000);
            expect(next.players[1].score).toBe(9000);
            expect(next.players[2].score).toBe(33000);
        });
    });

    describe("exhaustive_draw", () => {
        test("sets correct description", () => {
            const state = stateAfterRoundStarted();
            const event = makeExhaustiveDrawRoundEnd();
            const next = applyEvent(state, event);

            expect(next.lastEventDescription).toBe("Exhaustive draw");
        });

        test("updates scores", () => {
            const state = stateAfterRoundStarted();
            const event = makeExhaustiveDrawRoundEnd();
            const next = applyEvent(state, event);

            expect(next.players[0].score).toBe(26500);
            expect(next.players[1].score).toBe(23500);
        });
    });

    describe("abortive_draw", () => {
        test("includes reason string in description", () => {
            const state = stateAfterRoundStarted();
            const event = makeAbortiveDrawRoundEnd({ reason: "four_winds" });
            const next = applyEvent(state, event);

            expect(next.lastEventDescription).toBe("Abortive draw: four_winds");
        });

        test("with nine_terminals reason", () => {
            const state = stateAfterRoundStarted();
            const event = makeAbortiveDrawRoundEnd({ reason: "nine_terminals" });
            const next = applyEvent(state, event);

            expect(next.lastEventDescription).toBe("Abortive draw: nine_terminals");
        });
    });

    describe("nagashi_mangan", () => {
        test("includes qualifying player names", () => {
            const state = stateAfterRoundStarted();
            const event = makeNagashiManganRoundEnd({ qualifyingSeats: [0] });
            const next = applyEvent(state, event);

            expect(next.lastEventDescription).toBe("Nagashi mangan by Alice");
        });

        test("with multiple qualifying players", () => {
            const state = stateAfterRoundStarted();
            const event = makeNagashiManganRoundEnd({ qualifyingSeats: [0, 3] });
            const next = applyEvent(state, event);

            expect(next.lastEventDescription).toBe("Nagashi mangan by Alice and Bob");
        });

        test("updates scores", () => {
            const state = stateAfterRoundStarted();
            const event = makeNagashiManganRoundEnd();
            const next = applyEvent(state, event);

            expect(next.players[0].score).toBe(37000);
            expect(next.players[1].score).toBe(21000);
        });
    });

    test("does not mutate the input state", () => {
        const state = stateAfterRoundStarted();
        const originalScores = state.players.map((p) => p.score);
        applyEvent(state, makeTsumoRoundEnd());

        expect(state.players.map((p) => p.score)).toEqual(originalScores);
        expect(state.phase).toBe("in_round");
    });
});

describe("applyEvent - round_end result data", () => {
    test("tsumo populates single winner with correct hand data", () => {
        const state = stateAfterRoundStarted();
        const next = applyEvent(
            state,
            makeTsumoRoundEnd({ melds: [12345], winnerSeat: 0, winningTile: 52 }),
        );

        expect(next.roundEndResult).not.toBeNull();
        expect(next.roundEndResult!.resultType).toBe(ROUND_RESULT_TYPE.TSUMO);
        expect(next.roundEndResult!.winners).toHaveLength(1);

        const [winner] = next.roundEndResult!.winners;
        expect(winner.seat).toBe(0);
        expect(winner.melds).toEqual([12345]);
        expect(winner.winningTile).toBe(52);
    });

    test("tsumo populates yaku list and han/fu totals", () => {
        const state = stateAfterRoundStarted();
        const event = makeTsumoRoundEnd({
            handResult: {
                fu: 30,
                han: 4,
                yaku: [
                    { han: 1, yakuId: 0 },
                    { han: 1, yakuId: 1 },
                    { han: 1, yakuId: 12 },
                    { han: 1, yakuId: 120 },
                ],
            },
        });
        const next = applyEvent(state, event);
        const [winner] = next.roundEndResult!.winners;

        expect(winner.handResult.han).toBe(4);
        expect(winner.handResult.fu).toBe(30);
        expect(winner.handResult.yaku).toHaveLength(4);
    });

    test("tsumo populates scoreChanges", () => {
        const state = stateAfterRoundStarted();
        const event = makeTsumoRoundEnd({
            scoreChanges: { "0": 10000, "1": -3000, "2": -3000, "3": -4000 },
        });
        const next = applyEvent(state, event);

        expect(next.roundEndResult!.scoreChanges).toEqual({
            "0": 10000,
            "1": -3000,
            "2": -3000,
            "3": -4000,
        });
    });

    test("ron populates winner and loserSeat", () => {
        const state = stateAfterRoundStarted();
        const event = makeRonRoundEnd({
            closedTiles: [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
            loserSeat: 3,
            winnerSeat: 1,
            winningTile: 60,
        });
        const next = applyEvent(state, event);

        expect(next.roundEndResult!.resultType).toBe(ROUND_RESULT_TYPE.RON);
        expect(next.roundEndResult!.loserSeat).toBe(3);
        expect(next.roundEndResult!.winners).toHaveLength(1);

        const [winner] = next.roundEndResult!.winners;
        expect(winner.seat).toBe(1);
        expect(winner.winningTile).toBe(60);
    });

    test("double ron populates two winners with loserSeat", () => {
        const state = stateAfterRoundStarted();
        const event = makeDoubleRonRoundEnd();
        const next = applyEvent(state, event);

        expect(next.roundEndResult!.resultType).toBe(ROUND_RESULT_TYPE.DOUBLE_RON);
        expect(next.roundEndResult!.loserSeat).toBe(1);
        expect(next.roundEndResult!.winners).toHaveLength(2);

        const [w1, w2] = next.roundEndResult!.winners;
        expect(w1.seat).toBe(0);
        expect(w2.seat).toBe(2);
    });

    test("double ron winners share the same winning tile", () => {
        const state = stateAfterRoundStarted();
        const next = applyEvent(state, makeDoubleRonRoundEnd());

        const [w1, w2] = next.roundEndResult!.winners;
        expect(w1.winningTile).toBe(52);
        expect(w2.winningTile).toBe(52);
        expect(w1.closedTiles).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
        expect(w2.closedTiles).toEqual([26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38]);
    });

    test("exhaustive draw has empty winners array", () => {
        const state = stateAfterRoundStarted();
        const event = makeExhaustiveDrawRoundEnd();
        const next = applyEvent(state, event);

        expect(next.roundEndResult!.resultType).toBe(ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW);
        expect(next.roundEndResult!.winners).toEqual([]);
        expect(next.roundEndResult!.scoreChanges).toEqual({
            "0": 1500,
            "1": -1500,
            "2": 1500,
            "3": -1500,
        });
    });

    test("abortive draw has empty winners array", () => {
        const state = stateAfterRoundStarted();
        const event = makeAbortiveDrawRoundEnd();
        const next = applyEvent(state, event);

        expect(next.roundEndResult!.resultType).toBe(ROUND_RESULT_TYPE.ABORTIVE_DRAW);
        expect(next.roundEndResult!.winners).toEqual([]);
    });

    test("nagashi mangan has empty winners array", () => {
        const state = stateAfterRoundStarted();
        const event = makeNagashiManganRoundEnd();
        const next = applyEvent(state, event);

        expect(next.roundEndResult!.resultType).toBe(ROUND_RESULT_TYPE.NAGASHI_MANGAN);
        expect(next.roundEndResult!.winners).toEqual([]);
    });
});

describe("applyEvent - game_end result data", () => {
    test("populates gameEndResult with standings and finalScore", () => {
        const state = stateAfterRoundStarted();
        const event = makeGameEndEvent({
            standings: [
                { finalScore: 45.0, score: 35000, seat: 0 },
                { finalScore: 12.0, score: 22000, seat: 1 },
                { finalScore: -8.0, score: 18000, seat: 2 },
                { finalScore: -49.0, score: 25000, seat: 3 },
            ],
            winnerSeat: 0,
        });
        const next = applyEvent(state, event);

        expect(next.gameEndResult).not.toBeNull();
        expect(next.gameEndResult!.winnerSeat).toBe(0);
        expect(next.gameEndResult!.standings).toEqual([
            { finalScore: 45.0, score: 35000, seat: 0 },
            { finalScore: 12.0, score: 22000, seat: 1 },
            { finalScore: -8.0, score: 18000, seat: 2 },
            { finalScore: -49.0, score: 25000, seat: 3 },
        ]);
    });
});

describe("applyEvent - result clearing", () => {
    test("round_started clears roundEndResult", () => {
        const state = stateAfterRoundStarted();
        const roundEndState = applyEvent(state, makeTsumoRoundEnd());
        expect(roundEndState.roundEndResult).not.toBeNull();

        const nextRoundState = applyEvent(roundEndState, makeRoundStartedEvent());
        expect(nextRoundState.roundEndResult).toBeNull();
    });

    test("game_end clears stale roundEndResult", () => {
        const state = stateAfterRoundStarted();
        const roundEndState = applyEvent(state, makeTsumoRoundEnd());
        expect(roundEndState.roundEndResult).not.toBeNull();

        const gameEndState = applyEvent(roundEndState, makeGameEndEvent());
        expect(gameEndState.roundEndResult).toBeNull();
        expect(gameEndState.gameEndResult).not.toBeNull();
    });

    test("game_started clears both roundEndResult and gameEndResult", () => {
        const state = stateAfterRoundStarted();
        const roundEndState = applyEvent(state, makeTsumoRoundEnd());
        const gameEndState = applyEvent(roundEndState, makeGameEndEvent());
        expect(gameEndState.roundEndResult).toBeNull();
        expect(gameEndState.gameEndResult).not.toBeNull();

        const newGameState = applyEvent(gameEndState, makeGameStartedEvent());
        expect(newGameState.roundEndResult).toBeNull();
        expect(newGameState.gameEndResult).toBeNull();
    });
});

// --- full event sequence integration helpers ---
// Builds a realistic event sequence covering all 9 replay event types:
// game_started -> round_started -> draw -> discard -> meld (pon) ->
// riichi_declared -> discard (riichi) -> dora_revealed -> round_end (tsumo) -> game_end

function makeIntegrationSetupEvents() {
    const gameStarted: GameStartedEvent = {
        dealerDice: [
            [2, 3],
            [4, 5],
        ],
        dealerSeat: 0,
        gameId: "integration-test",
        players: [
            { isAiPlayer: false, name: "Alice", seat: 0 },
            { isAiPlayer: false, name: "Bob", seat: 1 },
            { isAiPlayer: true, name: "Bot-1", seat: 2 },
            { isAiPlayer: true, name: "Bot-2", seat: 3 },
        ],
        type: "game_started",
    };

    const roundStarted: RoundStartedEvent = {
        currentPlayerSeat: 0,
        dealerSeat: 0,
        dice: [3, 4],
        doraIndicators: [10],
        honbaSticks: 0,
        myTiles: null,
        players: [
            { score: 25000, seat: 0, tiles: [0, 4, 5, 6, 7, 8, 9, 10, 11, 53, 54, 55, 56] },
            { score: 25000, seat: 1, tiles: [1, 2, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 57] },
            { score: 25000, seat: 2, tiles: [26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38] },
            { score: 25000, seat: 3, tiles: [39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51] },
        ],
        riichiSticks: 0,
        roundNumber: 1,
        seat: null,
        type: "round_started",
        wind: 0,
    };

    return { gameStarted, roundStarted };
}

function makeIntegrationMidGameEvents() {
    // Dealer (seat 0) draws tile 52
    const draw: DrawEvent = {
        availableActions: [],
        seat: 0,
        tileId: 52,
        type: "draw",
    };

    // Dealer discards tile 0 (1m) from their hand
    const discard: DiscardEvent = {
        isRiichi: false,
        isTsumogiri: false,
        seat: 0,
        tileId: 0,
        type: "discard",
    };

    // Seat 1 calls pon on tile 0 (1m) using tiles [1, 2] from hand + [0] called
    const meld: MeldEvent = {
        calledTileId: 0,
        callerSeat: 1,
        fromSeat: 0,
        meldType: "pon",
        tileIds: [1, 2, 0],
        type: "meld",
    };

    // Seat 1 discards tile 16 after the pon
    const discardAfterMeld: DiscardEvent = {
        isRiichi: false,
        isTsumogiri: false,
        seat: 1,
        tileId: 16,
        type: "discard",
    };

    return { discard, discardAfterMeld, draw, meld };
}

function makeIntegrationLateGameEvents() {
    // Seat 2 draws and declares riichi
    const drawSeat2: DrawEvent = {
        availableActions: [],
        seat: 2,
        tileId: 58,
        type: "draw",
    };

    const riichiDeclared: RiichiDeclaredEvent = {
        seat: 2,
        type: "riichi_declared",
    };

    const riichiDiscard: DiscardEvent = {
        isRiichi: true,
        isTsumogiri: false,
        seat: 2,
        tileId: 26,
        type: "discard",
    };

    const doraRevealed: DoraRevealedEvent = {
        tileId: 60,
        type: "dora_revealed",
    };

    return { doraRevealed, drawSeat2, riichiDeclared, riichiDiscard };
}

function makeIntegrationEndEvents() {
    // Round ends with tsumo by seat 0
    const roundEnd: TsumoRoundEnd = {
        closedTiles: [4, 5, 6, 7, 8, 9, 10, 11, 53, 54, 55, 56, 52],
        handResult: { fu: 30, han: 4, yaku: [{ han: 1, yakuId: 0 }] },
        melds: [],
        paoSeat: null,
        resultType: ROUND_RESULT_TYPE.TSUMO,
        riichiSticksCollected: 0,
        scoreChanges: { "0": 12000, "1": -4000, "2": -4000, "3": -4000 },
        scores: { "0": 37000, "1": 21000, "2": 21000, "3": 21000 },
        type: "round_end",
        uraDoraIndicators: null,
        winnerSeat: 0,
        winningTile: 52,
    };

    // Game ends
    const gameEnd: GameEndEvent = {
        numRounds: 1,
        standings: [
            { finalScore: 47.0, score: 37000, seat: 0 },
            { finalScore: -9.0, score: 21000, seat: 1 },
            { finalScore: -9.0, score: 21000, seat: 2 },
            { finalScore: -29.0, score: 21000, seat: 3 },
        ],
        type: "game_end",
        winnerSeat: 0,
    };

    return { gameEnd, roundEnd };
}

function buildFullEventSequence(): ReplayEvent[] {
    const { gameStarted, roundStarted } = makeIntegrationSetupEvents();
    const { discard, discardAfterMeld, draw, meld } = makeIntegrationMidGameEvents();
    const { doraRevealed, drawSeat2, riichiDeclared, riichiDiscard } =
        makeIntegrationLateGameEvents();
    const { gameEnd, roundEnd } = makeIntegrationEndEvents();

    return [
        gameStarted,
        roundStarted,
        draw,
        discard,
        meld,
        discardAfterMeld,
        drawSeat2,
        riichiDeclared,
        riichiDiscard,
        doraRevealed,
        roundEnd,
        gameEnd,
    ];
}

function replayAllEvents(events: ReplayEvent[]) {
    const states: ReturnType<typeof applyEvent>[] = [createInitialTableState()];
    for (const event of events) {
        const prev = states[states.length - 1];
        states.push(applyEvent(prev, event));
    }
    return states;
}

function replayToFinalState() {
    const events = buildFullEventSequence();
    let state = createInitialTableState();
    for (const event of events) {
        state = applyEvent(state, event);
    }
    return state;
}

describe("applyEvent - full event sequence integration", () => {
    test("final state has correct game-level fields", () => {
        const state = replayToFinalState();

        expect(state.gameId).toBe("integration-test");
        expect(state.phase).toBe("game_ended");
        expect(state.lastEventDescription).toBe("Game over - Winner: Alice");
    });

    test("final state has correct scores from game_end standings", () => {
        const state = replayToFinalState();

        expect(state.players[0].score).toBe(37000);
        expect(state.players[1].score).toBe(21000);
        expect(state.players[2].score).toBe(21000);
        expect(state.players[3].score).toBe(21000);
    });

    test("final state preserves player names and AI flags", () => {
        const state = replayToFinalState();

        expect(state.players[0].name).toBe("Alice");
        expect(state.players[1].name).toBe("Bob");
        expect(state.players[2].isAiPlayer).toBe(true);
        expect(state.players[3].isAiPlayer).toBe(true);
    });

    describe("intermediate states reflect each event correctly", () => {
        function getAllStates() {
            return replayAllEvents(buildFullEventSequence());
        }

        test("produces correct number of states", () => {
            const states = getAllStates();
            expect(states).toHaveLength(13);
        });

        test("game_started sets pre_game phase with 4 players", () => {
            const states = getAllStates();
            expect(states[1].phase).toBe("pre_game");
            expect(states[1].players).toHaveLength(4);
        });

        test("round_started sets in_round phase with tiles and dora", () => {
            const states = getAllStates();

            expect(states[2].phase).toBe("in_round");
            expect(states[2].players[0].tiles).toHaveLength(13);
            expect(states[2].roundWind).toBe(0);
            expect(states[2].doraIndicators).toEqual([10]);
        });

        test("draw adds tile to hand and sets drawnTileId", () => {
            const states = getAllStates();

            expect(states[3].players[0].tiles).toHaveLength(14);
            expect(states[3].players[0].tiles).toContain(52);
            expect(states[3].players[0].drawnTileId).toBe(52);
        });

        test("discard removes tile and adds to discards", () => {
            const states = getAllStates();

            expect(states[4].players[0].tiles).toHaveLength(13);
            expect(states[4].players[0].tiles).not.toContain(0);
            expect(states[4].players[0].discards).toHaveLength(1);
            expect(states[4].players[0].discards[0].tileId).toBe(0);
        });

        test("meld creates pon and marks discard as claimed", () => {
            const states = getAllStates();

            expect(states[5].players[1].melds).toHaveLength(1);
            expect(states[5].players[1].melds[0].meldType).toBe("pon");
            expect(states[5].players[1].tiles).not.toContain(1);
            expect(states[5].players[1].tiles).not.toContain(2);
            expect(states[5].players[0].discards[0].claimed).toBe(true);
        });

        test("riichi, dora, round_end, and game_end transition correctly", () => {
            const states = getAllStates();

            expect(states[8].players[2].isRiichi).toBe(true);
            expect(states[9].players[2].discards).toHaveLength(1);
            expect(states[9].players[2].discards[0].isRiichi).toBe(true);
            expect(states[10].doraIndicators).toEqual([10, 60]);
            expect(states[11].phase).toBe("round_ended");
            expect(states[11].players[0].score).toBe(37000);
            expect(states[12].phase).toBe("game_ended");
        });
    });

    test("intermediate states are not mutated by subsequent events", () => {
        const states = replayAllEvents(buildFullEventSequence());

        // Snapshot key values from early states
        const [, , stateAfterRound, stateAfterDraw] = states;
        const seat0TilesAfterRound = [...stateAfterRound.players[0].tiles];
        const seat0DiscardsAfterRound = [...stateAfterRound.players[0].discards];

        // These should not have been mutated by later events (draw, discard, meld, etc.)
        expect(stateAfterRound.players[0].tiles).toEqual(seat0TilesAfterRound);
        expect(stateAfterRound.players[0].discards).toEqual(seat0DiscardsAfterRound);
        expect(stateAfterRound.phase).toBe("in_round");
        expect(stateAfterRound.doraIndicators).toEqual([10]);

        // State after draw should not have been mutated by the subsequent discard
        expect(stateAfterDraw.players[0].tiles).toContain(52);
        expect(stateAfterDraw.players[0].drawnTileId).toBe(52);
    });
});
