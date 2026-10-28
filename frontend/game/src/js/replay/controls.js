import $ from "jquery";

import { CUT_OFF, lastAction, outcomeParts, roundName, seatName } from "./describe.js";
import { POSITION } from "./paipu.js";
import { writeReplayPrefs } from "./prefs.js";
import { AUTOPLAY_SPEED, AUTOPLAY_SPEEDS } from "./speeds.js";

/** Holding Back or Next steps again after this long, then every HOLD_REPEAT_MS: fast to skim, slow enough to follow. */
export const HOLD_DELAY_MS = 350;
export const HOLD_REPEAT_MS = 120;

/** Fewer tiles left in the wall than this is a low wall, as Tenhou warns of it. */
const LOW_WALL = 8;

const FINAL_STANDINGS = "Final standings";
const FINAL_ROUND = "All last";

const SVG_NS = "http://www.w3.org/2000/svg";

const SEATS = 4;
const OPTIONS_ID = "replay-options";
const ROUNDS_ID = "replay-rounds";
const ROUNDS_TITLE_ID = "replay-rounds-title";

/**
 * The layouts whose strip has the room to show the round list in the info's place, where a move closes it so the info
 * shows again: a short landscape screen and an upright phone (`_replay.scss`'s `$short-landscape` and `_theme.scss`'s
 * `$portrait-touch`, which the two must match).
 */
export const ROUNDS_IN_STRIP_MEDIA =
    "screen and (height <= 450px) and (orientation: landscape), " +
    "screen and (width <= 800px) and (height >= 451px) and (pointer: coarse) and (orientation: portrait)";

/** The jump buttons, each with its icon as polygon point lists and a bar on a 24-unit square. */
const JUMPS = Object.freeze([
    {
        name: "first",
        className: "first",
        caption: "Start",
        label: "Game start",
        icon: { polygons: ["19,5 19,19 8,12"], bar: 4 },
        move: (viewer) => viewer.first(),
    },
    {
        name: "prevRound",
        className: "prev-round",
        caption: "Round",
        label: "Round start / previous round",
        icon: { polygons: ["12,5 12,19 3,12", "21,5 21,19 12,12"] },
        move: (viewer) => viewer.prevRound(),
    },
    {
        name: "nextRound",
        className: "next-round",
        caption: "Round",
        captionFirst: true,
        label: "Next round",
        icon: { polygons: ["3,5 3,19 12,12", "12,5 12,19 21,12"] },
        move: (viewer) => viewer.nextRound(),
    },
    {
        name: "last",
        className: "last",
        caption: "End",
        captionFirst: true,
        label: "Game end",
        icon: { polygons: ["5,5 5,19 16,12"], bar: 17.5 },
        move: (viewer) => viewer.last(),
    },
]);

/** The Play button's two faces: it starts autoplay, and while autoplay runs it pauses it. */
const PLAY = Object.freeze({
    text: "Play",
    title: "Play (pauses at each result)",
    icon: { polygons: ["6,4 6,20 20,12"] },
});
const PAUSE = Object.freeze({
    text: "Pause",
    title: "Pause",
    icon: { polygons: ["6,5 10,5 10,19 6,19", "14,5 18,5 18,19 14,19"] },
});

const STEPS = Object.freeze({
    back: { move: (viewer) => viewer.back(), canMove: (state) => state.canBack },
    next: { move: (viewer) => viewer.next(), canMove: (state) => state.canNext },
});

function svgElement(name, attributes) {
    const element = document.createElementNS(SVG_NS, name);
    for (const [key, value] of Object.entries(attributes)) {
        element.setAttribute(key, value);
    }
    return element;
}

function icon({ polygons, bar }) {
    const svg = svgElement("svg", {
        viewBox: "0 0 24 24",
        "aria-hidden": "true",
        focusable: "false",
    });
    for (const points of polygons) {
        svg.append(svgElement("polygon", { points }));
    }
    if (bar !== undefined) {
        svg.append(svgElement("rect", { x: bar, y: 5, width: 2.5, height: 14 }));
    }
    return svg;
}

function jumpButton(jump) {
    const caption = $('<span class="replay-caption" aria-hidden="true">').text(jump.caption);
    const glyph = icon(jump.icon);
    return $(`<button type="button" class="replay-jump replay-${jump.className}">`)
        .attr({ "aria-label": jump.label, title: jump.label })
        .append(jump.captionFirst ? [caption, glyph] : [glyph, caption]);
}

