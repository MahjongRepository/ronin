import { assert, describe, expect, it } from "vitest";

import { loadEngineReplay } from "#tests/fixtures/replays";
import {
    type BoardCallouts,
    type GamePhase,
    type TablePanelView,
    type TableState,
    tablePanel,
} from "@/entities/table";

const VIEW: TablePanelView = {
    callouts: null,
    overGameEnd: false,
    page: 0,
    viewerSeat: null,
};
const RON: BoardCallouts = {
    announced: true,
    items: [{ kind: "ron", label: "Ron", position: "right" }],
    key: "c1",
};
const PON: BoardCallouts = {
    announced: true,
    items: [{ kind: "pon", label: "Pon", position: "top" }],
    key: "c2",
};

function tableIn(phase: GamePhase, replay = "double_ron"): TableState {
    const table = loadEngineReplay(replay).tables.findLast(
        (candidate) => candidate.phase === phase && candidate.players.length > 0,
    );
    assert(table !== undefined, `no ${phase} table`);
    return table;
}

describe("tablePanel", () => {
    it("shows nothing of its own before the first deal or while a round plays", () => {
        expect([
            tablePanel(tableIn("pre_game"), VIEW),
            tablePanel(tableIn("in_round"), VIEW),
        ]).toEqual([null, null]);
    });

    it("shows a round's result at the page asked, the nearest past its last, held back only for a win's call", () => {
        const roundEnd = tableIn("round_ended");
        const pages = [0, 1, 5].map((page) => tablePanel(roundEnd, { ...VIEW, page }));
        const afterCall = [RON, PON, null].map((callouts) =>
            tablePanel(roundEnd, { ...VIEW, callouts }),
        );

        expect(pages.map((panel) => panel?.kind === "result" && panel.display.page)).toEqual([
            0, 1, 1,
        ]);
        expect(afterCall.map((panel) => panel?.kind === "result" && panel.afterCall)).toEqual([
            true,
            false,
            false,
        ]);
    });

    it("shows the game's end, or the last round's result over it while the view keeps it", () => {
        const ended = tableIn("game_ended", "pao");

        expect(tablePanel(ended, VIEW)?.kind).toBe("game_end");
        expect(tablePanel(ended, { ...VIEW, overGameEnd: true })?.kind).toBe("result");
    });
});
