import { assert, describe, expect, test } from "vitest";

import { encodeReplayLines, encodeReplayRecords, joinBytes } from "#tests/fixtures/replay-records";
import { ENGINE_REPLAYS, type EngineReplay, loadEngineReplay } from "#tests/fixtures/replays";
import { GAME_ID, HANDOFF, clientEvent } from "#tests/fixtures/scenario";
import {
    REPLAY_GAME_STARTED,
    REPLAY_ROUND_STARTED,
    WIRE_GAME_JOINED,
    WIRE_ROUND_STARTED,
} from "#tests/fixtures/wire";
import {
    type ClientStep,
    type ClientTimeline,
    type GameClientState,
    type LiveClient,
    type TimelineEntry,
    readReplayTimeline,
    startGameClient,
    stepGameClient,
} from "@/entities/client";
import { type ActionStep, buildNavigationIndex } from "@/entities/replay";
import {
    type BoardPerspective,
    type PlayerState,
    type ReplayEvent,
    type TableState,
    tableStateToDisplayState,
} from "@/entities/table";
import {
    EVENT_TYPE,
    REPLAY_VERSION,
    ROUND_RESULT_TYPE,
    type ReplayLine,
    type RoundEndEvent,
    SEAT_CONTROL_REASON,
    WIRE_KEY,
} from "@/shared/protocol";
import { WIRE_SCORE_DIVISOR } from "@/shared/protocol/constants";

const VERSION_LINE = JSON.stringify({ [WIRE_KEY.REPLAY_VERSION]: REPLAY_VERSION });
const SEAT_0_TABLE = [JSON.stringify(REPLAY_GAME_STARTED), JSON.stringify(REPLAY_ROUND_STARTED)];
const REPLAY_VIEW: BoardPerspective = { bottomSeat: 0, reveal: "all" };
const drawLine = JSON.stringify({
    [WIRE_KEY.PACKED_MOVE]: 0,
    [WIRE_KEY.EVENT_TYPE]: 1,
    [WIRE_KEY.TILES_REMAINING]: 69,
});
const discardLine = JSON.stringify({ [WIRE_KEY.PACKED_MOVE]: 0, [WIRE_KEY.EVENT_TYPE]: 2 });

function readLines(...lines: string[]): {
    damage: { lineNumber: number; detail: string } | null;
    types: (string | null)[];
} {
    const read = readReplayTimeline(
        encodeReplayLines([VERSION_LINE, ...SEAT_0_TABLE, ...lines].join("\n")),
    );
    assert(read.ok);
    const types = read.timeline.entries
        .slice(SEAT_0_TABLE.length)
        .map((entry) => entry.parsed?.type ?? null);
    return { damage: read.damage, types };
}

