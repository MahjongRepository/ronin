import { html, render } from "lit-html";
import { assert, describe, expect, it, vi } from "vitest";

import { tableStateToDisplayState } from "@/entities/table/lib/board-mapper";
import { type BoardCallouts, type SeatPosition } from "@/entities/table/model/board-types";
import {
    createInitialPlayerState,
    createInitialTableState,
} from "@/entities/table/model/initial-state";
import { type BoardNotice } from "@/entities/table/ui/board-notices";
import { GameBoard } from "@/entities/table/ui/game-board";
import { type DiscardTile } from "@/entities/tile";

function renderBoard(pinned: SeatPosition | null, onPin = vi.fn()): HTMLElement {
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
    render(GameBoard({ debug: false, platePress: { kind: "pin", onPin, pinned }, state }), host);
    return host;
}

function press(host: HTMLElement, selector: string, init: KeyboardEventInit | null = null): void {
    const target = host.querySelector(selector);
    if (target === null) {
        throw new Error(`nothing matches ${selector}`);
    }
    target.dispatchEvent(
        init === null
            ? new MouseEvent("click", { bubbles: true })
            : new KeyboardEvent("keydown", { bubbles: true, ...init }),
    );
}

function escapeKey(): KeyboardEvent {
    return new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Escape" });
}

function texts(host: HTMLElement, selector: string): (string | undefined)[] {
    return [...host.querySelectorAll(selector)].map((element) => element.textContent?.trim());
}

describe("GameBoard centre and dora", () => {
    it("gives each seat its wind and score in hundreds on its side of the centre, its differences beside, and its riichi stick", () => {
        const host = renderBoard(null);
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
        const host = renderBoard(null);
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

describe("GameBoard nameplates", () => {
    it("marks the board with the pinned plate, whose own click goes to the plate alone", () => {
        const onPin = vi.fn();
        const host = renderBoard("left", onPin);
        expect(host.querySelector(".game-board")?.classList.contains("game-board--diff-left")).toBe(
            true,
        );
        press(host, ".nameplate--top");
        expect(onPin.mock.calls).toEqual([["top"]]);
    });

    it("unpins the pinned plate on a click elsewhere on the board or on Escape", () => {
        const onPin = vi.fn();
        const host = renderBoard("left", onPin);
        press(host, ".board-center");
        press(host, ".nameplate--top", { key: "Escape" });
        expect(onPin.mock.calls).toEqual([[null], [null]]);
    });

    it("spends one Escape on one step: a pinned plate's unpinning first, and never an Escape a panel already took", () => {
        const onPin = vi.fn();
        const onEscape = vi.fn();
        function renderWith(pinned: SeatPosition | null): HTMLElement {
            const host = document.createElement("div");
            render(
                GameBoard({
                    debug: false,
                    onEscape,
                    platePress: { kind: "pin", onPin, pinned },
                    state: null,
                }),
                host,
            );
            return host;
        }
        renderWith("left").querySelector(".board-center")?.dispatchEvent(escapeKey());
        const taken = escapeKey();
        taken.preventDefault();
        const free = renderWith(null);
        free.querySelector(".board-center")?.dispatchEvent(taken);
        free.querySelector(".board-center")?.dispatchEvent(escapeKey());

        expect([onPin.mock.calls, onEscape.mock.calls.length]).toEqual([[[null]], 1]);
    });

    it("asks nothing on a click elsewhere or Escape while no plate is pinned", () => {
        const onPin = vi.fn();
        const host = renderBoard(null, onPin);
        press(host, ".board-center");
        press(host, ".board-center", { key: "Escape" });
        expect(onPin).not.toHaveBeenCalled();
    });
});

describe("GameBoard announcements", () => {
    const FACES: BoardNotice = { id: "faces", text: "Tile images did not load", tone: "warning" };
    const REFUSED: BoardNotice = { id: "refused", text: "That move was refused", tone: "warning" };
    const PON: BoardCallouts = {
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
                announceCalls: true,
                callouts,
                debug: false,
                notices,
                platePress: { kind: "pin", onPin: vi.fn(), pinned: null },
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
                platePress: { kind: "pin", onPin: vi.fn(), pinned: null },
                state: null,
            }),
            host,
        );
        return host;
    }

    const PON: BoardCallouts = {
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

    it("lays each call's chip over its caller's river clear of the latest discard", () => {
        const table = {
            ...createInitialTableState(),
            players: [0, 1, 2, 3].map((seat) =>
                createInitialPlayerState({
                    isAiPlayer: false,
                    name: `P${seat}`,
                    score: 25_000,
                    seat,
                }),
            ),
        };
        const board = tableStateToDisplayState(table, { bottomSeat: 0, reveal: "bottom" });
        assert(board !== null);
        function river(length: number): DiscardTile[] {
            return Array.from({ length }, (_unused, index) => ({
                face: "1m",
                last: index === length - 1,
            }));
        }
        const [bottom, right, top, left] = board.players;
        const state = {
            ...board,
            players: [
                { ...bottom, discards: river(9) },
                { ...right, discards: river(3) },
                top,
                left,
            ] as const,
        };
        const host = document.createElement("div");
        render(
            GameBoard({
                callouts: {
                    items: [
                        { kind: "pon", label: "Pon", position: "bottom" },
                        { kind: "chi", label: "Chi", position: "right" },
                        { kind: "kan", label: "Kan", position: "top" },
                    ],
                    key: "call-4",
                },
                debug: false,
                platePress: { kind: "pin", onPin: vi.fn(), pinned: null },
                state,
            }),
            host,
        );

        expect(
            [...host.querySelectorAll<HTMLElement>(".board-callout")].map((chip) =>
                chip.getAttribute("style"),
            ),
        ).toEqual([
            "--spot-along: 3; --spot-across: 0.5",
            "--spot-along: 1; --spot-across: 2",
            "--spot-along: 3; --spot-across: 2.5",
        ]);
    });
});

describe("GameBoard rivers", () => {
    it("rings the latest discard over its slot, past a sideways riichi tile earlier on its row", () => {
        const table = {
            ...createInitialTableState(),
            players: [0, 1, 2, 3].map((seat) =>
                createInitialPlayerState({
                    isAiPlayer: false,
                    name: `P${seat}`,
                    score: 25_000,
                    seat,
                }),
            ),
        };
        const board = tableStateToDisplayState(table, { bottomSeat: 0, reveal: "bottom" });
        assert(board !== null);
        const discards: DiscardTile[] = Array.from({ length: 9 }, (_unused, index) => ({
            face: "1m",
            last: index === 8,
            riichi: index === 7,
        }));
        const [bottom, ...others] = board.players;
        const host = document.createElement("div");
        render(
            GameBoard({
                debug: false,
                platePress: { kind: "pin", onPin: vi.fn(), pinned: null },
                state: { ...board, players: [{ ...bottom, discards }, ...others] as const },
            }),
            host,
        );

        expect(
            host.querySelector(".board-river--bottom .board-river__latest")?.getAttribute("style"),
        ).toBe("--latest-col: 2; --latest-row: 1; --latest-wide-before: 1; --latest-wide: 0");
    });
});
