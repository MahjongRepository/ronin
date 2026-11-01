import { assert, describe, expect, test } from "vitest";

import {
    makeAbortiveDrawRoundEnd,
    makeClosedKanEvent,
    makeDiscardEvent,
    makeDoraRevealedEvent,
    makeDoubleRonRoundEnd,
    makeDrawEvent,
    makeDrawNoticeEvent,
    makeExhaustiveDrawRoundEnd,
    makeGameEndEvent,
    makeGameStartedEvent,
    makeHandResult,
    makeMeldEvent,
    makeNagashiManganRoundEnd,
    makeRiichiDeclaredEvent,
    makeRonRoundEnd,
    makeRoundStartedEvent,
    makeTsumoRoundEnd,
} from "#tests/fixtures/events";
import { WIRE_GAME_RECONNECTED, WIRE_ROUND_RECORD } from "#tests/fixtures/wire";
import { tableStateToDisplayState } from "@/entities/table/lib/board-mapper";
import { applyEvent } from "@/entities/table/model/apply-event";
import { DesyncError } from "@/entities/table/model/desync-error";
import { createInitialTableState } from "@/entities/table/model/initial-state";
import { type ReplayEvent, type TableEvent, type TableState } from "@/entities/table/model/types";
import { meldTiles } from "@/entities/tile";
import { GAME_END_CAUSE, ROUND_RESULT_TYPE, parseServerMessage } from "@/shared/protocol";
import { type DecodedMeld } from "@/shared/protocol/decoders/meld";

describe("applyEvent - game_started", () => {
    test("seats the event's players at score 0 before the first deal, with its game id and dealer", () => {
        const next = applyEvent(
            createInitialTableState(),
            makeGameStartedEvent({ dealerSeat: 2, gameId: "abc-123" }),
        );

        expect([next.phase, next.gameId, next.dealerSeat]).toEqual(["pre_game", "abc-123", 2]);
        expect(next.players.map((p) => [p.seat, p.name, p.isAiPlayer, p.score])).toEqual([
            [0, "Alice", false, 0],
            [1, "Bot-1", true, 0],
            [2, "Bot-2", true, 0],
            [3, "Bob", false, 0],
        ]);
    });
});

describe("applyEvent - round_started", () => {
    function stateAfterGameStarted(): ReturnType<typeof applyEvent> {
        return applyEvent(createInitialTableState(), makeGameStartedEvent());
    }

    test("deals the event's round: each seat's tiles and score, the sticks, dora, wind and its round, turn and wall", () => {
        const event = makeRoundStartedEvent({
            currentPlayerSeat: 2,
            dealerSeat: 2,
            doraIndicators: [10, 20],
            honbaSticks: 2,
            players: [
                { score: 30_000, seat: 0, tiles: [0, 1] },
                { score: 22_000, seat: 1, tiles: [2] },
                { score: 18_000, seat: 2, tiles: [3] },
                { score: 30_000, seat: 3, tiles: [4] },
            ],
            riichiSticks: 1,
            roundInWind: 3,
            roundNumber: 3,
            tilesRemaining: 70,
            wind: 1,
        });
        const next = applyEvent(stateAfterGameStarted(), event);

        expect(next.players.map((p) => [p.tiles, p.score])).toEqual([
            [[0, 1], 30_000],
            [[2], 22_000],
            [[3], 18_000],
            [[4], 30_000],
        ]);
        expect(next).toMatchObject({
            currentPlayerSeat: 2,
            dealerSeat: 2,
            doraIndicators: [10, 20],
            honbaSticks: 2,
            phase: "in_round",
            riichiSticks: 1,
            roundInWind: 3,
            roundWind: 1,
            tilesRemaining: 70,
        });
    });

    test("resets previous round state (discards, melds cleared)", () => {
        const state = stateAfterGameStarted();
        const stateWithRoundData = {
            ...state,
            players: state.players.map((p) =>
                p.seat === 0
                    ? {
                          ...p,
                          discards: [{ isRiichi: false, isTsumogiri: false, tileId: 5 }],
                          drawnTileId: 7,
                          isRiichi: true,
                          melds: [
                              {
                                  calledTileId: 10,
                                  callerSeat: 0,
                                  fromSeat: 1,
                                  meldType: "pon" as const,
                                  tileIds: [8, 9, 10],
                              },
                          ],
                      }
                    : p,
            ),
        };

        const event = makeRoundStartedEvent();
        const next = applyEvent(stateWithRoundData, event);

        for (const player of next.players) {
            expect(player.discards).toEqual([]);
            expect(player.melds).toEqual([]);
            expect(player.isRiichi).toBe(false);
            expect(player.drawnTileId).toBeNull();
        }
    });

    test("deals a live seat its own tiles and every other seat a face-down count of 13", () => {
        const state = stateAfterGameStarted();
        const event = makeRoundStartedEvent({
            myTiles: [1, 2, 3],
            players: [0, 1, 2, 3].map((seat) => ({ score: 25_000, seat, tiles: null })),
            seat: 2,
        });
        const next = applyEvent(state, event);

        expect(next.players.map((p) => [p.tiles, p.concealedCount])).toEqual([
            [[], 13],
            [[], 13],
            [[1, 2, 3], 0],
            [[], 13],
        ]);
    });
});

