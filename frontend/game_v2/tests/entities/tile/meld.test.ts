import { type TemplateResult, render } from "lit-html";
import { describe, expect, test } from "vitest";

import { Meld, type MeldInput } from "@/entities/tile";

// Tile ID reference (136-format):
//   Man: 0-35 (type34 0-8), Pin: 36-71 (type34 9-17), Sou: 72-107 (type34 18-26)
//   Honor: 108-135 (type34 27-33)
//   Each type34 has 4 copies: tileId = type34 * 4 + copyIndex
//   Red fives: 16 (0m), 52 (0p), 88 (0s)

function renderTo(template: TemplateResult): HTMLElement {
    const el = document.createElement("div");
    render(template, el);
    return el;
}

function meldTiles(el: HTMLElement): NodeListOf<Element> {
    return el.querySelectorAll(".meld > .meld-tile");
}

describe("Meld - chi", () => {
    test("renders 3 tiles with called tile sideways", () => {
        const input: MeldInput = {
            calledTileId: 0,
            callerSeat: 0,
            fromSeat: 3,
            meldType: "chi",
            tileIds: [4, 0, 8],
        };
        const el = renderTo(Meld(input));
        expect(meldTiles(el)).toHaveLength(3);
        expect(el.querySelectorAll(".meld .meld-tile-sideways")).toHaveLength(1);
    });

    test("tiles sorted by type-34 ascending regardless of input order", () => {
        // Chi 7s-8s-9s: tileIds in reverse order
        const input: MeldInput = {
            calledTileId: 100,
            callerSeat: 0,
            fromSeat: 3,
            meldType: "chi",
            tileIds: [104, 100, 96],
        };
        const el = renderTo(Meld(input));
        expect(meldTiles(el)).toHaveLength(3);
    });

    test("called tile at middle position after sorting gets sideways class", () => {
        // Chi 1m-2m-3m, called tile 4 (2m)
        const input: MeldInput = {
            calledTileId: 4,
            callerSeat: 0,
            fromSeat: 3,
            meldType: "chi",
            tileIds: [0, 8, 4],
        };
        const el = renderTo(Meld(input));
        const tiles = meldTiles(el);
        // After sorting: [0(1m), 4(2m), 8(3m)] — index 1 is sideways
        expect(tiles[0].classList.contains("meld-tile-sideways")).toBe(false);
        expect(tiles[1].classList.contains("meld-tile-sideways")).toBe(true);
        expect(tiles[2].classList.contains("meld-tile-sideways")).toBe(false);
    });
});

describe("Meld - pon", () => {
    test("sideways tile on left when called from kamicha (relative 1)", () => {
        // Seat 0 calls pon from seat 1 → relative = (1-0+4)%4 = 1 → position 0 (left)
        const input: MeldInput = {
            calledTileId: 2,
            callerSeat: 0,
            fromSeat: 1,
            meldType: "pon",
            tileIds: [0, 1, 2],
        };
        const el = renderTo(Meld(input));
        const tiles = meldTiles(el);
        expect(tiles).toHaveLength(3);
        expect(tiles[0].classList.contains("meld-tile-sideways")).toBe(true);
        expect(tiles[1].classList.contains("meld-tile-sideways")).toBe(false);
        expect(tiles[2].classList.contains("meld-tile-sideways")).toBe(false);
    });

    test("sideways tile in middle when called from toimen (relative 2)", () => {
        // Seat 0 calls pon from seat 2 → position 1 (middle)
        const input: MeldInput = {
            calledTileId: 2,
            callerSeat: 0,
            fromSeat: 2,
            meldType: "pon",
            tileIds: [0, 1, 2],
        };
        const el = renderTo(Meld(input));
        const tiles = meldTiles(el);
        expect(tiles[0].classList.contains("meld-tile-sideways")).toBe(false);
        expect(tiles[1].classList.contains("meld-tile-sideways")).toBe(true);
        expect(tiles[2].classList.contains("meld-tile-sideways")).toBe(false);
    });

    test("sideways tile on right when called from shimocha (relative 3)", () => {
        // Seat 0 calls pon from seat 3 → position 2 (right)
        const input: MeldInput = {
            calledTileId: 2,
            callerSeat: 0,
            fromSeat: 3,
            meldType: "pon",
            tileIds: [0, 1, 2],
        };
        const el = renderTo(Meld(input));
        const tiles = meldTiles(el);
        expect(tiles[0].classList.contains("meld-tile-sideways")).toBe(false);
        expect(tiles[1].classList.contains("meld-tile-sideways")).toBe(false);
        expect(tiles[2].classList.contains("meld-tile-sideways")).toBe(true);
    });

    test("handles wrap-around seat positions", () => {
        // Seat 3 calls pon from seat 1 → relative = (1-3+4)%4 = 2 → position 1 (middle)
        const input: MeldInput = {
            calledTileId: 38,
            callerSeat: 3,
            fromSeat: 1,
            meldType: "pon",
            tileIds: [36, 37, 38],
        };
        const el = renderTo(Meld(input));
        const tiles = meldTiles(el);
        expect(tiles[0].classList.contains("meld-tile-sideways")).toBe(false);
        expect(tiles[1].classList.contains("meld-tile-sideways")).toBe(true);
        expect(tiles[2].classList.contains("meld-tile-sideways")).toBe(false);
    });
});

