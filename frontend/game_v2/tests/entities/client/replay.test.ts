import { assert, describe, expect, test } from "vitest";

import { ENGINE_REPLAYS, type EngineReplay, loadEngineReplay } from "#tests/fixtures/replays";
import { WIRE_GAME_STARTED, WIRE_ROUND_STARTED } from "#tests/fixtures/wire";
import {
    type ClientStep,
    type ClientTimeline,
    type GameClientState,
    type TimelineEntry,
    readReplayTimeline,
    startReplayClient,
    stepGameClient,
} from "@/entities/client";
import {
    type BoardPerspective,
    type PlayerState,
    type ReplayEvent,
    type TableState,
    buildActionSteps,
    buildNavigationIndex,
    tableStateToDisplayState,
} from "@/entities/table";
import {
    REPLAY_VERSION,
    ROUND_RESULT_TYPE,
    type ReplayLine,
    type RoundEndEvent,
    SEAT_CONTROL_REASON,
    WIRE_SCORE_DIVISOR,
} from "@/shared/protocol";

const VERSION_LINE = JSON.stringify({ version: REPLAY_VERSION });
const SEAT_0_TABLE = [JSON.stringify(WIRE_GAME_STARTED), JSON.stringify(WIRE_ROUND_STARTED)];
const REPLAY_VIEW: BoardPerspective = { bottomSeat: 0, reveal: "all" };
const drawLine = '{"d": 0, "t": 1}';
const discardLine = '{"d": 0, "t": 2}';

function readLines(...lines: string[]): { errors: readonly string[]; types: (string | null)[] } {
    const read = readReplayTimeline([VERSION_LINE, ...SEAT_0_TABLE, ...lines].join("\n"));
    assert(read.ok);
    const types = read.timeline.entries
        .slice(SEAT_0_TABLE.length)
        .map((entry) => entry.parsed?.type ?? null);
    return { errors: read.errors, types };
}

describe("readReplayTimeline - lines", () => {
    test("parses each event line in order through the dispatcher, blank lines skipped", () => {
        const { errors, types } = readLines(drawLine, "", "   ", discardLine);
        expect(errors).toEqual([]);
        expect(types).toEqual(["draw", "discard"]);
    });

    test("reports a line that is no message or one a replay never holds, and keeps the rest", () => {
        const { errors, types } = readLines(
            drawLine,
            "not json",
            VERSION_LINE,
            '{"t": 99}',
            '{"cd": "test_code", "msg": "test message", "t": 7}',
            '{"ai": 2, "s": 0, "t": 101}',
            discardLine,
        );
        expect(types).toEqual(["draw", null, null, null, null, "discard"]);
        expect(errors).toEqual([
            expect.stringMatching(/^Line 5: JSON parse error: /),
            "Line 6: Parse error: Message has neither 'type' (string) nor 't' (number) field",
            "Line 7: Parse error: Failed to parse game event t=99: Unknown game event type: t=99",
            "Line 8: Non-replay event type: error",
            "Line 9: Parse error: Failed to parse replay line t=101: Unknown seat control: ai=2",
        ]);
    });
});

function findEventIndex(timeline: EngineReplay, type: ReplayEvent["type"], after = -1): number {
    const index = timeline.events.findIndex((event, at) => at > after && event?.type === type);
    expect(index, `no ${type} event after ${after}`).toBeGreaterThanOrEqual(0);
    return index;
}

function stateAfter(timeline: EngineReplay, index: number): TableState {
    return timeline.tables[index + 1];
}

function findRoundEnd(timeline: EngineReplay): { event: RoundEndEvent; index: number } {
    const index = findEventIndex(timeline, "round_end");
    const event = timeline.events[index];
    assert(event?.type === "round_end");
    return { event, index };
}

function scoresOf(state: TableState): number[] {
    return state.players.map((player) => player.score);
}

interface RevealedHand {
    meldCount: number;
    seat: number;
    tiles: number[];
}

