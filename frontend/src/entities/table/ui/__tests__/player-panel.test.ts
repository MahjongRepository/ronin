import { type TemplateResult, render } from "lit-html";
import { describe, expect, test } from "vitest";

import { createInitialPlayerState } from "@/entities/table/model/initial-state";
import {
    type DiscardRecord,
    type MeldRecord,
    type PlayerState,
} from "@/entities/table/model/types";
import { PlayerPanel } from "@/entities/table/ui/player-panel";

function renderTo(template: TemplateResult): HTMLElement {
    const el = document.createElement("div");
    render(template, el);
    return el;
}

function makePlayer(overrides: Partial<PlayerState> = {}): PlayerState {
    return {
        ...createInitialPlayerState({ isAiPlayer: false, name: "Alice", score: 25000, seat: 0 }),
        ...overrides,
    };
}

describe("PlayerPanel", () => {
    describe("header rendering", () => {
        test("renders player name and score", () => {
            const el = renderTo(
                PlayerPanel(makePlayer({ name: "Bob", score: 32100 }), false, false),
            );
            expect(el.querySelector(".player-panel__name")?.textContent).toBe("Bob");
            expect(el.querySelector(".player-panel__score")?.textContent).toBe("32,100");
        });

        test("renders score of zero", () => {
            const el = renderTo(PlayerPanel(makePlayer({ score: 0 }), false, false));
            expect(el.querySelector(".player-panel__score")?.textContent).toBe("0");
        });

        test("shows dealer badge when isDealer is true", () => {
            const el = renderTo(PlayerPanel(makePlayer(), true, false));
            expect(el.querySelector(".player-panel__badge--dealer")?.textContent).toBe("Dealer");
        });

        test("hides dealer badge when isDealer is false", () => {
            const el = renderTo(PlayerPanel(makePlayer(), false, false));
            expect(el.querySelector(".player-panel__badge--dealer")).toBeNull();
        });

        test("shows riichi badge when player is in riichi", () => {
            const el = renderTo(PlayerPanel(makePlayer({ isRiichi: true }), false, false));
            expect(el.querySelector(".player-panel__badge--riichi")?.textContent).toBe("Riichi");
        });

        test("hides riichi badge when player is not in riichi", () => {
            const el = renderTo(PlayerPanel(makePlayer({ isRiichi: false }), false, false));
            expect(el.querySelector(".player-panel__badge--riichi")).toBeNull();
        });

        test("adds current-turn class when isCurrent is true", () => {
            const el = renderTo(PlayerPanel(makePlayer(), false, true));
            expect(el.querySelector(".player-panel--current")).not.toBeNull();
        });

        test("omits current-turn class when isCurrent is false", () => {
            const el = renderTo(PlayerPanel(makePlayer(), false, false));
            expect(el.querySelector(".player-panel--current")).toBeNull();
        });
    });

    describe("hand tiles", () => {
        test("renders hand tiles from player.tiles", () => {
            // tileId 0 = 1m, tileId 4 = 2m
            const el = renderTo(PlayerPanel(makePlayer({ tiles: [0, 4] }), false, false));
            const handTiles = el.querySelectorAll(".hand-tile");
            expect(handTiles).toHaveLength(2);
        });

        test("separates drawn tile from base hand", () => {
            // tiles has 3 entries, one of which matches drawnTileId
            const el = renderTo(
                PlayerPanel(makePlayer({ drawnTileId: 8, tiles: [0, 4, 8] }), false, false),
            );
            const handTiles = el.querySelectorAll(".hand-tile");
            // 2 base tiles + 1 drawn tile with gap
            expect(handTiles).toHaveLength(3);
            const drawnGap = el.querySelector(".hand-drawn-gap");
            expect(drawnGap).not.toBeNull();
        });

        test("renders all tiles inline when drawnTileId is null", () => {
            const el = renderTo(
                PlayerPanel(makePlayer({ drawnTileId: null, tiles: [0, 4, 8] }), false, false),
            );
            const drawnGap = el.querySelector(".hand-drawn-gap");
            expect(drawnGap).toBeNull();
        });

        test("renders empty hand when tiles is empty", () => {
            const el = renderTo(
                PlayerPanel(makePlayer({ drawnTileId: null, tiles: [] }), false, false),
            );
            const handTiles = el.querySelectorAll(".hand-tile");
            expect(handTiles).toHaveLength(0);
        });

        test("filters only first occurrence of drawnTileId from tiles", () => {
            // Two copies of the same tile ID; only one should be the drawn tile
            const el = renderTo(
                PlayerPanel(makePlayer({ drawnTileId: 4, tiles: [4, 4, 8] }), false, false),
            );
            const handTiles = el.querySelectorAll(".hand-tile");
            // 2 base tiles (one 4 + the 8) + 1 drawn tile (the other 4)
            expect(handTiles).toHaveLength(3);
            const drawnGap = el.querySelector(".hand-drawn-gap");
            expect(drawnGap).not.toBeNull();
        });
    });

    describe("melds", () => {
        test("renders melds when player has melds", () => {
            const ponMeld: MeldRecord = {
                calledTileId: 0,
                callerSeat: 0,
                fromSeat: 1,
                meldType: "pon",
                tileIds: [0, 1, 2],
            };
            const el = renderTo(PlayerPanel(makePlayer({ melds: [ponMeld] }), false, false));
            expect(el.querySelector(".player-panel__melds")).not.toBeNull();
            expect(el.querySelectorAll(".meld")).toHaveLength(1);
        });

        test("hides melds section when player has no melds", () => {
            const el = renderTo(PlayerPanel(makePlayer({ melds: [] }), false, false));
            expect(el.querySelector(".player-panel__melds")).toBeNull();
        });
    });

    describe("discards", () => {
        test("renders discards with grayed and riichi flags", () => {
            const discards: DiscardRecord[] = [
                { isRiichi: false, isTsumogiri: false, tileId: 0 },
                { isRiichi: true, isTsumogiri: false, tileId: 4 },
                { claimed: true, isRiichi: false, isTsumogiri: true, tileId: 8 },
            ];
            const el = renderTo(PlayerPanel(makePlayer({ discards }), false, false));
            const discardTiles = el.querySelectorAll(".discard-tile");
            expect(discardTiles).toHaveLength(3);

            const riichiTile = el.querySelector(".discard-tile-riichi");
            expect(riichiTile).not.toBeNull();

            const grayedTile = el.querySelector(".discard-tile-grayed");
            expect(grayedTile).not.toBeNull();
        });

        test("renders empty discards section when no discards", () => {
            const el = renderTo(PlayerPanel(makePlayer({ discards: [] }), false, false));
            const discardTiles = el.querySelectorAll(".discard-tile");
            expect(discardTiles).toHaveLength(0);
        });
    });
});
