import { type TemplateResult, render } from "lit-html";
import { describe, expect, test } from "vitest";

import { buildRiichiAction } from "@/shared/protocol";
import { storybookView } from "@/views/storybook";
import { mountStorybookDecisions } from "@/views/storybook-decisions";
import { storybookDiscardsView } from "@/views/storybook-discards";
import { storybookHandView } from "@/views/storybook-hand";
import { storybookMeldsView } from "@/views/storybook-melds";
import { storybookNav } from "@/views/storybook-nav";

function renderTo(template: TemplateResult): HTMLElement {
    const el = document.createElement("div");
    render(template, el);
    return el;
}

describe("storybookNav", () => {
    test("renders badge links for all storybook pages", () => {
        const el = renderTo(storybookNav("/play/storybook"));
        const badges = el.querySelectorAll(".storybook-badge");
        expect([...badges].map((badge) => badge.textContent)).toEqual([
            "Index",
            "Board",
            "Decisions",
            "Discards",
            "Hand",
            "Melds",
            "Replay",
            "Rotate",
        ]);
    });

    test("marks the current page badge as active", () => {
        const el = renderTo(storybookNav("/play/storybook/melds"));
        const active = el.querySelector(".storybook-badge.active");
        expect(active).not.toBeNull();
        expect(active?.textContent).toBe("Melds");
    });
});

describe("storybookView", () => {
    test("renders nav with index badge active", () => {
        const el = renderTo(storybookView());
        const active = el.querySelector(".storybook-badge.active");
        expect(active?.textContent).toBe("Index");
    });

    test("renders a link to /play/storybook/hand", () => {
        const el = renderTo(storybookView());
        const handLink = el.querySelector('a[href="/play/storybook/hand"]');
        expect(handLink).not.toBeNull();
    });
});

describe("storybookMeldsView", () => {
    test("renders sections for all 5 meld types", () => {
        const el = renderTo(storybookMeldsView());
        const container = el.querySelector(".storybook");
        expect(container).not.toBeNull();
        const sections = container?.querySelectorAll("section");
        expect(sections).toHaveLength(5);
    });

    test("renders nav with melds badge active", () => {
        const el = renderTo(storybookMeldsView());
        const active = el.querySelector(".storybook-badge.active");
        expect(active?.textContent).toBe("Melds");
    });
});

describe("storybookDiscardsView", () => {
    test("renders all 7 discard sections", () => {
        const el = renderTo(storybookDiscardsView());
        const container = el.querySelector(".storybook");
        expect(container).not.toBeNull();
        const sections = container?.querySelectorAll("section");
        expect(sections).toHaveLength(7);
    });

    test("renders nav with discards badge active", () => {
        const el = renderTo(storybookDiscardsView());
        const active = el.querySelector(".storybook-badge.active");
        expect(active?.textContent).toBe("Discards");
    });
});

describe("storybookHandView", () => {
    test("renders all 5 hand sections", () => {
        const el = renderTo(storybookHandView());
        const container = el.querySelector(".storybook");
        expect(container).not.toBeNull();
        const sections = container?.querySelectorAll("section");
        expect(sections).toHaveLength(5);
    });

    test("renders nav with hand badge active", () => {
        const el = renderTo(storybookHandView());
        const active = el.querySelector(".storybook-badge.active");
        expect(active?.textContent).toBe("Hand");
    });

    test("renders a link to /play/storybook", () => {
        const el = renderTo(storybookHandView());
        const indexLink = el.querySelector('a[href="/play/storybook"]');
        expect(indexLink).not.toBeNull();
    });
});

describe("mountStorybookDecisions", () => {
    test("shows a transcript's checkpoint and, when its board is played, the answer the client describes", () => {
        history.replaceState(null, "", "/play/storybook/decisions?state=riichi_pick");
        const host = document.createElement("div");
        mountStorybookDecisions(host);

        const pressed = host.querySelector('.decision-controls__action[aria-pressed="true"]');
        const tiles = host.querySelectorAll(".board-local button.hand-tile--selectable");
        tiles[0]?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        const sent = host.querySelector(".decisions-storybook__sent")?.textContent ?? "";

        expect([pressed?.textContent?.trim(), tiles.length]).toEqual(["Riichi", 1]);
        expect(JSON.parse(sent)).toEqual({ message: buildRiichiAction(120, 2), type: "send" });
    });
});
