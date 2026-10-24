import { describe, expect, test } from "vitest";

import { formatScore, tableStateToDisplayState } from "@/entities/table/lib/board-mapper";
import {
    createInitialPlayerState,
    createInitialTableState,
} from "@/entities/table/model/initial-state";
import { type PlayerState, type TableState } from "@/entities/table/model/types";

function makePlayer(overrides: Partial<PlayerState> = {}): PlayerState {
    return {
        ...createInitialPlayerState({ isAiPlayer: false, name: "Alice", score: 25000, seat: 0 }),
        ...overrides,
    };
}

function makeTableState(overrides: Partial<TableState> = {}): TableState {
    return {
        ...createInitialTableState(),
        players: [
            makePlayer({ name: "P0", seat: 0 }),
            makePlayer({ name: "P1", seat: 1 }),
            makePlayer({ name: "P2", seat: 2 }),
            makePlayer({ name: "P3", seat: 3 }),
        ],
        ...overrides,
    };
}

describe("tableStateToDisplayState", () => {
    describe("incomplete state handling", () => {
        test("returns null when players array is empty", () => {
            const state = makeTableState({ players: [] });
            expect(tableStateToDisplayState(state)).toBeNull();
        });

        test("returns null when players array has fewer than 4 entries", () => {
            const state = makeTableState({
                players: [makePlayer({ seat: 0 }), makePlayer({ seat: 1 })],
            });
            expect(tableStateToDisplayState(state)).toBeNull();
        });
    });

    describe("player display mapping", () => {
        test("bottom player (seat 0) gets face-up hand tiles", () => {
            const state = makeTableState({
                players: [
                    makePlayer({ seat: 0, tiles: [0, 4] }),
                    makePlayer({ seat: 1 }),
                    makePlayer({ seat: 2 }),
                    makePlayer({ seat: 3 }),
                ],
            });
            const result = tableStateToDisplayState(state)!;
            // Bottom player (index 0) should have show: "face"
            expect(result.players[0].hand[0].show).toBe("face");
            expect(result.players[0].hand[1].show).toBe("face");
        });

        test("non-bottom players get face-down hand tiles", () => {
            const state = makeTableState({
                players: [
                    makePlayer({ seat: 0 }),
                    makePlayer({ seat: 1, tiles: [0] }),
                    makePlayer({ seat: 2, tiles: [4] }),
                    makePlayer({ seat: 3, tiles: [8] }),
                ],
            });
            const result = tableStateToDisplayState(state)!;
            expect(result.players[1].hand[0].show).toBe("back");
            expect(result.players[2].hand[0].show).toBe("back");
            expect(result.players[3].hand[0].show).toBe("back");
        });

        test("drawn tile separated from base hand", () => {
            const state = makeTableState({
                players: [
                    makePlayer({ drawnTileId: 8, seat: 0, tiles: [0, 4, 8] }),
                    makePlayer({ seat: 1 }),
                    makePlayer({ seat: 2 }),
                    makePlayer({ seat: 3 }),
                ],
            });
            const result = tableStateToDisplayState(state)!;
            // 2 base tiles, 1 drawn tile
            expect(result.players[0].hand).toHaveLength(2);
            expect(result.players[0].drawnTile).toBeDefined();
            expect(result.players[0].drawnTile!.face).toBe("3m");
        });

        test("duplicate tile IDs: only first match becomes drawn tile", () => {
            const state = makeTableState({
                players: [
                    makePlayer({ drawnTileId: 4, seat: 0, tiles: [4, 4, 8] }),
                    makePlayer({ seat: 1 }),
                    makePlayer({ seat: 2 }),
                    makePlayer({ seat: 3 }),
                ],
            });
            const result = tableStateToDisplayState(state)!;
            // 2 base tiles (one 4 + the 8) + 1 drawn tile (the other 4)
            expect(result.players[0].hand).toHaveLength(2);
            expect(result.players[0].drawnTile).toBeDefined();
        });

        test("drawnTileId not in tiles array renders all tiles without drawn tile", () => {
            const state = makeTableState({
                players: [
                    makePlayer({ drawnTileId: 99, seat: 0, tiles: [0, 4, 8] }),
                    makePlayer({ seat: 1 }),
                    makePlayer({ seat: 2 }),
                    makePlayer({ seat: 3 }),
                ],
            });
            const result = tableStateToDisplayState(state)!;
            expect(result.players[0].hand).toHaveLength(3);
            expect(result.players[0].drawnTile).toBeUndefined();
        });

        test("null drawnTileId renders all tiles inline", () => {
            const state = makeTableState({
                players: [
                    makePlayer({ drawnTileId: null, seat: 0, tiles: [0, 4, 8] }),
                    makePlayer({ seat: 1 }),
                    makePlayer({ seat: 2 }),
                    makePlayer({ seat: 3 }),
                ],
            });
            const result = tableStateToDisplayState(state)!;
            expect(result.players[0].hand).toHaveLength(3);
            expect(result.players[0].drawnTile).toBeUndefined();
        });

        test("melds passed through to display state", () => {
            const state = makeTableState({
                players: [
                    makePlayer({
                        melds: [
                            {
                                calledTileId: 0,
                                callerSeat: 0,
                                fromSeat: 1,
                                meldType: "pon",
                                tileIds: [0, 1, 2],
                            },
                        ],
                        seat: 0,
                    }),
                    makePlayer({ seat: 1 }),
                    makePlayer({ seat: 2 }),
                    makePlayer({ seat: 3 }),
                ],
            });
            const result = tableStateToDisplayState(state)!;
            expect(result.players[0].melds).toHaveLength(1);
            expect(result.players[0].melds[0].meldType).toBe("pon");
            expect(result.players[0].melds[0].tileIds).toEqual([0, 1, 2]);
        });

        test("discards mapped with grayed and riichi flags", () => {
            const state = makeTableState({
                players: [
                    makePlayer({
                        discards: [
                            { isRiichi: false, isTsumogiri: false, tileId: 0 },
                            { claimed: true, isRiichi: false, isTsumogiri: false, tileId: 4 },
                            { isRiichi: true, isTsumogiri: false, tileId: 8 },
                        ],
                        seat: 0,
                    }),
                    makePlayer({ seat: 1 }),
                    makePlayer({ seat: 2 }),
                    makePlayer({ seat: 3 }),
                ],
            });
            const result = tableStateToDisplayState(state)!;
            expect(result.players[0].discards).toHaveLength(3);
            expect(result.players[0].discards[1].grayed).toBe(true);
            expect(result.players[0].discards[2].riichi).toBe(true);
        });

        test("unsorted players array produces correct seat positions", () => {
            const state = makeTableState({
                players: [
                    makePlayer({ name: "P3", seat: 3 }),
                    makePlayer({ name: "P1", seat: 1 }),
                    makePlayer({ name: "P0", seat: 0, tiles: [0] }),
                    makePlayer({ name: "P2", seat: 2 }),
                ],
            });
            const result = tableStateToDisplayState(state)!;
            // Seat 0 = bottom (index 0) should be face-up
            expect(result.players[0].hand[0].show).toBe("face");
        });
    });

    describe("center info mapping", () => {
        test("round display formatted as wind name + number", () => {
            const state = makeTableState({ roundNumber: 2, roundWind: 1 });
            const result = tableStateToDisplayState(state)!;
            expect(result.center.roundDisplay).toBe("South 2");
        });

        test("player scores formatted as plain numbers", () => {
            const state = makeTableState({
                players: [
                    makePlayer({ score: 32100, seat: 0 }),
                    makePlayer({ score: 25000, seat: 1 }),
                    makePlayer({ score: 18900, seat: 2 }),
                    makePlayer({ score: 24000, seat: 3 }),
                ],
            });
            const result = tableStateToDisplayState(state)!;
            expect(result.center.scores[0].score).toBe("32100");
            expect(result.center.scores[1].score).toBe("25000");
        });

        test("dealer always at bottom (position 0)", () => {
            const state = makeTableState({ dealerSeat: 2 });
            const result = tableStateToDisplayState(state)!;
            // Dealer rotates to position 0 (bottom)
            expect(result.center.scores[0].isDealer).toBe(true);
            expect(result.center.scores[1].isDealer).toBe(false);
            expect(result.center.scores[2].isDealer).toBe(false);
            expect(result.center.scores[3].isDealer).toBe(false);
        });

        test("current player marked based on currentPlayerSeat", () => {
            const state = makeTableState({ currentPlayerSeat: 1 });
            const result = tableStateToDisplayState(state)!;
            expect(result.center.scores[1].isCurrent).toBe(true);
            expect(result.center.scores[0].isCurrent).toBe(false);
        });

        test("seat-to-position mapping: 0=bottom, 1=right, 2=top, 3=left", () => {
            const state = makeTableState({ dealerSeat: 0 });
            const result = tableStateToDisplayState(state)!;
            // Seat 0 is dealer, wind relative to dealer is East
            expect(result.center.scores[0].wind).toBe("E");
            expect(result.center.scores[1].wind).toBe("S");
            expect(result.center.scores[2].wind).toBe("W");
            expect(result.center.scores[3].wind).toBe("N");
        });

        test("wind letters computed relative to dealer, dealer at bottom", () => {
            // Dealer at seat 2 rotates to bottom: position 0=E, 1=S, 2=W, 3=N
            const state = makeTableState({ dealerSeat: 2 });
            const result = tableStateToDisplayState(state)!;
            expect(result.center.scores[0].wind).toBe("E");
            expect(result.center.scores[1].wind).toBe("S");
            expect(result.center.scores[2].wind).toBe("W");
            expect(result.center.scores[3].wind).toBe("N");
        });

        test("scores tuple has exactly 4 entries", () => {
            const state = makeTableState();
            const result = tableStateToDisplayState(state)!;
            expect(result.center.scores).toHaveLength(4);
        });
    });
});

describe("formatScore", () => {
    test("formats as plain number", () => {
        expect(formatScore(25000)).toBe("25000");
    });

    test("formats zero", () => {
        expect(formatScore(0)).toBe("0");
    });

    test("formats negative scores", () => {
        expect(formatScore(-1500)).toBe("-1500");
    });
});
