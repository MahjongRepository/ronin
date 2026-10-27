import $ from "jquery";

import fadein from "../../vendor/majiang-ui/fadein.js";
import { WIN_CALL_MS } from "../ronin/results.js";
import { HISTORY_URL } from "../routes.js";
import { POSITION } from "./paipu.js";

const SEATS = 4;

function kindOf(message) {
    return Object.keys(message)[0];
}

function isIndex(index, length) {
    return Number.isInteger(index) && index >= 0 && index < length;
}

/**
 * Play one paipu message into a majiang-core Board. The core Board has no gangzimo: a replacement draw from the dead
 * wall is a draw to it, as majiang-core's Player plays it.
 */
function playIntoModel(model, message) {
    const kind = kindOf(message);
    switch (kind) {
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

/** Where the standings' exit leads: back to the lobby page the replay was opened from, else the game history. */
function exitUrl() {
    const referrer = document.referrer;
    if (referrer !== "" && new URL(referrer).origin === window.location.origin) {
        return referrer;
    }
    return HISTORY_URL;
}

/**
 * The cursor over a converted replay (`toReplay`): it moves through each round's positions and shows each on a
 * majiang-ui Board view drawing a majiang-core Board model. The model is the only state: a seek rebuilds the round
 * from its deal, silently, and stepping forward plays a position's messages into the model and the view, with sound.
 * A result position's range holds its first win only; the dialog's 次へ pages through a double ron's further wins
 * without moving the cursor, and leaving the result forward plays the ones not yet shown, so no win is played twice.
 *
 * Every move first cancels the viewer's pending timers (a result's dialog after its callouts). Autoplay (B3) belongs
 * here too, as play() and pause() with `playing` in the state, on those same timers, so any manual move pauses it.
 * `onChange` gets the state after every move and every page of a double ron.
 */
export class ReplayViewer {
    #pending = new Set();

    constructor({ replay, view, model, root, onChange = () => {} }) {
        this.replay = replay;
        this.view = view;
        this.model = model;
        this.root = root;
        this.onChange = onChange;
        this.round = 0;
        this.step = 0;
        this.pagedWins = 0;
    }

    /** Bind the result dialog's 次へ and the standings' exit, and show the position at (round, step). */
    start(round = 0, step = 0) {
        this.dialog()
            .off(".replay")
            .on("click.replay", ".next", () => this.pageResult());
        $(".summary .exit", this.root)
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
            seat: this.view.viewpoint,
            openHands: this.view.open_shoupai,
            canBack: this.canBack,
            canNext: this.canNext,
        };
    }

    hasPosition(round, step) {
        const { rounds } = this.replay;
        return isIndex(round, rounds.length) && isIndex(step, rounds[round].positions.length);
    }

    get canBack() {
        return this.round > 0 || this.step > 0;
    }

    get canNext() {
        return !this.atLastPosition();
    }

    next() {
        if (!this.canNext) {
            return;
        }
        this.cancelPending();
        this.playUnshownWins();
        this.pagedWins = 0;
        if (this.step + 1 < this.currentRound().positions.length) {
            this.step += 1;
        } else {
            this.round += 1;
            this.step = 0;
        }
        this.playForward();
        this.notifyChange();
    }

    /** Back one position; from a deal, to the previous round's result. */
    back() {
        if (this.step > 0) {
            this.seek(this.round, this.step - 1);
        } else if (this.round > 0) {
            this.seek(this.round - 1, this.lastStepOf(this.round - 1));
        }
    }

    /** Show the position at (round, step) silently: the round rebuilt from its deal, a result's first win open. */
    seek(round, step) {
        if (!this.hasPosition(round, step)) {
            throw new RangeError(`no replay position at round ${round}, step ${step}`);
        }
        this.cancelPending();
        this.round = round;
        this.step = step;
        this.pagedWins = 0;
        this.rebuild();
        this.notifyChange();
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

    last() {
        const round = this.replay.rounds.length - 1;
        this.seek(round, this.lastStepOf(round));
    }

    /** Put seat at the bottom of the table, keeping the position. */
    setViewpoint(seat) {
        if (!isIndex(seat, SEATS)) {
            throw new RangeError(`no seat ${seat}`);
        }
        this.view.viewpoint = seat;
        this.seek(this.round, this.step);
    }

    /** Show every hand face up, or only the viewpoint's, keeping the position. */
    setOpenHands(open) {
        this.view.open_shoupai = open;
        this.seek(this.round, this.step);
    }

    cancelPending() {
        for (const timer of this.#pending) {
            clearTimeout(timer);
        }
        this.#pending.clear();
    }

    #schedule(callback, delay) {
        const timer = setTimeout(() => {
            this.#pending.delete(timer);
            callback();
        }, delay);
        this.#pending.add(timer);
    }

    currentRound() {
        return this.replay.rounds[this.round];
    }

    currentPosition() {
        return this.currentRound().positions[this.step];
    }

    lastStepOf(round) {
        return this.replay.rounds[round].positions.length - 1;
    }

    atLastPosition() {
        const lastRound = this.replay.rounds.length - 1;
        return this.round === lastRound && this.step === this.lastStepOf(lastRound);
    }

    notifyChange() {
        this.onChange(this.state);
    }

    dialog() {
        return $(".hule-dialog", this.root);
    }

    play(message) {
        playIntoModel(this.model, message);
        this.view.update(message);
    }

    sayCallouts(position, silent) {
        for (const { name, l } of position.say) {
            this.view.say(name, l, silent);
        }
    }

    /** A double ron's wins after its first, which no position's range holds. */
    furtherWins() {
        const { end, wins } = this.currentPosition();
        return this.currentRound().log.slice(end, end + wins - 1);
    }

    /**
     * 次へ on a result: the next win of a double ron, past the last win the next position. The dialog hides until the
     * next win's opens, so a double click shows each win rather than skipping one.
     */
    pageResult() {
        if (this.dialog().hasClass("hide")) {
            return;
        }
        const further = this.furtherWins();
        if (this.pagedWins === further.length) {
            this.next();
            return;
        }
        fadein.hide(this.dialog());
        this.play(further[this.pagedWins]);
        this.pagedWins += 1;
        this.notifyChange();
    }

    playUnshownWins() {
        if (this.currentPosition().kind !== POSITION.RESULT) {
            return;
        }
        for (const win of this.furtherWins().slice(this.pagedWins)) {
            playIntoModel(this.model, win);
        }
    }

    rebuild() {
        const { log } = this.currentRound();
        const position = this.currentPosition();
        this.model.qipai(log[0].qipai);
        for (const message of log.slice(1, position.end)) {
            playIntoModel(this.model, message);
        }
        this.view.redraw();
        switch (position.kind) {
            case POSITION.RESULT:
                return this.view.update(log[position.end - 1], true);
            case POSITION.SUMMARY:
                return this.showStandings();
            default:
                return this.sayCallouts(position, true);
        }
    }

    playForward() {
        const position = this.currentPosition();
        switch (position.kind) {
            case POSITION.DEAL:
                this.model.qipai(this.currentRound().log[0].qipai);
                return this.view.redraw();
            case POSITION.SUMMARY:
                return this.showStandings();
            case POSITION.RESULT:
                return this.playResult(position);
            default:
                this.messagesOf(position).forEach((message) => this.play(message));
                return this.sayCallouts(position, false);
        }
    }

    messagesOf(position) {
        return this.currentRound().log.slice(position.start, position.end);
    }

    /** The result's callouts first, as the live game shows them; its dialog opens after them. */
    playResult(position) {
        const messages = this.messagesOf(position);
        const result = messages.at(-1);
        messages.slice(0, -1).forEach((message) => this.play(message));
        playIntoModel(this.model, result);
        if (position.say.length === 0) {
            this.view.update(result);
            return;
        }
        this.sayCallouts(position, false);
        this.#schedule(() => this.view.update(result), WIN_CALL_MS);
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
