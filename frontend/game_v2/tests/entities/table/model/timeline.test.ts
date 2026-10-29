import { assert, describe, expect, test } from "vitest";

import {
    makeDiscardEvent,
    makeDrawEvent,
    makeGameEndEvent,
    makeGameStartedEvent,
    makeRoundStartedEvent,
    makeTsumoRoundEnd,
} from "#tests/fixtures/events";
import { ENGINE_REPLAYS, loadEngineReplay } from "#tests/fixtures/replays";
import { buildTimeline } from "@/entities/table/model/timeline";
import { type PlayerState, type ReplayEvent, type TableState } from "@/entities/table/model/types";
import { ROUND_RESULT_TYPE, type RoundEndEvent } from "@/shared/protocol";

describe("buildTimeline", () => {
    describe("basic timeline structure", () => {
        test("empty events produces a single initial state", () => {
            const states = buildTimeline([]);

            expect(states).toHaveLength(1);
            expect(states[0].phase).toBe("pre_game");
            expect(states[0].players).toHaveLength(0);
            expect(states[0].gameId).toBe("");
        });

        test("returns events.length + 1 states for any event sequence", () => {
            const events: ReplayEvent[] = [makeGameStartedEvent(), makeRoundStartedEvent()];
            const states = buildTimeline(events);

            expect(states).toHaveLength(3);
        });

        test("state at index 0 is always the initial state before any events", () => {
            const events: ReplayEvent[] = [makeGameStartedEvent()];
            const states = buildTimeline(events);

            expect(states[0].phase).toBe("pre_game");
            expect(states[0].players).toHaveLength(0);
            expect(states[0].gameId).toBe("");
        });
    });

    describe("intermediate states", () => {
        function buildDrawTimeline() {
            const events: ReplayEvent[] = [
                makeGameStartedEvent({ gameId: "timeline-test" }),
                makeRoundStartedEvent(),
                makeDrawEvent(),
            ];
            return buildTimeline(events);
        }

        test("game_started creates players and sets gameId", () => {
            const [initial, afterGameStarted] = buildDrawTimeline();

            expect(initial.players).toHaveLength(0);
            expect(afterGameStarted.phase).toBe("pre_game");
            expect(afterGameStarted.players).toHaveLength(4);
            expect(afterGameStarted.gameId).toBe("timeline-test");
        });

        test("round_started deals tiles and enters in_round phase", () => {
            const [, , afterRoundStarted] = buildDrawTimeline();

            expect(afterRoundStarted.phase).toBe("in_round");
            expect(afterRoundStarted.players[0].tiles).toHaveLength(13);
            expect(afterRoundStarted.doraIndicators).toEqual([10]);
            expect(afterRoundStarted.roundWind).toBe(0);
        });

        test("draw adds a tile to the player's hand", () => {
            const [, , , afterDraw] = buildDrawTimeline();

            expect(afterDraw.players[0].tiles).toHaveLength(14);
            expect(afterDraw.players[0].tiles).toContain(52);
            expect(afterDraw.players[0].drawnTileId).toBe(52);
        });

        test("earlier states are not mutated by later events", () => {
            const events: ReplayEvent[] = [
                makeGameStartedEvent(),
                makeRoundStartedEvent(),
                makeDrawEvent(),
                makeDiscardEvent({ tileId: 0 }),
            ];
            const [, , stateAfterRound, stateAfterDraw, stateAfterDiscard] = buildTimeline(events);

            expect(stateAfterRound.players[0].tiles).toHaveLength(13);
            expect(stateAfterRound.players[0].discards).toHaveLength(0);

            expect(stateAfterDraw.players[0].tiles).toHaveLength(14);
            expect(stateAfterDraw.players[0].drawnTileId).toBe(52);

            expect(stateAfterDiscard.players[0].tiles).toHaveLength(13);
            expect(stateAfterDiscard.players[0].discards).toHaveLength(1);
        });
    });

    describe("full game lifecycle", () => {
        test("produces correct final and round-end states", () => {
            const events: ReplayEvent[] = [
                makeGameStartedEvent(),
                makeRoundStartedEvent(),
                makeTsumoRoundEnd({
                    scoreChanges: { "0": 12_000, "1": -4000, "2": -4000, "3": -4000 },
                }),
                makeGameEndEvent({
                    numRounds: 1,
                    standings: [
                        { finalScore: 47, score: 37_000, seat: 0 },
                        { finalScore: -9, score: 21_000, seat: 1 },
                        { finalScore: -9, score: 21_000, seat: 2 },
                        { finalScore: -29, score: 21_000, seat: 3 },
                    ],
                }),
            ];
            const [, , , stateAfterRoundEnd, finalState] = buildTimeline(events);

            expect(finalState.phase).toBe("game_ended");
            expect(finalState.players[0].score).toBe(37_000);
            expect(finalState.lastEventDescription).toBe("Game over - Winner: Alice");

            expect(stateAfterRoundEnd.phase).toBe("round_ended");
            expect(stateAfterRoundEnd.players[0].score).toBe(37_000);
        });
    });
});

