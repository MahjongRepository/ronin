import { type TemplateResult, render } from "lit-html";
import { describe, expect, test } from "vitest";

import { Meld, type MeldTileDisplay } from "@/entities/tile";

function renderTo(template: TemplateResult): HTMLElement {
    const el = document.createElement("div");
    render(template, el);
    return el;
}

describe("MeldTile", () => {
    test("upright tile renders a .tile span inside .meld-tile without sideways class", () => {
        const tiles: MeldTileDisplay[] = [{ face: "1m", kind: "upright" }];
        const el = renderTo(Meld(tiles));
        const wrapper = el.querySelector(".meld-tile");
        expect(wrapper).not.toBeNull();
        expect(wrapper?.classList.contains("meld-tile-sideways")).toBe(false);
        expect(wrapper?.querySelector(".tile")).not.toBeNull();
    });

    test("sideways tile has .meld-tile-sideways class and contains a .tile child", () => {
        const tiles: MeldTileDisplay[] = [{ face: "3p", kind: "sideways" }];
        const el = renderTo(Meld(tiles));
        const wrapper = el.querySelector(".meld-tile-sideways");
        expect(wrapper).not.toBeNull();
        expect(wrapper?.querySelector(".tile")).not.toBeNull();
    });

    test("facedown tile renders a .tile-back element", () => {
        const tiles: MeldTileDisplay[] = [{ face: "1z", kind: "facedown" }];
        const el = renderTo(Meld(tiles));
        expect(el.querySelector(".tile-back")).not.toBeNull();
    });

    test("stacked tile renders .meld-tile-stacked with two .meld-tile-sideways children", () => {
        const tiles: MeldTileDisplay[] = [{ bottom: "6s", kind: "stacked", top: "6s" }];
        const el = renderTo(Meld(tiles));
        const stacked = el.querySelector(".meld-tile-stacked");
        expect(stacked).not.toBeNull();
        const sidewaysChildren = stacked?.querySelectorAll(".meld-tile-sideways");
        expect(sidewaysChildren).toHaveLength(2);
        expect(stacked?.querySelector(".meld-tile-stacked-bottom")).not.toBeNull();
        expect(stacked?.querySelector(".meld-tile-stacked-top")).not.toBeNull();
    });
});

describe("Meld", () => {
    test("renders a .meld container with correct number of children", () => {
        const tiles: MeldTileDisplay[] = [
            { face: "1m", kind: "upright" },
            { face: "2m", kind: "upright" },
            { face: "3m", kind: "upright" },
        ];
        const el = renderTo(Meld(tiles));
        const meld = el.querySelector(".meld");
        expect(meld).not.toBeNull();
        const children = meld?.querySelectorAll(":scope > .meld-tile");
        expect(children).toHaveLength(3);
    });

    test("chi meld (1 sideways + 2 upright) has exactly one .meld-tile-sideways", () => {
        const tiles: MeldTileDisplay[] = [
            { face: "2m", kind: "sideways" },
            { face: "3m", kind: "upright" },
            { face: "4m", kind: "upright" },
        ];
        const el = renderTo(Meld(tiles));
        const sideways = el.querySelectorAll(":scope .meld > .meld-tile-sideways");
        expect(sideways).toHaveLength(1);
    });

    test("closed kan (facedown, upright, upright, facedown) has exactly two .tile-back elements", () => {
        const tiles: MeldTileDisplay[] = [
            { face: "1z", kind: "facedown" },
            { face: "1z", kind: "upright" },
            { face: "1z", kind: "upright" },
            { face: "1z", kind: "facedown" },
        ];
        const el = renderTo(Meld(tiles));
        const backs = el.querySelectorAll(".tile-back");
        expect(backs).toHaveLength(2);
    });
});
