"use strict";

/**
 * The seat's own countdown, kept on the client from the timer settings (tm) of game_started or the reconnect snapshot,
 * the way the server's TurnTimer paces the seat: a turn runs its base time, then drains the bank; a call prompt runs
 * the fixed call decision time and leaves the bank alone; each round start adds the round bonus, up to the cap. A
 * decision runs from the server message that opens its wait to the one that ends it, as the server's timer does, so a
 * refused answer keeps it running; an answer whose ending message can lag (a kan, behind other seats' chankan prompt)
 * holds it until then. A wait the server re-sends after a reconnect names how long it has run, and the decision is
 * backdated by that much, so a taken-over turn counts down what is left and charges the bank what the server will.
 * It is never synced otherwise, so it may drift from the server's by network delays.
 */
class TurnClock {

    constructor(now = () => Date.now()) {
        this.now = now;
        this.settings = null;
        this.bank = 0;
        this.decision = null;
    }

    configure(tm) {
        this.settings = tm;
        this.bank = tm.bk;
        this.decision = null;
    }

    addRoundBonus() {
        this.bank = Math.min(this.bank + this.settings.rb, this.settings.mb);
    }

    /**
     * Open a turn that has run for elapsed seconds; return what is left of its [base, bank] seconds, the limit and
     * allowance of majiang-ui's timer.
     */
    startTurn(elapsed = 0) {
        this.open(true, elapsed);
        return this.remaining();
    }

    /** Open a call prompt that has run for elapsed seconds; return what is left of its [decision, 0] seconds. */
    startCallDecision(elapsed = 0) {
        this.open(false, elapsed);
        return this.remaining();
    }

    open(turn, elapsed) {
        this.stop();
        this.decision = { turn, startedAt: this.now() - elapsed * 1000 };
    }

    /** What is left of the open decision, as [limit, allowance] seconds; null when none is open. */
    remaining() {
        if (! this.decision) return null;
        const elapsed = this.elapsed();
        if (! this.decision.turn) return [Math.max(0, this.settings.md - elapsed), 0];
        return [Math.max(0, this.settings.tb - elapsed), Math.max(0, this.bank - this.overtime(elapsed))];
    }

    /** Hold the open decision at the seat's answer, until the server ends or refuses it. */
    pause() {
        if (this.decision) this.decision = { ...this.decision, pausedAt: this.now() };
    }

    /** Let a refused answer's decision run on: the server's timer never stopped. */
    resume() {
        if (this.decision) this.decision = { turn: this.decision.turn, startedAt: this.decision.startedAt };
    }

    /** End the open decision, if any; a turn takes what it used beyond its base time from the bank. */
    stop() {
        if (! this.decision) return;
        if (this.decision.turn) this.bank = Math.max(0, this.bank - this.overtime(this.elapsed()));
        this.decision = null;
    }

    elapsed() {
        return ((this.decision.pausedAt ?? this.now()) - this.decision.startedAt) / 1000;
    }

    overtime(elapsed) {
        return Math.max(0, elapsed - this.settings.tb);
    }
}

export default TurnClock;