function stateAfterRoundStarted() {
    const s1 = applyEvent(createInitialTableState(), makeGameStartedEvent());
    return applyEvent(s1, makeRoundStartedEvent());
}

function stateAfterRoundEnded(): TableState {
    return applyEvent(stateAfterRoundStarted(), makeExhaustiveDrawRoundEnd());
}

describe("applyEvent - event order", () => {
    const unseated = createInitialTableState();
    const seated = applyEvent(unseated, makeGameStartedEvent());
    const roundEnded = stateAfterRoundEnded();
    const ended = applyEvent(roundEnded, makeGameEndEvent());
    const [heldTile] = roundEnded.players[0].tiles;
    const outOfOrder: [string, TableState, TableEvent][] = [
        ["a deal before the game start", unseated, makeRoundStartedEvent()],
        ["a second game start", seated, makeGameStartedEvent()],
        ["a draw before the deal", seated, makeDrawEvent()],
        ["the game's end with no round end", stateAfterRoundStarted(), makeGameEndEvent()],
        ["a discard after the round end", roundEnded, makeDiscardEvent({ tileId: heldTile })],
        ["a round end outside a round", roundEnded, makeTsumoRoundEnd()],
        ["a deal after the game end", ended, makeRoundStartedEvent()],
        ["a second deal in a round", stateAfterRoundStarted(), makeRoundStartedEvent()],
        ["a second game end", ended, makeGameEndEvent()],
        ["a meld after the round end", roundEnded, makeMeldEvent()],
        [
            "a kan declared after the round end",
            roundEnded,
            { kanType: "closed", seat: 0, tileId: heldTile, type: "kan_declared" },
        ],
        ["a riichi after the round end", roundEnded, makeRiichiDeclaredEvent()],
        ["a dora after the round end", roundEnded, makeDoraRevealedEvent()],
        ["a draw notice after the round end", roundEnded, makeDrawNoticeEvent(1)],
    ];

    test.each(outOfOrder)("refuses %s as a desync, by its phase", (_name, state, event) => {
        expect(() => applyEvent(state, event)).toThrow(DesyncError);
        expect(() => applyEvent(state, event)).toThrow(/reached a table in phase/);
    });

    test("refuses as a desync a round end paying collected sticks on a table out of step that never learned their value", () => {
        const lost = applyEvent(createInitialTableState(), { type: "lost_step" });
        expect(() => applyEvent(lost, makeTsumoRoundEnd({ riichiSticksCollected: 1 }))).toThrow(
            DesyncError,
        );
    });

    test("takes the snapshot on a fresh page, in a round and after a round end", () => {
        const [error, snapshot] = parseServerMessage(WIRE_GAME_RECONNECTED);
        assert(error === null && snapshot.type === "game_reconnected");
        for (const state of [unseated, stateAfterRoundStarted(), roundEnded]) {
            expect(applyEvent(state, snapshot).phase).toBe("in_round");
        }
    });
});

function shownRound(state: TableState): string | undefined {
    return tableStateToDisplayState(state, { bottomSeat: 0, reveal: "bottom" })?.center
        .roundDisplay;
}

describe("applyEvent - seat lookup", () => {
    test("refuses a move by a seat the table does not hold as a desync", () => {
        expect(() =>
            applyEvent(stateAfterRoundStarted(), makeDrawEvent({ seat: 99, tileId: 52 })),
        ).toThrow(DesyncError);
    });
});

