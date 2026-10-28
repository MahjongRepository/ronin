import * as immef from "../ronin/immef.js";
import * as mianzi from "../ronin/mianzi.js";
import {
    fullHandStr,
    jiejuStandings,
    kanMianzi,
    roundInWind,
    roundResults,
    seatL,
    seatOfL,
} from "../ronin/results.js";
import * as tiles from "../ronin/tiles.js";
import wire from "../ronin/wire.js";
import { roundOutcome } from "./round-end.js";
import { SEATS } from "./seats.js";

/**
 * What a position of a round shows: its last visible record, the round's result, the game's final standings after
 * the last round, or only silent records at a truncated end.
 */
export const POSITION = Object.freeze({
    DEAL: "deal",
    DRAW: "draw",
    DISCARD: "discard",
    CALL: "call",
    RESULT: "result",
    SUMMARY: "summary",
    SILENT: "silent",
});

/** A paipu message's kind: zimo, dapai, fulou, hule, … */
export function kindOf(message) {
    return Object.keys(message)[0];
}

/** A replay line the converter cannot read; `line` is its 1-based line in the replay file. */
export class MalformedReplayError extends Error {
    constructor(line, message, options) {
        super(`Malformed replay at line ${line}: ${message}`, options);
        this.name = "MalformedReplayError";
        this.line = line;
    }
}

function dealtPlayer(roundStart, seat) {
    const player = roundStart.p.find((p) => p.s === seat);
    if (player === undefined) {
        throw new Error(`round_started has no player in seat ${seat}`);
    }
    return player;
}

/** The winds whose fourth round is all last (オーラス): the game's last scheduled wind, and its sudden-death extension's. */
const LAST_WINDS = Object.freeze({
    [wire.GAME_TYPE.TONPUSEN]: [0, 1],
    [wire.GAME_TYPE.HANCHAN]: [1, 2],
});

/**
 * Whether the round is all last (オーラス) under the recorded game type: the fourth round of the game's last scheduled
 * wind or of its sudden-death extension. Read from the game type, never from what was played next, so a truncated
 * game's last round is not flagged by accident.
 */
function isFinalRound(gameType, roundStart, qijia) {
    return (
        roundInWind(roundStart.dl, qijia) === SEATS - 1 &&
        LAST_WINDS[gameType].includes(roundStart.w)
    );
}

function dealMessage(roundStart, qijia) {
    const defen = [];
    const shoupai = [];
    for (let l = 0; l < SEATS; l++) {
        const player = dealtPlayer(roundStart, seatOfL(l, roundStart.dl));
        defen[l] = player.sc * wire.SCORE_DIV;
        shoupai[l] = tiles.handStr(player.tl);
    }
    return {
        qipai: {
            zhuangfeng: roundStart.w,
            jushu: roundInWind(roundStart.dl, qijia),
            changbang: roundStart.h,
            lizhibang: roundStart.r,
            defen,
            shoupai,
            baopai: tiles.tileToStr(roundStart.di[0]),
        },
    };
}

function discardTile({ tileId, isTsumogiri, isRiichi }) {
    return tiles.tileToStr(tileId) + (isTsumogiri ? "_" : "") + (isRiichi ? "*" : "");
}

function notesField(notes) {
    return notes.length > 0 ? { notes } : {};
}

/** The tiles a meld takes from its caller's hand: all but the called tile, an added kan's fourth tile alone. */
function tilesFromHand(meld, pon) {
    switch (meld.meldType) {
        case wire.MELD.CLOSED_KAN:
            return meld.tileIds;
        case wire.MELD.ADDED_KAN:
            return meld.tileIds.filter((id) => !pon.tileIds.includes(id));
        default:
            return meld.tileIds.filter((id) => id !== meld.calledTileId);
    }
}

/**
 * What a round's records say of one seat that its round end omits: its concealed tiles, its latest draw, its melds
 * and whether it stands in riichi. The latest draw is read only right after it, when the seat declares kyuushu.
 */
class SeatState {
    constructor(dealtTileIds) {
        this.hand = [...dealtTileIds];
        this.lastDraw = null;
        this.melds = [];
        this.riichi = false;
    }

    draw(tileId) {
        this.hand.push(tileId);
        this.lastDraw = tileId;
    }

    discard(tileId) {
        this.removeFromHand([tileId]);
    }

    /** Lay a meld down; an added kan replaces the pon it extends, which it returns. */
    meld(meld) {
        const pon = meld.meldType === wire.MELD.ADDED_KAN ? this.takePon(meld) : null;
        this.melds.push(meld);
        this.removeFromHand(tilesFromHand(meld, pon));
        return pon;
    }

    declareRiichi() {
        this.riichi = true;
    }

    ponIndex(tile34) {
        return this.melds.findIndex((meld) => mianzi.isPonOf(meld, tile34));
    }

