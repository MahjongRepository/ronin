import { html, render } from "lit-html";
import { afterEach, assert, describe, expect, test, vi } from "vitest";

import { loadEngineReplay } from "#tests/fixtures/replays";
import { GameBoard, TablePanelDisplay, type TableState, tablePanel } from "@/entities/table";

function lastRoundEndTable(name: string): TableState {
    const table = loadEngineReplay(name).tables.findLast(
        (candidate) => candidate.phase === "round_ended",
    );
    assert(table !== undefined, `${name} has no round end`);
    return table;
}

function renderResult(table: TableState, page = 0, onPage?: (page: number) => void): HTMLElement {
    const panel = tablePanel(table, {
        bottomSeat: 0,
        holdsResult: false,
        overGameEnd: false,
        page,
        viewerSeat: null,
    });
    assert(panel !== null);
    const el = document.createElement("div");
    render(TablePanelDisplay(panel, { onPage }), el);
    return el;
}

function pageButton(el: HTMLElement, selector: string): HTMLButtonElement {
    const button = el.querySelector<HTMLButtonElement>(selector);
    assert(button !== null, `no ${selector}`);
    return button;
}

function heard(node: Element): string {
    const copy = node.cloneNode(true);
    if (!(copy instanceof Element)) {
        return "";
    }
    for (const hidden of copy.querySelectorAll('[aria-hidden="true"]')) {
        hidden.remove();
    }
    return copy.textContent?.replaceAll(/\s+/g, " ").trim() ?? "";
}

function texts(el: HTMLElement, selector: string): string[] {
    return [...el.querySelectorAll(selector)].map(heard);
}

function seatMarks(table: TableState, page = 0): string[][] {
    const el = renderResult(table, page);
    return [...el.querySelectorAll(".round-end-result__seat-mark")].map((mark) => [
        mark.parentElement?.querySelector(".round-end-result__score-name")?.textContent ?? "",
        heard(mark),
    ]);
}

async function mountResultOnBoard(table: TableState): Promise<HTMLElement> {
    const panel = tablePanel(table, {
        bottomSeat: 0,
        holdsResult: false,
        overGameEnd: false,
        page: 0,
        viewerSeat: null,
    });
    assert(panel !== null);
    const host = document.createElement("div");
    document.body.append(host);
    render(GameBoard({ debug: false, overlay: TablePanelDisplay(panel), state: null }), host);
    await Promise.resolve();
    return host;
}

function peekingAfter(host: HTMLElement, selector: string, type: string): boolean | undefined {
    const press = { bubbles: true, button: 0, isPrimary: true, pointerId: 1 };
    host.querySelector(selector)?.dispatchEvent(new PointerEvent(type, press));
    return host.querySelector(".board-overlay")?.classList.contains("board-overlay--peeking");
}

afterEach(() => {
    document.documentElement.lang = "";
});

