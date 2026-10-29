import { assert, describe, expect, test } from "vitest";

import {
    makeAbortiveDrawRoundEnd,
    makeDiscardEvent,
    makeDoraRevealedEvent,
    makeDoubleRonRoundEnd,
    makeDrawEvent,
    makeExhaustiveDrawRoundEnd,
    makeGameEndEvent,
    makeGameStartedEvent,
    makeHandResult,
    makeMeldEvent,
    makeNagashiManganRoundEnd,
    makeRiichiDeclaredEvent,
    makeRonRoundEnd,
    makeRoundStartedEvent,
    makeTsumoRoundEnd,
} from "#tests/fixtures/events";
import { WIRE_GAME_RECONNECTED } from "#tests/fixtures/wire";
import { tableStateToDisplayState } from "@/entities/table/lib/board-mapper";
import { applyEvent } from "@/entities/table/model/apply-event";
import { createInitialTableState } from "@/entities/table/model/initial-state";
import { type ReplayEvent, type TableState } from "@/entities/table/model/types";
import { MELD_TYPE, ROUND_RESULT_TYPE, parseServerMessage } from "@/shared/protocol";

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
        expect(next.honbaSticks).toBe(2);
        expect(next.riichiSticks).toBe(1);
        expect(next.doraIndicators).toEqual([10, 20]);
    });

    test("updates scores from player views", () => {
        const state = stateAfterGameStarted();
        const event = makeRoundStartedEvent({
            players: [
                { score: 30_000, seat: 0, tiles: [0] },
                { score: 22_000, seat: 1, tiles: [1] },
                { score: 18_000, seat: 2, tiles: [2] },
                { score: 30_000, seat: 3, tiles: [3] },
            ],
        });
        const next = applyEvent(state, event);

        expect(next.players[0].score).toBe(30_000);
        expect(next.players[1].score).toBe(22_000);
        expect(next.players[2].score).toBe(18_000);
        expect(next.players[3].score).toBe(30_000);
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

    test("deals a live seat its own tiles and every other seat a face-down count of 13", () => {
        const state = stateAfterGameStarted();
        const event = makeRoundStartedEvent({
            myTiles: [1, 2, 3],
            players: [0, 1, 2, 3].map((seat) => ({ score: 25_000, seat, tiles: null })),
            seat: 2,
        });
        const next = applyEvent(state, event);

        expect(next.players.map((p) => [p.tiles, p.concealedCount])).toEqual([
            [[], 13],
            [[], 13],
            [[1, 2, 3], 0],
            [[], 13],
        ]);
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

    test("sets tilesRemaining to 70 (live wall after dealing)", () => {
        const state = stateAfterGameStarted();
        const event = makeRoundStartedEvent();
        const next = applyEvent(state, event);

        expect(next.tilesRemaining).toBe(70);
    });
});

function stateAfterRoundStarted() {
    const s1 = applyEvent(createInitialTableState(), makeGameStartedEvent());
    return applyEvent(s1, makeRoundStartedEvent());
}

function shownRound(state: TableState): string | undefined {
    return tableStateToDisplayState(state, { bottomSeat: 0, reveal: "bottom" })?.center
        .roundDisplay;
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

    test("decrements tilesRemaining by 1", () => {
        const state = stateAfterRoundStarted();
        const event = makeDrawEvent({ seat: 0, tileId: 52 });
        const next = applyEvent(state, event);

        expect(next.tilesRemaining).toBe(69);
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

describe("applyEvent - hidden hands", () => {
    function liveDeal(): ReturnType<typeof applyEvent> {
        const dealt = makeRoundStartedEvent({
            myTiles: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            players: [0, 1, 2, 3].map((seat) => ({ score: 25_000, seat, tiles: null })),
            seat: 0,
        });
        return applyEvent(applyEvent(createInitialTableState(), makeGameStartedEvent()), dealt);
    }

    test("a draw re-sent after a reconnect, of a tile the hand holds, only marks it drawn", () => {
        const next = applyEvent(liveDeal(), makeDrawEvent({ seat: 0, tileId: 12 }));

        expect(next.players[0].tiles).toHaveLength(13);
        expect(next.players[0].drawnTileId).toBe(12);
        expect(next.tilesRemaining).toBe(70);
    });

    test("a hidden hand discarding without a draw this view saw drew one unseen from the wall", () => {
        const next = applyEvent(liveDeal(), makeDiscardEvent({ seat: 1, tileId: 100 }));

        expect(next.players[1].concealedCount).toBe(13);
        expect(next.players[1].discards.map((d) => d.tileId)).toEqual([100]);
        expect(next.tilesRemaining).toBe(69);
    });

    test("a hidden hand calls pon from its count and its discard after the call draws nothing", () => {
        const afterDiscard = applyEvent(liveDeal(), makeDiscardEvent({ seat: 1, tileId: 100 }));
        const pon = makeMeldEvent({
            calledTileId: 100,
            callerSeat: 2,
            fromSeat: 1,
            tileIds: [100, 101, 102],
        });
        const afterPon = applyEvent(afterDiscard, pon);
        const next = applyEvent(afterPon, makeDiscardEvent({ seat: 2, tileId: 120 }));

        expect(afterPon.players[2].concealedCount).toBe(11);
        expect(next.players[2].concealedCount).toBe(10);
        expect(next.tilesRemaining).toBe(69);
    });

    test("a hidden hand's closed kan follows its unseen draw, so four tiles leave a hand of 14", () => {
        const kan = makeMeldEvent({
            calledTileId: null,
            callerSeat: 3,
            fromSeat: null,
            meldType: MELD_TYPE.CLOSED_KAN,
            tileIds: [104, 105, 106, 107],
        });
        const next = applyEvent(liveDeal(), kan);

        expect(next.players[3].concealedCount).toBe(10);
        expect(next.tilesRemaining).toBe(69);
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

describe("applyEvent - seat presence", () => {
    test("marks the seat of a player who left as held by an AI player until the player reconnects", () => {
        const state = stateAfterRoundStarted();
        const left = applyEvent(state, { playerName: "Bob", type: "player_left" });
        const back = applyEvent(left, { playerName: "Bob", type: "player_reconnected" });

        expect(left.players.map((p) => p.aiStandIn)).toEqual([null, null, null, 0]);
        expect(back.players.map((p) => p.aiStandIn)).toEqual([null, null, null, null]);
    });
});

describe("applyEvent - game_reconnected", () => {
    test("rebuilds the seat's own hand by its tiles, every other by its count, and claimed river tiles", () => {
        const [error, snapshot] = parseServerMessage({
            ...WIRE_GAME_RECONNECTED,
            pst: [
                {
                    dsc: [{ ti: 100 }, { rd: true, ti: 33 }],
                    ml: [],
                    ri: true,
                    s: 0,
                    sc: 240,
                    tc: 13,
                },
                { dsc: [], ml: [17_409], ri: false, s: 1, sc: 250, tc: 11 },
            ],
            s: 1,
        });
        assert(error === null && snapshot.type === "game_reconnected");
        const next = applyEvent(createInitialTableState(), snapshot);

        expect(next.players.map((p) => [p.name, p.tiles, p.concealedCount])).toEqual([
            ["P1", [], 13],
            ["P2", [0, 1, 2], 0],
            ["B1", [], 0],
            ["B2", [], 0],
        ]);
        expect(next.players[0].discards).toEqual([
            { claimed: false, isRiichi: false, isTsumogiri: false, tileId: 100 },
            { claimed: true, isRiichi: true, isTsumogiri: false, tileId: 33 },
        ]);
        expect(next.tilesRemaining).toBe(70);
    });

    test("names the round from the first dealer its history lists, else from the dealer in play", () => {
        const history = { h: 0, rs: [], sch: {}, w: 0, ws: [] };
        const [error, later] = parseServerMessage({
            ...WIRE_GAME_RECONNECTED,
            dl: 1,
            n: 5,
            rh: [
                { ...history, dl: 3 },
                { ...history, dl: 0 },
            ],
            w: 1,
        });
        const [firstError, first] = parseServerMessage({ ...WIRE_GAME_RECONNECTED, dl: 2 });
        assert(error === null && later.type === "game_reconnected");
        assert(firstError === null && first.type === "game_reconnected");

        const initial = createInitialTableState();

        expect(shownRound(applyEvent(initial, later))).toBe("South 3");
        expect(shownRound(applyEvent(initial, first))).toBe("East 1");
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

        expect(next.players.map((player) => player.score)).toEqual([
            35_000, 22_000, 22_000, 21_000,
        ]);
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

describe("applyEvent - round_end", () => {
    describe("tsumo", () => {
        test("settles each score from the event's pre-payment score and sets round_ended", () => {
            const state = stateAfterRoundStarted();
            const event = makeTsumoRoundEnd({
                scores: { "0": 25_000, "1": 24_000, "2": 25_000, "3": 25_000 },
            });
            const next = applyEvent(state, event);

            expect(next.phase).toBe("round_ended");
            expect(next.players.map((player) => player.score)).toEqual([
                35_000, 21_000, 22_000, 21_000,
            ]);
            expect(next.roundEndResult?.scoresBeforePayment).toEqual(event.scores);
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

            expect(next.players[0].score).toBe(33_000);
            expect(next.players[1].score).toBe(17_000);
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

            expect(next.players[0].score).toBe(33_000);
            expect(next.players[1].score).toBe(9000);
            expect(next.players[2].score).toBe(33_000);
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

            expect(next.players[0].score).toBe(26_500);
            expect(next.players[1].score).toBe(23_500);
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

            expect(next.players[0].score).toBe(37_000);
            expect(next.players[1].score).toBe(21_000);
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
            makeTsumoRoundEnd({ melds: [12_345], winnerSeat: 0, winningTile: 52 }),
        );

        expect(next.roundEndResult).not.toBeNull();
        expect(next.roundEndResult!.resultType).toBe(ROUND_RESULT_TYPE.TSUMO);
        expect(next.roundEndResult!.winners).toHaveLength(1);

        const [winner] = next.roundEndResult!.winners;
        expect(winner.seat).toBe(0);
        expect(winner.melds).toEqual([12_345]);
        expect(winner.winningTile).toBe(52);
    });

    test("tsumo populates yaku list and han/fu totals", () => {
        const state = stateAfterRoundStarted();
        const event = makeTsumoRoundEnd({
            handResult: makeHandResult({
                fu: 30,
                han: 4,
                yaku: [
                    { han: 1, yakuId: 0 },
                    { han: 1, yakuId: 1 },
                    { han: 1, yakuId: 12 },
                    { han: 1, yakuId: 120 },
                ],
            }),
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
            scoreChanges: { "0": 10_000, "1": -3000, "2": -3000, "3": -4000 },
        });
        const next = applyEvent(state, event);

        expect(next.roundEndResult!.scoreChanges).toEqual({
            "0": 10_000,
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
        const event = makeGameEndEvent({ leftoverRiichiBonus: 2000, winnerSeat: 0 });
        const next = applyEvent(state, event);

        expect(next.gameEndResult).toEqual({
            leftoverRiichiBonus: 2000,
            standings: event.standings,
            winnerSeat: 0,
        });
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

    test("game_end keeps the last round's result beside the standings", () => {
        const state = stateAfterRoundStarted();
        const roundEndState = applyEvent(state, makeTsumoRoundEnd());

        const gameEndState = applyEvent(roundEndState, makeGameEndEvent());
        expect(gameEndState.roundEndResult).toBe(roundEndState.roundEndResult);
        expect(gameEndState.gameEndResult).not.toBeNull();
    });

    test("game_started clears both roundEndResult and gameEndResult", () => {
        const state = stateAfterRoundStarted();
        const roundEndState = applyEvent(state, makeTsumoRoundEnd());
        const gameEndState = applyEvent(roundEndState, makeGameEndEvent());
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
    const gameStarted = makeGameStartedEvent({
        gameId: "integration-test",
        players: [
            { isAiPlayer: false, name: "Alice", seat: 0 },
            { isAiPlayer: false, name: "Bob", seat: 1 },
            { isAiPlayer: true, name: "Bot-1", seat: 2 },
            { isAiPlayer: true, name: "Bot-2", seat: 3 },
        ],
    });

    const roundStarted = makeRoundStartedEvent({
        players: [
            { score: 25_000, seat: 0, tiles: [0, 4, 5, 6, 7, 8, 9, 10, 11, 53, 54, 55, 56] },
            { score: 25_000, seat: 1, tiles: [1, 2, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 57] },
            { score: 25_000, seat: 2, tiles: [26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38] },
            { score: 25_000, seat: 3, tiles: [39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51] },
        ],
    });

    return { gameStarted, roundStarted };
}

function makeIntegrationMidGameEvents() {
    // Dealer (seat 0) draws tile 52
    const draw = makeDrawEvent({ seat: 0, tileId: 52 });

    // Dealer discards tile 0 (1m) from their hand
    const discard = makeDiscardEvent({ seat: 0, tileId: 0 });

    // Seat 1 calls pon on tile 0 (1m) using tiles [1, 2] from hand + [0] called
    const meld = makeMeldEvent({
        calledTileId: 0,
        callerSeat: 1,
        fromSeat: 0,
        meldType: "pon",
        tileIds: [1, 2, 0],
    });

    // Seat 1 discards tile 16 after the pon
    const discardAfterMeld = makeDiscardEvent({ seat: 1, tileId: 16 });

    return { discard, discardAfterMeld, draw, meld };
}

function makeIntegrationLateGameEvents() {
    // Seat 2 draws and declares riichi
    const drawSeat2 = makeDrawEvent({ seat: 2, tileId: 58 });
    const riichiDeclared = makeRiichiDeclaredEvent({ seat: 2 });
    const riichiDiscard = makeDiscardEvent({ isRiichi: true, seat: 2, tileId: 26 });
    const doraRevealed = makeDoraRevealedEvent({ tileId: 60 });

    return { doraRevealed, drawSeat2, riichiDeclared, riichiDiscard };
}

function makeIntegrationEndEvents() {
    // Round ends with tsumo by seat 0
    const roundEnd = makeTsumoRoundEnd({
        closedTiles: [4, 5, 6, 7, 8, 9, 10, 11, 53, 54, 55, 56, 52],
        scoreChanges: { "0": 12_000, "1": -4000, "2": -4000, "3": -4000 },
        winnerSeat: 0,
        winningTile: 52,
    });

    // Game ends
    const gameEnd = makeGameEndEvent({
        numRounds: 1,
        standings: [
            { finalScore: 47, score: 37_000, seat: 0 },
            { finalScore: -9, score: 21_000, seat: 1 },
            { finalScore: -9, score: 21_000, seat: 2 },
            { finalScore: -29, score: 21_000, seat: 3 },
        ],
        winnerSeat: 0,
    });

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

        expect(state.players[0].score).toBe(37_000);
        expect(state.players[1].score).toBe(21_000);
        expect(state.players[2].score).toBe(21_000);
        expect(state.players[3].score).toBe(21_000);
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
            expect(states[11].players[0].score).toBe(37_000);
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
