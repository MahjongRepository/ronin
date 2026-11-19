import { SoundRow, WindsRow } from "@ronin/shared/settings-rows";
import { render } from "lit-html";
import { afterEach, describe, expect, it } from "vitest";

const BLOCK = "settings-page";

afterEach(() => {
    document.documentElement.lang = "";
    delete document.documentElement.dataset.winds;
    document.body.replaceChildren();
});

function mountedHost(): HTMLElement {
    const host = document.createElement("div");
    document.body.append(host);
    return host;
}

describe("SoundRow", () => {
    it("calls its handler on a click and shows the flipped state once rerendered", () => {
        const host = mountedHost();
        let on = true;
        function draw(): void {
            render(SoundRow(BLOCK, { on, onToggle }), host);
        }
        function onToggle(): void {
            on = !on;
            draw();
        }
        draw();
        const row = host.querySelector<HTMLButtonElement>(`.${BLOCK}__sound`);
        const before = row?.getAttribute("aria-checked");

        row?.click();

        expect([before, row?.getAttribute("aria-checked"), on]).toEqual(["true", "false", false]);
    });
});

describe("WindsRow", () => {
    it("offers only the scripts of the page's language", () => {
        const host = mountedHost();
        document.documentElement.lang = "ja";

        render(
            WindsRow(BLOCK, () => {}),
            host,
        );

        expect(
            [...host.querySelectorAll<HTMLElement>(`.${BLOCK}__winds-option`)].map(
                (option) => option.dataset.script,
            ),
        ).toEqual(["kanji", "latin"]);
    });
});
