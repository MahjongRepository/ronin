import { describe, expect, test } from "vitest";

import {
    makeAddedKanEvent,
    makeChankanPromptEvent,
    makeClosedKanEvent,
    makeDiscardEvent,
    makeDrawEvent,
    makeGameStartedEvent,
    makeMeldEvent,
    makeRoundStartedEvent,
} from "#tests/fixtures/events";
import { DesyncError, chankanKanDeclared } from "@/entities/table";
import { applyEvent } from "@/entities/table/model/apply-event";
import { createInitialTableState } from "@/entities/table/model/initial-state";
import { type KanDeclaredEvent, type TableState } from "@/entities/table/model/types";
import { type ClaimedMeldEvent, KAN_TYPE, type RoundStartedEvent } from "@/shared/protocol";

function roundStartedWithMeldHands(): RoundStartedEvent {
    return makeRoundStartedEvent({
        players: [
            { score: 25_000, seat: 0, tiles: [0, 1, 2, 4, 8, 12, 16, 20, 24, 28, 32, 36, 37] },
            { score: 25_000, seat: 1, tiles: [40, 41, 42, 44, 48, 52, 56, 60, 64, 68, 72, 76, 77] },
            {
                score: 25_000,
                seat: 2,
                tiles: [80, 81, 82, 84, 88, 92, 96, 100, 104, 108, 112, 116, 117],
            },
            { score: 25_000, seat: 3, tiles: [3, 5, 6, 7, 9, 10, 11, 13, 14, 15, 17, 18, 19] },
        ],
    });
}

function stateAfterRoundStarted(): TableState {
    const state = applyEvent(createInitialTableState(), makeGameStartedEvent());
    return applyEvent(state, roundStartedWithMeldHands());
}

function drawTile(state: TableState, seat: number, tileId: number): TableState {
    return applyEvent(state, makeDrawEvent({ seat, tileId }));
}

function stateWithDiscard(seat: number, tileId: number): TableState {
    const state = drawTile(stateAfterRoundStarted(), seat, tileId);
    return applyEvent(state, makeDiscardEvent({ seat, tileId }));
}

function ponOf1p(calledTileId = 38): ClaimedMeldEvent {
    return makeMeldEvent({
        calledTileId,
        callerSeat: 0,
        fromSeat: 1,
        meldType: "pon",
        tileIds: [36, 37, calledTileId],
    });
}

const CHI_OF_2M = makeMeldEvent({
    calledTileId: 5,
    callerSeat: 0,
    fromSeat: 3,
    meldType: "chi",
    tileIds: [0, 5, 8],
});

function stateWithChiAndPon(): TableState {
    const chi = applyEvent(stateWithDiscard(3, 5), CHI_OF_2M);
    const discarded = applyEvent(drawTile(chi, 1, 38), makeDiscardEvent({ seat: 1, tileId: 38 }));
    return applyEvent(discarded, ponOf1p());
}

function claimedFlags(state: TableState, seat: number): (boolean | undefined)[] {
    return state.players[seat].discards.map((d) => d.claimed);
}

describe("applyEvent - meld - chi", () => {
    test("takes the caller's two tiles into the chi and claims the discard", () => {
        const state = stateWithDiscard(3, 5);
        const next = applyEvent(state, CHI_OF_2M);

        expect(next.players[0].tiles).toEqual(
            state.players[0].tiles.filter((t) => t !== 0 && t !== 8),
        );
        expect(next.players[0].melds.map((m) => m.meldType)).toEqual(["chi"]);
        expect(claimedFlags(next, 3)).toEqual([true]);
    });
});

describe("applyEvent - meld - pon", () => {
    test("takes the caller's two tiles into the pon and claims the discard", () => {
        const state = stateWithDiscard(1, 38);
        const next = applyEvent(state, ponOf1p());

        expect(next.players[0].tiles).toEqual(
            state.players[0].tiles.filter((t) => t !== 36 && t !== 37),
        );
        expect(next.players[0].melds).toMatchObject([{ meldType: "pon", tileIds: [36, 37, 38] }]);
        expect(claimedFlags(next, 1)).toEqual([true]);
    });

    test("refuses a call on a tile that is not the table's latest discard as a desync", () => {
        const state = stateWithDiscard(1, 38);
        const passed = applyEvent(
            drawTile(state, 2, 120),
            makeDiscardEvent({ seat: 2, tileId: 120 }),
        );

        expect(() => applyEvent(state, ponOf1p(39))).toThrow(DesyncError);
        expect(() => applyEvent(passed, ponOf1p(38))).toThrow(DesyncError);
    });

    test("refuses a call by or from a seat the table does not hold, or of tiles the caller does not hold, as a desync", () => {
        const state = stateWithDiscard(1, 38);

        expect(() => applyEvent(state, { ...ponOf1p(), callerSeat: 9 })).toThrow(DesyncError);
        expect(() => applyEvent(state, { ...ponOf1p(), fromSeat: 9 })).toThrow(DesyncError);
        expect(() => applyEvent(state, { ...ponOf1p(), tileIds: [38, 100, 101] })).toThrow(
            DesyncError,
        );
    });
});

