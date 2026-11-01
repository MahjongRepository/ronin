import { assert, describe, expect, test } from "vitest";

import { type EngineReplay, loadEngineReplay } from "#tests/fixtures/replays";
import {
    type RoundEndResult,
    type TableState,
    extractRoundEndResult,
    roundEndPages,
} from "@/entities/table";
import { HAND_LIMIT, ROUND_RESULT_TYPE, type RoundEndEvent } from "@/shared/protocol";

interface RoundEnd {
    readonly event: RoundEndEvent;
    readonly before: TableState;
    readonly after: TableState;
    readonly result: RoundEndResult;
}

function roundEnds({ events, tables }: EngineReplay): RoundEnd[] {
    return events.flatMap((event, index) => {
        const result = tables[index + 1].roundEndResult;
        if (event?.type !== "round_end" || result === null) {
            return [];
        }
        return [{ after: tables[index + 1], before: tables[index], event, result }];
    });
}

function lastRoundEnd(name: string): RoundEnd {
    const end = roundEnds(loadEngineReplay(name)).at(-1);
    assert(end !== undefined, `${name} has no round end`);
    return end;
}

describe("extractRoundEndResult", () => {
    test("riichi tsumo: keeps the hand value, dora kinds, the winner's ura and the sticks it collected", () => {
        const { event, result } = lastRoundEnd("riichi");
        assert(event.resultType === ROUND_RESULT_TYPE.TSUMO);

        expect(result).toMatchObject({
            draw: null,
            headBumpedSeats: [],
            loserSeat: null,
            scoreChanges: event.scoreChanges,
            scoresBeforePayment: event.scores,
        });
        expect(result.winners).toEqual([
            {
                closedTiles: event.closedTiles,
                doraHan: { aka: 1, dora: 0, ura: 1 },
                handResult: event.handResult,
                honbaBonus: 0,
                melds: [],
                pao: null,
                riichiBonus: 2000,
                riichiSticksCollected: 2,
                scoreChanges: event.scoreChanges,
                seat: 1,
                uraDoraIndicators: event.uraDoraIndicators,
                winningTile: event.winningTile,
            },
        ]);
        expect(result.winners[0].handResult.points).toBe(8000);
    });

    test("riichi tsumo at a 1,500 stick value: the sticks pay 3,000 and the honba bonus is the server's, never the gain less the hand and sticks", () => {
        const { before, event } = lastRoundEnd("riichi");
        assert(event.resultType === ROUND_RESULT_TYPE.TSUMO);
        const onHonba = { ...event, honbaBonus: 300 };

        const { winners } = extractRoundEndResult(onHonba, { ...before, riichiStickValue: 1500 });
        expect(winners.map((entry) => [entry.honbaBonus, entry.riichiBonus])).toEqual([
            [300, 3000],
        ]);
    });

    test("double ron: a page per winner with its own payments and ura; the table settles the aggregate once", () => {
        const { after, before, event, result } = lastRoundEnd("double_ron");
        assert(event.resultType === ROUND_RESULT_TYPE.DOUBLE_RON);

        expect(roundEndPages(result).map((page) => page.kind)).toEqual(["win", "win"]);
        expect(
            result.winners.map((winner) => [
                winner.seat,
                winner.scoreChanges,
                winner.uraDoraIndicators,
                winner.riichiSticksCollected,
                winner.handResult.points,
            ]),
        ).toEqual(
            event.winners.map((winner) => [
                winner.winnerSeat,
                winner.scoreChanges,
                winner.uraDoraIndicators,
                winner.riichiSticksCollected,
                winner.handResult.points,
            ]),
        );
        expect(result).toMatchObject({ loserSeat: 0, scoreChanges: event.scoreChanges });
        expect(before.players.map((player) => player.score)).toEqual([
            25_000, 24_000, 24_000, 25_000,
        ]);
        expect(after.players.map((player) => player.score)).toEqual([5000, 38_000, 32_000, 25_000]);
    });

    test("double ron on honba: each winner collects its own honba bonus beyond its hand value", () => {
        const doubleRon = roundEnds(loadEngineReplay("double_ron_on_honba")).find(
            (end) => end.event.resultType === ROUND_RESULT_TYPE.DOUBLE_RON,
        );

        expect(doubleRon?.before.honbaSticks).toBe(2);
        expect(
            doubleRon?.result.winners.map((winner) => [
                winner.seat,
                winner.handResult.points,
                winner.honbaBonus,
            ]),
        ).toEqual([
            [1, 1600, 600],
            [3, 1600, 600],
        ]);
    });

    test("pao: names the seat liable for the yakuman with what it pays and keeps the winner's melds", () => {
        const { event, result } = lastRoundEnd("pao");
        assert(event.resultType === ROUND_RESULT_TYPE.TSUMO);

        expect(result.winners).toMatchObject([
            {
                melds: event.melds,
                pao: { paysHonba: false, seat: 0, share: "all", yakuIds: [103] },
                seat: 1,
            },
        ]);
        expect(result.winners[0].melds).toHaveLength(3);
    });

    test("head bump: keeps the ron callers the head bump passed over", () => {
        const { result } = lastRoundEnd("head_bump");

        expect(result).toMatchObject({ headBumpedSeats: [2], loserSeat: 0 });
        expect(result.winners.map((winner) => winner.seat)).toEqual([1]);
    });

    test("kazoe: the round's dealer and the hand's limit are the server's", () => {
        const { result } = lastRoundEnd("kazoe");

        expect(result.dealerSeat).toBe(0);
        expect(
            result.winners.map((winner) => [
                winner.seat,
                winner.handResult.limit,
                winner.handResult.yakumanCount,
            ]),
        ).toEqual([[0, HAND_LIMIT.KAZOE_YAKUMAN, 1]]);
    });

    test("exhaustive draw: one page naming tenpai and noten seats with the tenpai hands", () => {
        const { event, result } = lastRoundEnd("exhaustive_tenpai");
        assert(event.resultType === ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW);

        expect(result.winners).toEqual([]);
        expect(roundEndPages(result)).toEqual([{ draw: result.draw, kind: "draw" }]);
        expect(result.draw).toEqual({
            declarerSeat: null,
            kind: "exhaustive",
            nagashiRivers: [],
            nagashiSeats: [],
            notenSeats: [0, 3],
            ronSeats: [],
            tenpaiHands: event.tenpaiHands,
            tenpaiSeats: [1, 2],
        });
    });

    test("nagashi mangan: names the qualifying seat beside the tenpai seats", () => {
        const { result } = lastRoundEnd("nagashi");

        expect(result.draw).toMatchObject({
            kind: "nagashi_mangan",
            nagashiSeats: [1],
            notenSeats: [0, 1, 2],
            tenpaiSeats: [3],
        });
    });

    test.each([
        ["kyuushu", { declarerSeat: 1, kind: "nine_terminals", ronSeats: [] }],
        ["triple_ron", { declarerSeat: null, kind: "triple_ron", ronSeats: [1, 2, 3] }],
        ["four_riichi", { declarerSeat: null, kind: "four_riichi", ronSeats: [] }],
        ["four_winds_riichi", { declarerSeat: null, kind: "four_winds", ronSeats: [] }],
        ["four_kans", { declarerSeat: null, kind: "four_kans", ronSeats: [] }],
    ])("abortive draw %s: keeps its kind and the seats it names", (name, draw) => {
        const { result } = lastRoundEnd(name);

        expect(result.draw).toMatchObject({ ...draw, tenpaiHands: [], tenpaiSeats: [] });
    });
});
