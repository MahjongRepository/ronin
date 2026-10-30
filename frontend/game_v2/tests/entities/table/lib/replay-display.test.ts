import { assert, describe, expect, test } from "vitest";

import { engineReplayText } from "#tests/fixtures/replays";
import { type LoadedReplay, readReplay } from "@/entities/client";
import { type BoardPerspective, replayDisplay } from "@/entities/table";

const ALL: BoardPerspective = { bottomSeat: 0, reveal: "all" };

function replayOf(text: string): LoadedReplay {
    const read = readReplay(text);
    assert(read.ok);
    return read.replay;
}

function lastStop(replay: LoadedReplay): number {
    return replay.navigation.stops.length - 1;
}

describe("replayDisplay", () => {
    test("offers no move back at the first deal and none on at the standings", () => {
        const replay = replayOf(engineReplayText("pao"));
        const opening = replayDisplay(replay, { page: 0, stop: 0 }, ALL);
        const end = replayDisplay(replay, { page: 0, stop: lastStop(replay) }, ALL);

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
        expect([end.table.phase, end.incomplete, end.endNotice]).toEqual([
            "game_ended",
            null,
            null,
        ]);
    });

    test("shows a riichi's deposit on its discard when a seat changes hands in the call window", () => {
        const replay = replayOf(engineReplayText("riichi_ai_replacement"));
        const riichiStop = replay.navigation.stops.findIndex((stop) => {
            const move = replay.events[stop.moveEntry];
            return move.type === "discard" && move.isRiichi;
        });
        const display = replayDisplay(replay, { page: 0, stop: riichiStop }, ALL);
        const [, alice, charlie] = display.table.players;

        expect(display.narration).toBe(
            "Alice declares riichi, discarding Red dragon · AI plays for Charlie, who left",
        );
        expect([display.table.riichiSticks, alice.score, alice.isRiichi]).toEqual([
            1,
            24_000,
            true,
        ]);
        expect(charlie.aiStandIn).not.toBeNull();
    });

    test("shows a deal with its first draw when a seat changes hands between them", () => {
        const [version, gameStarted, dealt, ...rest] = engineReplayText("riichi").split("\n");
        const replacement = JSON.stringify({ ai: 1, r: 0, s: 2, t: 101 });
        const replay = replayOf([version, gameStarted, dealt, replacement, ...rest].join("\n"));
        const display = replayDisplay(replay, { page: 0, stop: 0 }, ALL);

        expect(display.narration).toBe("East 1: Diana deals · AI plays for Charlie, who left");
        expect(display.table.players[0].tiles).toHaveLength(14);
        expect(display.step.index).toBe(1);
    });

    test("names the round and marks it in the round list", () => {
        const replay = replayOf(engineReplayText("double_ron_on_honba"));
        const [, , third] = replay.navigation.rounds;
        const display = replayDisplay(replay, { page: 0, stop: third.firstStop + 1 }, ALL);

        expect([display.roundName, display.step.index]).toEqual(["East 2, 2 honba", 2]);
        expect(display.rounds.map((row) => row.current)).toEqual([false, false, true, false]);
        expect(display.rounds[2].start).toEqual({ page: 0, stop: third.firstStop });
    });

    test("labels a recording that stops before the game's end on every stop, and says so at its last", () => {
        const replay = replayOf(engineReplayText("truncated_after_round"));
        const opening = replayDisplay(replay, { page: 0, stop: 0 }, ALL);
        const end = replayDisplay(replay, { page: 0, stop: lastStop(replay) }, ALL);

        expect(opening.incomplete?.label).toBe("Incomplete");
        expect(opening.endNotice).toBeNull();
        expect(end.endNotice).toBe("The recording ends here, before the game's end");
    });

    test("labels a replay cut short by a line it cannot read, with the line", () => {
        const lines = engineReplayText("pao").trimEnd().split("\n");
        const replay = replayOf([...lines.slice(0, 10), "{broken", ...lines.slice(10)].join("\n"));
        const end = replayDisplay(replay, { page: 0, stop: lastStop(replay) }, ALL);

        expect(replay.navigation.complete).toBe(false);
        expect(end.incomplete).toEqual({
            detail: "Line 11 could not be read, so the replay stops before it.",
            label: "Damaged",
        });
        expect(end.endNotice).toBe("The replay stops here: line 11 could not be read");
    });
});