interface EngineTimeline {
    events: readonly ReplayEvent[];
    states: TableState[];
}

function buildEngineTimeline(name: string): EngineTimeline {
    const events = loadEngineReplay(name);
    return { events, states: buildTimeline(events) };
}

function findEventIndex(timeline: EngineTimeline, type: ReplayEvent["type"], after = -1): number {
    const index = timeline.events.findIndex((event, at) => at > after && event.type === type);
    expect(index, `no ${type} event after ${after}`).toBeGreaterThanOrEqual(0);
    return index;
}

function stateAfter(timeline: EngineTimeline, index: number): TableState {
    return timeline.states[index + 1];
}

function findRoundEnd(timeline: EngineTimeline): { event: RoundEndEvent; index: number } {
    const index = findEventIndex(timeline, "round_end");
    const event = timeline.events[index];
    assert(event.type === "round_end");
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
    const { events, states } = buildEngineTimeline(name);
    return events.flatMap((event, index) =>
        event.type === "round_end"
            ? revealedHands(event).map((hand) => ({
                  hand,
                  label: `${name}, event ${index}, seat ${hand.seat}`,
                  player: states[index + 1].players[hand.seat],
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
    const { events, states } = buildEngineTimeline(name);
    return events.flatMap((event, index) => {
        const next = events.findIndex((later, at) => at > index && later.type === "round_started");
        if (event.type !== "round_end" || next === -1) {
            return [];
        }
        return [
            {
                label: `${name}, event ${index}`,
                nextRoundScores: scoresOf(states[next + 1]),
                settledScores: scoresOf(states[index + 1]),
            },
        ];
    });
}

function compareTileIds(left: number, right: number): number {
    return left - right;
}

describe("buildTimeline - engine replays", () => {
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
        const timeline = buildEngineTimeline("riichi");
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
        const timeline = buildEngineTimeline("riichi");
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
        const timeline = buildEngineTimeline("kans");
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
        const timeline = buildEngineTimeline("kans");
        const { event, index } = findRoundEnd(timeline);
        assert(event.resultType === ROUND_RESULT_TYPE.TSUMO);
        const lastKan = timeline.events.findLastIndex((later) => later.type === "meld");
        const rinshanDraw = timeline.events[findEventIndex(timeline, "draw", lastKan)];
        assert(rinshanDraw.type === "draw");
        const end = stateAfter(timeline, index);

        expect(end.players[3].drawnTileId).toBe(rinshanDraw.tileId);
        expect(end.roundEndResult?.winners).toMatchObject([
            { handResult: event.handResult, seat: 3, winningTile: rinshanDraw.tileId },
        ]);
    });

    test("double ron: shows both winners of one discard, who dealt it and the settled scores", () => {
        const timeline = buildEngineTimeline("double_ron");
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
        const timeline = buildEngineTimeline("exhaustive_tenpai");
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

    test("a played-out game ends on the engine's standings and winner", () => {
        const timeline = buildEngineTimeline("eager_game");
        const gameEnd = timeline.events[timeline.events.length - 1];
        assert(gameEnd.type === "game_end");
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
