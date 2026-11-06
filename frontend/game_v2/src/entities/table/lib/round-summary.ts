import {
    type DrawResult,
    type PlayerState,
    type RoundEndResult,
    type WinnerResult,
} from "@/entities/table/model/types";
import { type MessageKey, formatList, t } from "@/shared/i18n";
import { ROUND_RESULT_TYPE } from "@/shared/protocol";

import { drawName } from "./draw-name";
import { formatPoints } from "./round-end-display";

type NameOf = (seat: number) => string;

type LoserRole = "none" | "dealt_in" | "kan_robbed";

const RON_KEYS: Readonly<Record<LoserRole, MessageKey>> = {
    dealt_in: "replay.outcome.ron_from",
    kan_robbed: "replay.outcome.ron_robbed",
    none: "replay.outcome.ron",
};

const DOUBLE_RON_KEYS: Readonly<Record<LoserRole, MessageKey>> = {
    dealt_in: "replay.outcome.double_ron",
    kan_robbed: "replay.outcome.double_ron_robbed",
    none: "replay.outcome.double_ron_no_loser",
};

function nameOf(players: readonly PlayerState[]): NameOf {
    return (seat) =>
        players.find((player) => player.seat === seat)?.name ??
        t("game.seat.fallback_name", { seat });
}

function winnerPoints(winner: WinnerResult, name: NameOf): string {
    const points = formatPoints(winner.handResult.points);
    const honba = formatPoints(winner.honbaBonus);
    const hasHonba = winner.honbaBonus > 0;
    if (winner.pao === null) {
        return hasHonba ? t("replay.outcome.points_honba", { honba, points }) : points;
    }
    const pao = name(winner.pao.seat);
    return hasHonba
        ? t("replay.outcome.points_honba_pao", { honba, pao, points })
        : t("replay.outcome.points_pao", { pao, points });
}

function seatList(seats: readonly number[], name: NameOf): string {
    return formatList(seats.map(name));
}

function drawSummary(draw: DrawResult, name: NameOf): string {
    const title = drawName(draw.kind);
    switch (draw.kind) {
        case "exhaustive": {
            if (draw.tenpaiSeats.length === 0) {
                return t("replay.outcome.all_noten", { draw: title });
            }
            return t("replay.outcome.tenpai", {
                draw: title,
                players: seatList(draw.tenpaiSeats, name),
            });
        }
        case "nagashi_mangan": {
            return t("replay.outcome.draw_seats", {
                draw: title,
                players: seatList(draw.nagashiSeats, name),
            });
        }
        case "nine_terminals": {
            return draw.declarerSeat === null
                ? title
                : t("replay.outcome.draw_seats", { draw: title, players: name(draw.declarerSeat) });
        }
        case "triple_ron": {
            return t("replay.outcome.draw_seats", {
                draw: title,
                players: seatList(draw.ronSeats, name),
            });
        }
        default: {
            return title;
        }
    }
}

function loserRole(result: RoundEndResult): LoserRole {
    if (result.loserSeat === null) {
        return "none";
    }
    return result.kanRobbed ? "kan_robbed" : "dealt_in";
}

function loserParams(result: RoundEndResult, name: NameOf): Readonly<Record<string, string>> {
    return result.loserSeat === null ? {} : { loser: name(result.loserSeat) };
}

function doubleRonSummary(result: RoundEndResult, name: NameOf): string {
    const wins = result.winners.map((winner) =>
        t("replay.outcome.win", { name: name(winner.seat), points: winnerPoints(winner, name) }),
    );
    return t(DOUBLE_RON_KEYS[loserRole(result)], {
        ...loserParams(result, name),
        wins: wins.join(t("replay.outcome.win_separator")),
    });
}

function winSummary(result: RoundEndResult, name: NameOf): string {
    if (result.winners.length > 1) {
        return doubleRonSummary(result, name);
    }
    const [first] = result.winners;
    const params = { points: winnerPoints(first, name), winner: name(first.seat) };
    if (result.resultType === ROUND_RESULT_TYPE.TSUMO) {
        return t("replay.outcome.tsumo", params);
    }
    return t(RON_KEYS[loserRole(result)], { ...params, ...loserParams(result, name) });
}

export function roundResultSummary(
    result: RoundEndResult | null,
    players: readonly PlayerState[],
): string {
    if (result === null) {
        return t("replay.outcome.no_result");
    }
    const name = nameOf(players);
    return result.draw === null ? winSummary(result, name) : drawSummary(result.draw, name);
}
