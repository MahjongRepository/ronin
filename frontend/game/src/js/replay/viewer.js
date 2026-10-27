import $ from "jquery";

import fadein from "../../vendor/majiang-ui/fadein.js";
import { WIN_CALL_MS } from "../ronin/results.js";
import { HISTORY_URL } from "../routes.js";
import { POSITION, kindOf } from "./paipu.js";

const SEATS = 4;

/** How long a step's callouts show before they fade: long enough to read, short enough to uncover the rivers under them. */
export const CALLOUT_MS = 1200;

/** The board's nameplates in turn order from the viewpoint's at the bottom, as majiang-ui places them. */
const NAMEPLATES = Object.freeze(["main", "xiajia", "duimian", "shangjia"]);

/** The messages that open a turn: the view redraws the previous turn's river when one plays. */
const TURN_STARTS = new Set(["zimo", "gangzimo", "fulou", "gang"]);

function isIndex(index, length) {
    return Number.isInteger(index) && index >= 0 && index < length;
}

/** A message of a converted replay the majiang-core model refuses: the replay is damaged past what the converter checks. */
export class UnplayableReplayError extends Error {
    constructor(message, options) {
        super(`the model cannot play ${JSON.stringify(message)}`, options);
        this.name = "UnplayableReplayError";
    }
}

/**
 * Play one paipu message into a majiang-core Board. The core Board has no gangzimo: a replacement draw from the dead
 * wall is a draw to it, as majiang-core's Player plays it.
 */
function playIntoModel(model, message) {
    try {
        applyToModel(model, message);
    } catch (error) {
        throw new UnplayableReplayError(message, { cause: error });
    }
}

function applyToModel(model, message) {
    const kind = kindOf(message);
    switch (kind) {
        case "qipai":
            return model.qipai(message.qipai);
        case "zimo":
            return model.zimo(message.zimo);
        case "gangzimo":
            return model.zimo(message.gangzimo);
        case "dapai":
            return model.dapai(message.dapai);
        case "fulou":
            return model.fulou(message.fulou);
        case "gang":
            return model.gang(message.gang);
        case "kaigang":
            return model.kaigang(message.kaigang);
        case "hule":
            return model.hule(message.hule);
        case "pingju":
            return model.pingju(message.pingju);
        default:
            throw new Error(`no model call for a ${kind} message`);
    }
}

/** How many wins a position holds after its first: a double ron's further wins, none anywhere else. */
function furtherWinCount(position) {
    return position.kind === POSITION.RESULT ? Math.max(0, position.wins - 1) : 0;
}

/** Where the standings' exit leads: back to the lobby page the replay was opened from, else the game history. */
function exitUrl() {
    const referrer = document.referrer;
    if (referrer !== "" && new URL(referrer).origin === window.location.origin) {
        return referrer;
    }
    return HISTORY_URL;
}

/** The exit's label names where it leads: the game history, or just back to another page. */
function exitLabel(url) {
    return new URL(url, window.location.origin).pathname.startsWith(HISTORY_URL)
        ? "履歴へ戻る"
        : "戻る";
}

/**
 * The cursor over a converted replay (`toReplay`): it moves through each round's positions and shows each on a
 * majiang-ui Board view drawing a majiang-core Board model. The model is the only state: a seek rebuilds the round
 * from its deal, silently, and stepping forward plays a position's messages into the model and the view, with sound.
 * A result position's range holds its first win only; the dialog's 次へ and Next alike page through a double ron's
 * further wins without moving the cursor, and leave the result only once its last win is shown; Back pages back.
 *
 * Every move first cancels the viewer's pending timers (a result's dialog after its callouts). Autoplay (B3) belongs
 * here too, as play() and pause() with `playing` in the state, on those same timers, so any manual move pauses it.
 * `onChange` gets the state after every move and every page of a double ron.
 *
 * A move plays its target position before the cursor moves there, so the cursor and the board never part. A move that
 * throws (an `UnplayableReplayError` from the model, or the board's own failure) stops the viewer: it goes to
 * `onError`, and no move runs after it.
 */
export class ReplayViewer {
    #pending = new Set();
    #pendingWin = null;
    #failed = false;