function revealedHands(event: RoundEndEvent): RevealedHand[] {
    switch (event.resultType) {
        case ROUND_RESULT_TYPE.TSUMO: {
            const tiles = [...event.closedTiles, event.winningTile];
            return [{ meldCount: event.melds.length, seat: event.winnerSeat, tiles }];
        }
        case ROUND_RESULT_TYPE.RON: {
            const tiles = event.closedTiles;
            return [{ meldCount: event.melds.length, seat: event.winnerSeat, tiles }];
        }
        case ROUND_RESULT_TYPE.DOUBLE_RON: {
            return event.winners.map((winner) => ({
                meldCount: winner.melds.length,
                seat: winner.winnerSeat,
                tiles: winner.closedTiles,
            }));
        }
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW:
        case ROUND_RESULT_TYPE.NAGASHI_MANGAN: {
            return event.tenpaiHands.map((hand) => ({
                meldCount: hand.melds.length,
                seat: hand.seat,
                tiles: hand.closedTiles,
            }));
        }
        case ROUND_RESULT_TYPE.ABORTIVE_DRAW: {
            return [];
        }
    }
}

interface HandCheck {
    hand: RevealedHand;
    label: string;
    player: PlayerState;
}

function pairRevealedHands(name: string): HandCheck[] {
    const { events, tables } = loadEngineReplay(name);
    return events.flatMap((event, index) =>
        event?.type === "round_end"
            ? revealedHands(event).map((hand) => ({
                  hand,
                  label: `${name}, event ${index}, seat ${hand.seat}`,
                  player: tables[index + 1].players[hand.seat],
              }))
            : [],
    );
}

interface SettlementCheck {
    label: string;
    nextRoundScores: number[];
    settledScores: number[];
}

function pairSettlements(name: string): SettlementCheck[] {
    const { events, tables } = loadEngineReplay(name);
    return events.flatMap((event, index) => {
        const next = events.findIndex((later, at) => at > index && later?.type === "round_started");
        if (event?.type !== "round_end" || next === -1) {
            return [];
        }
        return [
            {
                label: `${name}, event ${index}`,
                nextRoundScores: scoresOf(tables[next + 1]),
                settledScores: scoresOf(tables[index + 1]),
            },
        ];
    });
}

function compareTileIds(left: number, right: number): number {
    return left - right;
}

