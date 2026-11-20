import {
    type RoundEndResult,
    type RoundEndTable,
    createInitialPlayerState,
    extractRoundEndResult,
    seatEntry,
} from "@/entities/table";
import { WIRE_KEY, parseRoundEnd } from "@/shared/protocol";

const NAMES = ["Diana", "Alice", "Charlie", "Bob"];

function yaku(yakuId: number, han: number): Readonly<Record<number, number>> {
    return { [WIRE_KEY.YAKU_ID]: yakuId, [WIRE_KEY.HAN]: han, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 };
}

/**
 * A mid-game double ron, hand-written so the story's scores read like a real game's: South 2, Alice dealing, one honba and a riichi stick left
 * from the last hand. Bob deals 4m into Diana (riichi, mangan) and Charlie (closed, 3900); Diana sits closest to Bob, so
 * the honba and both sticks go to her.
 */
const DOUBLE_RON_WIRE = {
    [WIRE_KEY.EVENT_TYPE]: 4,
    [WIRE_KEY.RESULT_TYPE]: 2,
    [WIRE_KEY.RIICHI_STICKS]: 0,
    [WIRE_KEY.DEALER]: 1,
    [WIRE_KEY.DORA_INDICATORS]: [98],
    [WIRE_KEY.LOSER_SEAT]: 3,
    [WIRE_KEY.WINNING_TILE]: 12,
    [WIRE_KEY.WINNERS]: [
        {
            [WIRE_KEY.WINNER_SEAT]: 0,
            [WIRE_KEY.HAND_RESULT]: {
                [WIRE_KEY.HAN]: 5,
                [WIRE_KEY.FU]: 30,
                [WIRE_KEY.YAKU]: [yaku(1, 1), yaku(12, 1), yaku(13, 1), yaku(120, 1), yaku(122, 1)],
                [WIRE_KEY.POINTS]: 80,
                [WIRE_KEY.HAND_LIMIT]: "mangan",
            },
            [WIRE_KEY.SCORE_CHANGES]: { "0": 103, "1": 0, "2": 0, "3": -83 },
            [WIRE_KEY.RIICHI_COLLECTED]: 2,
            [WIRE_KEY.CLOSED_TILES]: [4, 8, 17, 20, 24, 40, 41, 44, 48, 53, 92, 96, 100],
            [WIRE_KEY.MELDS]: [],
            [WIRE_KEY.HONBA_BONUS]: 3,
            [WIRE_KEY.URA_DORA]: [0],
        },
        {
            [WIRE_KEY.WINNER_SEAT]: 2,
            [WIRE_KEY.HAND_RESULT]: {
                [WIRE_KEY.HAN]: 3,
                [WIRE_KEY.FU]: 30,
                [WIRE_KEY.YAKU]: [yaku(12, 1), yaku(13, 1), yaku(120, 1)],
                [WIRE_KEY.POINTS]: 39,
                [WIRE_KEY.HAND_LIMIT]: "none",
            },
            [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 39, "3": -39 },
            [WIRE_KEY.RIICHI_COLLECTED]: 0,
            [WIRE_KEY.CLOSED_TILES]: [18, 22, 42, 45, 49, 51, 54, 57, 80, 81, 93, 97, 101],
            [WIRE_KEY.MELDS]: [],
            [WIRE_KEY.HONBA_BONUS]: 0,
        },
    ],
    [WIRE_KEY.SCORES]: { "0": 240, "1": 314, "2": 183, "3": 243 },
    [WIRE_KEY.SCORE_CHANGES]: { "0": 103, "1": 0, "2": 39, "3": -122 },
};

/** The double ron story's table: South 2 with one honba, its scores and payments a real game's. */
export function realisticDoubleRon(): RoundEndTable {
    const event = parseRoundEnd(DOUBLE_RON_WIRE);
    return {
        firstDealerSeat: 0,
        honbaSticks: 1,
        inStep: true,
        players: NAMES.map((name, seat) =>
            createInitialPlayerState({
                isAiPlayer: false,
                name,
                score: seatEntry(event.scores, seat),
                seat,
            }),
        ),
        result: extractRoundEndResult(event, { riichiStickValue: 1000 }),
        roundInWind: 2,
        roundWind: 1,
    };
}

const MAX_INDICATOR_TILES = [8, 44, 76, 112, 128];

/** The result with five dora and five ura indicators, the most a hand can show: the indicators' worst case. */
export function withMaxIndicators(result: RoundEndResult): RoundEndResult {
    return {
        ...result,
        doraIndicators: MAX_INDICATOR_TILES,
        winners: result.winners.map((winner) => ({
            ...winner,
            uraDoraIndicators: MAX_INDICATOR_TILES.map((tile) => tile + 1),
        })),
    };
}