describe("applyEvent - draw", () => {
    test("appends the drawn tile to the drawer's hand, marks it drawn, gives the drawer the turn and the server's wall", () => {
        const state = stateAfterRoundStarted();
        const next = applyEvent(state, makeDrawEvent({ seat: 2, tileId: 60, tilesRemaining: 69 }));

        expect(next.players[2].tiles).toEqual([...state.players[2].tiles, 60]);
        expect([next.players[2].drawnTileId, next.currentPlayerSeat, next.tilesRemaining]).toEqual([
            60, 2, 69,
        ]);
    });

    test("takes the wall the server counts, never one less than the table held", () => {
        const afterKanReplacement = makeDrawEvent({ seat: 2, tileId: 60, tilesRemaining: 66 });

        expect(applyEvent(stateAfterRoundStarted(), afterKanReplacement).tilesRemaining).toBe(66);
        expect(
            applyEvent(stateAfterRoundStarted(), makeDrawNoticeEvent(1, 65)).tilesRemaining,
        ).toBe(65);
    });
});

describe("applyEvent - hidden hands", () => {
    function liveDeal(): ReturnType<typeof applyEvent> {
        const dealt = makeRoundStartedEvent({
            myTiles: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            players: [0, 1, 2, 3].map((seat) => ({ score: 25_000, seat, tiles: null })),
            seat: 0,
        });
        return applyEvent(applyEvent(createInitialTableState(), makeGameStartedEvent()), dealt);
    }

    test("a draw re-sent after a reconnect, of a tile the hand holds, only marks it drawn", () => {
        const next = applyEvent(
            liveDeal(),
            makeDrawEvent({ seat: 0, tileId: 12, tilesRemaining: 70 }),
        );

        expect(next.players[0].tiles).toHaveLength(13);
        expect(next.players[0].drawnTileId).toBe(12);
        expect(next.tilesRemaining).toBe(70);
    });

    test("another seat's draw notice moves the turn to it and a face-down tile from the wall into its hand", () => {
        const drawn = applyEvent(liveDeal(), makeDrawNoticeEvent(1));
        const next = applyEvent(drawn, makeDiscardEvent({ seat: 1, tileId: 100 }));

        expect([
            drawn.currentPlayerSeat,
            drawn.players[1].concealedCount,
            drawn.tilesRemaining,
        ]).toEqual([1, 14, 69]);
        expect([drawn.players[1].drawnConcealed, next.players[1].drawnConcealed]).toEqual([
            true,
            false,
        ]);
        expect(next.players[1].concealedCount).toBe(13);
        expect(next.players[1].discards.map((d) => d.tileId)).toEqual([100]);
        expect(next.tilesRemaining).toBe(69);
    });

    test("the next draw, the own or another seat's, leaves no latest discard", () => {
        const discarded = applyEvent(
            applyEvent(liveDeal(), makeDrawNoticeEvent(1)),
            makeDiscardEvent({ seat: 1, tileId: 100 }),
        );
        const ownDraw = applyEvent(
            discarded,
            makeDrawEvent({ seat: 0, tileId: 60, tilesRemaining: 68 }),
        );
        const otherDraw = applyEvent(discarded, makeDrawNoticeEvent(2, 68));

        expect([
            discarded.lastDiscardSeat,
            ownDraw.lastDiscardSeat,
            otherDraw.lastDiscardSeat,
        ]).toEqual([1, null, null]);
    });

    test("a hidden hand calls pon from its count and its discard after the call draws nothing", () => {
        const drawn = applyEvent(liveDeal(), makeDrawNoticeEvent(1));
        const afterDiscard = applyEvent(drawn, makeDiscardEvent({ seat: 1, tileId: 100 }));
        const pon = makeMeldEvent({
            calledTileId: 100,
            callerSeat: 2,
            fromSeat: 1,
            tileIds: [100, 101, 102],
        });
        const afterPon = applyEvent(afterDiscard, pon);
        const next = applyEvent(afterPon, makeDiscardEvent({ seat: 2, tileId: 120 }));

        expect(afterPon.players[2].concealedCount).toBe(11);
        expect(next.players[2].concealedCount).toBe(10);
        expect(next.tilesRemaining).toBe(69);
    });

    test("a hidden hand's closed kan after its draw notice takes four tiles from a hand of 14", () => {
        const kan = makeClosedKanEvent({ callerSeat: 3, tileIds: [104, 105, 106, 107] });
        const next = applyEvent(applyEvent(liveDeal(), makeDrawNoticeEvent(3)), kan);

        expect(next.players[3].concealedCount).toBe(10);
        expect(next.players[3].drawnConcealed).toBe(false);
        expect(next.tilesRemaining).toBe(69);
    });
});

