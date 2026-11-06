import { render } from "lit-html";
import { assert, describe, expect, test, vi } from "vitest";

import { loadEngineReplay } from "#tests/fixtures/replays";
import { TablePanelDisplay, type TableState, tablePanel } from "@/entities/table";

function lastRoundEndTable(name: string): TableState {
    const table = loadEngineReplay(name).tables.findLast(
        (candidate) => candidate.phase === "round_ended",
    );
    assert(table !== undefined, `${name} has no round end`);
    return table;
}

function renderResult(table: TableState, page = 0, onPage?: (page: number) => void): HTMLElement {
    const panel = tablePanel(table, {
        callouts: null,
        overGameEnd: false,
        page,
        viewerSeat: null,
    });
    assert(panel !== null);
    const el = document.createElement("div");
    render(TablePanelDisplay(panel, { onPage }), el);
    return el;
}

function texts(el: HTMLElement, selector: string): string[] {
    return [...el.querySelectorAll(selector)].map(
        (node) => node.textContent?.replaceAll(/\s+/g, " ").trim() ?? "",
    );
}

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
        expect(texts(el, ".round-end-result__win-label")).toEqual(["Tsumo"]);
        expect(el.querySelectorAll(".round-end-result__win-tile .hand-tile")).toHaveLength(1);
        expect(el.querySelectorAll(".round-end-result__melds .meld")).toHaveLength(3);
    });

    test("a double ron: the pager asks for the next or previous page and stops at the ends", () => {
        const onPage = vi.fn<(page: number) => void>();
        const table = lastRoundEndTable("double_ron");
        const [previous, next] = renderResult(table, 0, onPage).querySelectorAll<HTMLButtonElement>(
            ".round-end-result__page-btn",
        );
        const [, nextOnLast] = renderResult(table, 1, onPage).querySelectorAll<HTMLButtonElement>(
            ".round-end-result__page-btn",
        );

        expect(previous.disabled).toBe(true);
        expect(nextOnLast.disabled).toBe(true);
        next.click();
        expect(onPage).toHaveBeenCalledWith(1);
    });

    test("a page count without paging only says which page shows; a single win has no pager", () => {
        const unpaged = renderResult(lastRoundEndTable("double_ron"), 1);
        const single = renderResult(lastRoundEndTable("riichi"), 0, vi.fn());

        expect(texts(unpaged, ".round-end-result__page")).toEqual(["2 / 2"]);
        expect(unpaged.querySelector(".round-end-result__page-btn")).toBeNull();
        expect(single.querySelector(".round-end-result__pager")).toBeNull();
    });

    test("a draw: each tenpai hand under its player's name, each seat's tag beside its payment", () => {
        const table = lastRoundEndTable("exhaustive_tenpai");
        const el = renderResult(table);

        expect(texts(el, ".round-end-result__tenpai-hand .round-end-result__label")).toEqual([
            "Alice",
            "Charlie",
        ]);
        expect(texts(el, ".round-end-result__score")).toEqual([
            "East Diana Noten −1,500 23,500",
            "South Alice Tenpai +1,500 25,500",
            "West Charlie Tenpai +1,500 26,500",
            "North Bob Noten −1,500 23,500",
        ]);
    });

    test("a nagashi mangan: its maker's river under their name, the riichi discard sideways as in the river", () => {
        const table = lastRoundEndTable("nagashi");
        const result = table.roundEndResult;
        assert(result !== null && result.draw !== null);
        const declaredOn9p = {
            ...result.draw,
            nagashiRivers: result.draw.nagashiRivers.map((river) => ({
                ...river,
                discards: river.discards.map((discard) => ({
                    ...discard,
                    isRiichi: discard.tileId === 68,
                })),
            })),
        };
        const el = renderResult({ ...table, roundEndResult: { ...result, draw: declaredOn9p } });
        const sideways = [
            ...el.querySelectorAll(".round-end-result__river-tiles .discard-tile-riichi svg"),
        ].map((face) => face.getAttribute("aria-label"));

        expect(texts(el, ".round-end-result__river .round-end-result__label")).toEqual([
            "Alice's river",
        ]);
        expect(el.querySelectorAll(".round-end-result__river-tiles .tile")).toHaveLength(18);
        expect(sideways).toEqual(["9-pin"]);
    });
});
