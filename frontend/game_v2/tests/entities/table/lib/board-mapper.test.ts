import { describe, expect, test } from "vitest";

import { loadEngineReplay } from "#tests/fixtures/replays";
import { checkpointState } from "#tests/fixtures/seat-transcripts";
import { tableStateToDisplayState } from "@/entities/table/lib/board-mapper";
import { type BoardPerspective } from "@/entities/table/model/board-types";
import {
    createInitialPlayerState,
    createInitialTableState,
} from "@/entities/table/model/initial-state";
import { type PlayerState, type TableState } from "@/entities/table/model/types";
import { SEAT_CONTROL_REASON } from "@/shared/protocol";

const SEAT_0_VIEW: BoardPerspective = { bottomSeat: 0, reveal: "bottom" };
const REPLAY_VIEW: BoardPerspective = { bottomSeat: 0, reveal: "all" };

function makePlayer(overrides: Partial<PlayerState> = {}): PlayerState {
    return {
        ...createInitialPlayerState({ isAiPlayer: false, name: "Alice", score: 25_000, seat: 0 }),
        ...overrides,
    };
}

function makeTableState(overrides: Partial<TableState> = {}): TableState {
    return {
        ...createInitialTableState(),
        players: [
            makePlayer({ name: "P0", seat: 0 }),
            makePlayer({ name: "P1", seat: 1 }),
            makePlayer({ name: "P2", seat: 2 }),
            makePlayer({ name: "P3", seat: 3 }),
        ],
        ...overrides,
    };
}

