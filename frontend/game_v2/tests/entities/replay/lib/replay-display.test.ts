import { assert, describe, expect, test } from "vitest";

import { engineReplayText } from "#tests/fixtures/replays";
import {
    type LoadedReplay,
    type ReplayCursor,
    type ReplayDisplay,
    readReplay,
    replayDisplay,
} from "@/entities/replay";
import { shownReplayCall } from "@/entities/replay/model/replay-calls";
import { type BoardPerspective } from "@/entities/table";

const ALL: BoardPerspective = { bottomSeat: 0, reveal: "all" };

function replayOf(text: string): LoadedReplay {
    const read = readReplay(text);
    assert(read.ok);
    return read.replay;
}

function displayAt(
    replay: LoadedReplay,
    cursor: ReplayCursor,
    perspective: BoardPerspective = ALL,
): ReplayDisplay {
    return replayDisplay(replay, {
        cursor,
        perspective,
        seating: false,
        shownCall: shownReplayCall(replay, null, {
            announce: true,
            at: 0,
            from: null,
            to: cursor,
        }),
    });
}

function lastStop(replay: LoadedReplay): number {
    return replay.navigation.stops.length - 1;
}

describe("replayDisplay", () => {
    test("offers no move back at the first deal and none on at the standings", () => {
        const replay = replayOf(engineReplayText("pao"));
        const opening = displayAt(replay, { page: 0, stop: 0 });
        const end = displayAt(replay, { page: 0, stop: lastStop(replay) });

        expect([opening.moves.first, opening.moves.prev, opening.moves.prevRound]).toEqual([
            null,
            null,
            null,
        ]);
        expect([end.moves.last, end.moves.next, end.moves.nextRound]).toEqual([null, null, null]);
        expect(end.step).toEqual({
            count: replay.navigation.stops.length,
            index: replay.navigation.stops.length,
        });
        expect([end.overlay?.kind, end.incomplete, end.endNotice]).toEqual([
            "game_end",
            null,
            null,
        ]);
    });

    test("shows the seating at the starting scores over the table as the game started, then the stop's own panel", () => {
        const replay = replayOf(engineReplayText("double_ron"));
        const result = replay.navigation.stops.findIndex((stop) => stop.pages > 1);
        const seating = replayDisplay(replay, {
            cursor: { page: 0, stop: result },
            perspective: ALL,
            seating: true,
            shownCall: shownReplayCall(replay, null, {
                announce: false,
                at: 0,
                from: null,
                to: { page: 0, stop: result },
            }),
        });
        const shown = displayAt(replay, { page: 1, stop: result });

        assert(seating.overlay?.kind === "seating");
        expect(seating.overlay.display.seats.map((seat) => seat.score)).toEqual(
            Array.from({ length: 4 }, () => "25,000"),
        );
        expect([seating.callouts, seating.board === null]).toEqual([null, false]);
        assert(shown.overlay?.kind === "result");
        expect([shown.overlay.display.page, shown.overlay.afterCall]).toEqual([1, true]);
    });

    test("shows a riichi's deposit on its discard when a seat changes hands in the call window", () => {
        const replay = replayOf(engineReplayText("riichi_ai_replacement"));
        const riichiStop = replay.navigation.stops.findIndex((stop) => {
            const move = replay.events[stop.moveEntry];
            return move.type === "discard" && move.isRiichi;
        });
        const display = displayAt(replay, { page: 0, stop: riichiStop });
        assert(display.board !== null);
        const [, alice, charlie] = display.board.nameplates;

        expect([display.board.center.riichiSticks, alice.score, alice.isRiichi]).toEqual([
            1,
            "24000",
            true,
        ]);
        expect(charlie.aiMark?.tag).toBe("Away");
    });

    test("shows a deal with its first draw when a seat changes hands between them", () => {
        const [version, gameStarted, dealt, ...rest] = engineReplayText("riichi").split("\n");
        const replacement = JSON.stringify({ ai: 1, r: 0, s: 2, t: 101 });
        const replay = replayOf([version, gameStarted, dealt, replacement, ...rest].join("\n"));
        const display = displayAt(replay, { page: 0, stop: 0 });

        const bottom = display.board?.players[0];

        expect([bottom?.hand.length, bottom?.drawnTile]).toEqual([13, expect.anything()]);
        expect(display.step.index).toBe(1);
    });

    test("names the round and marks it in the round list", () => {
        const replay = replayOf(engineReplayText("double_ron_on_honba"));
        const [, , third] = replay.navigation.rounds;
        const display = displayAt(replay, { page: 0, stop: third.firstStop + 1 });

        expect([display.roundName, display.step.index]).toEqual(["East 2, 2 honba", 2]);
        expect(display.rounds.map((row) => row.current)).toEqual([false, false, true, false]);
        expect(display.rounds[2].start).toEqual({ page: 0, stop: third.firstStop });
    });

    test("labels a recording that stops before the game's end on every stop, and says so at its last", () => {
        const replay = replayOf(engineReplayText("truncated_after_round"));
        const opening = displayAt(replay, { page: 0, stop: 0 });
        const end = displayAt(replay, { page: 0, stop: lastStop(replay) });

        expect(opening.incomplete?.label).toBe("Incomplete");
        expect(opening.endNotice).toBeNull();
        expect(end.endNotice).toBe("The recording ends here, before the game's end");
    });

    test("labels a replay cut short by a line it cannot read, with the line", () => {
        const lines = engineReplayText("pao").trimEnd().split("\n");
        const replay = replayOf([...lines.slice(0, 10), "{broken", ...lines.slice(10)].join("\n"));
        const end = displayAt(replay, { page: 0, stop: lastStop(replay) });

        expect(replay.navigation.complete).toBe(false);
        expect(end.incomplete).toEqual({
            detail: "Line 11 could not be read, so the replay stops before it.",
            label: "Damaged",
        });
        expect(end.endNotice).toBe("The replay stops here: line 11 could not be read");
    });
});

