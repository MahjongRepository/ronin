import { describe, expect, test } from "vitest";

import { applyEvent } from "@/entities/table/model/apply-event";
import { createInitialTableState } from "@/entities/table/model/initial-state";
import {
    type DiscardEvent,
    type DrawEvent,
    type GameStartedEvent,
    type MeldEvent,
    type RoundStartedEvent,
} from "@/shared/protocol";

function makeGameStartedEvent(): GameStartedEvent {
    return {
        dealerDice: [
            [2, 3],
            [4, 5],
        ],
        dealerSeat: 0,
        gameId: "test-game-1",
        players: [
            { isAiPlayer: false, name: "Alice", seat: 0 },
            { isAiPlayer: false, name: "Bob", seat: 1 },
            { isAiPlayer: true, name: "Charlie", seat: 2 },
            { isAiPlayer: true, name: "Diana", seat: 3 },
        ],
        type: "game_started",
    };
}

function makeRoundStartedEvent(): RoundStartedEvent {
    return {
        currentPlayerSeat: 0,
        dealerSeat: 0,
        dice: [3, 4],
        doraIndicators: [10],
        honbaSticks: 0,
        myTiles: null,
        players: [
            // Alice: 1m-1m-1m-2m-3m-4m-5m-6m-7m-8m-9m-1p-1p (tiles 0-12)
            { score: 25000, seat: 0, tiles: [0, 1, 2, 4, 8, 12, 16, 20, 24, 28, 32, 36, 37] },
            // Bob: tiles 40-52
            { score: 25000, seat: 1, tiles: [40, 41, 42, 44, 48, 52, 56, 60, 64, 68, 72, 76, 77] },
            // Charlie: tiles 80-92
            {
                score: 25000,
                seat: 2,
                tiles: [80, 81, 82, 84, 88, 92, 96, 100, 104, 108, 112, 116, 117],
            },
            // Diana: tiles starting at 3 (1m copy 4), various
            { score: 25000, seat: 3, tiles: [3, 5, 6, 7, 9, 10, 11, 13, 14, 15, 17, 18, 19] },
        ],
        riichiSticks: 0,
        roundNumber: 1,
        seat: null,
        type: "round_started",
        wind: 0,
    };
}

function stateAfterRoundStarted() {
    let state = applyEvent(createInitialTableState(), makeGameStartedEvent());
    state = applyEvent(state, makeRoundStartedEvent());
    return state;
}

function drawTile(state: ReturnType<typeof createInitialTableState>, seat: number, tileId: number) {
    const drawEvent: DrawEvent = {
        availableActions: [],
        seat,
        tileId,
        type: "draw",
    };
    return applyEvent(state, drawEvent);
}

function stateWithDiscard(seat: number, tileId: number) {
    const state = drawTile(stateAfterRoundStarted(), seat, tileId);
    const discardEvent: DiscardEvent = {
        isRiichi: false,
        isTsumogiri: false,
        seat,
        tileId,
        type: "discard",
    };
    return applyEvent(state, discardEvent);
}

function stateWithPon() {
    // Bob (seat 1) discards tile 38 (1p), Alice calls pon with [36, 37, 38]
    const state = stateWithDiscard(1, 38);
    const ponEvent: MeldEvent = {
        calledTileId: 38,
        callerSeat: 0,
        fromSeat: 1,
        meldType: "pon",
        tileIds: [36, 37, 38],
        type: "meld",
    };
    return applyEvent(state, ponEvent);
}

function stateWithChiAndPon() {
    // Diana (seat 3) discards tile 5, Alice calls chi
    let state = stateWithDiscard(3, 5);
    const chiEvent: MeldEvent = {
        calledTileId: 5,
        callerSeat: 0,
        fromSeat: 3,
        meldType: "chi",
        tileIds: [0, 5, 8],
        type: "meld",
    };
    state = applyEvent(state, chiEvent);

    // Bob draws 38, then discards it; Alice pons with 36, 37
    state = drawTile(state, 1, 38);
    state = applyEvent(state, {
        isRiichi: false,
        isTsumogiri: false,
        seat: 1,
        tileId: 38,
        type: "discard",
    } as DiscardEvent);
    const ponEvent: MeldEvent = {
        calledTileId: 38,
        callerSeat: 0,
        fromSeat: 1,
        meldType: "pon",
        tileIds: [36, 37, 38],
        type: "meld",
    };
    return applyEvent(state, ponEvent);
}