describe("tableStateToDisplayState", () => {
    describe("incomplete state handling", () => {
        test("returns null until four players are seated", () => {
            const twoSeated = makeTableState({
                players: [makePlayer({ seat: 0 }), makePlayer({ seat: 1 })],
            });
            expect(
                tableStateToDisplayState(makeTableState({ players: [] }), SEAT_0_VIEW),
            ).toBeNull();
            expect(tableStateToDisplayState(twoSeated, SEAT_0_VIEW)).toBeNull();
        });
    });

    describe("player display mapping", () => {
        test("bottom player (seat 0) gets face-up hand tiles", () => {
            const state = makeTableState({
                players: [
                    makePlayer({ seat: 0, tiles: [0, 4] }),
                    makePlayer({ seat: 1 }),
                    makePlayer({ seat: 2 }),
                    makePlayer({ seat: 3 }),
                ],
            });
            const result = tableStateToDisplayState(state, SEAT_0_VIEW)!;
            // Bottom player (index 0) should have show: "face"
            expect(result.players[0].hand[0].show).toBe("face");
            expect(result.players[0].hand[1].show).toBe("face");
        });

        test("non-bottom players get face-down hand tiles", () => {
            const state = makeTableState({
                players: [
                    makePlayer({ seat: 0 }),
                    makePlayer({ seat: 1, tiles: [0] }),
                    makePlayer({ seat: 2, tiles: [4] }),
                    makePlayer({ seat: 3, tiles: [8] }),
                ],
            });
            const result = tableStateToDisplayState(state, SEAT_0_VIEW)!;
            expect(result.players[1].hand[0].show).toBe("back");
            expect(result.players[2].hand[0].show).toBe("back");
            expect(result.players[3].hand[0].show).toBe("back");
        });

        test("keeps each known tile's id and shows a concealed count as backs, under either reveal", () => {
            const state = makeTableState({
                players: [
                    makePlayer({ seat: 0 }),
                    makePlayer({ concealedCount: 2, seat: 1, tiles: [8] }),
                    makePlayer({ seat: 2 }),
                    makePlayer({ seat: 3 }),
                ],
            });
            const concealed = { show: "concealed" };

            expect(tableStateToDisplayState(state, SEAT_0_VIEW)?.players[1].hand).toEqual([
                { face: "3m", show: "back", tileId: 8 },
                concealed,
                concealed,
            ]);
            const allOpen = tableStateToDisplayState(state, { bottomSeat: 0, reveal: "all" });
            expect(allOpen?.players[1].hand).toEqual([
                { face: "3m", show: "face", tileId: 8 },
                concealed,
                concealed,
            ]);
        });

        test("sorts the hand row whatever the held order, setting the drawn tile apart", () => {
            const state = makeTableState({
                players: [
                    makePlayer({ drawnTileId: 8, seat: 0, tiles: [100, 8, 4, 0] }),
                    makePlayer({ seat: 1 }),
                    makePlayer({ seat: 2 }),
                    makePlayer({ seat: 3 }),
                ],
            });
            const result = tableStateToDisplayState(state, SEAT_0_VIEW)!;
            expect(result.players[0].hand.map((tile) => tile.tileId)).toEqual([0, 4, 100]);
            expect(result.players[0].drawnTile).toBeDefined();
            expect(result.players[0].drawnTile!.face).toBe("3m");
        });

        test("duplicate tile IDs: only first match becomes drawn tile", () => {
            const state = makeTableState({
                players: [
                    makePlayer({ drawnTileId: 4, seat: 0, tiles: [4, 4, 8] }),
                    makePlayer({ seat: 1 }),
                    makePlayer({ seat: 2 }),
                    makePlayer({ seat: 3 }),
                ],
            });
            const result = tableStateToDisplayState(state, SEAT_0_VIEW)!;
            // 2 base tiles (one 4 + the 8) + 1 drawn tile (the other 4)
            expect(result.players[0].hand).toHaveLength(2);
            expect(result.players[0].drawnTile).toBeDefined();
        });

        test("drawnTileId not in tiles array renders all tiles without drawn tile", () => {
            const state = makeTableState({
                players: [
                    makePlayer({ drawnTileId: 99, seat: 0, tiles: [0, 4, 8] }),
                    makePlayer({ seat: 1 }),
                    makePlayer({ seat: 2 }),
                    makePlayer({ seat: 3 }),
                ],
            });
            const result = tableStateToDisplayState(state, SEAT_0_VIEW)!;
            expect(result.players[0].hand).toHaveLength(3);
            expect(result.players[0].drawnTile).toBeUndefined();
        });

        test("null drawnTileId renders all tiles inline", () => {
            const state = makeTableState({
                players: [
                    makePlayer({ drawnTileId: null, seat: 0, tiles: [0, 4, 8] }),
                    makePlayer({ seat: 1 }),
                    makePlayer({ seat: 2 }),
                    makePlayer({ seat: 3 }),
                ],
            });
            const result = tableStateToDisplayState(state, SEAT_0_VIEW)!;
            expect(result.players[0].hand).toHaveLength(3);
            expect(result.players[0].drawnTile).toBeUndefined();
        });

        test("lays each meld out from the called seat's side", () => {
            const state = makeTableState({
                players: [
                    makePlayer({
                        melds: [
                            {
                                calledTileId: 0,
                                callerSeat: 0,
                                fromSeat: 3,
                                meldType: "pon",
                                tileIds: [0, 1, 2],
                            },
                        ],
                        seat: 0,
                    }),
                    makePlayer({ seat: 1 }),
                    makePlayer({ seat: 2 }),
                    makePlayer({ seat: 3 }),
                ],
            });
            const result = tableStateToDisplayState(state, SEAT_0_VIEW)!;
            expect(result.players[0].melds).toEqual([
                [
                    { face: "1m", kind: "sideways" },
                    { face: "1m", kind: "upright" },
                    { face: "1m", kind: "upright" },
                ],
            ]);
        });

        test("a claimed tile leaves the river, the declarer's next surviving discard lying sideways for a claimed riichi tile", () => {
            const state = makeTableState({
                players: [
                    makePlayer({
                        discards: [
                            { isRiichi: false, isTsumogiri: false, tileId: 0 },
                            { claimed: true, isRiichi: true, isTsumogiri: false, tileId: 4 },
                            { isRiichi: false, isTsumogiri: false, tileId: 8 },
                            { isRiichi: false, isTsumogiri: false, tileId: 12 },
                        ],
                        seat: 0,
                    }),
                    makePlayer({ seat: 1 }),
                    makePlayer({ seat: 2 }),
                    makePlayer({ seat: 3 }),
                ],
            });
            const result = tableStateToDisplayState(state, SEAT_0_VIEW)!;
            expect(result.players[0].discards).toEqual([
                { face: "1m", last: false, riichi: false },
                { face: "3m", last: false, riichi: true },
                { face: "4m", last: false, riichi: false },
            ]);
        });

        test("unsorted players array produces correct seat positions", () => {
            const state = makeTableState({
                players: [
                    makePlayer({ name: "P3", seat: 3 }),
                    makePlayer({ name: "P1", seat: 1 }),
                    makePlayer({ name: "P0", seat: 0, tiles: [0] }),
                    makePlayer({ name: "P2", seat: 2 }),
                ],
            });
            const result = tableStateToDisplayState(state, SEAT_0_VIEW)!;
            // Seat 0 = bottom (index 0) should be face-up
            expect(result.players[0].hand[0].show).toBe("face");
        });
    });

    describe("center info mapping", () => {
        test("round display counts the round within its wind from the first dealer, not the seat", () => {
            const state = makeTableState({ dealerSeat: 1, firstDealerSeat: 2, roundWind: 1 });
            const result = tableStateToDisplayState(state, SEAT_0_VIEW)!;
            expect(result.center.roundDisplay).toBe("South 4");
        });
    });
});