describe("readReplayTimeline - lines", () => {
    test("names the file's line of an error after a round end the dispatcher took in two parts", () => {
        const fixture = ENGINE_REPLAYS.get("chankan_added");
        assert(fixture);
        const text = joinBytes([fixture, encodeReplayRecords([{ [WIRE_KEY.EVENT_TYPE]: 99 }])]);
        const read = readReplayTimeline(text);
        assert(read.ok);

        expect(read.damage).toEqual({
            detail: "Parse error: Failed to parse game event EVENT_TYPE=99: Unknown game event type: EVENT_TYPE=99",
            lineNumber: read.timeline.entries.length + 1,
        });
        expect(read.timeline.entries.at(-1)?.parsed?.type).toBe("round_end");
    });

    test("parses each event line in order through the dispatcher, blank lines skipped", () => {
        const { damage, types } = readLines(drawLine, "", "   ", discardLine);
        expect(damage).toBeNull();
        expect(types).toEqual(["draw", "discard"]);
    });

    test.each([
        ["not json", /^Invalid MessagePack record/],
        [
            VERSION_LINE,
            /^Parse error: Message has neither 'SESSION_TYPE' \(string\) nor 'EVENT_TYPE' \(number\) field$/,
        ],
        [
            JSON.stringify({ [WIRE_KEY.EVENT_TYPE]: 99 }),
            /^Parse error: Failed to parse game event EVENT_TYPE=99: Unknown game event type: EVENT_TYPE=99$/,
        ],
        [
            JSON.stringify({
                [WIRE_KEY.GAME_ERROR_CODE]: "test_code",
                [WIRE_KEY.GAME_ERROR_MESSAGE]: "test message",
                [WIRE_KEY.EVENT_TYPE]: 7,
            }),
            /^Invalid MessagePack record/,
        ],
        [
            JSON.stringify({
                [WIRE_KEY.AI_PLAYER]: 2,
                [WIRE_KEY.SEAT]: 0,
                [WIRE_KEY.EVENT_TYPE]: 101,
            }),
            /^Parse error: Failed to parse replay line EVENT_TYPE=101: Unknown seat control: AI_PLAYER=2$/,
        ],
        [JSON.stringify(REPLAY_GAME_STARTED), /^Cannot be played: /],
        [
            JSON.stringify({
                ...REPLAY_ROUND_STARTED,
                [WIRE_KEY.PLAYERS]: WIRE_ROUND_STARTED[WIRE_KEY.PLAYERS],
            }),
            /^Parse error: Failed to parse deal EVENT_TYPE=9: it does not record every seat.s hand$/,
        ],
    ])("stops at a line it cannot show (%s), keeping only the lines before it", (bad, detail) => {
        const { damage, types } = readLines(drawLine, bad, discardLine);

        expect(types).toEqual(["draw"]);
        expect(damage).toEqual({ detail: expect.stringMatching(detail), lineNumber: 5 });
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

/** A stop's event type, phase, wall, and the given seat's closed hand size and meld types. */
function kanStop({ events, tables }: EngineReplay, step: ActionStep, seat: number): unknown[] {
    const table = tables[step.stateIndex];
    const player = table.players[seat];
    return [
        events[step.moveEntry]?.type,
        table.phase,
        table.tilesRemaining,
        player.tiles.length + player.concealedCount,
        player.melds.map((meld) => meld.meldType),
    ];
}

function rightRiverSideways(state: TableState): boolean[] {
    const board = tableStateToDisplayState(state, REPLAY_VIEW);
    return board?.players[1].discards.map((tile) => tile.riichi === true) ?? [];
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
    nextRound: (number | number[])[];
    settled: (number | number[])[];
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
                nextRound: [scoresOf(tables[next + 1]), tables[next + 1].riichiSticks],
                settled: [scoresOf(tables[index + 1]), tables[index + 1].riichiSticks],
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

    test("settles every round end to the scores and riichi sticks the next round starts from", () => {
        const checks = [...ENGINE_REPLAYS.keys()].flatMap(pairSettlements);
        expect(checks.length).toBeGreaterThan(0);
        for (const { label, nextRound, settled } of checks) {
            expect(settled, label).toEqual(nextRound);
        }
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

    test("chankan: stops on the robbed added kan as declared, then on the ron; its tile leaves the hand once", () => {
        const replay = loadEngineReplay("chankan_added");
        const { tables } = replay;
        const lastStops = buildNavigationIndex(replay.events, tables).stops.slice(-3);

        expect(lastStops.map((step) => kanStop(replay, step, 1))).toEqual([
            ["draw", "in_round", 65, 11, ["pon"]],
            ["kan_declared", "in_round", 65, 10, ["added_kan"]],
            ["round_end", "round_ended", 65, 10, ["added_kan"]],
        ]);
        const end = tables.at(-1);
        expect(end?.players[1].melds[0]).toMatchObject({
            addedTileId: 59,
            tileIds: [56, 57, 58, 59],
        });
        expect(end?.players[1].tiles).not.toContain(59);
        expect(end?.roundEndResult?.winners).toMatchObject([{ seat: 2, winningTile: 59 }]);
    });

    test("chankan: stops on the closed kan a kokushi robs as declared, all four copies out of the hand", () => {
        const replay = loadEngineReplay("chankan_closed_kokushi");
        const { tables } = replay;
        const lastStops = buildNavigationIndex(replay.events, tables).stops.slice(-4);

        expect(lastStops.map((step) => kanStop(replay, step, 1))).toEqual([
            ["draw", "in_round", 64, 14, []],
            ["kan_declared", "in_round", 64, 10, ["closed_kan"]],
            ["round_end", "round_ended", 64, 10, ["closed_kan"]],
            ["game_end", "game_ended", 64, 10, ["closed_kan"]],
        ]);
        const end = tables.at(-1);
        expect(end?.players[1].melds[0].tileIds).toEqual([32, 33, 34, 35]);
        expect(end?.players[1].tiles.filter((tileId) => tileId >> 2 === 8)).toEqual([]);
    });

    test("double ron: shows both winners of one discard, who dealt it and the settled scores", () => {
        const timeline = loadEngineReplay("double_ron");
        const { event, index } = findRoundEnd(timeline);
        assert(event.resultType === ROUND_RESULT_TYPE.DOUBLE_RON);
        const end = stateAfter(timeline, index);

        expect(scoresOf(end)).toEqual([5000, 38_000, 32_000, 25_000]);
        expect([timeline.tables[index].riichiSticks, end.riichiSticks]).toEqual([2, 0]);
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
        const marks = buildNavigationIndex(events, tables).stops.map((step) =>
            tables[step.stateIndex].players.map((player) => player.aiStandIn),
        );
        const { ABSENT, LEFT } = SEAT_CONTROL_REASON;

        expect(marks.slice(0, 9)).toEqual([
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
        expect(end.gameEndResult).toEqual({
            endCause: gameEnd.endCause,
            leftoverRiichiBonus: gameEnd.leftoverRiichiBonus,
            leftoverSticks: gameEnd.leftoverRiichiSticks,
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

describe("readReplayTimeline - riichi deposits", () => {
    test("reaches every round end on the scores it was taken at, every accepted riichi deposited", () => {
        const checks = [...ENGINE_REPLAYS.keys()].flatMap((name) => {
            const { events, tables } = loadEngineReplay(name);
            return events.flatMap((event, index) =>
                event?.type === "round_end"
                    ? [{ event, label: `${name}, event ${index}`, table: tables[index] }]
                    : [],
            );
        });
        expect(checks.length).toBeGreaterThan(0);
        for (const { event, label, table } of checks) {
            expect(scoresOf(table), label).toEqual(
                table.players.map((player) => event.scores[String(player.seat)]),
            );
        }
    });

    test("riichi: the stick is deposited once the declaration's discard passes, not on the discard", () => {
        const timeline = loadEngineReplay("riichi");
        const declared = findEventIndex(timeline, "riichi_declared");
        const declaredAgain = findEventIndex(timeline, "riichi_declared", declared);
        const onDiscard = timeline.tables[declared];

        expect(onDiscard.players[1].discards.at(-1)?.isRiichi).toBe(true);
        expect([scoresOf(onDiscard), onDiscard.riichiSticks]).toEqual([
            [25_000, 25_000, 25_000, 25_000],
            0,
        ]);
        expect([
            scoresOf(stateAfter(timeline, declared)),
            stateAfter(timeline, declared).riichiSticks,
        ]).toEqual([[25_000, 24_000, 25_000, 25_000], 1]);
        expect([
            scoresOf(stateAfter(timeline, declaredAgain)),
            stateAfter(timeline, declaredAgain).riichiSticks,
        ]).toEqual([[25_000, 24_000, 25_000, 24_000], 2]);
        expect(stateAfter(timeline, findRoundEnd(timeline).index).riichiSticks).toBe(0);
    });

    test("ron riichi discard: a ronned declaration discard deposits nothing", () => {
        const timeline = loadEngineReplay("ron_riichi_discard");
        const { index } = findRoundEnd(timeline);
        const ronned = timeline.tables[index];

        expect(ronned.players.map((player) => [player.score, player.isRiichi])).toEqual([
            [25_000, false],
            [24_000, true],
            [25_000, false],
            [25_000, false],
        ]);
        expect(ronned.players[2].discards.at(-1)?.isRiichi).toBe(true);
        expect(ronned.riichiSticks).toBe(1);
        expect(stateAfter(timeline, index).riichiSticks).toBe(0);
    });

    test("leftover riichi: the game end pays the stick left on the table, at the game's 1,500 stick value, to the winner's standing", () => {
        const timeline = loadEngineReplay("leftover_riichi");
        const { index } = findRoundEnd(timeline);
        const gameEnd = timeline.events.at(-1);
        assert(gameEnd?.type === "game_end");
        const drawn = stateAfter(timeline, index);
        const end = stateAfter(timeline, timeline.events.length - 1);

        expect([scoresOf(drawn), drawn.riichiSticks]).toEqual([
            [23_500, 24_500, 26_500, 23_500],
            1,
        ]);
        expect(gameEnd.leftoverRiichiBonus).toBe(1500);
        expect([scoresOf(end), end.riichiSticks]).toEqual([[23_500, 24_500, 28_000, 23_500], 0]);
        expect(end.gameEndResult).toMatchObject({
            leftoverRiichiBonus: 1500,
            leftoverSticks: 1,
            winnerSeat: 2,
        });
    });

    test("riichi: a pon claims a riichi discard, the discarder stays in riichi and its next discard lies sideways", () => {
        const timeline = loadEngineReplay("riichi");
        const pon = findEventIndex(timeline, "meld");
        const afterPon = stateAfter(timeline, pon);
        const nextDiscard = timeline.events.findIndex(
            (event, at) => at > pon && event?.type === "discard" && event.seat === 1,
        );

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
        expect(rightRiverSideways(afterPon)).not.toContain(true);
        expect(rightRiverSideways(stateAfter(timeline, nextDiscard))).toEqual([
            ...rightRiverSideways(afterPon),
            true,
        ]);
    });

    test("riichi: a riichi tsumo settles every score after the riichi deposits", () => {
        const timeline = loadEngineReplay("riichi");
        const { event, index } = findRoundEnd(timeline);
        assert(event.resultType === ROUND_RESULT_TYPE.TSUMO);
        const end = stateAfter(timeline, index);

        expect(end.phase).toBe("round_ended");
        expect(end.players.map((player) => player.isRiichi)).toEqual([false, true, false, true]);
        expect(scoresOf(end)).toEqual([21_000, 34_000, 23_000, 22_000]);
        expect(end.roundEndResult).toMatchObject({
            scoreChanges: event.scoreChanges,
            scoresBeforePayment: event.scores,
            winners: [
                {
                    handResult: event.handResult,
                    seat: event.winnerSeat,
                    uraDoraIndicators: event.uraDoraIndicators,
                    winningTile: event.winningTile,
                },
            ],
        });
    });
});

describe("readReplayTimeline - engine fixtures", () => {
    test("reads every replay the engine records and maps each of its steps to a board", () => {
        expect(ENGINE_REPLAYS.size).toBeGreaterThan(0);
        for (const name of ENGINE_REPLAYS.keys()) {
            const { events, tables } = loadEngineReplay(name);
            const { stops } = buildNavigationIndex(events, tables);
            const boards = stops.map((step) =>
                tableStateToDisplayState(tables[step.stateIndex], REPLAY_VIEW),
            );
            expect(boards.length, name).toBeGreaterThan(1);
            expect(boards.indexOf(null), name).toBe(-1);
        }
    });
});

type WireLine = Readonly<Record<string, unknown>>;

const PROJECTED_TIMER = {
    [WIRE_KEY.BANK_SECONDS]: 20,
    [WIRE_KEY.GAME_START_CONFIRM]: 3,
    [WIRE_KEY.MAX_BANK_SECONDS]: 20,
    [WIRE_KEY.ROUND_ADVANCE_TIMEOUT]: 15,
    [WIRE_KEY.BASE_TURN_SECONDS]: 5,
};

function projectLine(raw: WireLine, line: ReplayLine, seat: number): WireLine | null {
    switch (line.type) {
        case "game_started": {
            return {
                ...raw,
                [WIRE_KEY.RIICHI_STICK_VALUE]: line.riichiStickValue / WIRE_SCORE_DIVISOR,
                [WIRE_KEY.SEAT]: seat,
                [WIRE_KEY.TIMER_SETTINGS]: PROJECTED_TIMER,
            };
        }
        case "round_started": {
            const players = line.players.map((view) => ({
                [WIRE_KEY.SEAT]: view.seat,
                [WIRE_KEY.SCORE]: view.score / WIRE_SCORE_DIVISOR,
            }));
            const own = line.players.find((view) => view.seat === seat)?.tiles;
            return {
                ...raw,
                [WIRE_KEY.MY_TILES]: own,
                [WIRE_KEY.PLAYERS]: players,
                [WIRE_KEY.SEAT]: seat,
            };
        }
        case "draw": {
            const { [WIRE_KEY.TILES_REMAINING]: _tilesRemaining, ...liveDraw } = raw;
            return line.seat === seat
                ? {
                      ...liveDraw,
                      [WIRE_KEY.BANK_SECONDS]: PROJECTED_TIMER[WIRE_KEY.BANK_SECONDS],
                      [WIRE_KEY.WAIT_ID]: 1,
                  }
                : {
                      [WIRE_KEY.SEAT]: line.seat,
                      [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.DRAW_NOTICE,
                  };
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
    if (event.kind !== "replay_line" || parsed === null || parsed.type === "kan_declared") {
        return null;
    }
    return projectLine(event.raw, parsed, seat);
}

/**
 * Whether an entry ends its replay line: the reader takes a round end that robbed a kan as the kan declared, then the
 * result, and a live seat sees that kan from the round end alone.
 */
function endsLine(entry: TimelineEntry): boolean {
    return entry.parsed?.type !== "kan_declared";
}

function divergenceAt(
    entry: TimelineEntry,
    step: ClientStep<LiveClient>,
    seat: number,
): string | null {
    const expected = JSON.stringify(seatKnowledge(entry.state, seat));
    const actual = JSON.stringify(seatKnowledge(step.state, seat));
    const effects = step.effects.filter((effect) => effect.type !== "clear_handoff");
    if (effects.length === 0 && expected === actual) {
        return null;
    }
    return `${entry.parsed?.type}: replay ${expected}, view ${actual}, effects ${effects.length}`;
}

/** A seat's live client holding its seat: its socket open and its join admitted. */
function seatedClient(): LiveClient {
    const { state } = startGameClient(GAME_ID, HANDOFF, 0);
    return [clientEvent.opened(0), clientEvent.message(0, WIRE_GAME_JOINED)].reduce(
        (client, event) => stepGameClient(client, event).state,
        state,
    );
}

function firstDivergence(timeline: ClientTimeline, seat: number): string | null {
    let view = seatedClient();
    for (const [index, entry] of timeline.entries.entries()) {
        const raw = projectedEntry(entry, seat);
        const step: ClientStep<LiveClient> =
            raw === null
                ? { effects: [], state: view }
                : stepGameClient(view, { at: 0, kind: "server_message", raw });
        view = step.state;
        const found = endsLine(entry) ? divergenceAt(entry, step, seat) : null;
        if (found !== null) {
            return `entry ${index}, ${found}`;
        }
    }
    return null;
}

describe("stepGameClient - per-seat projections of the engine replays", () => {
    test("a seat seeing its own draws and the others' draw notices keeps every hand size, its tiles, the wall and the turn after every line", () => {
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
