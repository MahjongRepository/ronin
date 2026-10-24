import { type TemplateResult, render } from "lit-html";
import { describe, expect, test } from "vitest";

import { type DiscardTile, Discards } from "@/entities/tile";

function renderTo(template: TemplateResult): HTMLElement {
    const el = document.createElement("div");
    render(template, el);
    return el;
}

function makeTiles(count: number, overrides?: Partial<DiscardTile>): DiscardTile[] {
    const faces = [
        "1m",
        "2m",
        "3m",
        "4m",
        "5m",
        "6m",
        "7m",
        "8m",
        "9m",
        "1p",
        "2p",
        "3p",
        "4p",
        "5p",
        "6p",
        "7p",
        "8p",
        "9p",
        "1s",
        "2s",
    ] as const;
    return Array.from({ length: count }, (_unused, i) => ({
        face: faces[i % faces.length],
        ...overrides,
    }));
}

describe("Discards tile classes", () => {
    test("normal tile renders .discard-tile without grayed or riichi classes", () => {
        const tiles: DiscardTile[] = [{ face: "1m" }];
        const el = renderTo(Discards(tiles));
        const wrapper = el.querySelector(".discard-tile");
        expect(wrapper).not.toBeNull();
        expect(wrapper?.classList.contains("discard-tile-grayed")).toBe(false);
        expect(wrapper?.classList.contains("discard-tile-riichi")).toBe(false);
    });

    test("grayed tile has .discard-tile-grayed class", () => {
        const tiles: DiscardTile[] = [{ face: "3p", grayed: true }];
        const el = renderTo(Discards(tiles));
        const wrapper = el.querySelector(".discard-tile");
        expect(wrapper?.classList.contains("discard-tile-grayed")).toBe(true);
    });

    test("riichi tile has .discard-tile-riichi class", () => {
        const tiles: DiscardTile[] = [{ face: "5s", riichi: true }];
        const el = renderTo(Discards(tiles));
        const wrapper = el.querySelector(".discard-tile");
        expect(wrapper?.classList.contains("discard-tile-riichi")).toBe(true);
    });

    test("tile with both grayed and riichi has both classes", () => {
        const tiles: DiscardTile[] = [{ face: "7z", grayed: true, riichi: true }];
        const el = renderTo(Discards(tiles));
        const wrapper = el.querySelector(".discard-tile");
        expect(wrapper?.classList.contains("discard-tile-grayed")).toBe(true);
        expect(wrapper?.classList.contains("discard-tile-riichi")).toBe(true);
    });
});

describe("Discards container", () => {
    test("renders .discards container with correct number of .discard-tile children", () => {
        const tiles = makeTiles(4);
        const el = renderTo(Discards(tiles));
        const container = el.querySelector(".discards");
        expect(container).not.toBeNull();
        const allTiles = container?.querySelectorAll(".discard-tile");
        expect(allTiles).toHaveLength(4);
    });

    test("empty discards renders .discards container with no rows", () => {
        const el = renderTo(Discards([]));
        const container = el.querySelector(".discards");
        expect(container).not.toBeNull();
        expect(container?.querySelectorAll(".discard-row")).toHaveLength(0);
    });
});

describe("Discards row splitting", () => {
    test("6 tiles produce 1 row with 6 tiles", () => {
        const el = renderTo(Discards(makeTiles(6)));
        const rows = el.querySelectorAll(".discard-row");
        expect(rows).toHaveLength(1);
        expect(rows[0].querySelectorAll(":scope > .discard-tile")).toHaveLength(6);
    });

    test("12 tiles produce 2 rows with 6 tiles each", () => {
        const el = renderTo(Discards(makeTiles(12)));
        const rows = el.querySelectorAll(".discard-row");
        expect(rows).toHaveLength(2);
        expect(rows[0].querySelectorAll(":scope > .discard-tile")).toHaveLength(6);
        expect(rows[1].querySelectorAll(":scope > .discard-tile")).toHaveLength(6);
    });

    test("20 tiles produce 3 rows: 6, 6, 8", () => {
        const el = renderTo(Discards(makeTiles(20)));
        const rows = el.querySelectorAll(".discard-row");
        expect(rows).toHaveLength(3);
        expect(rows[0].querySelectorAll(":scope > .discard-tile")).toHaveLength(6);
        expect(rows[1].querySelectorAll(":scope > .discard-tile")).toHaveLength(6);
        expect(rows[2].querySelectorAll(":scope > .discard-tile")).toHaveLength(8);
    });
});