describe("replayDisplay callouts", () => {
    function stopWhere(replay: LoadedReplay, type: string): number {
        return replay.navigation.stops.findIndex((stop) => {
            const move = replay.events[stop.moveEntry];
            return move.type === type && (move.type !== "discard" || move.isRiichi);
        });
    }

    test("shows the calls a stop's own move made by their seats, and none arriving afresh on the next move's stop", () => {
        const replay = replayOf(engineReplayText("kans"));
        const kan = stopWhere(replay, "meld");
        const fromKanSeat = { bottomSeat: 2, reveal: "all" } as const;

        expect(displayAt(replay, { page: 0, stop: kan }).callouts).toEqual({
            announced: true,
            items: [{ kind: "kan", label: "Kan", position: "top" }],
            key: `call-${kan}-0`,
        });
        expect(displayAt(replay, { page: 0, stop: kan }, fromKanSeat).callouts?.items).toEqual([
            { kind: "kan", label: "Kan", position: "bottom" },
        ]);
        expect(displayAt(replay, { page: 0, stop: kan + 1 }).callouts).toBeNull();
    });

    test("calls a riichi on its declaring discard, its accepted stick kept with it", () => {
        const replay = replayOf(engineReplayText("double_ron"));
        const riichi = stopWhere(replay, "discard");

        expect(displayAt(replay, { page: 0, stop: riichi }).callouts?.items).toEqual([
            { kind: "riichi", label: "Riichi", position: "right" },
        ]);
        expect(displayAt(replay, { page: 0, stop: riichi + 1 }).callouts).toBeNull();
    });

    test("calls a triple ron's three rons by their seats, though the round ends drawn", () => {
        const replay = replayOf(engineReplayText("triple_ron"));
        const result = stopWhere(replay, "round_end");

        expect(displayAt(replay, { page: 0, stop: result }).callouts?.items).toEqual([
            { kind: "ron", label: "Ron", position: "right" },
            { kind: "ron", label: "Ron", position: "top" },
            { kind: "ron", label: "Ron", position: "left" },
        ]);
    });

    test("keeps a double ron's two calls as its pages turn, and calls a robbed kan on its own stop first", () => {
        const doubleRon = replayOf(engineReplayText("double_ron"));
        const result = stopWhere(doubleRon, "round_end");
        const chankan = replayOf(engineReplayText("chankan_added"));
        const declared = stopWhere(chankan, "kan_declared");

        expect(displayAt(doubleRon, { page: 1, stop: result }).callouts).toEqual(
            displayAt(doubleRon, { page: 0, stop: result }).callouts,
        );
        expect(displayAt(doubleRon, { page: 0, stop: result }).callouts?.items).toEqual([
            { kind: "ron", label: "Ron", position: "right" },
            { kind: "ron", label: "Ron", position: "top" },
        ]);
        expect(displayAt(chankan, { page: 0, stop: declared }).callouts?.items).toEqual([
            { kind: "kan", label: "Kan", position: "right" },
        ]);
        expect(displayAt(chankan, { page: 0, stop: declared + 1 }).callouts?.items).toEqual([
            { kind: "ron", label: "Ron", position: "top" },
        ]);
    });
});