    constructor({
        replay,
        view,
        model,
        root,
        onChange = () => {},
        onError = (error) => {
            throw error;
        },
    }) {
        this.replay = replay;
        this.view = view;
        this.model = model;
        this.root = root;
        this.onChange = onChange;
        this.onError = onError;
        this.round = 0;
        this.step = 0;
        this.pagedWins = 0;
    }

    /**
     * Bind the result dialog's 次へ, the standings' exit and the nameplates (a click views the table from that seat), and
     * show the position at (round, step).
     */
    start(round = 0, step = 0) {
        this.dialog()
            .off(".replay")
            .on("click.replay", ".next", () => this.pageResult());
        $("> .player", this.root)
            .off(".replay")
            .on("click.replay", (event) => this.viewFromNameplate(event.currentTarget));
        $(".summary .exit", this.root)
            .text(exitLabel(exitUrl()))
            .off(".replay")
            .on("click.replay", () => window.location.assign(exitUrl()));
        this.seek(round, step);
    }

    get state() {
        return {
            round: this.round,
            step: this.step,
            kind: this.currentPosition().kind,
            endedEarly: this.replay.standings === null && this.atLastPosition(),
            page: this.pagedWins,
            seat: this.view.viewpoint,
            openHands: this.view.open_shoupai,
            canBack: this.canBack,
            canNext: this.canNext,
            canNextRound: !this.#failed && this.round + 1 < this.replay.rounds.length,
            atEnd: !this.canNext,
            tilesLeft: this.model.shan.paishu,
        };
    }

    hasPosition(round, step) {
        const { rounds } = this.replay;
        return isIndex(round, rounds.length) && isIndex(step, rounds[round].positions.length);
    }

    /** Whether a move failed, which stopped the viewer. */
    get failed() {
        return this.#failed;
    }

    get canBack() {
        return !this.#failed && (this.round > 0 || this.step > 0 || this.pagedWins > 0);
    }

    get canNext() {
        return !this.#failed && (!this.atLastPosition() || this.hasUnshownWin());
    }

    /**
     * One position forward; on a result with a win not shown yet, that win, as the dialog's 次へ shows it. While a
     * double ron's win is still opening, Next opens it at once instead, so a press is never lost and never skips a win.
     */
    next() {
        if (!this.canNext) {
            return;
        }
        if (this.isWinOpening()) {
            this.#move(() => this.openWin());
        } else if (this.hasUnshownWin()) {
            this.#move(() => this.pageWin());
        } else {
            this.#move(() => this.stepForward());
        }
    }

    /** Back one position or one shown win, undoing Next; from a deal, to the previous round's result at its last win. */
    back() {
        if (this.pagedWins > 0) {
            this.show(this.round, this.step, this.pagedWins - 1);
        } else if (this.step > 0) {
            this.showAllWins(this.round, this.step - 1);
        } else if (this.round > 0) {
            this.showAllWins(this.round - 1, this.lastStepOf(this.round - 1));
        }
    }

    /** Show the position at (round, step) silently: the round rebuilt from its deal, a result's first win open. */
    seek(round, step) {
        if (!this.hasPosition(round, step)) {
            throw new RangeError(`no replay position at round ${round}, step ${step}`);
        }
        this.show(round, step, 0);
    }

    nextRound() {
        if (this.round + 1 < this.replay.rounds.length) {
            this.seek(this.round + 1, 0);
        }
    }

    /** To the current round's deal, or the previous round's when already at it. */
    prevRound() {
        if (this.step > 0) {
            this.seek(this.round, 0);
        } else if (this.round > 0) {
            this.seek(this.round - 1, 0);
        }
    }

    first() {
        this.seek(0, 0);
    }

    /** To the game's end: its last position with every win of its result shown. */
    last() {
        const round = this.replay.rounds.length - 1;
        this.showAllWins(round, this.lastStepOf(round));
    }

    /** Put seat at the bottom of the table, keeping the position and a double ron's page. */
    setViewpoint(seat) {
        if (!isIndex(seat, SEATS)) {
            throw new RangeError(`no seat ${seat}`);
        }
        this.view.viewpoint = seat;
        this.show(this.round, this.step, this.pagedWins);
    }

    viewFromNameplate(plate) {
        const offset = NAMEPLATES.findIndex((name) => plate.classList.contains(name));
        if (offset > 0) {
            this.setViewpoint((this.view.viewpoint + offset) % SEATS);
        }
    }

