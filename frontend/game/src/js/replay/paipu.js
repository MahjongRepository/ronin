import * as immef from "../ronin/immef.js";
import * as mianzi from "../ronin/mianzi.js";
import { seatL } from "../ronin/results.js";
import * as tiles from "../ronin/tiles.js";
import wire from "../ronin/wire.js";

const SEATS = 4;

/** What a position of a round shows: its last visible record, or only silent records at a truncated end. */
export const POSITION = Object.freeze({
    DEAL: "deal",
    DRAW: "draw",
    DISCARD: "discard",
    CALL: "call",
    SILENT: "silent",
});

/** A replay line the converter cannot read; `line` is its 1-based line in the replay file. */
export class MalformedReplayError extends Error {
    constructor(line, message, options) {
        super(`Malformed replay at line ${line}: ${message}`, options);
        this.name = "MalformedReplayError";
        this.line = line;
    }
}

function dealMessage(roundStart, qijia) {
    const defen = [];
    const shoupai = [];
    for (let l = 0; l < SEATS; l++) {
        const seat = (roundStart.dl + l) % SEATS;
        const player = roundStart.p.find((p) => p.s === seat);
        if (player === undefined) {
            throw new Error(`round_started has no player in seat ${seat}`);
        }
        defen[l] = player.sc * wire.SCORE_DIV;
        shoupai[l] = tiles.handStr(player.tl);
    }
    return {
        qipai: {
            zhuangfeng: roundStart.w,
            jushu: (roundStart.dl - qijia + SEATS) % SEATS,
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

/**
 * One round's paipu log and its positions. A position is a run of silent records (they add to the log, or not at
 * all, but show nothing of their own) closed by the next visible one; `end` is the log index it reaches, and
 * `notes`, present only when one of its silent records left one, what those records say about it.
 */
class RoundBuilder {
    constructor(roundStart, qijia) {
        this.dealer = roundStart.dl;
        this.summary = {
            wind: roundStart.w,
            dealer: roundStart.dl,
            honba: roundStart.h,
            sticks: roundStart.r,
        };
        this.log = [dealMessage(roundStart, qijia)];
        this.positions = [];
        this.pendingSilent = [];
        this.melds = Array.from({ length: SEATS }, () => []);
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

    addPosition(kind, say = []) {
        const notes = this.takePendingNotes();
        this.positions.push({ end: this.log.length, kind, say, ...notesField(notes) });
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
        this.addVisible(POSITION.DRAW, rinshan ? { gangzimo: draw } : { zimo: draw });
    }

    discard(packed) {
        const discard = immef.decodeDiscard(packed);
        const l = this.l(discard.seat);
        this.kanSeat = null;
        const say = discard.isRiichi ? [{ name: "lizhi", l }] : [];
        this.addVisible(POSITION.DISCARD, { dapai: { l, p: discardTile(discard) } }, say);
    }

    meld(compact) {
        const meld = immef.decodeMeldCompact(compact);
        const seatMelds = this.melds[meld.callerSeat];
        const pon = meld.meldType === wire.MELD.ADDED_KAN ? this.takePon(seatMelds, meld) : null;
        seatMelds.push(meld);
        this.kanSeat = mianzi.KAN_TYPES.has(meld.meldType) ? meld.callerSeat : null;
        const l = this.l(meld.callerSeat);
        const message = {
            [mianzi.KIND_OF_MELD[meld.meldType]]: { l, m: mianzi.mianziStr(meld, pon) },
        };
        this.addVisible(POSITION.CALL, message, [{ name: mianzi.SAY_OF_MELD[meld.meldType], l }]);
    }

    takePon(seatMelds, kan) {
        const tile34 = Math.floor(kan.tileIds[0] / 4);
        const index = seatMelds.findIndex((meld) => mianzi.isPonOf(meld, tile34));
        if (index < 0) {
            throw new Error("added kan without its pon");
        }
        return seatMelds.splice(index, 1)[0];
    }

    revealDora(tileId) {
        this.addSilent({ kaigang: { baopai: tiles.tileToStr(tileId) } });
    }

    declareRiichi() {
        this.addSilent(null);
    }

    /** A round end closes the round; its silent records join the round's last position. */
    closeAtRoundEnd() {
        const last = this.positions.pop();
        const notes = [...(last.notes ?? []), ...this.takePendingNotes()];
        this.positions.push({ ...last, end: this.log.length, ...notesField(notes) });
        return this.build();
    }

    /** A truncated round ends where the replay does; silent records with nothing after them are its last position. */
    closeTruncated() {
        if (this.pendingSilent.length > 0) {
            this.addPosition(POSITION.SILENT);
        }
        return this.build();
    }

    build() {
        return { ...this.summary, log: this.log, positions: this.positions, outcome: null };
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
        this.gameType = gameStarted.gt;
        this.rounds = [];
        this.round = null;
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
                return this.currentRound().declareRiichi();
            case wire.E.ROUND_END:
                return this.closeRound();
            case wire.E.GAME_END:
                return;
            default:
                throw new Error(`unknown record type ${line.t}`);
        }
    }

    startRound(roundStart) {
        if (this.round !== null) {
            throw new Error("round started before the previous round ended");
        }
        this.round = new RoundBuilder(roundStart, this.qijia);
    }

    closeRound() {
        this.rounds.push(this.currentRound().closeAtRoundEnd());
        this.round = null;
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
            standings: null,
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
