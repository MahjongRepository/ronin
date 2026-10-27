import $ from "jquery";

import { lastAction, roundName } from "./describe.js";
import { POSITION } from "./paipu.js";

/** Holding Back or Next steps again after this long, then every HOLD_REPEAT_MS: fast to skim, slow enough to follow. */
export const HOLD_DELAY_MS = 350;
export const HOLD_REPEAT_MS = 120;

/** Fewer tiles left in the wall than this is a low wall, as Tenhou warns of it. */
const LOW_WALL = 8;

const ENDED_EARLY = "The game ended here: the server stopped it";
const FINAL_STANDINGS = "Final standings";
const FINAL_ROUND = "All last";

const SVG_NS = "http://www.w3.org/2000/svg";

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

/** The info: the last action (the one live region) above the round and step, and a line for the early end. */
function infoMarkup() {
    return $('<div class="replay-position">').append(
        $('<p class="replay-action" aria-live="polite">'),
        $('<p class="replay-where">').append(
            $('<span class="replay-round" lang="ja">'),
            $('<span class="replay-final badge">').text(FINAL_ROUND),
            $('<span class="replay-step">'),
            $('<span class="replay-wall-low badge">'),
        ),
        $('<p class="replay-ended">'),
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
 * The replay's control strip: first, previous round, Back, Next, next round and last, and the position's info (the
 * last action, the round with its all-last flag, the step, a low-wall warning). Back and Next step once per press and
 * repeat while held, stopping at a result or where they can go no further.
 */
export class ReplayControls {
    #holdTimer = null;
    #pressed = new Set();

    constructor(replay) {
        this.replay = replay;
        this.viewer = null;
        this.buttons = {
            back: stepButton("back", "Back", "◀", true),
            next: stepButton("next", "Next", "▶", false),
            ...Object.fromEntries(JUMPS.map((jump) => [jump.name, jumpButton(jump)])),
        };
        const { first, prevRound, back, next, nextRound, last } = this.buttons;
        this.element = $('<nav class="replay-controls" aria-label="Replay" lang="en">').append(
            infoMarkup(),
            $('<div class="replay-buttons">').append(first, prevRound, back, next, nextRound, last),
        );
        this.action = $(".replay-action", this.element);
    }

    /** Drive `viewer` from the buttons. */
    bind(viewer) {
        this.viewer = viewer;
        for (const jump of JUMPS) {
            this.buttons[jump.name].on("click", () => jump.move(viewer));
        }
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

    /** Hold the live region while repeating, so a screen reader announces where the hold ends rather than every step. */
    startHold(step) {
        this.stopHold();
        this.action.attr("aria-busy", "true");
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
        this.action.removeAttr("aria-busy");
    }

    /** Show the viewer's `state`: the buttons it allows and the position's info. */
    show(state) {
        const { first, prevRound, back, next, nextRound, last } = this.buttons;
        const all = Object.values(this.buttons);
        setEnabled(first, state.canBack, all);
        setEnabled(prevRound, state.canBack, all);
        setEnabled(back, state.canBack, [next, ...all]);
        setEnabled(next, state.canNext, [back, ...all]);
        setEnabled(nextRound, state.canNextRound, all);
        setEnabled(last, !state.atEnd, all);
        this.showInfo(state);
    }

    showInfo(state) {
        const round = this.replay.rounds[state.round];
        const info = this.element;
        this.showAction(lastAction(this.replay, state));
        $(".replay-round", info).text(roundName(round));
        $(".replay-final", info).toggleClass("hide", !round.final);
        $(".replay-step", info).text(stepText(round, state));
        const warning = wallWarning(state);
        $(".replay-wall-low", info)
            .text(warning)
            .toggleClass("hide", warning === "");
        $(".replay-ended", info).text(state.endedEarly ? ENDED_EARLY : "");
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