describe("applyEvent - discard", () => {
    test("moves each discarded tile from the hand to the end of the river with its flags, clearing the drawn mark", () => {
        const drawn = applyEvent(stateAfterRoundStarted(), makeDrawEvent({ seat: 0, tileId: 52 }));
        const tsumogiri = applyEvent(
            drawn,
            makeDiscardEvent({ isTsumogiri: true, seat: 0, tileId: 52 }),
        );
        const next = applyEvent(
            tsumogiri,
            makeDiscardEvent({ isRiichi: true, seat: 0, tileId: 0 }),
        );

        expect(tsumogiri.players[0].drawnTileId).toBeNull();
        expect(next.players[0].tiles).toEqual(
            drawn.players[0].tiles.filter((t) => t !== 52 && t !== 0),
        );
        expect(next.players[0].discards).toEqual([
            { isRiichi: false, isTsumogiri: true, tileId: 52 },
            { isRiichi: true, isTsumogiri: false, tileId: 0 },
        ]);
    });
});

describe("applyEvent - riichi_declared", () => {
    test("marks the declaring seat alone as in riichi", () => {
        const next = applyEvent(stateAfterRoundStarted(), makeRiichiDeclaredEvent({ seat: 1 }));

        expect(next.players.map((p) => p.isRiichi)).toEqual([false, true, false, false]);
    });

    test("takes the declarer's score and the table's sticks from the server, never its own riichi cost", () => {
        const state = { ...stateAfterRoundStarted(), riichiCost: 1000, riichiSticks: 0 };
        const next = applyEvent(
            state,
            makeRiichiDeclaredEvent({ riichiSticks: 3, score: 23_000, seat: 1 }),
        );

        expect([next.players[1].score, next.riichiSticks]).toEqual([23_000, 3]);
    });
});

describe("applyEvent - dora_revealed", () => {
    test("appends each revealed indicator after the deal's", () => {
        const after1 = applyEvent(stateAfterRoundStarted(), makeDoraRevealedEvent({ tileId: 20 }));
        const after2 = applyEvent(after1, makeDoraRevealedEvent({ tileId: 30 }));

        expect(after2.doraIndicators).toEqual([10, 20, 30]);
    });
});

describe("applyEvent - seat presence", () => {
    test("marks a seat the live session hands to an AI player as held for its human until the human returns", () => {
        const [awayError, away] = parseServerMessage({ r: 0, s: 3, type: "seat_control" });
        const [backError, back] = parseServerMessage({ s: 3, type: "seat_control" });
        assert(awayError === null && away.type === "ai_replacement");
        assert(backError === null && back.type === "human_return");

        const left = applyEvent(stateAfterRoundStarted(), away);

        expect(left.players.map((p) => p.aiStandIn)).toEqual([null, null, null, 0]);
        expect(applyEvent(left, back).players.map((p) => p.aiStandIn)).toEqual([
            null,
            null,
            null,
            null,
        ]);
    });
});

describe("applyEvent - game_reconnected", () => {
    test("rebuilds the seat's own hand by its tiles, every other by its count, and claimed river tiles", () => {
        const ownHand = [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40];
        const [error, snapshot] = parseServerMessage({
            ...WIRE_GAME_RECONNECTED,
            mt: ownHand,
            pst: [
                {
                    dsc: [{ ti: 100 }, { rd: true, ti: 33 }],
                    ml: [],
                    ri: true,
                    s: 0,
                    sc: 240,
                    tc: 13,
                },
                { dsc: [], ml: [17_409], ri: false, s: 1, sc: 250, tc: 11 },
                { dsc: [], ml: [], ri: false, s: 2, sc: 250, tc: 13 },
                { dsc: [], ml: [], ri: false, s: 3, sc: 260, tc: 14 },
            ],
            s: 1,
        });
        assert(error === null && snapshot.type === "game_reconnected");
        const next = applyEvent(createInitialTableState(), snapshot);

        expect(next.players.map((p) => [p.name, p.tiles, p.concealedCount])).toEqual([
            ["P1", [], 13],
            ["P2", ownHand, 0],
            ["B1", [], 13],
            ["B2", [], 14],
        ]);
        expect(next.players[0].discards).toEqual([
            { claimed: false, isRiichi: false, isTsumogiri: false, tileId: 100 },
            { claimed: true, isRiichi: true, isTsumogiri: false, tileId: 33 },
        ]);
        expect(next.tilesRemaining).toBe(70);
    });

    test("keeps an added kan's added tile, laid stacked on its called tile", () => {
        const addedKanOf1p = 22_457;
        const [error, snapshot] = parseServerMessage({
            ...WIRE_GAME_RECONNECTED,
            pst: [0, 1, 2, 3].map((seat) => ({
                dsc: [],
                ml: seat === 1 ? [addedKanOf1p] : [],
                ri: false,
                s: seat,
                sc: 250,
                tc: seat === 1 ? 10 : 13,
            })),
        });
        assert(error === null && snapshot.type === "game_reconnected");
        const [kan] = applyEvent(createInitialTableState(), snapshot).players[1].melds;

        expect(kan).toMatchObject({ addedTileId: 39, calledTileId: 38, meldType: "added_kan" });
        expect(meldTiles(kan).map((tile) => tile.kind)).toEqual(["upright", "stacked", "upright"]);
    });

    test("names the round and the first dealer as the snapshot does, never from its history's dealers", () => {
        const history = { ...WIRE_ROUND_RECORD, dl: 2 };
        const [error, later] = parseServerMessage({
            ...WIRE_GAME_RECONNECTED,
            dl: 1,
            fd: 3,
            n: 2,
            rh: [history, history],
            rw: 3,
            w: 1,
        });
        assert(error === null && later.type === "game_reconnected");

        const table = applyEvent(createInitialTableState(), later);

        expect([shownRound(table), table.firstDealerSeat]).toEqual(["South 3", 3]);
    });
});

