import { describe, expect, test } from "vitest";

import {
    createInitialPlayerState,
    createInitialTableState,
} from "@/entities/table/model/initial-state";

describe("createInitialTableState", () => {
    test("returns pre_game phase with empty players", () => {
        const state = createInitialTableState();
        expect(state.phase).toBe("pre_game");
        expect(state.players).toEqual([]);
    });

    test("returns zeroed round-level fields", () => {
        const state = createInitialTableState();
        expect(state.roundWind).toBe(0);
        expect(state.roundNumber).toBe(0);
        expect(state.honbaSticks).toBe(0);
        expect(state.riichiSticks).toBe(0);
        expect(state.doraIndicators).toEqual([]);
    });

    test("each call returns a distinct object", () => {
        const stateA = createInitialTableState();
        const stateB = createInitialTableState();
        expect(stateA).not.toBe(stateB);
        expect(stateA.doraIndicators).not.toBe(stateB.doraIndicators);
    });
});

describe("createInitialPlayerState", () => {
    test("sets seat, name, isAiPlayer, and score from arguments", () => {
        const player = createInitialPlayerState({
            isAiPlayer: false,
            name: "Alice",
            score: 25000,
            seat: 2,
        });
        expect(player.seat).toBe(2);
        expect(player.name).toBe("Alice");
        expect(player.isAiPlayer).toBe(false);
        expect(player.score).toBe(25000);
    });

    test("initializes empty hand, discards, melds, and no drawn tile", () => {
        const player = createInitialPlayerState({
            isAiPlayer: true,
            name: "Bot",
            score: 0,
            seat: 0,
        });
        expect(player.tiles).toEqual([]);
        expect(player.discards).toEqual([]);
        expect(player.melds).toEqual([]);
        expect(player.drawnTileId).toBeNull();
        expect(player.isRiichi).toBe(false);
    });
});