describe("RoundEndDisplay", () => {
    test("a win: the closed hand, then the winning tile with its label for a screen reader, then the melds", () => {
        const el = renderResult(lastRoundEndTable("pao"));
        const hand = el.querySelector(".round-end-result__hand");
        assert(hand !== null);

        expect([...hand.children].map((child) => child.className)).toEqual([
            "hand",
            "round-end-result__win-tile",
            "round-end-result__melds",
        ]);
        expect(hand.querySelector(".round-end-result__win-tile")?.getAttribute("aria-label")).toBe(
            "Tsumo",
        );
        expect(el.querySelectorAll(".round-end-result__win-tile .hand-tile")).toHaveLength(1);
        expect(el.querySelectorAll(".round-end-result__melds .meld")).toHaveLength(3);
        expect(el.querySelectorAll(".tile--standing")).toHaveLength(0);
    });

    test("a press beside the result shows the board under it until the press ends, never one on the result", async () => {
        const host = await mountResultOnBoard(lastRoundEndTable("double_ron"));
        const seen = [
            peekingAfter(host, ".round-end-result", "pointerdown"),
            peekingAfter(host, ".board-overlay", "pointerdown"),
            peekingAfter(host, ".board-overlay", "pointermove"),
            peekingAfter(host, ".board-overlay", "pointerup"),
        ];
        render(html``, host);
        host.remove();

        expect(seen).toEqual([false, true, true, false]);
    });

    test("a double ron: one layer per winner, only the shown one heard", () => {
        const second = renderResult(lastRoundEndTable("double_ron"), 1);

        expect(
            [
                ...second.querySelectorAll(
                    ".round-end-result__stack--hand > .round-end-result__layer",
                ),
            ].map((layer) => layer.getAttribute("aria-hidden")),
        ).toEqual(["true", "false"]);
        expect(texts(second, ".round-end-result__winner")).toEqual(["Charlie"]);
    });

    test("a win tags the winner's card with how it won and the card of the seat that dealt in", () => {
        expect(seatMarks(lastRoundEndTable("double_ron"), 1)).toEqual([
            ["Diana", "Dealt in"],
            ["Charlie", "Ron"],
        ]);
        expect(seatMarks(lastRoundEndTable("pao"))).toEqual([[expect.any(String), "Tsumo"]]);
        expect(seatMarks(lastRoundEndTable("exhaustive_tenpai"))).toEqual([]);
    });

    test("a double ron: its buttons name the winner of the page they ask for, none past either end", () => {
        const onPage = vi.fn<(page: number) => void>();
        const table = lastRoundEndTable("double_ron");
        const [first, second] = [0, 1].map((page) => renderResult(table, page, onPage));
        const next = pageButton(first, ".round-end-result__next");
        const previous = pageButton(second, ".round-end-result__prev");
        next.click();
        previous.click();

        expect([
            first.querySelector(".round-end-result__prev"),
            second.querySelector(".round-end-result__next"),
        ]).toEqual([null, null]);
        expect(
            [next, previous].map((button) => [button.getAttribute("aria-label"), heard(button)]),
        ).toEqual([
            ["Show Charlie's win", "Charlie"],
            ["Show Alice's win", "Alice"],
        ]);
        expect(onPage.mock.calls).toEqual([[1], [0]]);
    });

    test("a page count without paging only says which page shows; a single win offers no other page", () => {
        const unpaged = renderResult(lastRoundEndTable("double_ron"), 0);
        const single = renderResult(lastRoundEndTable("riichi"), 0, vi.fn());

        expect(texts(unpaged, ".round-end-result__page")).toEqual(["1 / 2"]);
        expect(unpaged.querySelector("button")).toBeNull();
        expect(
            single.querySelector(
                ".round-end-result__prev, .round-end-result__next, .round-end-result__page",
            ),
        ).toBeNull();
    });

    test("a draw: each tenpai hand under its player's name; each seat where it sits with its placement and payment", () => {
        const table = lastRoundEndTable("exhaustive_tenpai");
        const el = renderResult(table);

        expect(texts(el, ".round-end-result__tenpai-hand .round-end-result__label")).toEqual([
            "Alice",
            "Charlie",
        ]);
        expect(
            [...el.querySelectorAll(".round-end-result__seat")].map((seat) => [
                seat.className,
                heard(seat),
            ]),
        ).toEqual([
            [
                "round-end-result__seat round-end-result__seat--bottom round-end-result__seat--loss",
                "East Diana −1,500 23,500 3rd",
            ],
            [
                "round-end-result__seat round-end-result__seat--right round-end-result__seat--gain",
                "South Alice +1,500 25,500 2nd",
            ],
            [
                "round-end-result__seat round-end-result__seat--top round-end-result__seat--gain",
                "West Charlie +1,500 26,500 1st",
            ],
            [
                "round-end-result__seat round-end-result__seat--left round-end-result__seat--loss",
                "North Bob −1,500 23,500 4th",
            ],
        ]);
        expect(texts(el, ".round-end-result__title")).toEqual(["Exhaustive draw"]);
        document.documentElement.lang = "ru";
        expect(texts(renderResult(table), ".round-end-result__title")).toEqual(["Ничья"]);
    });

    test("a nagashi mangan: its name, limit and value, and the seats that paid it", () => {
        const el = renderResult(lastRoundEndTable("nagashi"));

        expect(heard(el)).toBe(
            "Nagashi Mangan Mangan 8,000 East Diana −4,000 21,000 4th South Alice +8,000 33,000 1st West Charlie −2,000 23,000 2nd North Bob −2,000 23,000 3rd East 1",
        );
    });
});
