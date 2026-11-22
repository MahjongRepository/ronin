import { describe, expect, it } from "vitest";

import { TILE_ASPECT, TOP_HAND_EDGE_SHARE } from "@/entities/table/lib/board-constants";
import {
    type BoardBox,
    boardGeometry,
    phonePromptHeight,
} from "@/entities/table/lib/board-geometry";
import { type TableView, surfaceViewValues, tableView } from "@/entities/table/lib/table-view";

const NO_EDGES = { bottom: 0, left: 0, right: 0, top: 0 };

const WIDE: readonly (readonly [string, BoardBox])[] = [
    ["a 2560x1440 window", { height: 1440, width: 2560 }],
    ["a 1440x900 window", { height: 900, width: 1440 }],
    ["a 1280x800 window", { height: 800, width: 1280 }],
    ["a laptop's 1366x657 window", { height: 657, width: 1366 }],
    ["a 1840x1380 window", { height: 1380, width: 1840 }],
    ["a tall 1680x1220 window", { height: 1220, width: 1680 }],
];

const WIDTH_BOUND: readonly (readonly [string, BoardBox])[] = [
    ["a 1024x768 window", { height: 768, width: 1024 }],
    ["an 800x600 window", { height: 600, width: 800 }],
    ["a 1000x1000 window", { height: 1000, width: 1000 }],
];

const SHORTEST_PHONE: readonly [string, BoardBox] = [
    "a 667x375 phone",
    { height: 375, width: 667 },
];

function viewOf(box: BoardBox): {
    readonly screen: ReturnType<typeof boardGeometry>;
    readonly view: ReturnType<typeof tableView>;
} {
    const screen = boardGeometry({
        appliedEdges: NO_EDGES,
        box,
        safeInsets: NO_EDGES,
        slots: { band: "play" as const },
    });
    return { screen, view: tableView(screen) };
}

function cssAffine(value: string): (left: number, top: number) => [number, number] {
    const [scaleX = 0, skewY = 0, skewX = 0, scaleY = 0, moveX = 0, moveY = 0] = value
        .replace(/^matrix\(|\)$/g, "")
        .split(",")
        .map(Number);
    return (left, top) => [
        scaleX * left + skewX * top + moveX,
        skewY * left + scaleY * top + moveY,
    ];
}

function topHandFoot(view: TableView): number {
    return (TILE_ASPECT + TOP_HAND_EDGE_SHARE) * (view.plane.lengths["rw"] ?? 0);
}

function shownBackAspect(view: TableView, hand: (left: number, top: number) => number[]): number {
    const width = view.pieces["strip-top"].right - view.pieces["strip-top"].left;
    const foot = topHandFoot(view);
    const tileWidth = view.plane.lengths["rw"] ?? 0;
    const shownTileWidth = ((hand(width, foot)[0] - hand(0, foot)[0]) / width) * tileWidth;
    return (hand(0, foot)[1] - hand(0, 0)[1]) / shownTileWidth;
}

describe("the top hand", () => {
    it.each([...WIDE, ...WIDTH_BOUND, SHORTEST_PHONE])(
        "concealed on %s: on the revealed hand's foot at its width, a back at most 1.38 tall, as a revealing back scaled from its foot",
        (_shape, box) => {
            const { view } = viewOf(box);
            const values = Object.fromEntries(surfaceViewValues(view));
            const concealed = cssAffine(values["--geo-camera-top-hand"] ?? "");
            const revealed = cssAffine(values["--geo-camera-top-hand-revealed"] ?? "");
            const width = view.pieces["strip-top"].right - view.pieces["strip-top"].left;
            const foot = topHandFoot(view);

            for (const along of [0, width]) {
                expect(concealed(along, foot)).toEqual(
                    revealed(along, foot).map((at) => expect.closeTo(at, 3)),
                );
                expect(concealed(along, 0)).toEqual(
                    revealed(along, foot * (1 - Number(values["--geo-top-hand-back-scale"]))).map(
                        (at) => expect.closeTo(at, 3),
                    ),
                );
            }
            expect(shownBackAspect(view, concealed)).toBeCloseTo(
                Math.min(shownBackAspect(view, revealed), 1.38),
                3,
            );
        },
    );
});

describe("tableView between the grid's windows", () => {
    it("never moves a phone's river tile more than 2px between neighbours 20 across or 10 down apart off the grid, 3px where the widest prompt first fits", () => {
        const widths = Array.from({ length: 15 }, (_unused, across) => 645 + 20 * across);
        const heights = Array.from({ length: 20 }, (_unused, down) => 305 + 10 * down);
        const boards = heights.map((height) =>
            widths.map((width) => {
                const { screen } = viewOf({ height, width });
                if (screen.family !== "phone") {
                    return null;
                }
                const { bottom = 0, left = 0, right = 0, top = 0 } = screen.areas["actions"] ?? {};
                return {
                    holdsPrompt:
                        bottom - top >=
                        phonePromptHeight(right - left, screen.lengths["timer-w"] ?? 0) - 0.001,
                    river: screen.lengths["rw"] ?? 0,
                };
            }),
        );
        const cliffs = boards.flatMap((row, down) =>
            row.flatMap((board, across) =>
                [
                    [row[across + 1], widths[across + 1], heights[down]] as const,
                    [boards[down + 1]?.[across], widths[across], heights[down + 1]] as const,
                ].flatMap(([next, width, height]) => {
                    if (board === null || next === null || next === undefined) {
                        return [];
                    }
                    const bound = board.holdsPrompt === next.holdsPrompt ? 2 : 3;
                    return Math.abs(next.river - board.river) <= bound
                        ? []
                        : [
                              `${widths[across]}x${heights[down]} ${board.river} -> ${width}x${height} ${next.river}`,
                          ];
                }),
            ),
        );

        expect(cliffs).toStrictEqual([]);
    });
});