function stepButton(name, text, arrow, arrowFirst) {
    const glyph = $('<span aria-hidden="true">').text(arrow);
    return $(`<button type="button" class="replay-step-button replay-${name}">`)
        .attr({ "aria-label": text, title: `${text} (hold to repeat)` })
        .append(arrowFirst ? [glyph, ` ${text}`] : [`${text} `, glyph]);
}

function playButton() {
    return $('<button type="button" class="replay-step-button replay-play">');
}

/** The Play button's face for `playing`: filled, and offering to pause, while autoplay runs. */
function showPlayFace(button, playing) {
    const face = playing ? PAUSE : PLAY;
    button
        .attr({ "aria-label": face.text, title: face.title })
        .toggleClass("replay-playing", playing)
        .empty()
        .append(icon(face.icon), $("<span>").text(face.text));
}

function speedName(speed) {
    return speed[0].toUpperCase() + speed.slice(1);
}

/** The round's name, which opens the round list: "東一局 0本場 · Rounds ▾". */
function roundsToggle() {
    return $('<button type="button" class="replay-rounds-toggle" aria-expanded="false">')
        .attr({ "aria-controls": ROUNDS_ID, title: "Round list" })
        .append(
            $('<span class="replay-round" lang="ja">'),
            $('<span class="replay-rounds-word">').text(" · Rounds"),
            $('<span class="replay-rounds-chevron" aria-hidden="true">').text("▾"),
        );
}

/** The info: the last action (the one live region) above the round and step, and a line for the early end. */
function infoMarkup(toggle) {
    return $('<div class="replay-position">').append(
        $('<p class="replay-action" aria-live="polite">'),
        $('<p class="replay-where">').append(
            toggle,
            $('<span class="replay-final badge">').text(FINAL_ROUND),
            $('<span class="replay-step">'),
            $('<span class="replay-wall-low badge">'),
        ),
        $('<p class="replay-ended">'),
    );
}

/** The secondary choices: the seat at the bottom of the table, autoplay's speed and whether opponents' hands are hidden. */
function optionsMarkup() {
    return $(`<div class="replay-options" id="${OPTIONS_ID}" role="group">`)
        .attr("aria-label", "Replay options")
        .append(
            $('<label class="replay-option replay-option-seat">').append(
                $("<span>").text("View from"),
                $('<select class="replay-select replay-seat">'),
            ),
            $('<label class="replay-option replay-option-speed">').append(
                $("<span>").text("Speed"),
                $('<select class="replay-select replay-speed">').append(
                    Object.keys(AUTOPLAY_SPEEDS).map((speed) =>
                        $("<option>").val(speed).text(speedName(speed)),
                    ),
                ),
            ),
            $('<label class="replay-option">').append(
                $('<input type="checkbox" role="switch" class="replay-hide-hands">'),
                $("<span>").text("Hide opponents' hands"),
            ),
        );
}

/** Every round of the replay with its outcome, each a button to its deal. */
function roundsMarkup(replay) {
    const entries = replay.rounds.map((round, index) =>
        $("<li>").append(
            $('<button type="button" class="replay-round-entry">')
                .attr("data-round", index)
                .append(
                    $('<span class="replay-round-name" lang="ja">').text(roundName(round)),
                    $('<span class="replay-round-outcome">').append(
                        actionNodes(outcomeParts(replay, round)),
                    ),
                ),
        ),
    );
    return $(`<section class="replay-rounds" id="${ROUNDS_ID}">`)
        .attr("aria-labelledby", ROUNDS_TITLE_ID)
        .append(
            $('<div class="replay-rounds-head">').append(
                $(`<h2 id="${ROUNDS_TITLE_ID}">`).text("Rounds"),
                $('<button type="button" class="replay-rounds-close">')
                    .attr({ "aria-label": "Close the round list", title: "Close" })
                    .append($('<span aria-hidden="true">').text("✕")),
            ),
            $('<ol class="replay-round-list">').append(entries),
        );
}

/** Opens the options in the info's place where the strip has no room for both; it names the seat viewed from and the speed. */
function optionsToggle() {
    return $('<button type="button" class="replay-options-toggle" aria-expanded="false">')
        .attr({ "aria-controls": OPTIONS_ID, title: "Replay options" })
        .append(
            $('<span class="replay-options-view">'),
            $('<span class="replay-options-tail">').append(
                $('<span class="replay-options-speed">'),
                $('<span class="replay-options-chevron" aria-hidden="true">').text("▾"),
            ),
        );
}