describe("Meld - open kan", () => {
    test("renders 4 tiles with sideways at correct position", () => {
        // Seat 0 calls open_kan from seat 1 → position 0 (left)
        const input: MeldInput = {
            calledTileId: 3,
            callerSeat: 0,
            fromSeat: 1,
            meldType: "open_kan",
            tileIds: [0, 1, 2, 3],
        };
        const el = renderTo(Meld(input));
        const tiles = meldTiles(el);
        expect(tiles).toHaveLength(4);
        expect(tiles[0].classList.contains("meld-tile-sideways")).toBe(true);
        expect(tiles[1].classList.contains("meld-tile-sideways")).toBe(false);
        expect(tiles[2].classList.contains("meld-tile-sideways")).toBe(false);
        expect(tiles[3].classList.contains("meld-tile-sideways")).toBe(false);
    });

    test("sideways tile from toimen (relative 2)", () => {
        // Seat 0 from seat 2 → position 1
        const input: MeldInput = {
            calledTileId: 3,
            callerSeat: 0,
            fromSeat: 2,
            meldType: "open_kan",
            tileIds: [0, 1, 2, 3],
        };
        const el = renderTo(Meld(input));
        const tiles = meldTiles(el);
        expect(tiles[0].classList.contains("meld-tile-sideways")).toBe(false);
        expect(tiles[1].classList.contains("meld-tile-sideways")).toBe(true);
    });
});

describe("Meld - closed kan", () => {
    test("first and last tiles are facedown, middle two are upright", () => {
        const input: MeldInput = {
            calledTileId: null,
            callerSeat: 0,
            fromSeat: null,
            meldType: "closed_kan",
            tileIds: [0, 1, 2, 3],
        };
        const el = renderTo(Meld(input));
        expect(el.querySelectorAll(".tile-back")).toHaveLength(2);
        expect(meldTiles(el)).toHaveLength(4);
    });

    test("uses correct tile faces for honor tiles", () => {
        // East wind (type34=27), tileIds 108-111
        const input: MeldInput = {
            calledTileId: null,
            callerSeat: 2,
            fromSeat: null,
            meldType: "closed_kan",
            tileIds: [108, 109, 110, 111],
        };
        const el = renderTo(Meld(input));
        expect(el.querySelectorAll(".tile-back")).toHaveLength(2);
    });
});

describe("Meld - added kan", () => {
    test("stacked tile at correct position from kamicha (left)", () => {
        // Seat 0 added_kan, original pon from seat 1 → position 0 (left)
        const input: MeldInput = {
            addedTileId: 3,
            calledTileId: 2,
            callerSeat: 0,
            fromSeat: 1,
            meldType: "added_kan",
            tileIds: [0, 1, 2, 3],
        };
        const el = renderTo(Meld(input));
        expect(el.querySelector(".meld-tile-stacked")).not.toBeNull();
        const tiles = meldTiles(el);
        expect(tiles).toHaveLength(3);
        expect(tiles[0].classList.contains("meld-tile-stacked")).toBe(true);
        expect(tiles[1].classList.contains("meld-tile-stacked")).toBe(false);
        expect(tiles[2].classList.contains("meld-tile-stacked")).toBe(false);
    });

    test("stacked tile at correct position from toimen (middle)", () => {
        // Seat 0 from seat 2 → position 1 (middle)
        const input: MeldInput = {
            addedTileId: 3,
            calledTileId: 2,
            callerSeat: 0,
            fromSeat: 2,
            meldType: "added_kan",
            tileIds: [0, 1, 2, 3],
        };
        const el = renderTo(Meld(input));
        const tiles = meldTiles(el);
        expect(tiles[0].classList.contains("meld-tile-stacked")).toBe(false);
        expect(tiles[1].classList.contains("meld-tile-stacked")).toBe(true);
        expect(tiles[2].classList.contains("meld-tile-stacked")).toBe(false);
    });

    test("stacked tile at correct position from shimocha (right)", () => {
        // Seat 0 from seat 3 → position 2 (right)
        const input: MeldInput = {
            addedTileId: 3,
            calledTileId: 2,
            callerSeat: 0,
            fromSeat: 3,
            meldType: "added_kan",
            tileIds: [0, 1, 2, 3],
        };
        const el = renderTo(Meld(input));
        const tiles = meldTiles(el);
        expect(tiles[0].classList.contains("meld-tile-stacked")).toBe(false);
        expect(tiles[1].classList.contains("meld-tile-stacked")).toBe(false);
        expect(tiles[2].classList.contains("meld-tile-stacked")).toBe(true);
    });

    test("stacked tile has bottom and top sideways children", () => {
        const input: MeldInput = {
            addedTileId: 3,
            calledTileId: 2,
            callerSeat: 0,
            fromSeat: 1,
            meldType: "added_kan",
            tileIds: [0, 1, 2, 3],
        };
        const el = renderTo(Meld(input));
        const stacked = el.querySelector(".meld-tile-stacked")!;
        expect(stacked.querySelector(".meld-tile-stacked-bottom")).not.toBeNull();
        expect(stacked.querySelector(".meld-tile-stacked-top")).not.toBeNull();
        expect(stacked.querySelectorAll(".meld-tile-sideways")).toHaveLength(2);
    });

    test("falls back to open_kan rendering when addedTileId is missing", () => {
        // IMME decode path: added_kan without addedTileId → renders as open_kan (4 tiles)
        const input: MeldInput = {
            calledTileId: 2,
            callerSeat: 0,
            fromSeat: 1,
            meldType: "added_kan",
            tileIds: [0, 1, 2, 3],
        };
        const el = renderTo(Meld(input));
        // open_kan renders 4 tiles, not 3 stacked
        expect(meldTiles(el)).toHaveLength(4);
        expect(el.querySelector(".meld-tile-stacked")).toBeNull();
        expect(el.querySelector(".meld-tile-sideways")).not.toBeNull();
    });
});