    findPon(tile34) {
        const index = this.ponIndex(tile34);
        return index < 0 ? undefined : this.melds[index];
    }

    takePon(kan) {
        const index = this.ponIndex(Math.floor(kan.tileIds[0] / 4));
        if (index < 0) {
            throw new Error("added kan without its pon");
        }
        return this.melds.splice(index, 1)[0];
    }

    removeFromHand(tileIds) {
        for (const tileId of tileIds) {
            const index = this.hand.indexOf(tileId);
            if (index < 0) {
                throw new Error(`hand does not hold tile ${tileId}`);
            }
            this.hand.splice(index, 1);
        }
    }

    /** The concealed hand right after the seat's latest draw as a shoupai string, that tile last. */
    handAfterDraw() {
        return fullHandStr(this.hand, [], this.lastDraw);
    }
}

/**
 * One round's paipu log and its positions. A position is a run of silent records (they add to the log, or not at
 * all, but show nothing of their own) closed by the next visible one. It holds the messages log[start, end) and,
 * present only when one of its silent records left one, `notes` on what those records say about it. A result position
 * also has `wins`, the count of its hule messages; its range holds only its first win. A double ron's further wins
 * sit at log[end, end + wins - 1), in no position's range: the viewer applies them as the result's dialog pages through
 * them, or before it leaves the position, and the position after it starts past them.
 */
class RoundBuilder {
    constructor(roundStart, qijia, gameType) {
        this.dealer = roundStart.dl;
        this.seats = Array.from(
            { length: SEATS },
            (_, seat) => new SeatState(dealtPlayer(roundStart, seat).tl),
        );
        this.outcome = null;
        this.summary = {
            wind: roundStart.w,
            dealer: roundStart.dl,
            honba: roundStart.h,
            sticks: roundStart.r,
            final: isFinalRound(gameType, roundStart, qijia),
        };
        this.log = [dealMessage(roundStart, qijia)];
        this.positions = [];
        this.nextStart = 0;
        this.pendingSilent = [];
        this.kanSeat = null;
        this.addPosition(POSITION.DEAL);
    }

    l(seat) {
        return seatL(seat, this.dealer);
    }

    takePendingNotes() {
        const notes = this.pendingSilent.filter((note) => note !== null);
        this.pendingSilent = [];
        return notes;
    }

    addPosition(kind, say = [], fields = {}) {
        const notes = this.takePendingNotes();
        const position = { start: this.nextStart, end: this.log.length, kind, say, ...fields };
        this.positions.push({ ...position, ...notesField(notes) });
        this.nextStart = this.log.length;
    }

    addSilent(message, note = null) {
        if (message !== null) {
            this.log.push(message);
        }
        this.pendingSilent.push(note);
    }

    addVisible(kind, message, say) {
        this.log.push(message);
        this.addPosition(kind, say);
    }

    /** A draw right after the drawing seat's own kan is its replacement tile from the dead wall. */
    draw(packed) {
        const { seat, tileId } = immef.decodeDraw(packed);
        const draw = { l: this.l(seat), p: tiles.tileToStr(tileId) };
        const rinshan = this.kanSeat === seat;
        this.kanSeat = null;
        this.seats[seat].draw(tileId);
        this.addVisible(POSITION.DRAW, rinshan ? { gangzimo: draw } : { zimo: draw });
    }

    discard(packed) {
        const discard = immef.decodeDiscard(packed);
        const l = this.l(discard.seat);
        this.kanSeat = null;
        this.seats[discard.seat].discard(discard.tileId);
        const say = discard.isRiichi ? [{ name: mianzi.CALLOUT.RIICHI, l }] : [];
        this.addVisible(POSITION.DISCARD, { dapai: { l, p: discardTile(discard) } }, say);
    }

    meld(compact) {
        const meld = immef.decodeMeldCompact(compact);
        const pon = this.seats[meld.callerSeat].meld(meld);
        this.kanSeat = mianzi.KAN_TYPES.has(meld.meldType) ? meld.callerSeat : null;
        const l = this.l(meld.callerSeat);
        const message = {
            [mianzi.KIND_OF_MELD[meld.meldType]]: { l, m: mianzi.mianziStr(meld, pon) },
        };
        this.addVisible(POSITION.CALL, message, [{ name: mianzi.SAY_OF_MELD[meld.meldType], l }]);
    }

    revealDora(tileId) {
        this.addSilent({ kaigang: { baopai: tiles.tileToStr(tileId) } });
    }

    declareRiichi(seat) {
        this.seats[seat].declareRiichi();
        this.addSilent(null);
    }