/** Where the position stands in its round, counted from 1 at the deal; the standings are not a step of the round. */
function stepText(round, state) {
    if (state.kind === POSITION.SUMMARY) {
        return FINAL_STANDINGS;
    }
    const steps = round.positions.filter((position) => position.kind !== POSITION.SUMMARY);
    return `Step ${state.step + 1}\u00a0/\u00a0${steps.length}`;
}

/** The low-wall warning while the round is in play; a result or the standings show none. */
function wallWarning(state) {
    const inPlay = state.kind !== POSITION.RESULT && state.kind !== POSITION.SUMMARY;
    return inPlay && state.tilesLeft < LOW_WALL ? `Wall low: ${state.tilesLeft} left` : "";
}

function actionNodes(parts) {
    return parts.map((part) =>
        typeof part === "string"
            ? document.createTextNode(part)
            : $('<span lang="ja">').text(part.ja),
    );
}

function plainText(parts) {
    return parts.map((part) => (typeof part === "string" ? part : part.ja)).join("");
}

/** Enable or disable a button, first handing its focus to a neighbour that stays enabled, so the keyboard keeps a place. */
function setEnabled(button, enabled, neighbours) {
    if (!enabled && document.activeElement === button[0]) {
        neighbours
            .find((neighbour) => neighbour[0] !== button[0] && !neighbour.prop("disabled"))
            ?.trigger("focus");
    }
    button.prop("disabled", !enabled);
}

/**
 * The replay's control strip: first, previous round, Back, Play, Next, next round and last, the position's info (the
 * last action, the round with its all-last flag, the step, a low-wall warning) and the replay options (the viewpoint
 * seat, autoplay's speed, hiding opponents' hands), beside the buttons on a wide screen and behind a toggle elsewhere, and
 * the round list with each round's outcome, opened from the round's name, beside the table or in the info's place.
 * Back and Next step once per press and repeat while held, stopping at a result or where they can go no further; Play
 * starts and pauses the viewer's autoplay.
 */
export class ReplayControls {
    #holdTimer = null;
    #holding = false;
    #pressed = new Set();

    constructor(replay) {
        this.replay = replay;
        this.viewer = null;
        this.buttons = {
            back: stepButton("back", "Back", "◀", true),
            play: playButton(),
            next: stepButton("next", "Next", "▶", false),
            ...Object.fromEntries(JUMPS.map((jump) => [jump.name, jumpButton(jump)])),
        };
        const { first, prevRound, back, play, next, nextRound, last } = this.buttons;
        this.optionsToggle = optionsToggle();
        this.roundsToggle = roundsToggle();
        this.rounds = roundsMarkup(replay);
        this.element = $('<nav class="replay-controls" aria-label="Replay" lang="en">').append(
            infoMarkup(this.roundsToggle),
            $('<div class="replay-buttons">').append(
                first,
                prevRound,
                back,
                play,
                next,
                nextRound,
                last,
            ),
            this.optionsToggle,
            optionsMarkup(),
            this.rounds,
        );
        this.action = $(".replay-action", this.element);
        this.seat = $(".replay-seat", this.element);
        this.hideHands = $(".replay-hide-hands", this.element);
        this.speed = $(".replay-speed", this.element);
        this.shownPlaying = null;
        this.seatsRound = null;
        this.shownPosition = null;
        this.listedRound = null;
    }

    /** Drive `viewer` from the buttons. */
    bind(viewer) {
        this.viewer = viewer;
        for (const jump of JUMPS) {
            this.buttons[jump.name].on("click", () => jump.move(viewer));
        }
        this.buttons.play.on("click", () =>
            viewer.state.playing ? viewer.pause() : viewer.play(),
        );
        for (const [name, step] of Object.entries(STEPS)) {
            this.bindHold(name, step);
        }
        $(window).on("pointerup.replay pointercancel.replay blur.replay pagehide.replay", () =>
            this.stopHold(),
        );
        $(document).on("visibilitychange.replay", () => {
            if (document.hidden) {
                this.stopHold();
            }
        });
        this.element.on("contextmenu", "button", (event) => event.preventDefault());
        this.bindOptions(viewer);
        this.bindRounds(viewer);
    }

