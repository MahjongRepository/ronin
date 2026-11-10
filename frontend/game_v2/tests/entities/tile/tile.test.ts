import { type TemplateResult, render } from "lit-html";
import { afterEach, describe, expect, test, vi } from "vitest";

import {
    TILE_FACES,
    TILE_LABELS_KEY,
    Tile,
    applyTileLabels,
    injectTileSprite,
    restoreTileLabels,
    spokenTileName,
} from "@/entities/tile";
import { WIND_SCRIPT_KEY, applyWindScript, t } from "@/shared/i18n";

function renderTo(template: TemplateResult): HTMLElement {
    const el = document.createElement("div");
    render(template, el);
    return el;
}

const SPRITE =
    '<svg xmlns="http://www.w3.org/2000/svg"><symbol id="tile-1m" viewBox="0 0 300 400"><path d="M0 0h1"/></symbol></svg>';

describe("injectTileSprite", () => {
    afterEach(() => {
        document.body.innerHTML = "";
        delete document.documentElement.dataset.tileSprite;
    });

    test("puts the sprite's symbols in the document and marks the root, which hides the tiles' names", () => {
        injectTileSprite(SPRITE);

        expect(document.querySelector("symbol#tile-1m")).not.toBeNull();
        expect(document.documentElement.dataset.tileSprite).toBe("ready");
    });

    test("throws on markup with no tile symbol, such as an error page, and leaves the root unmarked", () => {
        expect(() => injectTileSprite("<html><body>Bad gateway</body></html>")).toThrow(
            "the tile sprite holds no tile symbol",
        );

        expect(document.body.childElementCount).toBe(0);
        expect(document.documentElement.dataset.tileSprite).toBeUndefined();
    });
});

describe("Tile", () => {
    test("face tile references the correct sprite symbol", () => {
        const el = renderTo(Tile("1m", "face"));
        const use = el.querySelector("use");
        expect(use?.getAttribute("href")).toBe("#tile-1m");
    });

    test("red five references its own sprite symbol", () => {
        const el = renderTo(Tile("0p", "face"));
        const use = el.querySelector("use");
        expect(use?.getAttribute("href")).toBe("#tile-0p");
    });

    test("face tile has aria-label matching its name", () => {
        const el = renderTo(Tile("5p", "face"));
        const svgEl = el.querySelector("svg");
        expect(svgEl?.getAttribute("aria-label")).toBe("5-pin");
    });

    test("face tile shows its short name under the sprite, a red five's in red", () => {
        const names = (["0p", "9s", "1z", "7z"] as const).map((face) => {
            const name = renderTo(Tile(face, "face")).querySelector("text");
            return [name?.textContent, name?.classList.contains("tile__name--red")];
        });

        expect(names).toEqual([
            ["5p", true],
            ["9s", false],
            ["東", false],
            ["中", false],
        ]);
    });

    test("back mode renders tile-back instead of a sprite reference", () => {
        const el = renderTo(Tile("1m", "back"));
        expect(el.querySelector(".tile-back")).not.toBeNull();
        expect(el.querySelector("use")).toBeNull();
    });
});

describe("Tile labels", () => {
    afterEach(() => {
        document.documentElement.lang = "";
        delete document.documentElement.dataset.tileLabels;
        delete document.documentElement.dataset.winds;
        localStorage.removeItem(TILE_LABELS_KEY);
        localStorage.removeItem(WIND_SCRIPT_KEY);
    });

    function labels(): (string | null)[] {
        return (["0p", "9s", "2z", "5z", "7z"] as const).map((face) => {
            const label = renderTo(Tile(face, "face")).querySelector(".tile__label");
            const red = label?.classList.contains("tile__label--red") === true ? " red" : "";
            return label === null ? null : `${label.textContent}${red}`;
        });
    }

    test("label a suit tile by its rank, a red five's in red, a wind in the page's wind script and a dragon by its colour, an honor unlabelled in kanji", () => {
        document.documentElement.lang = "ru";
        const off = labels();
        applyTileLabels(true);
        const latin = labels();
        applyWindScript("cyrillic");
        const cyrillic = labels();
        applyWindScript("kanji");

        expect([off, latin, cyrillic, labels()]).toEqual([
            [null, null, null, null, null],
            ["5 red", "9", "S", "Wh", "R"],
            ["5 red", "9", "Ю", "Б", "К"],
            ["5 red", "9", null, null, null],
        ]);
    });

    test("come back on at the next page load once switched on, and stay off once switched off", () => {
        applyTileLabels(true);
        delete document.documentElement.dataset.tileLabels;
        restoreTileLabels();
        const restoredOn = labels();
        applyTileLabels(false);
        restoreTileLabels();

        expect([restoredOn, labels()]).toEqual([
            ["5 red", "9", "S", "Wh", "R"],
            [null, null, null, null, null],
        ]);
    });
});

describe("spokenTileName", () => {
    afterEach(() => {
        document.documentElement.lang = "";
        vi.restoreAllMocks();
    });

    test.each([
        ["en", "5-pin"],
        ["ja", "ウーピン"],
        ["ru", "пятёрка пин"],
    ])("speaks every tile face in %s without the generic fallback", (locale, fivePin) => {
        document.documentElement.lang = locale;
        const report = vi.spyOn(console, "error").mockImplementation(() => undefined);

        const names = TILE_FACES.map(spokenTileName);

        expect(names).not.toContain(t("tile.unknown"));
        expect(new Set(names).size).toBe(TILE_FACES.length);
        expect(spokenTileName("5p")).toBe(fivePin);
        expect(report).not.toHaveBeenCalled();
    });
});
