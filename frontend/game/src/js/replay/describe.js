import { formatNumber, locale, t, tileVisible } from "../../i18n/index.js";
import { DIR } from "../ronin/mianzi.js";
import { seatL, seatOfL } from "../ronin/results.js";
import { drawName, roundWithHonba, windName } from "../ronin/terms.js";
import wire from "../ronin/wire.js";
import { NOTE, POSITION, kindOf } from "./paipu.js";
import { OUTCOME } from "./round-end.js";
import { SEATS } from "./seats.js";

/** What the strip and the round list say where the replay stops before the game's end. */
export function cutOffText() {
    return t("replay.cut_off");
}

/** Why an AI player replaced a seat's human, as an AI replacement note says it, by catalog key. */
const REASON_KEYS = Object.freeze({
    [wire.SEAT_CONTROL_REASON.LEFT]: "replay.note.reason_left",
    [wire.SEAT_CONTROL_REASON.ABSENT]: "replay.note.reason_absent",
});

/** A call on a discard by its meld's numbers (a red five counts as a five), as its narration's key. */
const CALL_KEYS = Object.freeze({
    openKan: "replay.action.open_kan",
    pon: "replay.action.pon",
    chi: "replay.action.chi",
});

/** Japanese text in a line of another language: the reader marks it `lang="ja"`. */
function ja(text) {
    return { ja: text };
}

/** A round as the board names it, with its honba: 東四局 1本場, East 4, 1 honba. */
export function roundName(round) {
    const { zhuangfeng, jushu } = round.log[0].qipai;
    return roundWithHonba(zhuangfeng, jushu, round.honba);
}

/** A seat as the viewpoint picker names it in a round: its wind there (East marks the dealer) and its player. */
export function seatName(round, seat, player) {
    return t("replay.seat_option", { wind: windName(seatL(seat, round.dealer)), player });
}

/** A paipu tile, its marks (tsumogiri, riichi, called) dropped, by its visible name: 5萬, red 5p, Chun. */
function tileName(p) {
    return tileVisible(p.slice(0, 2));
}

function namesText(names) {
    return names.join(t("list.separator"));
}

function callKey(numbers) {
    if (numbers.length === 4) {
        return CALL_KEYS.openKan;
    }
    return new Set(numbers).size === 1 ? CALL_KEYS.pon : CALL_KEYS.chi;
}

/** What a call did, from its meld string: who called which tile from whom, or which kan a seat declared alone. */
function callText(kind, { l, m }, nameOf) {
    const called = m.match(/(\d)([+=-])/);
    const tile = tileName(m[0] + (called?.[1] ?? m[1]));
    const player = nameOf(l);
    if (called === null) {
        return t("replay.action.closed_kan", { player, tile });
    }
    if (kind === "gang") {
        return t("replay.action.added_kan", { player, tile });
    }
    const numbers = m.match(/\d/g).map((digit) => (digit === "0" ? "5" : digit));
    const giver = nameOf((l + DIR.indexOf(called[2])) % SEATS);
    return t(callKey(numbers), { player, tile, giver });
}

function discardText({ l, p }, nameOf) {
    const riichi = p.includes("*");
    const tsumogiri = p.includes("_");
    const key = riichi
        ? tsumogiri
            ? "replay.action.riichi_tsumogiri"
            : "replay.action.riichi_discards"
        : tsumogiri
          ? "replay.action.tsumogiri"
          : "replay.action.discards";
    return t(key, { player: nameOf(l), tile: tileName(p) });
}

function honbaText(honba) {
    return honba > 0 ? t("replay.outcome.honba", { points: honba }) : null;
}

function paoText(winner, nameOfSeat) {
    return winner.liable === null
        ? null
        : t("replay.outcome.pao", { player: nameOfSeat(winner.liable) });
}

/** Text pieces joined by spaces, the absent ones left out. */
function joined(...pieces) {
    return pieces.filter((piece) => piece !== null).join(" ");
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
    return high === undefined
        ? t("replay.outcome.split_all", { points: low })
        : `(${formatNumber(low)}/${formatNumber(high)})`;
}

function tsumoText(winner, nameOfSeat) {
    const { honba, payers } = winPayments(winner);
    const split = winner.liable === null ? tsumoSplit(payers, honba) : null;
    const main = t("replay.outcome.tsumo", {
        winner: nameOfSeat(winner.seat),
        points: winner.points,
    });
    return joined(main, split, honbaText(honba), paoText(winner, nameOfSeat));
}

function ronValue(winner, nameOfSeat) {
    return joined(formatNumber(winner.points), paoText(winner, nameOfSeat));
}

/** A double ron, with which of its wins the dialog shows when one does: "Double ron 1/2 from Bob: …". */
function doubleRonText(outcome, nameOfSeat, shownWin) {
    const wins = namesText(
        outcome.winners.map((each) => `${nameOfSeat(each.seat)} ${ronValue(each, nameOfSeat)}`),
    );
    const honba = outcome.winners.reduce((sum, each) => sum + winPayments(each).honba, 0);
    const loser = nameOfSeat(outcome.loser);
    const main =
        shownWin === null
            ? t("replay.outcome.double_ron", { loser, wins })
            : t("replay.outcome.double_ron_page", {
                  number: shownWin + 1,
                  total: outcome.winners.length,
                  loser,
                  wins,
              });
    return joined(main, honbaText(honba));
}