    /**
     * The options change the view at the position shown or autoplay's pace; the speed and the hidden-hands choice are
     * remembered for later replays. Where they open in the info's place, a seat or speed change, Escape or any move but
     * autoplay's closes them, so the info shows again.
     */
    bindOptions(viewer) {
        this.optionsToggle.on("click", () => {
            const open = !this.optionsOpen;
            if (open) {
                this.setRoundsOpen(false);
            }
            this.setOptionsOpen(open);
        });
        this.seat.on("change", () => {
            viewer.setViewpoint(Number(this.seat.val()));
            this.setOptionsOpen(false);
        });
        this.speed.on("change", () => {
            const speed = this.speed.val();
            writeReplayPrefs({ speed });
            viewer.setSpeed(speed);
            this.setOptionsOpen(false);
        });
        this.hideHands.on("change", () => {
            const hidden = this.hideHands.prop("checked");
            writeReplayPrefs({ hideHands: hidden });
            viewer.setOpenHands(!hidden);
        });
        $(window).on("keydown.replay", (event) => {
            if (event.key !== "Escape" || !this.optionsOpen) {
                return;
            }
            const focused = $.contains(this.options()[0], document.activeElement);
            this.setOptionsOpen(false);
            if (focused) {
                this.optionsToggle.trigger("focus");
            }
        });
    }

    /**
     * The round's name opens the round list, at the round shown, and Escape closes it; a round picked there is shown from
     * its deal, a manual move that pauses autoplay. The list and the options never show together, so Escape closes the
     * one open.
     */
    bindRounds(viewer) {
        this.roundsToggle.on("click", () => {
            const open = !this.roundsOpen;
            this.setRoundsOpen(open);
            if (open) {
                this.currentEntry().trigger("focus");
            }
        });
        $(".replay-rounds-close", this.rounds).on("click", () => this.setRoundsOpen(false));
        this.rounds.on("click", ".replay-round-entry", (event) => {
            viewer.seek(Number(event.currentTarget.dataset.round), 0);
            if (this.roundsInStrip()) {
                this.setRoundsOpen(false);
            }
        });
        $(window).on("keydown.replay", (event) => {
            if (event.key === "Escape" && this.roundsOpen) {
                this.setRoundsOpen(false);
            }
        });
    }

    get roundsOpen() {
        return this.roundsToggle.attr("aria-expanded") === "true";
    }

    currentEntry() {
        return $('.replay-round-entry[aria-current="true"]', this.rounds);
    }

    scrollToCurrentEntry(block) {
        this.currentEntry()[0]?.scrollIntoView?.({ block });
    }

    /** Open or close the round list; closing it hands the keyboard focus it held back to the round's name. */
    setRoundsOpen(open) {
        if (open) {
            this.setOptionsOpen(false);
        }
        const focused = $.contains(this.rounds[0], document.activeElement);
        this.roundsToggle.attr("aria-expanded", String(open));
        $(".replay-rounds-chevron", this.roundsToggle).text(open ? "▴" : "▾");
        this.element.toggleClass("replay-rounds-open", open);
        if (open) {
            this.scrollToCurrentEntry("center");
        } else if (focused) {
            this.roundsToggle.trigger("focus");
        }
    }

    /** Whether the open round list takes the info's place, where a move closes it so the info shows again. */
    roundsInStrip() {
        return this.roundsOpen && window.matchMedia(ROUNDS_IN_STRIP_MEDIA).matches;
    }

    /** Give the keyboard focus to the round's name, as after a jump from the standings, whose button the jump hides. */
    focusRounds() {
        this.roundsToggle.trigger("focus");
    }

    get optionsOpen() {
        return this.optionsToggle.attr("aria-expanded") === "true";
    }

    options() {
        return $(".replay-options", this.element);
    }

    setOptionsOpen(open) {
        this.optionsToggle.attr("aria-expanded", String(open));
        this.element.toggleClass("replay-options-open", open);
        $(".replay-options-chevron", this.optionsToggle).text(open ? "▴" : "▾");
    }

    /**
     * A press steps at once and repeats while held. The click that ends a press is that press's own, so it does not
     * step again; a click with no press before it (the keyboard's Enter or Space) steps once, and a held key steps
     * only once.
     */
    bindHold(name, step) {
        const button = this.buttons[name];
        button.on("pointerdown", (event) => {
            if ((event.button ?? 0) !== 0) {
                return;
            }
            this.#pressed.add(name);
            this.startHold(step);
        });
        button.on("pointerleave pointercancel", (event) => {
            if (event.type === "pointercancel") {
                this.#pressed.delete(name);
            }
            this.stopHold();
        });
        button.on("keydown", (event) => {
            this.#pressed.delete(name);
            if (event.originalEvent?.repeat) {
                event.preventDefault();
            }
        });
        button.on("click", () => {
            if (!this.#pressed.delete(name)) {
                step.move(this.viewer);
            }
        });
    }

    startHold(step) {
        this.stopHold();
        this.#holding = true;
        this.showBusy(this.viewer.state);
        this.holdStep(step, HOLD_DELAY_MS);
    }

