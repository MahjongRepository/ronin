import { type TemplateResult, render } from "lit-html";
import { afterEach, describe, expect, test, vi } from "vitest";

import {
    STANDING_BODY,
    StandingTile,
    TILE_FACES,
    TILE_LABELS_KEY,
    Tile,
    applyTileLabels,
    injectTileBodies,
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

const BODIES =
    '<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0"><symbol id="body-standing" viewBox="0 0 100 150"><rect width="100" height="150"/></symbol></svg>';

describe("injectTileBodies", () => {
    afterEach(() => {
        document.body.innerHTML = "";
    });

    test("puts the body symbols in a rendered zero-size sprite, so their gradients and masks paint through a use", () => {
        injectTileBodies(BODIES);

        const sprite = document.querySelector("symbol#body-standing")?.closest("svg");
        expect([sprite?.style.display, sprite?.style.width, sprite?.style.height]).toEqual([
            "",
            "0px",
            "0px",
        ]);
        expect(sprite?.getAttribute("aria-hidden")).toBe("true");
    });

    test("throws on markup with no body symbol", () => {
        expect(() => injectTileBodies(SPRITE)).toThrow("the tile body sprite holds no body symbol");
        expect(document.body.childElementCount).toBe(0);
    });
});

describe("StandingTile", () => {
    function artOf(face: "1m" | "1p"): Record<"bottom" | "top" | "width", number> {
        const el = renderTo(StandingTile(face, null));
        const box = el.querySelector("svg.tile__face");
        const art = box?.querySelector(`use[href="#tile-${face}"]`);
        const [boxTop, boxWidth, boxHeight] = ["y", "width", "height"].map((name) =>
            Number(box?.getAttribute(name)),
        );
        const [, viewTop = 0, viewWidth = 0, viewHeight = 0] = (box?.getAttribute("viewBox") ?? "")
            .split(" ")
            .map(Number);
        const across = boxWidth / viewWidth;
        const down = boxHeight / viewHeight;
        return {
            bottom: boxTop + (Number(art?.getAttribute("height")) - viewTop) * down,
            top: boxTop - viewTop * down,
            width: Number(art?.getAttribute("width")) * across,
        };
    }

    test("draws a man face's art larger than a pin face's, each below the body's crest and inside its height", () => {
        const man = artOf("1m");
        const pin = artOf("1p");

        expect(man.width).toBeGreaterThan(pin.width * 1.03);
        for (const art of [man, pin]) {
            expect(art.top).toBeGreaterThan(STANDING_BODY.ridge * 100);
            expect(art.bottom).toBeLessThan(STANDING_BODY.height * 100);
        }
    });

    test("keeps a red five's name red and marks its corner label as a red five's, below the face's top", () => {
        const el = renderTo(StandingTile("0s", "latin"));
        const box = el.querySelector("svg.tile__face");
        const label = el.querySelector(".tile__label");
        const [, top = 0] = (box?.getAttribute("viewBox") ?? "").split(" ").map(Number);

        expect([
            el.querySelector(".tile__name")?.classList.contains("tile__name--red"),
            label?.classList.contains("tile__label--red-five"),
            label?.closest("svg") === box,
        ]).toEqual([true, true, true]);
        expect(Number(label?.getAttribute("y"))).toBeGreaterThan(top);
    });
});

describe("Tile", () => {
    test("spans a face's viewport over the whole body, so a corner label past the art box stays whole", () => {
        const el = renderTo(Tile("9m", "face", { labels: "latin" }));
        const body = el.querySelector("svg.tile__body");
        const face = el.querySelector("svg.tile__face");
        const [left = 0, , width = 0] = (face?.getAttribute("viewBox") ?? "")
            .split(" ")
            .map(Number);
        const labelX = Number(el.querySelector(".tile__label")?.getAttribute("x"));

        expect(`0 0 ${face?.getAttribute("width")} ${face?.getAttribute("height")}`).toBe(
            body?.getAttribute("viewBox"),
        );
        expect(labelX).toBeGreaterThan(300);
        expect(labelX).toBeLessThan(left + width);
    });

    test("face tile references the correct sprite symbol", () => {
        const el = renderTo(Tile("1m", "face"));
        const use = el.querySelector('use[href^="#tile-"]');
        expect(use?.getAttribute("href")).toBe("#tile-1m");
    });

    test("red five references its own sprite symbol", () => {
        const el = renderTo(Tile("0p", "face"));
        const use = el.querySelector('use[href^="#tile-"]');
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
        expect(el.querySelector('use[href^="#tile-"]')).toBeNull();
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
            const red =
                label?.classList.contains("tile__label--red-five") === true ? " red five" : "";
            return label === null ? null : `${label.textContent}${red}`;
        });
    }

    test("label a suit tile by its rank, a red five's marked as one, a wind in the page's wind script and a dragon by its colour, an honor unlabelled in kanji", () => {
        document.documentElement.lang = "ru";
        const off = labels();
        applyTileLabels(true);
        const latin = labels();
        applyWindScript("cyrillic");
        const cyrillic = labels();
        applyWindScript("kanji");

        expect([off, latin, cyrillic, labels()]).toEqual([
            [null, null, null, null, null],
            ["5 red five", "9", "S", "Wh", "R"],
            ["5 red five", "9", "Ю", "Б", "К"],
            ["5 red five", "9", null, null, null],
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
            ["5 red five", "9", "S", "Wh", "R"],
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