    /**
     * A round end closes the round with its result position, which takes in the silent records before it. A robbed
     * kan, which no meld record shows, is first its own position, declared as a call.
     */
    closeAtRoundEnd(roundEnd) {
        if (roundEnd.rk != null) {
            this.declareRobbedKan(roundEnd.rk);
        }
        const { results, callouts } = roundResults(roundEnd, {
            dealer: this.dealer,
            riichi: this.seats.map((seat) => seat.riichi),
            handOf: (seat) => this.seats[seat].handAfterDraw(),
        });
        const [first, ...further] = results;
        this.log.push(first);
        this.addPosition(POSITION.RESULT, callouts, {
            wins: results.filter((message) => "hule" in message).length,
        });
        this.log.push(...further);
        this.nextStart = this.log.length;
        this.outcome = roundOutcome(roundEnd, results);
        return this.build();
    }

    declareRobbedKan(kan) {
        const m = kanMianzi(kan, (seat, tile34) => this.seats[seat].findPon(tile34));
        const l = this.l(kan.s);
        this.addVisible(POSITION.CALL, { gang: { l, m } }, [{ name: mianzi.CALLOUT.KAN, l }]);
    }

    /** A truncated round ends where the replay does; silent records with nothing after them are its last position. */
    closeTruncated() {
        if (this.pendingSilent.length > 0) {
            this.addPosition(POSITION.SILENT);
        }
        return this.build();
    }

    build() {
        return { ...this.summary, log: this.log, positions: this.positions, outcome: this.outcome };
    }
}

class ReplayBuilder {
    constructor(gameStarted) {
        this.players = [];
        this.ai = [];
        for (const player of gameStarted.p) {
            this.players[player.s] = player.nm;
            this.ai[player.s] = Boolean(player.ai);
        }
        this.qijia = gameStarted.dl;
        if (!Object.hasOwn(LAST_WINDS, gameStarted.gt)) {
            throw new Error(`unknown game type ${gameStarted.gt}`);
        }
        this.gameType = gameStarted.gt;
        this.rounds = [];
        this.round = null;
        this.standings = null;
    }

    currentRound() {
        if (this.round === null) {
            throw new Error("round event outside a round");
        }
        return this.round;
    }

    apply(line) {
        switch (line.t) {
            case wire.E.ROUND_STARTED:
                return this.startRound(line);
            case wire.E.DRAW:
                return this.currentRound().draw(line.d);
            case wire.E.DISCARD:
                return this.currentRound().discard(line.d);
            case wire.E.MELD:
                return this.currentRound().meld(line.m);
            case wire.E.DORA_REVEALED:
                return this.currentRound().revealDora(line.ti);
            case wire.E.RIICHI_DECL:
                return this.currentRound().declareRiichi(line.s);
            case wire.E.ROUND_END:
                return this.closeRound(line);
            case wire.E.GAME_END:
                return this.endGame(line);
            default:
                throw new Error(`unknown record type ${line.t}`);
        }
    }

    startRound(roundStart) {
        if (this.round !== null) {
            throw new Error("round started before the previous round ended");
        }
        this.round = new RoundBuilder(roundStart, this.qijia, this.gameType);
    }

    closeRound(roundEnd) {
        this.rounds.push(this.currentRound().closeAtRoundEnd(roundEnd));
        this.round = null;
    }

    /** The final standings, shown as one more position of the last round, after its result. */
    endGame(gameEnd) {
        const last = this.rounds.at(-1);
        if (this.round !== null || last === undefined) {
            throw new Error("game ended outside a round end");
        }
        const end = last.log.length;
        const summary = { start: end, end, kind: POSITION.SUMMARY, say: [] };
        this.rounds[this.rounds.length - 1] = { ...last, positions: [...last.positions, summary] };
        this.standings = jiejuStandings(gameEnd);
    }

    build() {
        if (this.round !== null) {
            this.rounds.push(this.round.closeTruncated());
        }
        return {
            players: this.players,
            ai: this.ai,
            qijia: this.qijia,
            gameType: this.gameType,
            rounds: this.rounds,
            standings: this.standings,
        };
    }
}

function applyAt(lineNumber, apply) {
    try {
        return apply();
    } catch (error) {
        throw new MalformedReplayError(lineNumber, error.message, { cause: error });
    }
}

/**
 * Convert a parsed replay (`parseReplay`'s `{ lines, lineNumbers }`) into its players and rounds: each round's deal
 * and play as majiang paipu messages, and its positions, the steps a viewer moves through. Throws a
 * `MalformedReplayError` naming the file line it cannot read.
 */
export function toReplay({ lines, lineNumbers }) {
    const [gameStarted, ...records] = lines;
    const builder = applyAt(lineNumbers[0], () => new ReplayBuilder(gameStarted));
    records.forEach((record, index) => {
        applyAt(lineNumbers[index + 1], () => builder.apply(record));
    });
    return builder.build();
}
