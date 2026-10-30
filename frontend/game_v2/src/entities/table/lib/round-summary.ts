import {
    type DrawResult,
    type PlayerState,
    type RoundEndResult,
    type WinnerResult,
} from "@/entities/table/model/types";
import { ROUND_RESULT_TYPE } from "@/shared/protocol";

import { drawName } from "./draw-name";
import { formatPoints } from "./round-end-display";

type NameOf = (seat: number) => string;

function nameOf(players: readonly PlayerState[]): NameOf {
    return (seat) => players.find((player) => player.seat === seat)?.name ?? `Seat ${seat}`;
}

function winnerPoints(winner: WinnerResult, name: NameOf): string {
    const honba = winner.honbaBonus > 0 ? ` (+${formatPoints(winner.honbaBonus)} honba)` : "";
    const pao = winner.paoSeat === null ? "" : `, pao ${name(winner.paoSeat)}`;
    return `${formatPoints(winner.handResult.points)}${honba}${pao}`;
}

function seatList(seats: readonly number[], name: NameOf): string {
    return seats.map(name).join(", ");
}

function drawSummary(draw: DrawResult, name: NameOf): string {
    const title = drawName(draw.kind);
    switch (draw.kind) {
        case "exhaustive": {
            if (draw.tenpaiSeats.length === 0) {
                return `${title}: all noten`;
            }
            return `${title}: tenpai ${seatList(draw.tenpaiSeats, name)}`;
        }
        case "nagashi_mangan": {
            return `${title}: ${seatList(draw.nagashiSeats, name)}`;
        }
        case "nine_terminals": {
            return draw.declarerSeat === null ? title : `${title}: ${name(draw.declarerSeat)}`;
        }
        case "triple_ron": {
            return `${title}: ${seatList(draw.ronSeats, name)}`;
        }
        default: {
            return title;
        }
    }
}

function loserPhrase(result: RoundEndResult, name: NameOf): string {
    if (result.loserSeat === null) {
        return "";
    }
    return result.kanRobbed
        ? ` robbing ${name(result.loserSeat)}'s kan`
        : ` from ${name(result.loserSeat)}`;
}

function winSummary(result: RoundEndResult, name: NameOf): string {
    const [first] = result.winners;
    const from = loserPhrase(result, name);
    if (result.winners.length > 1) {
        const wins = result.winners.map(
            (winner) => `${name(winner.seat)} ${winnerPoints(winner, name)}`,
        );
        return `Double ron${from}: ${wins.join("; ")}`;
    }
    const kind = result.resultType === ROUND_RESULT_TYPE.TSUMO ? "Tsumo" : "Ron";
    return `${kind} by ${name(first.seat)}${from}: ${winnerPoints(first, name)}`;
}

/**
 * A round's result in a line, with the points of each win (the hand's value, then its honba bonus): "Ron by Charlie
 * from Alice: 3,900 (+300 honba)", "Exhaustive draw: tenpai Alice, Bob". A round the recording stops before says so.
 */
export function roundResultSummary(
    result: RoundEndResult | null,
    players: readonly PlayerState[],
): string {
    if (result === null) {
        return "No result recorded";
    }
    const name = nameOf(players);
    return result.draw === null ? winSummary(result, name) : drawSummary(result.draw, name);
}