describe("applyEvent - meld - chi", () => {
    test("removes 2 tiles from caller's hand", () => {
        // Diana (seat 3) discards tile 5 (2m), Alice (seat 0) calls chi with 1m-2m-3m
        const state = stateWithDiscard(3, 5);

        // Alice has tiles [0, 1, 2, 4, 8, 12, 16, 20, 24, 28, 32, 36, 37]
        // Chi: tiles [0, 5, 8] where 5 is the called tile from Diana
        const meldEvent: MeldEvent = {
            calledTileId: 5,
            callerSeat: 0,
            fromSeat: 3,
            meldType: "chi",
            tileIds: [0, 5, 8],
            type: "meld",
        };
        const next = applyEvent(state, meldEvent);

        // Tiles 0 and 8 removed from Alice's hand (5 was from discard, not in hand)
        expect(next.players[0].tiles).not.toContain(0);
        expect(next.players[0].tiles).not.toContain(8);
        // Tile 5 was never in Alice's hand, it came from the discard
        expect(next.players[0].melds).toHaveLength(1);
        expect(next.players[0].melds[0].meldType).toBe("chi");
    });

    test("marks last discard of fromSeat as claimed", () => {
        const state = stateWithDiscard(3, 5);

        const meldEvent: MeldEvent = {
            calledTileId: 5,
            callerSeat: 0,
            fromSeat: 3,
            meldType: "chi",
            tileIds: [0, 5, 8],
            type: "meld",
        };
        const next = applyEvent(state, meldEvent);

        const dianaDiscards = next.players[3].discards;
        expect(dianaDiscards[dianaDiscards.length - 1].claimed).toBe(true);
    });

    test("clears caller's drawnTileId", () => {
        // Give Alice a drawn tile, then call chi
        const state = drawTile(stateWithDiscard(3, 5), 0, 53);

        const meldEvent: MeldEvent = {
            calledTileId: 5,
            callerSeat: 0,
            fromSeat: 3,
            meldType: "chi",
            tileIds: [0, 5, 8],
            type: "meld",
        };
        const next = applyEvent(state, meldEvent);

        expect(next.players[0].drawnTileId).toBeNull();
    });
});

describe("applyEvent - meld - pon", () => {
    test("removes 2 tiles from caller's hand", () => {
        // Bob (seat 1) discards tile 38 (1p), Alice has tiles 36, 37 in hand
        const state = stateWithDiscard(1, 38);

        // Pon: Alice calls with [36, 37, 38] - calledTile 38 from Bob
        const meldEvent: MeldEvent = {
            calledTileId: 38,
            callerSeat: 0,
            fromSeat: 1,
            meldType: "pon",
            tileIds: [36, 37, 38],
            type: "meld",
        };
        const next = applyEvent(state, meldEvent);

        expect(next.players[0].tiles).not.toContain(36);
        expect(next.players[0].tiles).not.toContain(37);
        expect(next.players[0].melds).toHaveLength(1);
        expect(next.players[0].melds[0].meldType).toBe("pon");
        expect(next.players[0].melds[0].tileIds).toEqual([36, 37, 38]);
    });

    test("marks last discard of fromSeat as claimed", () => {
        const state = stateWithDiscard(1, 38);

        const meldEvent: MeldEvent = {
            calledTileId: 38,
            callerSeat: 0,
            fromSeat: 1,
            meldType: "pon",
            tileIds: [36, 37, 38],
            type: "meld",
        };
        const next = applyEvent(state, meldEvent);

        const bobDiscards = next.players[1].discards;
        expect(bobDiscards[bobDiscards.length - 1].claimed).toBe(true);
    });
});

describe("applyEvent - meld - open_kan", () => {
    test("removes 3 tiles from caller's hand", () => {
        // Alice has tiles 0, 1, 2 (three 1m copies). Bob discards tile 3 (fourth 1m copy).
        const state = stateWithDiscard(1, 3);

        const meldEvent: MeldEvent = {
            calledTileId: 3,
            callerSeat: 0,
            fromSeat: 1,
            meldType: "open_kan",
            tileIds: [0, 1, 2, 3],
            type: "meld",
        };
        const next = applyEvent(state, meldEvent);

        expect(next.players[0].tiles).not.toContain(0);
        expect(next.players[0].tiles).not.toContain(1);
        expect(next.players[0].tiles).not.toContain(2);
        expect(next.players[0].melds).toHaveLength(1);
        expect(next.players[0].melds[0].meldType).toBe("open_kan");
    });

    test("marks last discard of fromSeat as claimed", () => {
        const state = stateWithDiscard(1, 3);

        const meldEvent: MeldEvent = {
            calledTileId: 3,
            callerSeat: 0,
            fromSeat: 1,
            meldType: "open_kan",
            tileIds: [0, 1, 2, 3],
            type: "meld",
        };
        const next = applyEvent(state, meldEvent);

        const bobDiscards = next.players[1].discards;
        expect(bobDiscards[bobDiscards.length - 1].claimed).toBe(true);
    });
});