describe("applyEvent - game_end", () => {
    test("ends the game with each seat's score from the standings", () => {
        const next = applyEvent(stateAfterRoundEnded(), makeGameEndEvent());

        expect(next.phase).toBe("game_ended");
        expect(next.players.map((player) => player.score)).toEqual([
            35_000, 22_000, 22_000, 21_000,
        ]);
    });
});

describe("applyEvent - round_end", () => {
    test("keeps the riichi sticks the server says the result left, never the table's count less those collected", () => {
        const state = { ...stateAfterRoundStarted(), riichiSticks: 2 };
        const next = applyEvent(
            state,
            makeTsumoRoundEnd({ riichiSticks: 1, riichiSticksCollected: 2 }),
        );

        expect(next.riichiSticks).toBe(1);
    });

    test("settles each score from the event's pre-payment score and its change, ending the round", () => {
        const event = makeTsumoRoundEnd({
            scores: { "0": 25_000, "1": 24_000, "2": 25_000, "3": 25_000 },
        });
        const next = applyEvent(stateAfterRoundStarted(), event);

        expect(next.phase).toBe("round_ended");
        expect(next.players.map((player) => player.score)).toEqual([
            35_000, 21_000, 22_000, 21_000,
        ]);
        expect(next.roundEndResult?.scoresBeforePayment).toEqual(event.scores);
    });

    test("takes a tsumo's one winner with its hand, melds, winning tile and the round's score changes", () => {
        const handResult = makeHandResult({
            fu: 30,
            han: 4,
            yaku: [
                { han: 1, yakuId: 0, yakumanCount: 0 },
                { han: 1, yakuId: 120, yakumanCount: 0 },
            ],
        });
        const chi: DecodedMeld = {
            calledTileId: 0,
            callerSeat: 0,
            fromSeat: 3,
            meldType: "chi",
            tileIds: [0, 4, 8],
        };
        const event = makeTsumoRoundEnd({
            handResult,
            melds: [chi],
            winnerSeat: 0,
            winningTile: 52,
        });
        const result = applyEvent(stateAfterRoundStarted(), event).roundEndResult;

        expect(result?.resultType).toBe(ROUND_RESULT_TYPE.TSUMO);
        expect(result?.scoreChanges).toEqual(event.scoreChanges);
        expect(result?.winners).toMatchObject([
            { handResult, melds: [chi], seat: 0, winningTile: 52 },
        ]);
    });

    test("takes a ron's winner and the seat that dealt in", () => {
        const event = makeRonRoundEnd({ loserSeat: 3, winnerSeat: 1, winningTile: 60 });
        const result = applyEvent(stateAfterRoundStarted(), event).roundEndResult;

        expect([result?.resultType, result?.loserSeat]).toEqual([ROUND_RESULT_TYPE.RON, 3]);
        expect(result?.winners).toMatchObject([{ seat: 1, winningTile: 60 }]);
    });

    test("takes a double ron's two winners, each with its own hand, on the one tile the seat that dealt in discarded", () => {
        const result = applyEvent(stateAfterRoundStarted(), makeDoubleRonRoundEnd()).roundEndResult;

        expect([result?.resultType, result?.loserSeat]).toEqual([ROUND_RESULT_TYPE.DOUBLE_RON, 1]);
        expect(result?.winners).toMatchObject([
            { closedTiles: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], seat: 0, winningTile: 52 },
            {
                closedTiles: [26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38],
                seat: 2,
                winningTile: 52,
            },
        ]);
    });

    test.each([
        [ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW, makeExhaustiveDrawRoundEnd()],
        [ROUND_RESULT_TYPE.ABORTIVE_DRAW, makeAbortiveDrawRoundEnd()],
        [ROUND_RESULT_TYPE.NAGASHI_MANGAN, makeNagashiManganRoundEnd()],
    ])("takes a %s with no winner", (resultType, event) => {
        const result = applyEvent(stateAfterRoundStarted(), event).roundEndResult;

        expect([result?.resultType, result?.winners]).toEqual([resultType, []]);
    });
});

