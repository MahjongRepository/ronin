import { type TemplateResult, render } from "lit-html";
import { describe, expect, test } from "vitest";

import { type DiscardTile, Discards, LYING_BODY } from "@/entities/tile";

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
    test("normal tile renders .discard-tile without riichi or latest classes", () => {
        const tiles: DiscardTile[] = [{ face: "1m" }];
        const el = renderTo(Discards(tiles));
        const wrapper = el.querySelector(".discard-tile");
        expect(wrapper).not.toBeNull();
        expect(wrapper?.classList.contains("discard-tile-riichi")).toBe(false);
        expect(wrapper?.classList.contains("discard-tile--last")).toBe(false);
    });

    test("riichi tile has .discard-tile-riichi class", () => {
        const tiles: DiscardTile[] = [{ face: "5s", riichi: true }];
        const el = renderTo(Discards(tiles));
        const wrapper = el.querySelector(".discard-tile");
        expect(wrapper?.classList.contains("discard-tile-riichi")).toBe(true);
    });

    test("reserves a riichi discard its sideways oblique slot, foreshortened along the screen's y axis in every river", () => {
        const slots = ([0, 90] as const).map((turn) => {
            const wrapper = renderTo(
                Discards([{ face: "5s", riichi: true }], "run-on", turn),
            ).querySelector<HTMLElement>(".discard-tile-riichi");
            return ["--slot-across-share", "--slot-down-share"].map((name) =>
                Number(wrapper?.style.getPropertyValue(name)),
            );
        });

        expect(slots).toEqual([
            [1, LYING_BODY.topShare],
            [LYING_BODY.topShare, 1],
        ]);
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

    test("a side river wraps 20 tiles into a fourth row of two, where a top or bottom river runs its third row on to eight", () => {
        function rowLengths(overflow: "run-on" | "wrap"): number[] {
            return [
                ...renderTo(Discards(makeTiles(20), overflow)).querySelectorAll(".discard-row"),
            ].map((row) => row.querySelectorAll(":scope > .discard-tile").length);
        }
        expect(rowLengths("wrap")).toEqual([6, 6, 6, 2]);
        expect(rowLengths("run-on")).toEqual([6, 6, 8]);
    });
});

describe("Discards paint order", () => {
    function zIndexes(el: HTMLElement): string[][] {
        return [...el.querySelectorAll(".discard-row")].map((row) =>
            [...row.querySelectorAll<HTMLElement>(":scope > .discard-tile")].map(
                (tile) => tile.style.zIndex,
            ),
        );
    }

    function joined(el: HTMLElement): boolean[][] {
        return [...el.querySelectorAll(".discard-row")].map((row) =>
            [...row.querySelectorAll(".tile__body > use")].map(
                (use) => use.getAttribute("href")?.endsWith("-joined") === true,
            ),
        );
    }

    test("paints each tile over the edge of the one above it on the screen, square-topped against it, whatever the river's turn", () => {
        const tiles = makeTiles(8);
        const rivers = [
            Discards(tiles, "run-on", 0),
            Discards(tiles, "run-on", 180),
            Discards(tiles, "wrap", 270),
            Discards(tiles, "wrap", 90),
        ].map((river) => renderTo(river));
        const [unturned, top, right] = rivers.map((river) => zIndexes(river));

        expect(unturned).toEqual([
            ["", "", "", "", "", ""],
            ["", ""],
        ]);
        expect(top).toEqual([
            ["2", "2", "2", "2", "2", "2"],
            ["1", "1"],
        ]);
        expect(right).toEqual([
            ["6", "5", "4", "3", "2", "1"],
            ["2", "1"],
        ]);
        expect(rivers.map((river) => joined(river))).toEqual([
            [
                [false, false, false, false, false, false],
                [true, true],
            ],
            [
                [true, true, false, false, false, false],
                [false, false],
            ],
            [
                [true, true, true, true, true, false],
                [true, false],
            ],
            [
                [false, true, true, true, true, true],
                [false, true],
            ],
        ]);
    });

    test("draws a side river's riichi discard upright on the screen and its others across", () => {
        const el = renderTo(
            Discards(
                makeTiles(2).map((tile, index) => ({ ...tile, riichi: index === 1 })),
                "wrap",
                90,
            ),
        );

        expect(
            [...el.querySelectorAll(".tile__body > use")].map((use) => use.getAttribute("href")),
        ).toEqual(["#body-lying-sideways", "#body-lying-joined"]);
    });
});