describe("readReplayTimeline - engine replays", () => {
    test("tracks every hand the engine reveals at a round end", () => {
        const checks = [...ENGINE_REPLAYS.keys()].flatMap(pairRevealedHands);
        expect(checks.length).toBeGreaterThan(0);
        for (const { hand, label, player } of checks) {
            expect(player.tiles.toSorted(compareTileIds), label).toEqual(
                hand.tiles.toSorted(compareTileIds),
            );
            expect(player.melds, label).toHaveLength(hand.meldCount);
        }
    });

    test("settles every round end to the scores the next round starts from", () => {
        const checks = [...ENGINE_REPLAYS.keys()].flatMap(pairSettlements);
        expect(checks.length).toBeGreaterThan(0);
        for (const { label, nextRoundScores, settledScores } of checks) {
            expect(settledScores, label).toEqual(nextRoundScores);
        }
    });

    test("riichi: a pon claims a riichi discard and the discarder stays in riichi", () => {
        const timeline = loadEngineReplay("riichi");
        const afterPon = stateAfter(timeline, findEventIndex(timeline, "meld"));

        expect(afterPon.players[1].isRiichi).toBe(true);
        expect(afterPon.players[1].discards.at(-1)).toEqual({
            claimed: true,
            isRiichi: true,
            isTsumogiri: true,
            tileId: 134,
        });
        expect(afterPon.players[2].melds).toEqual([
            {
                calledTileId: 134,
                callerSeat: 2,
                fromSeat: 1,
                meldType: "pon",
                tileIds: [132, 133, 134],
            },
        ]);
        expect(afterPon.players[2].tiles).toHaveLength(11);
    });

    test("riichi: a riichi tsumo settles every score after the riichi deposits", () => {
        const timeline = loadEngineReplay("riichi");
        const { event, index } = findRoundEnd(timeline);
        assert(event.resultType === ROUND_RESULT_TYPE.TSUMO);
        const end = stateAfter(timeline, index);

        expect(end.phase).toBe("round_ended");
        expect(end.lastEventDescription).toBe("Tsumo by Alice");
        expect(end.players.map((player) => player.isRiichi)).toEqual([false, true, false, true]);
        expect(scoresOf(end)).toEqual([21_000, 34_000, 23_000, 22_000]);
        expect(end.roundEndResult).toMatchObject({
            scoreChanges: event.scoreChanges,
            scoresBeforePayment: event.scores,
            uraDoraIndicators: event.uraDoraIndicators,
            winners: [
                {
                    handResult: event.handResult,
                    seat: event.winnerSeat,
                    winningTile: event.winningTile,
                },
            ],
        });
    });

    test("kans: keeps an open, an added and a closed kan, each with its dora", () => {
        const timeline = loadEngineReplay("kans");
        const end = stateAfter(timeline, findRoundEnd(timeline).index);

        expect(end.players.map((player) => player.melds.map((meld) => meld.meldType))).toEqual([
            [],
            ["added_kan"],
            ["open_kan"],
            ["closed_kan"],
        ]);
        expect(end.players[1].melds[0]).toMatchObject({
            addedTileId: 127,
            calledTileId: 126,
            fromSeat: 3,
            tileIds: [124, 125, 126, 127],
        });
        expect(end.players.map((player) => player.tiles.length)).toEqual([13, 10, 10, 11]);
        expect(end.doraIndicators).toEqual([102, 103, 104, 107]);
    });

    test("kans: the tsumo wins on the rinshan draw after the last kan", () => {
        const timeline = loadEngineReplay("kans");
        const { event, index } = findRoundEnd(timeline);
        assert(event.resultType === ROUND_RESULT_TYPE.TSUMO);
        const lastKan = timeline.events.findLastIndex((later) => later?.type === "meld");
        const rinshanDraw = timeline.events[findEventIndex(timeline, "draw", lastKan)];
        assert(rinshanDraw?.type === "draw");
        const end = stateAfter(timeline, index);

        expect(end.players[3].drawnTileId).toBe(rinshanDraw.tileId);
        expect(end.roundEndResult?.winners).toMatchObject([
            { handResult: event.handResult, seat: 3, winningTile: rinshanDraw.tileId },
        ]);
    });

    test("double ron: shows both winners of one discard, who dealt it and the settled scores", () => {
        const timeline = loadEngineReplay("double_ron");
        const { event, index } = findRoundEnd(timeline);
        assert(event.resultType === ROUND_RESULT_TYPE.DOUBLE_RON);
        const end = stateAfter(timeline, index);

        expect(end.lastEventDescription).toBe("Double ron by Alice and Charlie");
        expect(scoresOf(end)).toEqual([5000, 38_000, 32_000, 25_000]);
        expect(end.roundEndResult).toMatchObject({
            loserSeat: event.loserSeat,
            scoreChanges: event.scoreChanges,
        });
        expect(
            end.roundEndResult?.winners.map((winner) => [
                winner.seat,
                winner.winningTile,
                winner.handResult,
            ]),
        ).toEqual(
            event.winners.map((winner) => [
                winner.winnerSeat,
                event.winningTile,
                winner.handResult,
            ]),
        );
    });

    test("exhaustive draw: empties the wall, settles scores, and the next round resets riichi", () => {
        const timeline = loadEngineReplay("exhaustive_tenpai");
        const { index } = findRoundEnd(timeline);
        const roundEnd = stateAfter(timeline, index);

        expect(roundEnd.tilesRemaining).toBe(0);
        expect(roundEnd.lastEventDescription).toBe("Exhaustive draw");
        expect(scoresOf(roundEnd)).toEqual([23_500, 25_500, 26_500, 23_500]);

        const nextRound = stateAfter(timeline, findEventIndex(timeline, "round_started", index));
        expect(nextRound.roundEndResult).toBeNull();
        expect(nextRound.players.map((player) => [player.score, player.isRiichi])).toEqual([
            [23_500, false],
            [25_500, false],
            [26_500, false],
            [23_500, false],
        ]);
    });

    test("ai replacements: marks a seat an AI holds from the move after its line until its human returns", () => {
        const { events, tables } = loadEngineReplay("ai_replacements");
        const marks = buildActionSteps(events).map((step) =>
            tables[step.stateIndex].players.map((player) => player.aiStandIn),
        );
        const { ABSENT, LEFT } = SEAT_CONTROL_REASON;

        expect(marks.slice(0, 10)).toEqual([
            [null, null, null, null],
            [null, null, null, ABSENT],
            [null, null, null, ABSENT],
            [null, null, null, ABSENT],
            [null, null, null, ABSENT],
            [null, null, null, ABSENT],
            [null, null, LEFT, ABSENT],
            [null, null, LEFT, ABSENT],
            [LEFT, null, LEFT, null],
            [LEFT, null, null, null],
        ]);
    });

    test("a played-out game ends on the engine's standings and winner", () => {
        const timeline = loadEngineReplay("eager_game");
        const gameEnd = timeline.events.at(-1);
        assert(gameEnd?.type === "game_end");
        const end = stateAfter(timeline, timeline.events.length - 1);

        expect(end.phase).toBe("game_ended");
        expect(end.lastEventDescription).toBe("Game over - Winner: Bob");
        expect(end.gameEndResult).toEqual({
            standings: gameEnd.standings,
            winnerSeat: gameEnd.winnerSeat,
        });
        expect(end.players.map((player) => [player.seat, player.score])).toEqual(
            gameEnd.standings
                .map((standing) => [standing.seat, standing.score])
                .toSorted(([left], [right]) => left - right),
        );
    });
});

