import { Tile, TileBack, TileBackColor, injectSprite } from "@/tiles";
import { type TemplateResult, render } from "lit-html";
import { afterEach, describe, expect, test } from "vitest";

function renderTo(template: TemplateResult): HTMLElement {
    const el = document.createElement("div");
    render(template, el);
    return el;
}

// injectSprite tests run first because the module-level flag is
// set permanently once called — subsequent describe blocks are unaffected
// since they only inspect rendered template markup, not the sprite DOM.
describe("injectSprite", () => {
    afterEach(() => {
        document.body.innerHTML = "";
    });

    test("only injects one sprite container when called multiple times", () => {
        injectSprite();
        injectSprite();
        const containers = document.body.querySelectorAll("[aria-hidden='true']");
        expect(containers).toHaveLength(1);
    });
});

describe("Tile", () => {
    test("face tile references the correct sprite symbol", () => {
        const el = renderTo(Tile("1m"));
        const use = el.querySelector("use");
        expect(use?.getAttribute("href")).toBe("#tile-1m");
    });

    test("red five references its own sprite symbol", () => {
        const el = renderTo(Tile("0p"));
        const use = el.querySelector("use");
        expect(use?.getAttribute("href")).toBe("#tile-0p");
    });

    test("face tile has aria-label matching its name", () => {
        const el = renderTo(Tile("5p"));
        const svgEl = el.querySelector("svg");
        expect(svgEl?.getAttribute("aria-label")).toBe("5p");
    });

    test("'back' renders tile-back instead of a sprite reference", () => {
        const el = renderTo(Tile("back"));
        expect(el.querySelector(".tile-back")).not.toBeNull();
        expect(el.querySelector("use")).toBeNull();
    });
});

describe("TileBack", () => {
    test("has aria-label 'back'", () => {
        const el = renderTo(TileBack());
        const span = el.querySelector(".tile-back");
        expect(span?.getAttribute("aria-label")).toBe("back");
    });
});

describe("TileBackColor", () => {
    test("renders with configured background color", () => {
        const el = renderTo(TileBackColor());
        const span = el.querySelector(".tile-back-color") as HTMLElement;
        expect(span.style.background).toContain("#f0d070");
    });

    test("has aria-label 'back'", () => {
        const el = renderTo(TileBackColor());
        const span = el.querySelector(".tile-back-color");
        expect(span?.getAttribute("aria-label")).toBe("back");
    });
});
