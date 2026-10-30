import {
    type DrawKind,
    type RoundEndResult,
    type RoundOutcome,
    type RoundRecord,
    type TableState,
} from "@/entities/table/model/types";
import { assertNever } from "@/shared/lib";
import {
    type GameReconnectedEvent,
    ROUND_RESULT_TYPE,
    type RoundResultType,
} from "@/shared/protocol";

type HistoryEntry = GameReconnectedEvent["roundHistory"][number];

const TENPAI_JUDGING_DRAWS: ReadonlySet<DrawKind> = new Set(["exhaustive", "nagashi_mangan"]);

function resultOutcome(result: RoundEndResult): RoundOutcome {
    if (result.draw !== null) {
        return result.draw.kind;
    }
    return result.resultType === ROUND_RESULT_TYPE.TSUMO ? "tsumo" : "ron";
}

/** The record of the round a table ends with `result`, read before the result settles it. */
export function roundRecordOfResult(table: TableState, result: RoundEndResult): RoundRecord {
    const outcome = resultOutcome(result);
    const { draw } = result;
    return {
        dealerSeat: table.dealerSeat,
        honba: table.honbaSticks,
        loserSeat: result.loserSeat,
        outcome,
        riichiSeats: table.players.filter((player) => player.isRiichi).map((player) => player.seat),
        scoreChanges: result.scoreChanges,
        tenpaiSeats: draw !== null && TENPAI_JUDGING_DRAWS.has(draw.kind) ? draw.tenpaiSeats : null,
        wind: table.roundWind,
        winnerSeats: result.winners.map((winner) => winner.seat),
    };
}

function historyOutcome(resultType: RoundResultType, entry: HistoryEntry): RoundOutcome {
    switch (resultType) {
        case ROUND_RESULT_TYPE.TSUMO: {
            return "tsumo";
        }
        case ROUND_RESULT_TYPE.RON:
        case ROUND_RESULT_TYPE.DOUBLE_RON: {
            return "ron";
        }
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW: {
            return "exhaustive";
        }
        case ROUND_RESULT_TYPE.NAGASHI_MANGAN: {
            return "nagashi_mangan";
        }
        case ROUND_RESULT_TYPE.ABORTIVE_DRAW: {
            if (entry.abortiveReason === null) {
                throw new Error("An abortive draw in the round history names no reason");
            }
            return entry.abortiveReason;
        }
        default: {
            return assertNever(resultType);
        }
    }
}

/** The record of a round a reconnect's snapshot lists in its history. */
export function roundRecordOfHistory(entry: HistoryEntry): RoundRecord {
    return {
        dealerSeat: entry.dealerSeat,
        honba: entry.honbaSticks,
        loserSeat: entry.loserSeat,
        outcome: historyOutcome(entry.resultType, entry),
        riichiSeats: entry.riichiSeats,
        scoreChanges: entry.scoreChanges,
        tenpaiSeats: entry.tenpaiSeats,
        wind: entry.wind,
        winnerSeats: entry.winnerSeats,
    };
}
