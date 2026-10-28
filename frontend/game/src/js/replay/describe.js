import { jushu_name as jushuName } from "../../vendor/majiang-ui/board.js";
import { DIR } from "../ronin/mianzi.js";
import {
    ABORTIVE_NAMES,
    DRAW_NAMES,
    GENERIC_ABORTIVE_NAME,
    seatL,
    seatOfL,
} from "../ronin/results.js";
import wire from "../ronin/wire.js";
import { NOTE, POSITION, kindOf } from "./paipu.js";
import { OUTCOME } from "./round-end.js";
import { SEATS } from "./seats.js";

const SUIT_NAMES = Object.freeze({ m: "萬", p: "筒", s: "索" });
const HONOR_NAMES = Object.freeze(["", "東", "南", "西", "北", "白", "發", "中"]);
const WIND_NAMES = Object.freeze(HONOR_NAMES.slice(1, 5));

/** What the strip and the round list say where the replay stops before the game's end. */
export const CUT_OFF = "Cut off: the server stopped the game";

/** What the strip says at the standings, the position after the game's last result. */
const FINAL_STANDINGS = "Final standings";

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
    return `${jushuName(zhuangfeng, jushu)} ${round.honba}本場`;
}

/** A seat as the viewpoint picker names it in a round: its wind there (東 marks the dealer) and its player. */
export function seatName(round, seat, player) {
    return `${WIND_NAMES[seatL(seat, round.dealer)]} ${player}`;
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

function honbaText(honba) {
    return honba > 0 ? ` (+${points(honba)} honba)` : "";
}

function paoText(winner, nameOfSeat) {
    return winner.liable === null ? "" : ` (pao: ${nameOfSeat(winner.liable)} pays)`;
}

/** A win's hand points and the honba its payers paid on top, which is all they paid beyond the hand. */
function winPayments(winner) {
    const total = winner.paid.reduce((sum, paid) => sum + paid, 0);
    return { honba: total - winner.points, payers: winner.paid.filter((paid) => paid > 0) };
}

/**
 * What a tsumo's payers paid for the hand, without the honba they shared: "(2,000/4,000)" from the non-dealers and the
 * dealer, "(4,000 all)" to a dealer.
 */
function tsumoSplit(payers, honba) {
    const shares = new Set(payers.map((paid) => paid - honba / payers.length));
    const [low, high] = [...shares].sort((a, b) => a - b);
    return high === undefined ? ` (${points(low)} all)` : ` (${points(low)}/${points(high)})`;
}

function tsumoText(winner, nameOfSeat) {
    const { honba, payers } = winPayments(winner);
    const split = winner.liable === null ? tsumoSplit(payers, honba) : "";
    const extras = `${split}${honbaText(honba)}${paoText(winner, nameOfSeat)}`;
    return `Tsumo: ${nameOfSeat(winner.seat)} ${points(winner.points)}${extras}`;
}

function ronValue(winner, nameOfSeat) {
    return `${points(winner.points)}${paoText(winner, nameOfSeat)}`;
}

/** A double ron's label, with which of its wins the dialog shows when one does: "Double ron 1/2". */
function doubleRonLabel(outcome, shownWin) {
    return shownWin === null
        ? "Double ron"
        : `Double ron ${shownWin + 1}/${outcome.winners.length}`;
}

function winText(outcome, nameOfSeat, shownWin) {
    const [winner] = outcome.winners;
    switch (outcome.kind) {
        case OUTCOME.TSUMO:
            return tsumoText(winner, nameOfSeat);
        case OUTCOME.RON: {
            const value = ronValue(winner, nameOfSeat);
            const honba = honbaText(winPayments(winner).honba);
            return `Ron: ${nameOfSeat(winner.seat)} from ${nameOfSeat(outcome.loser)} ${value}${honba}`;
        }
        case OUTCOME.DOUBLE_RON: {
            const winners = outcome.winners.map(
                (each) => `${nameOfSeat(each.seat)} ${ronValue(each, nameOfSeat)}`,
            );
            const honba = outcome.winners.reduce((sum, each) => sum + winPayments(each).honba, 0);
            const label = doubleRonLabel(outcome, shownWin);
            return `${label} from ${nameOfSeat(outcome.loser)}: ${winners.join(", ")}${honbaText(honba)}`;
        }
        default:
            throw new Error(`no win outcome ${outcome.kind}`);
    }
}

/** Who a draw names: the tenpai seats of an exhaustive draw, the nagashi players, a nine-terminals declarer. */
function drawSeatsText(outcome, nameOfSeat) {
    const names = (seats) => seats.map(nameOfSeat).join(", ");
    switch (outcome.kind) {
        case OUTCOME.EXHAUSTIVE:
            if (outcome.tenpai.length === 0) {
                return ": all noten";
            }
            return outcome.tenpai.length === SEATS
                ? ": all tenpai"
                : `: tenpai ${names(outcome.tenpai)}`;
        case OUTCOME.NAGASHI:
            return `: ${names(outcome.players)}`;
        case OUTCOME.ABORT:
            return outcome.declarer === null ? "" : `: ${nameOfSeat(outcome.declarer)}`;
        default:
            throw new Error(`no draw outcome ${outcome.kind}`);
    }
}

/** A draw by its English name and the seats it names first, its Japanese name after them. */
function drawParts(outcome, nameOfSeat) {
    const english = DRAW_TEXT[outcome.name] ?? "Draw";
    return [`${english}${drawSeatsText(outcome, nameOfSeat)} (`, ja(outcome.name), ")"];
}

/**
 * How a round ended, as the round list and the strip's result line say it, its key facts first: "Tsumo: Diana 8,000
 * (2,000/4,000)", "Tsumo: Bob 12,000 (4,000 all)", "Ron: Charlie from Alice 1,300", "Double ron from Bob: Alice 1,600,
 * Diana 1,600", with "(+300 honba)" when the payers paid honba on top (a double ron's both wins' together); a draw by its English name and the seats it
 * names, then its Japanese name. A pao tsumo shows only its total, "(pao: Diana pays)" in place of the split, since the
 * liable seat pays what the others would. A round the replay cuts off says so. shownWin, the index of the win a result
 * dialog shows, numbers a double ron's label: "Double ron 1/2 from Bob: …".
 */
export function outcomeParts(replay, round, shownWin = null) {
    const { outcome } = round;
    const nameOfSeat = (seat) => replay.players[seat];
    if (outcome === null) {
        return [CUT_OFF];
    }
    switch (outcome.kind) {
        case OUTCOME.TSUMO:
        case OUTCOME.RON:
        case OUTCOME.DOUBLE_RON:
            return [winText(outcome, nameOfSeat, shownWin)];
        case OUTCOME.EXHAUSTIVE:
        case OUTCOME.NAGASHI:
        case OUTCOME.ABORT:
            return drawParts(outcome, nameOfSeat);
        default:
            throw new Error(`no outcome ${outcome.kind}`);
    }
}

/** A draw names its tile only where the table shows it: the viewpoint's own, or any while every hand is open. */
function drawnTileParts(body, nameOf, tileShown, from = []) {
    const tile = tileShown(body.l) ? [" ", tileName(body.p)] : [];
    return [`${nameOf(body.l)}: draws`, ...tile, ...from];
}

function messageParts(message, nameOf, tileShown) {
    const kind = kindOf(message);
    const body = message[kind];
    switch (kind) {
        case "zimo":
            return drawnTileParts(body, nameOf, tileShown);
        case "gangzimo":
            return drawnTileParts(body, nameOf, tileShown, [" from the dead wall"]);
        case "dapai":
            return discardParts(body, nameOf);
        case "fulou":
        case "gang":
            return callParts(kind, body, nameOf);
        default:
            throw new Error(`no action line for a ${kind} message`);
    }
}

/** Between the action and each note: a no-break space before the dot keeps it off the start of a line. */
const NOTE_SEPARATOR = "\u00a0· ";

/** Why an AI player replaced a seat's human, as an AI replacement note says it. */
const REASON_TEXT = Object.freeze({
    [wire.SEAT_CONTROL_REASON.LEFT]: "left",
    [wire.SEAT_CONTROL_REASON.ABSENT]: "absent",
});

/** What a note says of the seat it names: "AI plays for Bob (absent)", "AI plays for Diana (left)", "Bob returns". */
function noteText(note, players) {
    const name = players[note.seat];
    switch (note.kind) {
        case NOTE.AI_REPLACEMENT:
            return `AI\u00a0plays for ${name} (${REASON_TEXT[note.reason]})`;
        case NOTE.HUMAN_RETURN:
            return `${name} returns`;
        default:
            throw new Error(`no text for a ${note.kind} note`);
    }
}

/** What the position itself shows, before its notes. */
function positionParts(replay, round, position, { page, seat, openHands }) {
    const nameOf = (l) => replay.players[seatOfL(l, round.dealer)];
    const tileShown = (l) => openHands || seatOfL(l, round.dealer) === seat;
    switch (position.kind) {
        case POSITION.SUMMARY:
            return [FINAL_STANDINGS];
        case POSITION.SILENT:
            return [];
        case POSITION.DEAL:
            return [`${nameOf(0)} deals`];
        case POSITION.RESULT:
            return outcomeParts(replay, round, page);
        default:
            return messageParts(round.log[position.end - 1], nameOf, tileShown);
    }
}

/**
 * The last action of the position the viewer `state` stands at, as English strings and `{ ja }` Japanese parts:
 * "Alice: riichi, discards 中", "Charlie: pon 中 ← Alice". A result tells the round's outcome (every win of a double
 * ron, numbered by the win the dialog shows: "Double ron 1/2 from …"), the standings say so, and silent records at a
 * truncated end name nothing. With opponents' hands hidden, their draws keep their tiles hidden too. The position's
 * notes of who controls a seat follow, each after a " · ": "Alice deals · Bob returns · AI plays for Diana (left)".
 */
export function lastAction(replay, { round: roundIndex, step, page = 0, seat, openHands }) {
    const round = replay.rounds[roundIndex];
    const position = round.positions[step];
    const shown = positionParts(replay, round, position, { page, seat, openHands });
    const notes = position.notes ?? [];
    if (notes.length === 0) {
        return shown;
    }
    const joined = notes.map((note) => noteText(note, replay.players)).join(NOTE_SEPARATOR);
    return shown.length === 0 ? [joined] : [...shown, NOTE_SEPARATOR, joined];
}

/** Parts as DOM nodes: each English string a text node, each Japanese part a `lang="ja"` span. */
export function actionNodes(parts) {
    return parts.map((part) => {
        if (typeof part === "string") {
            return document.createTextNode(part);
        }
        const span = document.createElement("span");
        span.lang = "ja";
        span.textContent = part.ja;
        return span;
    });
}