describe("applyEvent - meld - closed_kan", () => {
    function makeClosedKanEvent(): MeldEvent {
        return {
            calledTileId: null,
            callerSeat: 0,
            fromSeat: null,
            meldType: "closed_kan",
            tileIds: [0, 1, 2, 3],
            type: "meld",
        };
    }

    function stateReadyForClosedKan() {
        // Alice already has tiles 0, 1, 2. Give her tile 3 via draw.
        return drawTile(stateAfterRoundStarted(), 0, 3);
    }

    test("removes all 4 tiles from caller's hand", () => {
        const next = applyEvent(stateReadyForClosedKan(), makeClosedKanEvent());

        expect(next.players[0].tiles).not.toContain(0);
        expect(next.players[0].tiles).not.toContain(1);
        expect(next.players[0].tiles).not.toContain(2);
        expect(next.players[0].tiles).not.toContain(3);
        expect(next.players[0].melds).toHaveLength(1);
        expect(next.players[0].melds[0].meldType).toBe("closed_kan");
    });

    test("does not mark any discard as claimed (no fromSeat)", () => {
        const next = applyEvent(stateReadyForClosedKan(), makeClosedKanEvent());

        for (const player of next.players) {
            for (const discard of player.discards) {
                expect(discard.claimed).toBeUndefined();
            }
        }
    });

    test("clears drawnTileId", () => {
        const state = stateReadyForClosedKan();
        expect(state.players[0].drawnTileId).toBe(3);

        const next = applyEvent(state, makeClosedKanEvent());

        expect(next.players[0].drawnTileId).toBeNull();
    });
});

describe("applyEvent - meld - added_kan", () => {
    function makeAddedKanEvent(): MeldEvent {
        // calledTileId is the original pon's called tile (38).
        // The handler derives the added tile (39) by comparing
        // event.tileIds against the existing pon's tileIds.
        return {
            calledTileId: 38,
            callerSeat: 0,
            fromSeat: 1,
            meldType: "added_kan",
            tileIds: [36, 37, 38, 39],
            type: "meld",
        };
    }

    test("removes 1 tile from caller's hand and replaces matching pon meld", () => {
        const ponState = stateWithPon();
        expect(ponState.players[0].melds).toHaveLength(1);
        expect(ponState.players[0].melds[0].meldType).toBe("pon");

        // Alice draws tile 39 (fourth 1p copy) and declares added_kan
        const state = drawTile(ponState, 0, 39);
        const next = applyEvent(state, makeAddedKanEvent());

        expect(next.players[0].tiles).not.toContain(39);
        expect(next.players[0].melds).toHaveLength(1);
        expect(next.players[0].melds[0].meldType).toBe("added_kan");
        expect(next.players[0].melds[0].tileIds).toEqual([36, 37, 38, 39]);
    });

    test("stores addedTileId and preserves original calledTileId", () => {
        const ponState = stateWithPon();
        const state = drawTile(ponState, 0, 39);
        const next = applyEvent(state, makeAddedKanEvent());

        const [kanMeld] = next.players[0].melds;
        // calledTileId remains the original pon's called tile
        expect(kanMeld.calledTileId).toBe(38);
        // addedTileId is the tile derived from the hand
        expect(kanMeld.addedTileId).toBe(39);
    });

    test("preserves other melds when replacing pon with added_kan", () => {
        const chiAndPonState = stateWithChiAndPon();
        expect(chiAndPonState.players[0].melds).toHaveLength(2);

        // Draw tile 39 and upgrade pon to added_kan
        const state = drawTile(chiAndPonState, 0, 39);
        const next = applyEvent(state, makeAddedKanEvent());

        expect(next.players[0].melds).toHaveLength(2);
        expect(next.players[0].melds[0].meldType).toBe("chi");
        expect(next.players[0].melds[1].meldType).toBe("added_kan");
    });

    test("throws when no matching pon exists for added_kan", () => {
        const state = stateAfterRoundStarted();
        const addedKanEvent: MeldEvent = {
            calledTileId: 38,
            callerSeat: 0,
            fromSeat: 1,
            meldType: "added_kan",
            tileIds: [36, 37, 38, 39],
            type: "meld",
        };
        expect(() => applyEvent(state, addedKanEvent)).toThrow(
            "No matching pon found for added_kan at seat 0",
        );
    });
});

describe("applyEvent - meld - description", () => {
    test("generates description with player name, meld type, and tile name", () => {
        const state = stateWithDiscard(1, 38);

        const meldEvent: MeldEvent = {
            calledTileId: 38,
            callerSeat: 0,
            fromSeat: 1,
            meldType: "pon",
            tileIds: [36, 37, 38],
            type: "meld",
        };
        const next = applyEvent(state, meldEvent);

        // tileId 38 = 1p (copy index 2 of tile-34 index 9, which is 1p)
        expect(next.lastEventDescription).toBe("Alice called pon on 1p");
    });
});

describe("applyEvent - meld - immutability", () => {
    test("does not mutate the input state", () => {
        const state = stateWithDiscard(1, 38);
        const originalTiles = [...state.players[0].tiles];
        const originalMelds = [...state.players[0].melds];
        const originalDiscards = [...state.players[1].discards];

        const meldEvent: MeldEvent = {
            calledTileId: 38,
            callerSeat: 0,
            fromSeat: 1,
            meldType: "pon",
            tileIds: [36, 37, 38],
            type: "meld",
        };
        applyEvent(state, meldEvent);

        expect(state.players[0].tiles).toEqual(originalTiles);
        expect(state.players[0].melds).toEqual(originalMelds);
        expect(state.players[1].discards).toEqual(originalDiscards);
    });
});