describe("readReplayTimeline - engine fixtures", () => {
    test("reads every replay the engine records and maps each of its steps to a board", () => {
        expect(ENGINE_REPLAYS.size).toBeGreaterThan(0);
        for (const name of ENGINE_REPLAYS.keys()) {
            const { events, tables } = loadEngineReplay(name);
            const steps = buildActionSteps(events);
            buildNavigationIndex(events, steps, tables);
            const boards = steps.map((step) =>
                tableStateToDisplayState(tables[step.stateIndex], REPLAY_VIEW),
            );
            expect(boards.length, name).toBeGreaterThan(1);
            expect(boards.indexOf(null), name).toBe(-1);
        }
    });
});

type WireLine = Readonly<Record<string, unknown>>;

function projectLine(raw: WireLine, line: ReplayLine, seat: number): WireLine | null {
    switch (line.type) {
        case "game_started": {
            return { ...raw, s: seat };
        }
        case "round_started": {
            const players = line.players.map((view) => ({
                s: view.seat,
                sc: view.score / WIRE_SCORE_DIVISOR,
            }));
            const own = line.players.find((view) => view.seat === seat)?.tiles;
            return { ...raw, mt: own, p: players, s: seat };
        }
        case "draw": {
            return line.seat === seat ? raw : null;
        }
        case "ai_replacement":
        case "human_return": {
            return null;
        }
        default: {
            return raw;
        }
    }
}

function seatKnowledge(state: GameClientState, seat: number): unknown {
    const { currentPlayerSeat, players, tilesRemaining } = state.table;
    return {
        currentPlayerSeat,
        handSizes: players.map((player) => player.tiles.length + player.concealedCount),
        ownTiles: players
            .find((player) => player.seat === seat)
            ?.tiles.toSorted((left, right) => left - right),
        tilesRemaining,
    };
}

function projectedEntry(entry: TimelineEntry, seat: number): WireLine | null {
    const { event, parsed } = entry;
    if (event.kind !== "replay_line" || parsed === null) {
        return null;
    }
    return projectLine(event.raw, parsed, seat);
}

function divergenceAt(entry: TimelineEntry, step: ClientStep, seat: number): string | null {
    const expected = JSON.stringify(seatKnowledge(entry.state, seat));
    const actual = JSON.stringify(seatKnowledge(step.state, seat));
    if (step.effects.length === 0 && expected === actual) {
        return null;
    }
    return `${entry.parsed?.type}: replay ${expected}, view ${actual}, effects ${step.effects.length}`;
}

function firstDivergence(timeline: ClientTimeline, seat: number): string | null {
    let view = startReplayClient(0);
    for (const [index, entry] of timeline.entries.entries()) {
        const raw = projectedEntry(entry, seat);
        if (raw !== null) {
            const step = stepGameClient(view, { at: 0, kind: "server_message", raw });
            view = step.state;
            const found = divergenceAt(entry, step, seat);
            if (found !== null) {
                return `entry ${index}, ${found}`;
            }
        }
    }
    return null;
}

describe("stepGameClient - per-seat projections of the engine replays", () => {
    test("a seat seeing only its own hand and draws keeps every hand size, its tiles, the wall and the turn", () => {
        const divergences = [...ENGINE_REPLAYS.keys()].flatMap((name) => {
            const { timeline } = loadEngineReplay(name);
            return [0, 1, 2, 3].flatMap((seat) => {
                const divergence = firstDivergence(timeline, seat);
                return divergence === null ? [] : [`${name}, seat ${seat}: ${divergence}`];
            });
        });

        expect(divergences).toEqual([]);
    });
});