describe("tableStateToDisplayState announced draws", () => {
    test("sets an announced face-down draw apart from the concealed count", () => {
        const state = makeTableState({
            players: [
                makePlayer({ seat: 0 }),
                makePlayer({ concealedCount: 3, drawnConcealed: true, seat: 1, tiles: [] }),
                makePlayer({ seat: 2 }),
                makePlayer({ seat: 3 }),
            ],
        });
        const right = tableStateToDisplayState(state, SEAT_0_VIEW)?.players[1];

        expect(right?.hand).toHaveLength(2);
        expect(right?.drawnTile).toEqual({ show: "concealed" });
    });
});

describe("tableStateToDisplayState nameplates", () => {
    test("seats the perspective's seat at the bottom whoever deals, its wind still from the dealer", () => {
        const state = makeTableState({ dealerSeat: 0 });
        const result = tableStateToDisplayState(state, { bottomSeat: 2, reveal: "bottom" })!;
        expect(result.nameplates.map((plate) => [plate.name, plate.wind, plate.isDealer])).toEqual([
            ["P2", "W", false],
            ["P3", "N", false],
            ["P0", "E", true],
            ["P1", "S", false],
        ]);
    });

    test("gives each plate its signed difference from every other seat's score, by board position", () => {
        const state = makeTableState({
            players: [
                makePlayer({ score: 32_100, seat: 0 }),
                makePlayer({ score: 0, seat: 1 }),
                makePlayer({ score: -1500, seat: 2 }),
                makePlayer({ score: 0, seat: 3 }),
            ],
        });
        const { nameplates } = tableStateToDisplayState(state, SEAT_0_VIEW)!;
        const [bottom, right] = nameplates;
        expect(nameplates.map((plate) => plate.score)).toEqual(["32100", "0", "-1500", "0"]);
        expect(bottom.scoreDiffs).toEqual({
            bottom: "",
            left: "+32100",
            right: "+32100",
            top: "+33600",
        });
        expect(right.scoreDiffs).toEqual({ bottom: "-32100", left: "±0", right: "", top: "+1500" });
    });

    test("marks an AI player seated from the start apart from one standing in for a human who left or never came", () => {
        const state = makeTableState({
            players: [
                makePlayer({ seat: 0 }),
                makePlayer({ isAiPlayer: true, seat: 1 }),
                makePlayer({ aiStandIn: SEAT_CONTROL_REASON.LEFT, seat: 2 }),
                makePlayer({ aiStandIn: SEAT_CONTROL_REASON.ABSENT, seat: 3 }),
            ],
        });
        const result = tableStateToDisplayState(state, SEAT_0_VIEW)!;
        expect(result.nameplates.map((plate) => plate.aiMark)).toEqual([
            null,
            { tag: "AI", words: "An AI player plays this seat" },
            { tag: "Away", words: "Disconnected: an AI player plays this seat" },
            { tag: "Away", words: "Absent: an AI player plays this seat" },
        ]);
    });
});

