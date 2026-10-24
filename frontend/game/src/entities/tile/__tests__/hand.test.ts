import { type TemplateResult, render } from "lit-html";
import { describe, expect, test } from "vitest";

import { Hand, type HandTile } from "@/entities/tile";

function renderTo(template: TemplateResult): HTMLElement {
    const el = document.createElement("div");
    render(template, el);
    return el;
}

describe("Hand tile rendering", () => {
    test("face tile renders .tile span with SVG use element", () => {
        const tiles: HandTile[] = [{ face: "1m", show: "face" }];
        const el = renderTo(Hand(tiles));
        const tile = el.querySelector(".hand-tile .tile");
        expect(tile).not.toBeNull();
        expect(tile?.querySelector("use")).not.toBeNull();
    });

    test("back tile renders .tile-back element", () => {
        const tiles: HandTile[] = [{ face: "1m", show: "back" }];
        const el = renderTo(Hand(tiles));
        expect(el.querySelector(".hand-tile .tile-back")).not.toBeNull();
    });
});

describe("Hand container", () => {
    test("renders .hand container with correct number of .hand-tile children", () => {
        const tiles: HandTile[] = [
            { face: "1m", show: "face" },
            { face: "2m", show: "face" },
            { face: "3m", show: "face" },
        ];
        const el = renderTo(Hand(tiles));
        const hand = el.querySelector(".hand");
        expect(hand).not.toBeNull();
        const children = hand?.querySelectorAll(":scope > .hand-tile");
        expect(children).toHaveLength(3);
    });

    test("drawn tile adds .hand-drawn-gap class to the drawn tile wrapper", () => {
        const tiles: HandTile[] = [{ face: "1m", show: "face" }];
        const drawn: HandTile = { face: "9m", show: "face" };
        const el = renderTo(Hand(tiles, drawn));
        const gap = el.querySelector(".hand-drawn-gap");
        expect(gap).not.toBeNull();
    });

    test("without drawn tile has no .hand-drawn-gap element", () => {
        const tiles: HandTile[] = [{ face: "1m", show: "face" }];
        const el = renderTo(Hand(tiles));
        expect(el.querySelector(".hand-drawn-gap")).toBeNull();
    });

    test("single tile hand renders 1 .hand-tile child", () => {
        const tiles: HandTile[] = [{ face: "5s", show: "face" }];
        const el = renderTo(Hand(tiles));
        const hand = el.querySelector(".hand");
        const children = hand?.querySelectorAll(":scope > .hand-tile");
        expect(children).toHaveLength(1);
    });

    test("13+1 hand renders 13 .hand-tile + 1 .hand-drawn-gap child", () => {
        const tiles: HandTile[] = [
            { face: "1m", show: "face" },
            { face: "2m", show: "face" },
            { face: "3m", show: "face" },
            { face: "4m", show: "face" },
            { face: "5m", show: "face" },
            { face: "6m", show: "face" },
            { face: "7m", show: "face" },
            { face: "8m", show: "face" },
            { face: "9m", show: "face" },
            { face: "1p", show: "face" },
            { face: "2p", show: "face" },
            { face: "3p", show: "face" },
            { face: "4p", show: "face" },
        ];
        const drawn: HandTile = { face: "5p", show: "face" };
        const el = renderTo(Hand(tiles, drawn));
        const hand = el.querySelector(".hand");
        const regularTiles = hand?.querySelectorAll(":scope > .hand-tile:not(.hand-drawn-gap)");
        expect(regularTiles).toHaveLength(13);
        const drawnTiles = hand?.querySelectorAll(":scope > .hand-drawn-gap");
        expect(drawnTiles).toHaveLength(1);
    });
});
