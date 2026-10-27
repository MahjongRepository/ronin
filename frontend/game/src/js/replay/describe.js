import { DIR } from "../ronin/mianzi.js";
import { ABORTIVE_NAMES, DRAW_NAMES, GENERIC_ABORTIVE_NAME } from "../ronin/results.js";
import { POSITION, kindOf, seatOfL } from "./paipu.js";

const SEATS = 4;

const WIND_NAMES = Object.freeze(["東", "南", "西", "北"]);
const ROUND_NUMERALS = Object.freeze(["一", "二", "三", "四"]);
const SUIT_NAMES = Object.freeze({ m: "萬", p: "筒", s: "索" });
const HONOR_NAMES = Object.freeze(["", "東", "南", "西", "北", "白", "發", "中"]);

/** Each draw's name in English, beside the board's Japanese one. */
const DRAW_TEXT = Object.freeze({
    [DRAW_NAMES.EXHAUSTIVE]: "Exhaustive draw",
    [DRAW_NAMES.NAGASHI]: "Nagashi mangan",
    [ABORTIVE_NAMES.nine_terminals]: "Nine terminals",
    [ABORTIVE_NAMES.four_riichi]: "Four riichi",
    [ABORTIVE_NAMES.triple_ron]: "Triple ron",
    [ABORTIVE_NAMES.four_kans]: "Four kans",
    [ABORTIVE_NAMES.four_winds]: "Four winds",
    [GENERIC_ABORTIVE_NAME]: "Abortive draw",
});

/** Japanese text in a line of English: the reader marks it `lang="ja"`. */
function ja(text) {
    return { ja: text };
}

/** A round as the board names it: 東四局 1本場. */
export function roundName(round) {
    const { zhuangfeng, jushu } = round.log[0].qipai;
    return `${WIND_NAMES[zhuangfeng]}${ROUND_NUMERALS[jushu]}局 ${round.honba}本場`;
}

/** A paipu tile in the board's Japanese: 5萬, 赤5筒, 中. */
function tileName(p) {
    const suit = p[0];
    const number = Number(p[1]);
    if (suit === "z") {
        return ja(HONOR_NAMES[number]);
    }
    return ja(number === 0 ? `赤5${SUIT_NAMES[suit]}` : `${number}${SUIT_NAMES[suit]}`);
}

function points(defen) {
    return defen.toLocaleString("en");
}

/** A call on a discard by its meld's numbers (a red five counts as a five): an open kan, a pon or a chi. */
function callName(numbers) {
    if (numbers.length === 4) {
        return "open kan";
    }
    return new Set(numbers).size === 1 ? "pon" : "chi";
}

/** What a call did, from its meld string: who called which tile from whom, or which kan a seat declared alone. */
function callParts(kind, { l, m }, nameOf) {
    const called = m.match(/(\d)([+=-])/);
    const tile = tileName(m[0] + (called?.[1] ?? m[1]));
    if (called === null) {
        return [`${nameOf(l)}: closed kan `, tile];
    }
    if (kind === "gang") {
        return [`${nameOf(l)}: added kan `, tile];
    }
    const numbers = m.match(/\d/g).map((digit) => (digit === "0" ? "5" : digit));
    const giver = nameOf((l + DIR.indexOf(called[2])) % SEATS);
    return [`${nameOf(l)}: ${callName(numbers)} `, tile, ` ← ${giver}`];
}

function discardParts({ l, p }, nameOf) {
    const riichi = p.includes("*") ? "riichi, " : "";
    const discard = p.includes("_") ? "tsumogiri" : "discards";
    return [`${nameOf(l)}: ${riichi}${discard} `, tileName(p)];
}

function resultParts(message, nameOf) {
    if ("pingju" in message) {
        const { name } = message.pingju;
        return [`${DRAW_TEXT[name] ?? "Draw"} (`, ja(name), ")"];
    }
    const { l, baojia, defen } = message.hule;
    if (baojia === null) {
        return [`${nameOf(l)}: tsumo ${points(defen)}`];
    }
    return [`${nameOf(l)}: ron ${points(defen)} ← ${nameOf(baojia)}`];
}

function messageParts(message, nameOf) {
    const kind = kindOf(message);
    const body = message[kind];
    switch (kind) {
        case "zimo":
            return [`${nameOf(body.l)}: draws `, tileName(body.p)];
        case "gangzimo":
            return [`${nameOf(body.l)}: draws `, tileName(body.p), " from the dead wall"];
        case "dapai":
            return discardParts(body, nameOf);
        case "fulou":
        case "gang":
            return callParts(kind, body, nameOf);
        default:
            return resultParts(message, nameOf);
    }
}

/**
 * The last action of the position the viewer `state` stands at, as English strings and `{ ja }` Japanese parts:
 * "Alice: riichi, discards 中", "Charlie: pon 中 ← Alice". A result names the win its dialog shows (a double ron's page);
 * the standings, and silent records at a truncated end, name nothing.
 */
export function lastAction(replay, { round: roundIndex, step, page }) {
    const round = replay.rounds[roundIndex];
    const position = round.positions[step];
    const nameOf = (l) => replay.players[seatOfL(l, round.dealer)];
    switch (position.kind) {
        case POSITION.SUMMARY:
        case POSITION.SILENT:
            return [];
        case POSITION.DEAL:
            return [`${nameOf(0)} deals`];
        case POSITION.RESULT:
            return resultParts(round.log[position.end - 1 + page], nameOf);
        default:
            return messageParts(round.log[position.end - 1], nameOf);
    }
}
