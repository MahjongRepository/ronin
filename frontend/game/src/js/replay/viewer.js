import $ from "jquery";

import fadein from "../../vendor/majiang-ui/fadein.js";
import { WIN_CALL_MS } from "../ronin/results.js";
import { HISTORY_URL } from "../routes.js";
import { COARSE_POINTER_MEDIA } from "./media.js";
import { POSITION, kindOf } from "./paipu.js";
import { SEATS } from "./seats.js";
import { AUTOPLAY_SPEEDS, DEFAULT_AUTOPLAY_SPEED } from "./speeds.js";

/** How long a step's callouts show before they fade: long enough to read, short enough to uncover the rivers under them. */
export const CALLOUT_MS = 1200;

/** The deal stays up at least this long under autoplay, whatever the speed: a new hand to take in. */
export const AUTOPLAY_DEAL_MS = 1500;

/** How often autoplay looks whether a result's dialog has opened, since the board opens it on timers of its own. */
export const AUTOPLAY_DIALOG_POLL_MS = 100;

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
 * Every move first cancels the viewer's pending timers (a result's dialog after its callouts, a callout's fade, autoplay's
 * next step). Autoplay steps as Next does, on one of those timers: at once on Play, then at the chosen speed, a draw at
 * half of it, the deal and a position with callouts for at least as long as they need. It pauses at each win's dialog
 * once the dialog is fully shown, never cutting a win's callouts short, and at the end; Play on a result pages to its
 * next win or moves on, and so does 次へ where autoplay paused itself. Any other move (Next included) pauses it, as does
 * hiding the page; a change of viewpoint or of the hands shown redraws the position and plays on. `onChange` gets the
 * state after every move, every page of a double ron and every start or pause of autoplay.
 *
 * A move plays its target position before the cursor moves there, so the cursor and the board never part. A move that
 * throws (an `UnplayableReplayError` from the model, or the board's own failure) stops the viewer: it goes to
 * `onError`, and no move runs after it.
 */
export class ReplayViewer {
    #pending = new Set();
    #pendingWin = null;
    #failed = false;
    #playing = false;
    #leaving = false;
    #waitedForDialog = false;
    #pausedAtResult = false;
    #autoplayTimer = null;

    constructor({
        replay,
        view,
        model,
        root,
        speed = DEFAULT_AUTOPLAY_SPEED,
        onChange = () => {},
        onStandingsJump = () => {},
        onError = (error) => {
            throw error;
        },
    }) {
        this.replay = replay;
        this.view = view;
        this.model = model;
        this.root = root;
        this.onChange = onChange;
        this.onStandingsJump = onStandingsJump;
        this.onError = onError;
        this.speed = speed;
        this.round = 0;
        this.step = 0;
        this.pagedWins = 0;
    }

    /**
     * Bind the result dialog's 次へ, the standings' exit and rounds (a click shows that round from its deal, then
     * `onStandingsJump` runs), and the nameplates (a click views the table from that seat), and show the position at
     * (round, step).
     */
    start(round = 0, step = 0) {
        this.dialog()
            .off(".replay")
            .on("click.replay", ".next", () => this.pageResult());
        $("> .player", this.root)
            .off(".replay")
            .on("click.replay", (event) => this.viewFromNameplate(event.currentTarget));
        $(".summary", this.root)
            .off(".replay")
            .on("click.replay", ".body .row-diff", (event) =>
                this.seekFromStandings(event.currentTarget),
            );
        $(".summary .exit", this.root)
            .text(exitLabel(exitUrl()))
            .off(".replay")
            .on("click.replay", () => window.location.assign(exitUrl()));
        $(document)
            .off(".replay-autoplay")
            .on("visibilitychange.replay-autoplay", () => {
                if (document.hidden && this.#playing) {
                    this.pause();
                }
            });
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
            playing: this.#playing,
            speed: this.speed,
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
        this.pause();
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
        this.#redraw();
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
        this.#redraw();
    }

    /** Draw the position shown afresh, a double ron's page kept; autoplay plays on from it. */
    #redraw() {
        this.#rebuildAt(this.round, this.step, this.pagedWins);
        if (this.#playing) {
            this.#armAutoplay(this.#autoplayDelay());
        }
    }

    /** Step forward on its own: once at once, then at the chosen speed, until a result's dialog, the end or a pause. */
    play() {
        if (this.#playing || !this.canNext) {
            return;
        }
        this.#playing = true;
        this.#leaving = true;
        this.#waitedForDialog = false;
        this.#pausedAtResult = false;
        this.notifyChange();
        this.#stepAutoplay();
    }

    pause() {
        this.#pausedAtResult = false;
        if (!this.#playing) {
            return;
        }
        this.#stopAutoplay();
        this.notifyChange();
    }

    /** Autoplay at another speed; playing, its next step waits by the new speed from now. */
    setSpeed(speed) {
        if (!Object.hasOwn(AUTOPLAY_SPEEDS, speed)) {
            throw new RangeError(`no autoplay speed ${speed}`);
        }
        this.speed = speed;
        if (this.#playing) {
            this.#armAutoplay(this.#autoplayDelay());
        }
        this.notifyChange();
    }

    #armAutoplay(delay) {
        this.#cancelAutoplay();
        this.#autoplayTimer = this.#schedule(() => this.#stepAutoplay(), delay);
    }

    #cancelAutoplay() {
        clearTimeout(this.#autoplayTimer);
        this.#pending.delete(this.#autoplayTimer);
        this.#autoplayTimer = null;
    }

    #stopAutoplay() {
        this.#playing = false;
        this.#cancelAutoplay();
    }

    #stepAutoplay() {
        if (this.isAtResult()) {
            this.#stepAutoplayAtResult();
        } else {
            this.#advanceAutoplay();
        }
    }

    /**
     * A result waits until its dialog is fully shown, its callouts never cut short. Reached by autoplay, it pauses there;
     * where Play was pressed, it is left: at once if its dialog was already up, else after showing it for a step's time.
     */
    #stepAutoplayAtResult() {
        if (!this.isDialogFullyShown()) {
            this.#waitedForDialog = true;
            this.#armAutoplay(AUTOPLAY_DIALOG_POLL_MS);
        } else if (!this.#leaving) {
            this.#pauseAtResult();
        } else if (this.#waitedForDialog) {
            this.#waitedForDialog = false;
            this.#armAutoplay(AUTOPLAY_SPEEDS[this.speed]);
        } else {
            this.#advanceAutoplay();
        }
    }

    /** Next's step, never opening a win early: a double ron's next win, else the next position. */
    #advanceAutoplay() {
        this.#leaving = false;
        this.#waitedForDialog = false;
        this.#move(() => (this.hasUnshownWin() ? this.pageWin() : this.stepForward()));
        if (!this.#playing) {
            return;
        }
        if (!this.canNext && !this.isAtResult()) {
            this.pause();
            return;
        }
        this.#armAutoplay(this.#autoplayDelay());
    }

    #pauseAtResult() {
        this.#stopAutoplay();
        this.#pausedAtResult = true;
        this.notifyChange();
    }

    /** How long autoplay stays at the position shown: a result until its dialog opens, anything else by the speed. */
    #autoplayDelay() {
        const position = this.currentPosition();
        const delay = AUTOPLAY_SPEEDS[this.speed];
        if (position.kind === POSITION.RESULT) {
            return AUTOPLAY_DIALOG_POLL_MS;
        }
        if (position.kind === POSITION.DEAL) {
            return Math.max(delay, AUTOPLAY_DEAL_MS);
        }
        if (position.say.length > 0) {
            return Math.max(delay, CALLOUT_MS);
        }
        return position.kind === POSITION.DRAW ? delay / 2 : delay;
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
        return timer;
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
            this.#playing = false;
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
        this.pause();
        this.#rebuildAt(round, step, pagedWins);
    }

    #rebuildAt(round, step, pagedWins) {
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

    playMessage(message) {
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

    isAtResult() {
        return this.currentPosition().kind === POSITION.RESULT;
    }

    /** Whether the position shown is one a held Back or Next, or a scrolled wheel, stops at: a result or the standings. */
    isAtStop() {
        const { kind } = this.currentPosition();
        return kind === POSITION.RESULT || kind === POSITION.SUMMARY;
    }

    /** Whether a result's dialog is up and done fading in, so autoplay may stop at it or leave it. */
    isDialogFullyShown() {
        const dialog = this.dialog();
        if (dialog.hasClass("hide") || dialog.hasClass("fadeout")) {
            return false;
        }
        const fading = dialog[0].getAnimations?.() ?? [];
        return fading.every((animation) => animation.playState !== "running");
    }

    hasUnshownWin() {
        return this.pagedWins < furtherWinCount(this.currentPosition());
    }

    /** Whether a double ron's win is still on its way to the dialog: its callouts, the board's delay or its fade-in. */
    isWinOpening() {
        return furtherWinCount(this.currentPosition()) > 0 && this.dialog().hasClass("hide");
    }

    /**
     * 次へ on a result: the next win of a double ron, past the last win the next position; where autoplay paused itself
     * (or waits on the dialog), it plays on from there. It is ignored while the dialog is hidden (its callouts, or the
     * next win's opening), so a double click shows each win rather than skipping one.
     */
    pageResult() {
        if (this.dialog().hasClass("hide")) {
            return;
        }
        if (this.#pausedAtResult || this.#playing) {
            this.#stopAutoplay();
            this.play();
            return;
        }
        this.pause();
        if (this.hasUnshownWin()) {
            this.#move(() => this.pageWin());
        } else {
            this.next();
        }
    }

    /** The double ron's next win: the dialog closes, and the win's own opens after the board's delay. */
    pageWin() {
        fadein.hide(this.dialog());
        this.playMessage(this.furtherWins(this.round, this.step)[this.pagedWins]);
        this.moveTo({ round: this.round, step: this.step, pagedWins: this.pagedWins + 1 });
    }

    /** Open the win on its way to the dialog now, rather than after its callouts, the board's delay and the fade-in. */
    openWin() {
        const pendingWin = this.#pendingWin;
        this.cancelPending();
        if (pendingWin !== null) {
            this.view.update(pendingWin);
        }
        this.showWinDialogNow();
    }

    /** The win the board is about to show, in its dialog now rather than after the board's delay and fade-in. */
    showWinDialogNow() {
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
     * winners' hands face up too. A win's dialog opens at once, not after the board's delay, so a Next pressed right
     * after Back lands on a double ron pages on rather than opening the same win; a draw's still waits for its own timer.
     */
    showWin(firstWin, target) {
        const wins = [
            firstWin,
            ...this.furtherWins(target.round, target.step).slice(0, target.pagedWins),
        ];
        wins.forEach((win) => playIntoModel(this.model, win));
        this.view.update(wins.at(-1), true);
        wins.slice(0, -1).forEach((win) => this.view.reveal(win.hule.l));
        if (kindOf(wins.at(-1)) === "hule") {
            this.showWinDialogNow();
        }
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
                messages.forEach((message) => this.playMessage(message));
                return this.sayCallouts(position, false);
        }
    }

    /** The result's callouts first, as the live game shows them; its dialog opens after them. */
    playResult(position, messages) {
        const result = messages.at(-1);
        messages.slice(0, -1).forEach((message) => this.playMessage(message));
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
        this.linkStandingsRounds();
    }

    /**
     * Each round's name in the standings is a button to that round's deal, and a click anywhere on its row does the
     * same; a line under the table says so, a tap on a touch screen.
     */
    linkStandingsRounds() {
        $(".summary .body .row-diff .jushu", this.root).each((_, cell) => {
            const name = cell.textContent;
            $(cell)
                .empty()
                .append(
                    $('<button type="button" class="replay-summary-round">')
                        .attr("title", "Show this round from its deal")
                        .text(name),
                );
        });
        const table = $(".summary table", this.root);
        if (table.next(".replay-summary-hint").length === 0) {
            const verb = window.matchMedia(COARSE_POINTER_MEDIA).matches ? "Tap" : "Click";
            table.after(
                $('<p class="replay-summary-hint" lang="en">').text(`${verb} a round to replay it`),
            );
        }
    }

    /** The standings have a row per round, in order: a click on one shows that round from its deal. */
    seekFromStandings(row) {
        const index = $(".summary .body .row-diff", this.root).index(row);
        this.seek(index, 0);
        this.onStandingsJump();
    }
}
