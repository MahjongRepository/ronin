import { html, render } from "lit-html";
import { describe, expect, it } from "vitest";

import { tableStateToDisplayState } from "@/entities/table/lib/board-mapper";
import { type BoardCallouts } from "@/entities/table/model/board-types";
import {
    createInitialPlayerState,
    createInitialTableState,
} from "@/entities/table/model/initial-state";
import { type BoardNotice } from "@/entities/table/ui/board-notices";
import { GameBoard } from "@/entities/table/ui/game-board";

function showHeldPanel(host: HTMLElement, held: boolean): void {
    render(
        GameBoard({ debug: false, overlay: html`<p>Result</p>`, overlayHeld: held, state: null }),
        host,
    );
}

function renderBoard(): HTMLElement {
    const players = [0, 1, 2, 3].map((seat) => ({
        ...createInitialPlayerState({
            isAiPlayer: false,
            name: `P${seat}`,
            score: 25_000 + 1000 * seat,
            seat,
        }),
        isRiichi: seat === 3,
    }));
    const table = {
        ...createInitialTableState(),
        dealerSeat: 1,
        doraIndicators: [0],
        honbaSticks: 2,
        players,
        riichiSticks: 1,
        tilesRemaining: 34,
    };
    const state = tableStateToDisplayState(table, { bottomSeat: 0, reveal: "bottom" });
    const host = document.createElement("div");
    render(GameBoard({ debug: false, state }), host);
    return host;
}

function texts(host: HTMLElement, selector: string): (string | undefined)[] {
    return [...host.querySelectorAll(selector)].map((element) => element.textContent?.trim());
}

describe("GameBoard centre and dora", () => {
    it("gives each seat its wind and score in hundreds on its side of the centre, its differences beside, and its riichi stick", () => {
        const host = renderBoard();
        expect(texts(host, ".board-center__wind")).toEqual(["N", "E", "S", "W"]);
        expect(texts(host, ".board-center__seat--dealer .board-center__wind")).toEqual(["E"]);
        expect(texts(host, ".board-center__score")).toEqual(["25000", "26000", "27000", "28000"]);
        expect(
            texts(host, ".board-center__seat--bottom .board-center__score .board-center__hundreds"),
        ).toEqual(["00"]);
        expect(texts(host, ".board-center__seat--left .board-center__diff--bottom")).toEqual([
            "+3000",
        ]);
        expect(
            host.querySelectorAll(".board-center__riichi:not(.board-center__riichi--none)"),
        ).toHaveLength(1);
        expect(
            host.querySelector(".board-center__seat--left .board-center__riichi--none"),
        ).toBeNull();
    });

    it("shows the dora indicators turned so far, a back in each of the five slots still to turn, and counts the wall and sticks in the centre", () => {
        const host = renderBoard();
        const slots = [...host.querySelectorAll(".board-dora__tile .tile")];
        expect(slots.map((tile) => tile.classList.contains("tile-back"))).toEqual([
            false,
            true,
            true,
            true,
            true,
        ]);
        expect(
            texts(host, ".board-center__count").map((text) => text?.replaceAll(/\s+/gu, " ")),
        ).toEqual(["Wall 34", "Honba 2", "Riichi sticks 1"]);
    });
});

describe("GameBoard announcements", () => {
    const FACES: BoardNotice = { id: "faces", text: "Tile images did not load", tone: "warning" };
    const REFUSED: BoardNotice = { id: "refused", text: "That move was refused", tone: "warning" };
    const PON: BoardCallouts = {
        announced: true,
        items: [{ kind: "pon", label: "Pon", position: "top" }],
        key: "call-2",
    };

    function draw(
        host: HTMLElement,
        notices: readonly BoardNotice[],
        callouts: BoardCallouts | null,
    ): void {
        render(
            GameBoard({
                callouts,
                debug: false,
                notices,
                state: null,
            }),
            host,
        );
    }

    /** What a screen reader hears from the board's live regions: the text each change adds. */
    async function heardWhile(host: HTMLElement, change: () => void): Promise<string[]> {
        const heard: string[] = [];
        const observer = new MutationObserver((records) => {
            for (const record of records) {
                heard.push(...[...record.addedNodes].map((node) => node.textContent?.trim() ?? ""));
            }
        });
        for (const region of host.querySelectorAll("[aria-live]")) {
            observer.observe(region, { characterData: true, childList: true, subtree: true });
        }
        change();
        await Promise.resolve();
        observer.disconnect();
        return heard.filter((text) => text !== "");
    }

    it("reads each notice and each showing of calls once: a redraw reads nothing, a new one only its own words", async () => {
        const host = document.createElement("div");
        draw(host, [FACES], null);
        const redrawn = await heardWhile(host, () => draw(host, [FACES], null));
        const added = await heardWhile(host, () => draw(host, [FACES, REFUSED], PON));
        const again = await heardWhile(host, () => draw(host, [FACES, REFUSED], PON));

        expect(redrawn).toEqual([]);
        expect(added).toEqual(["That move was refused", "Pon"]);
        expect(again).toEqual([]);
        expect([
            host.querySelector(".board-notices [aria-live]"),
            host.querySelector(".board-callouts")?.getAttribute("aria-hidden"),
            ...[...host.querySelectorAll("[aria-live]")].map((region) =>
                ["role", "aria-atomic", "aria-relevant"].map((name) => region.getAttribute(name)),
            ),
        ]).toEqual([null, "true", [null, "false", "additions"], [null, "false", "additions"]]);
    });
});

describe("GameBoard callouts", () => {
    function renderCallouts(
        callouts: BoardCallouts,
        host: HTMLElement = document.createElement("div"),
    ): HTMLElement {
        render(
            GameBoard({
                callouts,
                debug: false,
                overlay: html`<p>Result</p>`,
                state: null,
            }),
            host,
        );
        return host;
    }

    const PON: BoardCallouts = {
        announced: true,
        items: [{ kind: "pon", label: "Pon", position: "top" }],
        key: "call-2",
    };

    it("draws a new showing afresh, so its animation replays, and keeps the element through a redraw", () => {
        const host = renderCallouts(PON);
        const first = host.querySelector(".board-callout");
        renderCallouts(PON, host);
        const redrawn = host.querySelector(".board-callout");
        renderCallouts({ ...PON, key: "call-3" }, host);

        expect(first?.textContent?.trim()).toBe("Pon");
        expect(first?.classList.contains("board-callout--top")).toBe(true);
        expect(redrawn).toBe(first);
        expect(host.querySelector(".board-callout")).not.toBe(first);
    });

    it("decides a panel's opening delay on its first showing alone, never restarting or adding it later", () => {
        const held = document.createElement("div");
        const open = document.createElement("div");
        showHeldPanel(held, true);
        const panel = held.querySelector(".board-overlay--held");
        showHeldPanel(held, false);
        showHeldPanel(open, false);
        showHeldPanel(open, true);

        expect(panel).not.toBeNull();
        expect(held.querySelector(".board-overlay--held")).toBe(panel);
        expect(open.querySelector(".board-overlay--held")).toBeNull();
    });
});