function winText(outcome, nameOfSeat, shownWin) {
    const [winner] = outcome.winners;
    switch (outcome.kind) {
        case OUTCOME.TSUMO:
            return tsumoText(winner, nameOfSeat);
        case OUTCOME.RON: {
            const main = t("replay.outcome.ron", {
                winner: nameOfSeat(winner.seat),
                loser: nameOfSeat(outcome.loser),
                points: ronValue(winner, nameOfSeat),
            });
            return joined(main, honbaText(winPayments(winner).honba));
        }
        case OUTCOME.DOUBLE_RON:
            return doubleRonText(outcome, nameOfSeat, shownWin);
        default:
            throw new Error(`no win outcome ${outcome.kind}`);
    }
}

/** A draw by its name and the seats it names: the tenpai seats of an exhaustive draw, the nagashi players, a declarer. */
function drawText(outcome, nameOfSeat) {
    const draw = drawName(outcome.code);
    const names = (seats) => namesText(seats.map(nameOfSeat));
    switch (outcome.kind) {
        case OUTCOME.EXHAUSTIVE:
            if (outcome.tenpai.length === 0) {
                return t("replay.outcome.all_noten", { draw });
            }
            return outcome.tenpai.length === SEATS
                ? t("replay.outcome.all_tenpai", { draw })
                : t("replay.outcome.tenpai", { draw, players: names(outcome.tenpai) });
        case OUTCOME.NAGASHI:
            return `${draw}: ${names(outcome.players)}`;
        case OUTCOME.ABORT:
            return outcome.declarer === null ? draw : `${draw}: ${nameOfSeat(outcome.declarer)}`;
        default:
            throw new Error(`no draw outcome ${outcome.kind}`);
    }
}

/** A draw's text, its Japanese name after it, marked as such, when the page is in another language. */
function drawParts(outcome, nameOfSeat) {
    const text = drawText(outcome, nameOfSeat);
    return locale() === "ja" ? [text] : [`${text} (`, ja(outcome.name), ")"];
}

/**
 * How a round ended, as the round list and the strip's result line say it, its key facts first: "Tsumo: Diana 8,000
 * (2,000/4,000)", "Tsumo: Bob 12,000 (4,000 all)", "Ron: Charlie from Alice 1,300", "Double ron from Bob: Alice 1,600,
 * Diana 1,600", with "(+300 honba)" when the payers paid honba on top (a double ron's both wins' together); a draw by
 * its name and the seats it names, then, outside Japanese, its Japanese name. A pao tsumo shows only its total, "(pao:
 * Diana pays)" in place of the split, since the liable seat pays what the others would. A round the replay cuts off says
 * so. shownWin, the index of the win a result dialog shows, numbers a double ron's label: "Double ron 1/2 from Bob: …".
 */
export function outcomeParts(replay, round, shownWin = null) {
    const { outcome } = round;
    const nameOfSeat = (seat) => replay.players[seat];
    if (outcome === null) {
        return [cutOffText()];
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
function drawnTileText(body, nameOf, tileShown, deadWall) {
    const player = nameOf(body.l);
    if (!tileShown(body.l)) {
        return t(deadWall ? "replay.action.draws_dead_wall" : "replay.action.draws", { player });
    }
    const tile = tileName(body.p);
    return t(deadWall ? "replay.action.draws_tile_dead_wall" : "replay.action.draws_tile", {
        player,
        tile,
    });
}

function messageText(message, nameOf, tileShown) {
    const kind = kindOf(message);
    const body = message[kind];
    switch (kind) {
        case "zimo":
            return drawnTileText(body, nameOf, tileShown, false);
        case "gangzimo":
            return drawnTileText(body, nameOf, tileShown, true);
        case "dapai":
            return discardText(body, nameOf);
        case "fulou":
        case "gang":
            return callText(kind, body, nameOf);
        default:
            throw new Error(`no action line for a ${kind} message`);
    }
}

/** Between the action and each note: a no-break space before the dot keeps it off the start of a line. */
const NOTE_SEPARATOR = " · ";

/** What a note says of the seat it names: "AI plays for Bob (absent)", "AI plays for Diana (left)", "Bob returns". */
function noteText(note, players) {
    const player = players[note.seat];
    switch (note.kind) {
        case NOTE.AI_REPLACEMENT:
            return t("replay.note.ai", { player, reason: t(REASON_KEYS[note.reason]) });
        case NOTE.HUMAN_RETURN:
            return t("replay.note.returns", { player });
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
            return [t("replay.final_standings")];
        case POSITION.SILENT:
            return [];
        case POSITION.DEAL:
            return [t("replay.action.deals", { player: nameOf(0) })];
        case POSITION.RESULT:
            return outcomeParts(replay, round, page);
        default:
            return [messageText(round.log[position.end - 1], nameOf, tileShown)];
    }
}

/**
 * The last action of the position the viewer `state` stands at, as strings and `{ ja }` Japanese parts in the page's
 * locale: "Alice: riichi, discards Chun", "Charlie: pon Chun ← Alice". A result tells the round's outcome (every win of
 * a double ron, numbered by the win the dialog shows: "Double ron 1/2 from …"), the standings say so, and silent records
 * at a truncated end name nothing. With opponents' hands hidden, their draws keep their tiles hidden too. The
 * position's notes of who controls a seat follow, each after a " · ": "Alice deals · Bob returns · AI plays for Diana
 * (left)".
 */
export function lastAction(replay, { round: roundIndex, step, page = 0, seat, openHands }) {
    const round = replay.rounds[roundIndex];
    const position = round.positions[step];
    const shown = positionParts(replay, round, position, { page, seat, openHands });
    const notes = position.notes ?? [];
    if (notes.length === 0) {
        return shown;
    }
    const joinedNotes = notes.map((note) => noteText(note, replay.players)).join(NOTE_SEPARATOR);
    return shown.length === 0 ? [joinedNotes] : [...shown, NOTE_SEPARATOR, joinedNotes];
}

/** Parts as DOM nodes: each string a text node, each Japanese part a `lang="ja"` span. */
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
