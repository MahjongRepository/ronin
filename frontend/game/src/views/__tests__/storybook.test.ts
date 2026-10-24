import { type TemplateResult, render } from "lit-html";
import { describe, expect, test } from "vitest";

import { storybookView } from "@/views/storybook";
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
        expect(badges).toHaveLength(5);
        expect(badges[0].textContent).toBe("Index");
        expect(badges[1].textContent).toBe("Board");
        expect(badges[2].textContent).toBe("Discards");
        expect(badges[3].textContent).toBe("Hand");
        expect(badges[4].textContent).toBe("Melds");
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
    test("renders all 6 discard sections", () => {
        const el = renderTo(storybookDiscardsView());
        const container = el.querySelector(".storybook");
        expect(container).not.toBeNull();
        const sections = container?.querySelectorAll("section");
        expect(sections).toHaveLength(6);
    });

    test("renders nav with discards badge active", () => {
        const el = renderTo(storybookDiscardsView());
        const active = el.querySelector(".storybook-badge.active");
        expect(active?.textContent).toBe("Discards");
    });
});

describe("storybookHandView", () => {
    test("renders all 4 hand sections", () => {
        const el = renderTo(storybookHandView());
        const container = el.querySelector(".storybook");
        expect(container).not.toBeNull();
        const sections = container?.querySelectorAll("section");
        expect(sections).toHaveLength(4);
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