describe("applyEvent - meld - open_kan", () => {
    test("takes the caller's three tiles into the kan and claims the discard", () => {
        const state = stateWithDiscard(1, 3);
        const next = applyEvent(
            state,
            makeMeldEvent({
                calledTileId: 3,
                callerSeat: 0,
                fromSeat: 1,
                meldType: "open_kan",
                tileIds: [0, 1, 2, 3],
            }),
        );

        expect(next.players[0].tiles).toEqual(state.players[0].tiles.filter((t) => t > 2));
        expect(next.players[0].melds.map((m) => m.meldType)).toEqual(["open_kan"]);
        expect(claimedFlags(next, 1)).toEqual([true]);
    });
});

describe("applyEvent - meld - closed_kan", () => {
    test("takes all four tiles from the hand, clearing the drawn mark and claiming no discard", () => {
        const state = drawTile(stateWithDiscard(1, 120), 0, 3);
        const next = applyEvent(
            state,
            makeClosedKanEvent({ callerSeat: 0, tileIds: [0, 1, 2, 3] }),
        );

        expect(next.players[0].tiles).toEqual(state.players[0].tiles.filter((t) => t > 3));
        expect(next.players[0].melds.map((m) => m.meldType)).toEqual(["closed_kan"]);
        expect(next.players[0].drawnTileId).toBeNull();
        expect(claimedFlags(next, 1)).toEqual([undefined]);
    });
});

describe("applyEvent - meld - added_kan", () => {
    const ADDED_KAN_OF_1P = makeAddedKanEvent({
        addedTileId: 39,
        calledTileId: 38,
        callerSeat: 0,
        fromSeat: 1,
        tileIds: [36, 37, 38, 39],
    });

    test("raises the matching pon in place with the tile from the hand, keeping the pon's called tile and the other melds", () => {
        const next = applyEvent(drawTile(stateWithChiAndPon(), 0, 39), ADDED_KAN_OF_1P);

        expect(next.players[0].tiles).not.toContain(39);
        expect(next.players[0].melds).toMatchObject([
            { meldType: "chi" },
            { addedTileId: 39, calledTileId: 38, meldType: "added_kan", tileIds: [36, 37, 38, 39] },
        ]);
    });

    test("refuses an added kan with no pon to raise as a desync", () => {
        expect(() => applyEvent(stateAfterRoundStarted(), ADDED_KAN_OF_1P)).toThrow(DesyncError);
    });
});

describe("applyEvent - kan_declared", () => {
    function declared(kanType: KanDeclaredEvent["kanType"], tileId: number): KanDeclaredEvent {
        return { kanType, seat: 0, tileId, type: "kan_declared" };
    }

    test("lays the kan a chankan prompt names: a closed kan of the four copies, an added kan on its pon", () => {
        const closed = chankanKanDeclared(
            makeChankanPromptEvent({ kanType: KAN_TYPE.CLOSED, tileId: 3 }),
        );
        const added = chankanKanDeclared(
            makeChankanPromptEvent({ kanType: KAN_TYPE.ADDED, tileId: 39 }),
        );

        const closedTable = applyEvent(drawTile(stateWithDiscard(1, 120), 0, 3), closed);
        const addedTable = applyEvent(drawTile(stateWithChiAndPon(), 0, 39), added);

        expect(closedTable.players[0].melds).toMatchObject([
            { meldType: "closed_kan", tileIds: [0, 1, 2, 3] },
        ]);
        expect(addedTable.players[0].melds).toMatchObject([
            { meldType: "chi" },
            { addedTileId: 39, meldType: "added_kan", tileIds: [36, 37, 38, 39] },
        ]);
    });

    test("refuses an added kan with no pon to raise, or a closed kan of tiles the hand does not hold, as a desync", () => {
        const state = stateAfterRoundStarted();

        expect(() => applyEvent(state, declared(KAN_TYPE.ADDED, 39))).toThrow(DesyncError);
        expect(() => applyEvent(state, declared(KAN_TYPE.CLOSED, 120))).toThrow(DesyncError);
    });
});