describe("tableStateToDisplayState nameplates on a replay", () => {
    function platesAfter(name: string, type: string, nth = 0): readonly string[] {
        const replay = loadEngineReplay(name);
        const indices = replay.events.flatMap((event, index) =>
            event?.type === type ? [index] : [],
        );
        const index = indices[nth];
        if (index === undefined) {
            throw new Error(`${name} has no ${type} #${nth}`);
        }
        const display = tableStateToDisplayState(replay.tables[index + 1], REPLAY_VIEW)!;
        return display.nameplates.map(
            (plate) =>
                `${plate.name} ${plate.wind}${plate.isDealer ? " dealer" : ""}${plate.isCurrent ? " turn" : ""}` +
                `${plate.isRiichi ? " riichi" : ""} ${plate.score}${plate.aiMark === null ? "" : ` [${plate.aiMark.tag}]`}`,
        );
    }

    test("names every seat with its wind and marks the dealer, the turn while a round plays and the seats AI players hold, stop by stop", () => {
        expect(platesAfter("ai_replacements", "draw")).toEqual([
            "Diana E dealer turn 25000",
            "Alice S 25000",
            "Charlie W 25000",
            "Bob N 25000 [Away]",
        ]);
        expect(platesAfter("ai_replacements", "round_end")).toEqual([
            "Diana E dealer 25000",
            "Alice S 33000",
            "Charlie W 17000 [Away]",
            "Bob N 25000 [Away]",
        ]);
        expect(platesAfter("ai_replacements", "discard", 3)).toEqual([
            "Diana N 25000 [Away]",
            "Alice E dealer turn 33000",
            "Charlie S 17000",
            "Bob W 25000",
        ]);
    });

    test("marks each riichi once its stick is down, the score less the deposit", () => {
        expect(platesAfter("riichi", "riichi_declared")).toEqual([
            "Diana E dealer 25000",
            "Alice S turn riichi 24000",
            "Charlie W 25000",
            "Bob N 25000",
        ]);
        expect(platesAfter("riichi", "riichi_declared", 1)).toEqual([
            "Diana E dealer 25000",
            "Alice S riichi 24000",
            "Charlie W 25000",
            "Bob N turn riichi 24000",
        ]);
    });
});

describe("tableStateToDisplayState last discard", () => {
    function marked(table: TableState, bottomSeat = 0): readonly string[] {
        const display = tableStateToDisplayState(table, { bottomSeat, reveal: "all" })!;
        return display.players.flatMap((player, position) =>
            player.discards.flatMap((tile, at) =>
                tile.last ? [`${position}:${at} ${tile.face}`] : [],
            ),
        );
    }

    function markedAfter(
        name: string,
        matches: (
            event: NonNullable<ReturnType<typeof loadEngineReplay>["events"][number]>,
        ) => boolean,
        nth = 0,
    ): readonly string[] {
        const replay = loadEngineReplay(name);
        const index = replay.events.flatMap((event, at) =>
            event !== null && matches(event) ? [at] : [],
        )[nth];
        if (index === undefined) {
            throw new Error(`${name} has no such event #${nth}`);
        }
        return marked(replay.tables[index + 1]);
    }

    test("marks the latest discard, moving with each discard and kept through the next draw, a kan from the hand and an added kan open to chankan, and none once a call claims it", () => {
        expect(markedAfter("pao", (event) => event.type === "discard")).toEqual(["0:0 5z"]);
        expect(markedAfter("pao", (event) => event.type === "draw", 1)).toEqual(["1:0 9p"]);
        expect(markedAfter("pao", (event) => event.type === "meld")).toEqual([]);
        const kans = loadEngineReplay("kans");
        const closedKan = kans.events.findIndex(
            (event) => event?.type === "meld" && event.meldType === "closed_kan",
        );
        expect(marked(kans.tables[closedKan])).toEqual(["2:2 7z"]);
        expect(marked(kans.tables[closedKan + 1])).toEqual(["2:2 7z"]);
        expect(marked(checkpointState("chankan_passed_seat_3", "chankan prompt").table)).toEqual([
            "0:0 7z",
        ]);
    });

    test("marks after a reconnect the latest discard the snapshot names: in a call prompt, at a draw, in a chankan window and under a pending result, kept through the re-sent draw", () => {
        const marks = [
            "reconnect_seat_1",
            "own_turn_seat_1",
            "chankan_passed_seat_3",
            "chankan_robbed_seat_1",
            "riichi_reconnect_seat_1",
        ].map((name) => marked(checkpointState(name, "reconnected").table));
        expect(marks).toEqual([["0:0 5z"], ["0:0 2z"], ["0:0 7z"], ["0:1 7z"], ["2:0 6s"]]);
        expect(marked(checkpointState("own_turn_seat_1", "draw re-sent").table)).toEqual([
            "0:0 2z",
        ]);
    });
});