describe("applyEvent - game_end result data", () => {
    test("populates gameEndResult with standings and finalScore, the leftover sticks counted by the server", () => {
        const state = { ...stateAfterRoundEnded(), riichiSticks: 3 };
        const event = makeGameEndEvent({
            endCause: GAME_END_CAUSE.TOBI,
            leftoverRiichiBonus: 2000,
            leftoverRiichiSticks: 2,
            winnerSeat: 0,
        });
        const next = applyEvent(state, event);

        expect(next.gameEndResult).toEqual({
            endCause: GAME_END_CAUSE.TOBI,
            leftoverRiichiBonus: 2000,
            leftoverSticks: 2,
            standings: event.standings,
            winnerSeat: 0,
        });
    });
});

describe("applyEvent - result clearing", () => {
    test("round_started clears roundEndResult", () => {
        const state = stateAfterRoundStarted();
        const roundEndState = applyEvent(state, makeTsumoRoundEnd());
        expect(roundEndState.roundEndResult).not.toBeNull();

        const nextRoundState = applyEvent(roundEndState, makeRoundStartedEvent());
        expect(nextRoundState.roundEndResult).toBeNull();
    });

    test("game_end keeps the last round's result beside the standings", () => {
        const state = stateAfterRoundStarted();
        const roundEndState = applyEvent(state, makeTsumoRoundEnd());

        const gameEndState = applyEvent(roundEndState, makeGameEndEvent());
        expect(gameEndState.roundEndResult).toBe(roundEndState.roundEndResult);
        expect(gameEndState.gameEndResult).not.toBeNull();
    });
});

function buildFullEventSequence(): ReplayEvent[] {
    return [
        makeGameStartedEvent(),
        makeRoundStartedEvent({
            players: [
                { score: 25_000, seat: 0, tiles: [0, 4, 5, 6, 7, 8, 9, 10, 11, 53, 54, 55, 56] },
                {
                    score: 25_000,
                    seat: 1,
                    tiles: [1, 2, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 57],
                },
                {
                    score: 25_000,
                    seat: 2,
                    tiles: [26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38],
                },
                {
                    score: 25_000,
                    seat: 3,
                    tiles: [39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51],
                },
            ],
        }),
        makeDrawEvent({ seat: 0, tileId: 52 }),
        makeDiscardEvent({ seat: 0, tileId: 0 }),
        makeMeldEvent({
            calledTileId: 0,
            callerSeat: 1,
            fromSeat: 0,
            meldType: "pon",
            tileIds: [1, 2, 0],
        }),
        makeDiscardEvent({ seat: 1, tileId: 16 }),
        makeDrawEvent({ seat: 2, tileId: 58 }),
        makeRiichiDeclaredEvent({ seat: 2 }),
        makeDiscardEvent({ isRiichi: true, seat: 2, tileId: 26 }),
        makeDoraRevealedEvent({ tileId: 60 }),
        makeTsumoRoundEnd({
            closedTiles: [4, 5, 6, 7, 8, 9, 10, 11, 53, 54, 55, 56, 52],
            winnerSeat: 0,
            winningTile: 52,
        }),
        makeGameEndEvent(),
    ];
}

describe("applyEvent - timeline", () => {
    test("keeps every earlier state of the timeline as it was when each later event applies", () => {
        const states: TableState[] = [createInitialTableState()];
        const takenWhenMade: TableState[] = [structuredClone(states[0])];
        for (const event of buildFullEventSequence()) {
            const next = applyEvent(states[states.length - 1], event);
            states.push(next);
            takenWhenMade.push(structuredClone(next));
        }

        expect(states).toEqual(takenWhenMade);
    });
});
