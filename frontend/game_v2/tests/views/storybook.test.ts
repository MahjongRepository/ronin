import { type TemplateResult, render } from "lit-html";
import { afterEach, describe, expect, test } from "vitest";

import { loadSeatScenario, receivedPayload } from "#tests/fixtures/seat-transcripts";
import { CLIENT_MESSAGE_TYPE, GAME_ACTION, buildRiichiAction } from "@/shared/protocol";
import { storybookView } from "@/views/storybook";
import { mountStorybookDecisions } from "@/views/storybook-decisions";
import { storybookDiscardsView } from "@/views/storybook-discards";
import { storybookHandView } from "@/views/storybook-hand";
import { storybookMeldsView } from "@/views/storybook-melds";
import { storybookHref, storybookNav } from "@/views/storybook-nav";

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
            "Sounds",
        ]);
    });

    test("marks the current page badge as active", () => {
        const el = renderTo(storybookNav("/play/storybook/melds"));
        const active = el.querySelector(".storybook-badge.active");
        expect(active).not.toBeNull();
        expect(active?.textContent).toBe("Melds");
    });
});

describe("storybookHref", () => {
    test("carries only the page's client version, beside the link's own query", () => {
        expect([
            storybookHref("/play/storybook/replay?state=game_end", "?state=kicked&v=2&debug"),
            storybookHref("/play/storybook", "?state=kicked"),
            storybookHref("/play/storybook/board?state=worst#seat", "?v=2"),
        ]).toEqual([
            "/play/storybook/replay?state=game_end&v=2",
            "/play/storybook",
            "/play/storybook/board?state=worst&v=2#seat",
        ]);
    });
});

describe("storybookView", () => {
    afterEach(() => {
        history.replaceState(null, "", "/");
    });

    test("keeps the v2 client's query on every link: the header's and the replay stories'", () => {
        history.replaceState(null, "", "/play/storybook?v=2");
        const hrefs = [...renderTo(storybookView()).querySelectorAll("a")].map((link) =>
            new URL(link.href).searchParams.get("v"),
        );

        expect(hrefs.length).toBeGreaterThan(8);
        expect(hrefs.filter((version) => version !== "2")).toEqual([]);
    });

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

const CALL_PROMPT = loadSeatScenario("call_prompt_seat_1").transcript;

/** The decisions storybook mounted on the story `story` names. */
function mountStory(story: string): HTMLElement {
    history.replaceState(null, "", `/play/storybook/decisions?state=${story}`);
    const host = document.createElement("div");
    mountStorybookDecisions(host);
    return host;
}

describe("mountStorybookDecisions", () => {
    test("shows a transcript's checkpoint and, when its board is played, the answer the client describes", () => {
        const host = mountStory("riichi_pick");

        const pressed = host.querySelector('.decision-controls__action[aria-pressed="true"]');
        const tiles = host.querySelectorAll(".board-local button.hand-tile--declaring");
        tiles[0]?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        const sent = host.querySelector(".decisions-storybook__sent")?.textContent ?? "";

        expect([pressed?.textContent?.trim(), tiles.length]).toEqual(["Riichi", 1]);
        expect(JSON.parse(sent)).toEqual({ message: buildRiichiAction(120, 2), type: "send" });
    });

    test("its Back link keeps the v2 client's query", () => {
        const back =
            mountStory("call_prompt&v=2").querySelector<HTMLAnchorElement>(
                "a.board-storybook__btn",
            );

        expect(back?.getAttribute("href")).toBe("/play/storybook?v=2");
    });

    test("builds every story the picker lists from its transcript's checkpoint", () => {
        const picker = mountStory("call_prompt");
        const stories = [...picker.querySelectorAll("option")].map((option) => option.value);

        expect(stories).not.toEqual([]);
        for (const story of stories) {
            expect(mountStory(story).querySelector(".game-board"), story).not.toBeNull();
        }
    });

    test("the page's settings cog says what ended the session: removed, replaced by another tab, or the game's end", () => {
        const labels = ["kicked", "replaced", "game_end"].map((story) =>
            mountStory(story).querySelector(".game-menu__toggle")?.getAttribute("aria-label"),
        );

        expect(labels).toEqual(["Settings, Removed", "Settings, Replaced", "Settings, Ended"]);
    });

    test("reopens the kuikae turn on the move_refused story's scripted refusal: its notice, and a discard sends again", () => {
        const host = mountStory("move_refused");
        const turnWaitId = Number(receivedPayload(CALL_PROMPT, "turn").wi);
        const [playable] = host.querySelectorAll<HTMLElement>(
            ".board-local .hand-tile--selectable",
        );
        playable.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        const sent = JSON.parse(
            host.querySelector(".decisions-storybook__sent")?.textContent ?? "",
        );

        expect(host.querySelector(".board-notice--warning")).not.toBeNull();
        expect(sent).toMatchObject({
            message: { t: CLIENT_MESSAGE_TYPE.GAME_ACTION, wi: turnWaitId },
        });
        expect(sent.message.a).toBe(GAME_ACTION.DISCARD);
    });
});