    holdStep(step, delay) {
        step.move(this.viewer);
        const state = this.viewer.state;
        const stop = state.kind === POSITION.RESULT || state.kind === POSITION.SUMMARY;
        if (stop || !step.canMove(state)) {
            this.stopHold();
            return;
        }
        this.#holdTimer = setTimeout(() => this.holdStep(step, HOLD_REPEAT_MS), delay);
    }

    stopHold() {
        clearTimeout(this.#holdTimer);
        this.#holdTimer = null;
        this.#holding = false;
        if (this.viewer !== null) {
            this.showBusy(this.viewer.state);
        }
    }

    /**
     * Hold the live region while Back or Next repeats and while autoplay runs faster than slow, so a screen reader
     * announces where they stop rather than every step.
     */
    showBusy(state) {
        const busy = this.#holding || (state.playing && state.speed !== AUTOPLAY_SPEED.SLOW);
        if (busy) {
            this.action.attr("aria-busy", "true");
        } else {
            this.action.removeAttr("aria-busy");
        }
    }

    /** Show the viewer's `state`: the buttons it allows and the position's info. */
    show(state) {
        const { first, prevRound, back, play, next, nextRound, last } = this.buttons;
        const all = Object.values(this.buttons);
        setEnabled(first, state.canBack, all);
        setEnabled(prevRound, state.canBack, all);
        setEnabled(back, state.canBack, [next, ...all]);
        setEnabled(play, state.playing || state.canNext, [back, ...all]);
        setEnabled(next, state.canNext, [back, ...all]);
        setEnabled(nextRound, state.canNextRound, all);
        setEnabled(last, !state.atEnd, all);
        if (this.shownPlaying !== state.playing) {
            this.shownPlaying = state.playing;
            showPlayFace(play, state.playing);
        }
        this.showBusy(state);
        this.showInfo(state);
        this.showRounds(state);
        this.showOptions(state);
    }

    /** The round list marks the round shown, scrolled into view when the round changes. */
    showRounds(state) {
        if (this.listedRound === state.round) {
            return;
        }
        this.listedRound = state.round;
        const entries = $(".replay-round-entry", this.rounds);
        entries.removeAttr("aria-current");
        entries.eq(state.round).attr("aria-current", "true");
        if (this.roundsOpen) {
            this.scrollToCurrentEntry("nearest");
        }
    }

    /**
     * The seats as the shown round names them, the viewpoint's selected, the speed and the hidden-hands switch; a move to
     * another position closes the options, and a round list in the info's place, unless autoplay made it.
     */
    showOptions(state) {
        if (this.seatsRound !== state.round) {
            const round = this.replay.rounds[state.round];
            const seats = Array.from({ length: SEATS }, (_, seat) =>
                $("<option>")
                    .val(seat)
                    .text(seatName(round, seat, this.replay.players[seat])),
            );
            this.seat.empty().append(seats);
            this.seatsRound = state.round;
        }
        this.seat.val(String(state.seat));
        this.speed.val(state.speed);
        this.hideHands.prop("checked", !state.openHands);
        $(".replay-options-view", this.optionsToggle).text(
            `View: ${this.replay.players[state.seat]}`,
        );
        $(".replay-options-speed", this.optionsToggle).text(` · ${speedName(state.speed)}`);
        const position = `${state.round}/${state.step}/${state.page}`;
        if (position !== this.shownPosition) {
            this.shownPosition = position;
            if (!state.playing) {
                this.setOptionsOpen(false);
                if (this.roundsInStrip()) {
                    this.setRoundsOpen(false);
                }
            }
        }
    }

    showInfo(state) {
        const round = this.replay.rounds[state.round];
        const info = this.element;
        this.showAction(lastAction(this.replay, state));
        const name = roundName(round);
        $(".replay-round", info).text(name);
        this.roundsToggle.attr("aria-label", `Round list, ${name}`);
        $(".replay-final", info).toggleClass("hide", !round.final);
        $(".replay-step", info).text(stepText(round, state));
        const warning = wallWarning(state);
        $(".replay-wall-low", info)
            .text(warning)
            .toggleClass("hide", warning === "");
        $(".replay-ended", info).text(state.endedEarly ? CUT_OFF : "");
    }

    /** Write the action line only when it changes, so its live region announces each action once. */
    showAction(parts) {
        const text = plainText(parts);
        if (this.action.text() === text) {
            return;
        }
        this.action.empty().append(actionNodes(parts)).attr("title", text);
    }
}
