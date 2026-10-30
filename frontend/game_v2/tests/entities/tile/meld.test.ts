import { type TemplateResult, render } from "lit-html";
import { describe, expect, test } from "vitest";

import { Meld, type MeldInput, meldTiles } from "@/entities/tile";

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

function laidTiles(el: HTMLElement): NodeListOf<Element> {
    return el.querySelectorAll(".meld > .meld-tile");
}

/** The index of each laid tile carrying `cls`, left to right. */
function slotsWith(el: HTMLElement, cls: string): number[] {
    return [...laidTiles(el)].flatMap((tile, idx) => (tile.classList.contains(cls) ? [idx] : []));
}

function faces(el: HTMLElement): (string | null)[] {
    return [...laidTiles(el)].map((tile) => tile.querySelector("svg")!.getAttribute("aria-label"));
}

describe("Meld - chi", () => {
    test("called tile sideways at the left, the other two sorted after it", () => {
        const input: MeldInput = {
            calledTileId: 4,
            callerSeat: 0,
            fromSeat: 3,
            meldType: "chi",
            tileIds: [8, 4, 0],
        };
        const el = renderTo(Meld(meldTiles(input)));
        expect(slotsWith(el, "meld-tile-sideways")).toEqual([0]);
        expect(faces(el)).toEqual(["2m", "1m", "3m"]);
    });
});

describe("Meld - pon (seat + 1 plays next: the caller's right, shimocha)", () => {
    test.each([
        { feeder: "kamicha", fromSeat: 3, slot: 0 },
        { feeder: "toimen", fromSeat: 2, slot: 1 },
        { feeder: "shimocha", fromSeat: 1, slot: 2 },
    ])("called from $feeder lies sideways at slot $slot", ({ fromSeat, slot }) => {
        const input: MeldInput = {
            calledTileId: 2,
            callerSeat: 0,
            fromSeat,
            meldType: "pon",
            tileIds: [0, 1, 2],
        };
        const el = renderTo(Meld(meldTiles(input)));
        expect(slotsWith(el, "meld-tile-sideways")).toEqual([slot]);
    });

    test("called from kamicha across seat 0 lies sideways at the left", () => {
        const input: MeldInput = {
            calledTileId: 38,
            callerSeat: 1,
            fromSeat: 0,
            meldType: "pon",
            tileIds: [36, 37, 38],
        };
        const el = renderTo(Meld(meldTiles(input)));
        expect(slotsWith(el, "meld-tile-sideways")).toEqual([0]);
    });
});

describe("Meld - open kan", () => {
    test.each([
        { feeder: "kamicha", fromSeat: 3, slot: 0 },
        { feeder: "toimen", fromSeat: 2, slot: 1 },
        { feeder: "shimocha", fromSeat: 1, slot: 3 },
    ])("called from $feeder lies sideways at slot $slot of 4", ({ fromSeat, slot }) => {
        const input: MeldInput = {
            calledTileId: 3,
            callerSeat: 0,
            fromSeat,
            meldType: "open_kan",
            tileIds: [0, 1, 2, 3],
        };
        const el = renderTo(Meld(meldTiles(input)));
        expect(laidTiles(el)).toHaveLength(4);
        expect(slotsWith(el, "meld-tile-sideways")).toEqual([slot]);
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
        const el = renderTo(Meld(meldTiles(input)));
        expect(el.querySelectorAll(".tile-back")).toHaveLength(2);
        expect(laidTiles(el)).toHaveLength(4);
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
        const el = renderTo(Meld(meldTiles(input)));
        expect(el.querySelectorAll(".tile-back")).toHaveLength(2);
    });
});

describe("Meld - added kan", () => {
    test.each([
        { feeder: "kamicha", fromSeat: 3, slot: 0 },
        { feeder: "toimen", fromSeat: 2, slot: 1 },
        { feeder: "shimocha", fromSeat: 1, slot: 2 },
    ])("called from $feeder stacks at slot $slot", ({ fromSeat, slot }) => {
        const input: MeldInput = {
            addedTileId: 3,
            calledTileId: 2,
            callerSeat: 0,
            fromSeat,
            meldType: "added_kan",
            tileIds: [0, 1, 2, 3],
        };
        const el = renderTo(Meld(meldTiles(input)));
        expect(laidTiles(el)).toHaveLength(3);
        expect(slotsWith(el, "meld-tile-stacked")).toEqual([slot]);
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
        const el = renderTo(Meld(meldTiles(input)));
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
        const el = renderTo(Meld(meldTiles(input)));
        // open_kan renders 4 tiles, not 3 stacked
        expect(laidTiles(el)).toHaveLength(4);
        expect(el.querySelector(".meld-tile-stacked")).toBeNull();
        expect(el.querySelector(".meld-tile-sideways")).not.toBeNull();
    });
});