    /** Show every hand face up, or only the viewpoint's, keeping the position and a double ron's page. */
    setOpenHands(open) {
        this.view.open_shoupai = open;
        this.show(this.round, this.step, this.pagedWins);
    }

    cancelPending() {
        for (const timer of this.#pending) {
            clearTimeout(timer);
        }
        this.#pending.clear();
        this.#pendingWin = null;
    }

    #schedule(callback, delay) {
        const timer = setTimeout(() => {
            this.#pending.delete(timer);
            this.#move(callback);
        }, delay);
        this.#pending.add(timer);
    }

    /** Run a move unless the viewer has stopped; a move that throws stops it and goes to `onError`. */
    #move(action) {
        if (this.#failed) {
            return;
        }
        try {
            action();
        } catch (error) {
            this.#failed = true;
            this.cancelPending();
            this.onError(error);
        }
    }

    currentRound() {
        return this.replay.rounds[this.round];
    }

    currentPosition() {
        return this.currentRound().positions[this.step];
    }

    /** Where Next leaves for: the round's next position, past its last the next round's deal. */
    nextCursor() {
        if (this.step + 1 < this.currentRound().positions.length) {
            return { round: this.round, step: this.step + 1, pagedWins: 0 };
        }
        return { round: this.round + 1, step: 0, pagedWins: 0 };
    }

    lastStepOf(round) {
        return this.replay.rounds[round].positions.length - 1;
    }

    atLastPosition() {
        const lastRound = this.replay.rounds.length - 1;
        return this.round === lastRound && this.step === this.lastStepOf(lastRound);
    }

    /** Rebuild the table silently at (round, step), a result showing its win after `pagedWins` further ones. */
    show(round, step, pagedWins) {
        this.#move(() => {
            const target = { round, step, pagedWins };
            this.cancelPending();
            this.rebuild(target);
            this.moveTo(target);
        });
    }

    stepForward() {
        const target = this.nextCursor();
        this.cancelPending();
        this.playForward(target);
        this.moveTo(target);
    }

    /** Put the cursor at `target` once its position has played, and say so. */
    moveTo({ round, step, pagedWins }) {
        this.round = round;
        this.step = step;
        this.pagedWins = pagedWins;
        this.titleNameplates();
        this.notifyChange();
    }

    /** The other seats' nameplates say that a click views the table from them. */
    titleNameplates() {
        NAMEPLATES.forEach((place, offset) => {
            const plate = $(`> .player.${place}`, this.root);
            const name = this.replay.players[(this.view.viewpoint + offset) % SEATS];
            const title = offset === 0 ? name : `View from ${name}`;
            plate.add($(".name", plate)).attr("title", title);
        });
    }

    showAllWins(round, step) {
        this.show(round, step, furtherWinCount(this.replay.rounds[round].positions[step]));
    }

    /** The dialog's 次へ is hidden where it has nowhere to go: the last win of a truncated replay's last result. */
    notifyChange() {
        $(".next", this.dialog()).toggleClass("hide", !this.canNext);
        this.onChange(this.state);
    }

    dialog() {
        return $(".hule-dialog", this.root);
    }

    play(message) {
        playIntoModel(this.model, message);
        this.view.update(message);
    }

    /** A step's callouts, faded after a moment so they do not hide the rivers under them for the rest of the turn. */
    sayCallouts(position, silent) {
        for (const { name, l } of position.say) {
            this.view.say(name, l, silent);
        }
        if (position.say.length > 0) {
            this.#schedule(() => this.view.clear_bubbles(), CALLOUT_MS);
        }
    }

    /** A double ron's wins after its first, which no position's range holds. */
    furtherWins(round, step) {
        const { log, positions } = this.replay.rounds[round];
        const { end, wins } = positions[step];
        return log.slice(end, end + wins - 1);
    }

    hasUnshownWin() {
        return this.pagedWins < furtherWinCount(this.currentPosition());
    }

    /** Whether a double ron's win is still on its way to the dialog: its callouts, the board's delay or its fade-in. */
    isWinOpening() {
        return furtherWinCount(this.currentPosition()) > 0 && this.dialog().hasClass("hide");
    }

    /**
     * 次へ on a result: the next win of a double ron, past the last win the next position. It is ignored while the
     * dialog is hidden (its callouts, or the next win's opening), so a double click shows each win rather than skipping
     * one.
     */
    pageResult() {
        if (this.dialog().hasClass("hide")) {
            return;
        }
        if (this.hasUnshownWin()) {
            this.#move(() => this.pageWin());
        } else {
            this.next();
        }
    }

    /** The double ron's next win: the dialog closes, and the win's own opens after the board's delay. */
    pageWin() {
        fadein.hide(this.dialog());
        this.play(this.furtherWins(this.round, this.step)[this.pagedWins]);
        this.moveTo({ round: this.round, step: this.step, pagedWins: this.pagedWins + 1 });
    }

    /** Open the win on its way to the dialog now, rather than after its callouts, the board's delay and the fade-in. */
    openWin() {
        const pendingWin = this.#pendingWin;
        this.cancelPending();
        if (pendingWin !== null) {
            this.view.update(pendingWin);
        }
        this.view.open_hule();
        fadein.show(this.dialog());
    }

    /**
     * Rebuild the table at `target` as stepping forward left it. The model replays the round up to the turn in play,
     * and the view draws that, then plays the turn's own messages since (a discard, a dora reveal) as stepping does: the
     * last discard keeps its mark, and a riichi discard shows no stick before the next turn deposits it. The standings
     * show the whole round drawn at once, since no turn is in play.
     */
    rebuild(target) {
        const round = this.replay.rounds[target.round];
        const position = round.positions[target.step];
        const messages = round.log.slice(1, position.end);
        const result = position.kind === POSITION.RESULT ? messages.pop() : null;
        const turn =
            position.kind === POSITION.SUMMARY
                ? messages.length
                : messages.findLastIndex((message) => TURN_STARTS.has(kindOf(message))) + 1;
        playIntoModel(this.model, round.log[0]);
        messages.slice(0, turn).forEach((message) => playIntoModel(this.model, message));
        this.view.redraw();
        for (const message of messages.slice(turn)) {
            playIntoModel(this.model, message);
            this.view.update(message, true);
        }
        switch (position.kind) {
            case POSITION.RESULT:
                return this.showWin(result, target);
            case POSITION.SUMMARY:
                return this.showStandings();
            default:
                return this.sayCallouts(position, true);
        }
    }

    /**
     * The result's win after `pagedWins` further ones, which the table shows as stepping forward left it: the earlier
     * winners' hands face up too.
     */
    showWin(firstWin, target) {
        const wins = [
            firstWin,
            ...this.furtherWins(target.round, target.step).slice(0, target.pagedWins),
        ];
        wins.forEach((win) => playIntoModel(this.model, win));
        this.view.update(wins.at(-1), true);
        wins.slice(0, -1).forEach((win) => this.view.reveal(win.hule.l));
    }

    /** Play the position at `target`, the one after the cursor's, into the model and the view, with sound. */
    playForward(target) {
        const round = this.replay.rounds[target.round];
        const position = round.positions[target.step];
        const messages = round.log.slice(position.start, position.end);
        switch (position.kind) {
            case POSITION.DEAL:
                playIntoModel(this.model, round.log[0]);
                return this.view.redraw();
            case POSITION.SUMMARY:
                return this.showStandings();
            case POSITION.RESULT:
                return this.playResult(position, messages);
            default:
                messages.forEach((message) => this.play(message));
                return this.sayCallouts(position, false);
        }
    }

    /** The result's callouts first, as the live game shows them; its dialog opens after them. */
    playResult(position, messages) {
        const result = messages.at(-1);
        messages.slice(0, -1).forEach((message) => this.play(message));
        playIntoModel(this.model, result);
        if (position.say.length === 0) {
            this.view.update(result);
            return;
        }
        this.sayCallouts(position, false);
        this.#schedule(() => this.showPendingWin(), WIN_CALL_MS);
        this.#pendingWin = result;
    }

    showPendingWin() {
        const win = this.#pendingWin;
        this.#pendingWin = null;
        this.view.update(win);
    }

    showStandings() {
        const { players, qijia, rounds, standings } = this.replay;
        this.model.jieju(standings);
        this.view.update();
        this.view.summary({
            player: players,
            qijia,
            log: rounds.map((round) => round.log),
            ...standings,
        });
    }
}
