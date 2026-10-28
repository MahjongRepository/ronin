import $ from "jquery";

import { t } from "../../i18n/index.js";
import { actionNodes, cutOffText, lastAction, seatName } from "./describe.js";
import { ReplayHelp } from "./help.js";
import { HOLD_DELAY_MS, HOLD_REPEAT_MS } from "./hold.js";
import { COMMAND, ariaKeys, shownKeys } from "./keys.js";
import { UPRIGHT_PHONE_MEDIA } from "./media.js";
import { POSITION } from "./paipu.js";
import { writeReplayPrefs } from "./prefs.js";
import { ReplayRounds } from "./rounds.js";
import { SEATS } from "./seats.js";
import { AUTOPLAY_SPEED, AUTOPLAY_SPEEDS } from "./speeds.js";

/** Fewer tiles left in the wall than this is a low wall, as Tenhou warns of it. */
const LOW_WALL = 8;

const SVG_NS = "http://www.w3.org/2000/svg";

const OPTIONS_ID = "replay-options";

/**
 * The layouts that show the options beside the info, never in its place, their toggle hidden: a wide screen and an
 * upright phone (`_replay.scss`'s `options-beside-info` includes, which the two must match).
 */
const OPTIONS_BESIDE_INFO_MEDIA = `(width >= 1280px) and (height > 450px), ${UPRIGHT_PHONE_MEDIA}`;

/** The jump buttons, each with its caption and label keys and its icon as polygon point lists and a bar on a 24-unit square. */
const JUMPS = Object.freeze([
    {
        name: COMMAND.FIRST,
        className: "first",
        caption: "replay.jump.start_caption",
        label: "replay.jump.first",
        icon: { polygons: ["19,5 19,19 8,12"], bar: 4 },
        move: (viewer) => viewer.first(),
    },
    {
        name: COMMAND.PREV_ROUND,
        className: "prev-round",
        caption: "replay.jump.round_caption",
        label: "replay.jump.prev_round",
        icon: { polygons: ["12,5 12,19 3,12", "21,5 21,19 12,12"] },
        move: (viewer) => viewer.prevRound(),
    },
    {
        name: COMMAND.NEXT_ROUND,
        className: "next-round",
        caption: "replay.jump.round_caption",
        captionFirst: true,
        label: "replay.jump.next_round",
        icon: { polygons: ["3,5 3,19 12,12", "12,5 12,19 21,12"] },
        move: (viewer) => viewer.nextRound(),
    },
    {
        name: COMMAND.LAST,
        className: "last",
        caption: "replay.jump.end_caption",
        captionFirst: true,
        label: "replay.jump.last",
        icon: { polygons: ["5,5 5,19 16,12"], bar: 17.5 },
        move: (viewer) => viewer.last(),
    },
]);

/** The Play button's two faces, by catalog key: it starts autoplay, and while autoplay runs it pauses it. */
const PLAY = Object.freeze({
    text: "replay.play",
    title: "replay.play_title",
    icon: { polygons: ["6,4 6,20 20,12"] },
});
const PAUSE = Object.freeze({
    text: "replay.pause",
    title: "replay.pause_title",
    icon: { polygons: ["6,5 10,5 10,19 6,19", "14,5 18,5 18,19 14,19"] },
});

const STEPS = Object.freeze({
    [COMMAND.BACK]: { move: (viewer) => viewer.back(), canMove: (state) => state.canBack },
    [COMMAND.NEXT]: { move: (viewer) => viewer.next(), canMove: (state) => state.canNext },
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
    const caption = $('<span class="replay-caption" aria-hidden="true">').text(t(jump.caption));
    const glyph = icon(jump.icon);
    const label = t(jump.label);
    return $(`<button type="button" class="replay-jump replay-${jump.className}">`)
        .attr({
            "aria-label": label,
            "aria-keyshortcuts": ariaKeys(jump.name),
            title: `${label} (${shownKeys(jump.name)})`,
        })
        .append(jump.captionFirst ? [caption, glyph] : [glyph, caption]);
}

function stepButton(name, key, arrow, arrowFirst) {
    const text = t(key);
    const glyph = $('<span aria-hidden="true">').text(arrow);
    return $(`<button type="button" class="replay-step-button replay-${name}">`)
        .attr({
            "aria-label": text,
            "aria-keyshortcuts": ariaKeys(name),
            title: t("replay.step_title", { label: text, keys: shownKeys(name) }),
        })
        .append(
            arrowFirst
                ? [glyph, document.createTextNode(` ${text}`)]
                : [document.createTextNode(`${text} `), glyph],
        );
}

function playButton() {
    return $('<button type="button" class="replay-step-button replay-play">').attr(
        "aria-keyshortcuts",
        ariaKeys(COMMAND.PLAY),
    );
}

/** The Play button's face for `playing`: filled, and offering to pause, while autoplay runs. */
function showPlayFace(button, playing) {
    const face = playing ? PAUSE : PLAY;
    const text = t(face.text);
    button
        .attr({ "aria-label": text, title: t(face.title, { keys: shownKeys(COMMAND.PLAY) }) })
        .toggleClass("replay-playing", playing)
        .empty()
        .append(icon(face.icon), $("<span>").text(text));
}

function speedName(speed) {
    return t(`replay.speed.${speed}`);
}

/**
 * The info: the last action (the one live region) above the round and step, with the help's toggle at the end of
 * their line, and a line for the early end.
 */
function infoMarkup(roundsButton, helpButton) {
    return $('<div class="replay-position">').append(
        $('<p class="replay-action" aria-live="polite">'),
        $('<p class="replay-where">').append(
            $('<span class="replay-where-text">').append(
                roundsButton,
                $('<span class="replay-final badge">').text(t("replay.final_round")),
                $('<span class="replay-step">'),
                $('<span class="replay-wall-low badge">'),
            ),
            helpButton,
        ),
        $('<p class="replay-ended">'),
    );
}

/** The secondary choices: the seat at the bottom of the table, autoplay's speed and whether opponents' hands are hidden. */
function optionsMarkup() {
    return $(`<div class="replay-options" id="${OPTIONS_ID}" role="group">`)
        .attr("aria-label", t("replay.options.label"))
        .append(
            $('<label class="replay-option replay-option-seat">').append(
                $("<span>").text(t("replay.options.view_from")),
                $('<select class="replay-select replay-seat">'),
            ),
            $('<label class="replay-option replay-option-speed">').append(
                $("<span>").text(t("replay.options.speed")),
                $('<select class="replay-select replay-speed">').append(
                    Object.keys(AUTOPLAY_SPEEDS).map((speed) =>
                        $("<option>").val(speed).text(speedName(speed)),
                    ),
                ),
            ),
            $('<label class="replay-option">').append(
                $('<input type="checkbox" role="switch" class="replay-hide-hands">'),
                $("<span>").text(t("replay.options.hide_hands")),
            ),
        );
}

/**
 * Opens the options in the info's place where the strip has no room for both; it names the seat viewed from and the
 * speed, the dot between them kept with the seat so a wrapped speed never starts its line with it.
 */
function optionsToggle() {
    return $('<button type="button" class="replay-options-toggle" aria-expanded="false">')
        .attr({ "aria-controls": OPTIONS_ID, title: t("replay.options.label") })
        .append(
            $('<span class="replay-options-head">').append($('<span class="replay-options-view">')),
            $('<span class="replay-options-tail">').append(
                $('<span class="replay-options-speed">'),
                $('<span class="replay-options-chevron" aria-hidden="true">').text("▾"),
            ),
        );
}

/** Where the position stands in its round, counted from 1 at the deal; the standings are no step of it and have none. */
function stepText(round, state) {
    if (state.kind === POSITION.SUMMARY) {
        return "";
    }
    const steps = round.positions.filter((position) => position.kind !== POSITION.SUMMARY);
    return t("replay.step", { step: state.step + 1, steps: steps.length });
}

/** The low-wall warning while the round is in play; a result or the standings show none. */
function wallWarning(state) {
    const inPlay = state.kind !== POSITION.RESULT && state.kind !== POSITION.SUMMARY;
    return inPlay && state.tilesLeft < LOW_WALL
        ? t("replay.wall_low", { tiles: state.tilesLeft })
        : "";
}

function plainText(parts) {
    return parts.map((part) => (typeof part === "string" ? part : part.ja)).join("");
}

/**
 * After a select is changed with the pointer, the keyboard focus returns to the page, so the replay's keys work again;
 * a change made with the keyboard keeps the focus there.
 */
function releaseFocusAfterPointerChange(select) {
    let byPointer = false;
    select.on("pointerdown", () => {
        byPointer = true;
    });
    select.on("keydown", () => {
        byPointer = false;
    });
    select.on("change", () => {
        if (byPointer) {
            select.trigger("blur");
        }
        byPointer = false;
    });
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
 * the round list with each round's outcome (`rounds.js`), opened from the round's name, beside the table or in the
 * info's place. Back and Next step once per press and repeat while held, stopping at a result or where they can go no
 * further; Play starts and pauses the viewer's autoplay. A help popover over the table, opened from the info's round
 * line, lists the keys (`keys.js`) the buttons announce and what the pointer does where (`help.js`); the keys reach the
 * strip through its methods. `closeSettings` closes the settings gear's menu, which the help closes with the options
 * and the round list, so that Escape closes what shows.
 */
export class ReplayControls {
    #replay;
    #viewer = null;
    #buttons;
    #optionsToggle;
    #rounds;
    #help;
    #action;
    #seat;
    #hideHands;
    #speed;
    #holdTimer = null;
    #holding = false;
    #keyHeld = false;
    #pressed = new Set();
    #shownPlaying = null;
    #seatsRound = null;
    #shownPosition = null;

    constructor(replay, { closeSettings }) {
        this.#replay = replay;
        this.#buttons = {
            [COMMAND.BACK]: stepButton(COMMAND.BACK, "replay.back", "◀", true),
            [COMMAND.PLAY]: playButton(),
            [COMMAND.NEXT]: stepButton(COMMAND.NEXT, "replay.next", "▶", false),
            ...Object.fromEntries(JUMPS.map((jump) => [jump.name, jumpButton(jump)])),
        };
        const { first, prevRound, back, play, next, nextRound, last } = this.#buttons;
        this.#optionsToggle = optionsToggle();
        this.#rounds = new ReplayRounds(replay, {
            beforeOpen: () => this.#setOptionsOpen(false),
            onOpenChange: (open) => this.element.toggleClass("replay-rounds-open", open),
        });
        this.#help = new ReplayHelp({
            beforeOpen: () => {
                closeSettings();
                this.#closeOptions();
                this.#rounds.setOpen(false);
            },
        });
        this.element = $('<nav class="replay-controls">')
            .attr("aria-label", t("replay.nav"))
            .append(
                infoMarkup(this.#rounds.button, this.#help.button),
                $('<div class="replay-buttons">').append(
                    first,
                    prevRound,
                    back,
                    play,
                    next,
                    nextRound,
                    last,
                ),
                this.#optionsToggle,
                optionsMarkup(),
                this.#rounds.element,
                this.#help.element,
            );
        this.#action = $(".replay-action", this.element);
        this.#seat = $(".replay-seat", this.element);
        this.#hideHands = $(".replay-hide-hands", this.element);
        this.#speed = $(".replay-speed", this.element);
    }

    /** Drive `viewer` from the buttons. */
    bind(viewer) {
        this.#viewer = viewer;
        for (const jump of JUMPS) {
            this.#buttons[jump.name].on("click", () => jump.move(viewer));
        }
        this.#buttons.play.on("click", () => this.togglePlay());
        for (const [name, step] of Object.entries(STEPS)) {
            this.#bindHold(name, step);
        }
        $(window)
            .off(".replay-controls")
            .on(
                "pointerup.replay-controls pointercancel.replay-controls blur.replay-controls pagehide.replay-controls",
                () => this.#stopHold(),
            );
        $(document)
            .off(".replay-controls")
            .on("visibilitychange.replay-controls", () => {
                if (document.hidden) {
                    this.#stopHold();
                }
            });
        this.element.on("contextmenu", "button", (event) => event.preventDefault());
        this.#bindOptions(viewer);
        this.#rounds.bind(viewer);
        this.#help.bind();
    }

    togglePlay() {
        const viewer = this.#viewer;
        if (viewer.state.playing) {
            viewer.pause();
        } else {
            viewer.play();
        }
    }

    viewNextSeat() {
        this.#viewer.setViewpoint((this.#viewer.state.seat + 1) % SEATS);
    }

    toggleHiddenHands() {
        this.#setHiddenHands(this.#viewer.state.openHands);
    }

    /**
     * Close the topmost of the help, the options in the info's place and the round list, and say whether one was open;
     * options shown beside the info are never "open".
     */
    closeTopmost() {
        if (this.#help.isOpen) {
            this.#help.setOpen(false);
            return true;
        }
        if (this.#optionsInPlace()) {
            this.#closeOptions();
            return true;
        }
        if (this.#rounds.isOpen) {
            this.#rounds.setOpen(false);
            return true;
        }
        return false;
    }

    /** Whether `element` is in the round list or the help, which keep the keys that move through or scroll them. */
    keepsNavigationKeys(element) {
        return this.#rounds.contains(element) || this.#help.contains(element);
    }

    /** Mark a held key's repeating steps as busy, as a held button's are. */
    setKeyHeld(held) {
        if (this.#keyHeld === held) {
            return;
        }
        this.#keyHeld = held;
        this.#showBusy(this.#viewer.state);
    }

    toggleHelp() {
        this.#help.toggleOpen();
    }

    /** Give the keyboard focus to the round's name, as after a jump from the standings, whose button the jump hides. */
    focusRounds() {
        this.#rounds.focusToggle();
    }

    /** Show the viewer's `state`: the buttons it allows and the position's info. */
    show(state) {
        const { first, prevRound, back, play, next, nextRound, last } = this.#buttons;
        const all = Object.values(this.#buttons);
        setEnabled(first, state.canBack, all);
        setEnabled(prevRound, state.canBack, all);
        setEnabled(back, state.canBack, [next, ...all]);
        setEnabled(play, state.playing || state.canNext, [back, ...all]);
        setEnabled(next, state.canNext, [back, ...all]);
        setEnabled(nextRound, state.canNextRound, all);
        setEnabled(last, !state.atEnd, all);
        if (this.#shownPlaying !== state.playing) {
            this.#shownPlaying = state.playing;
            showPlayFace(play, state.playing);
        }
        this.#showBusy(state);
        this.#showInfo(state);
        this.#rounds.show(state, this.#replay.rounds[state.round]);
        this.#showOptions(state);
    }

    /** Hide or show opponents' hands, a choice remembered for later replays. */
    #setHiddenHands(hidden) {
        writeReplayPrefs({ hideHands: hidden });
        this.#viewer.setOpenHands(!hidden);
    }

    /**
     * The options change the view at the position shown or autoplay's pace; the speed and the hidden-hands choice are
     * remembered for later replays. Where they open in the info's place, a seat or speed change, Escape (`closeTopmost`)
     * or any move but autoplay's closes them, so the info shows again.
     */
    #bindOptions(viewer) {
        this.#optionsToggle.on("click", () => {
            const open = !this.#optionsOpen;
            if (open) {
                this.#rounds.setOpen(false);
            }
            this.#setOptionsOpen(open);
        });
        releaseFocusAfterPointerChange(this.#seat);
        releaseFocusAfterPointerChange(this.#speed);
        window.matchMedia(OPTIONS_BESIDE_INFO_MEDIA).addEventListener("change", (event) => {
            if (event.matches) {
                this.#setOptionsOpen(false);
            }
        });
        this.#seat.on("change", () => {
            viewer.setViewpoint(Number(this.#seat.val()));
            this.#setOptionsOpen(false);
        });
        this.#speed.on("change", () => {
            const speed = this.#speed.val();
            writeReplayPrefs({ speed });
            viewer.setSpeed(speed);
            this.#setOptionsOpen(false);
        });
        this.#hideHands.on("change", () => this.#setHiddenHands(this.#hideHands.prop("checked")));
    }

    get #optionsOpen() {
        return this.#optionsToggle.attr("aria-expanded") === "true";
    }

    /** Whether the options are open in the info's place; beside the info they always show, with no toggle. */
    #optionsInPlace() {
        return this.#optionsOpen && !window.matchMedia(OPTIONS_BESIDE_INFO_MEDIA).matches;
    }

    /** Close the options, handing a keyboard focus they held in the info's place back to their toggle. */
    #closeOptions() {
        const focused = $.contains($(".replay-options", this.element)[0], document.activeElement);
        const inPlace = this.#optionsInPlace();
        this.#setOptionsOpen(false);
        if (inPlace && focused) {
            this.#optionsToggle.trigger("focus");
        }
    }

    #setOptionsOpen(open) {
        this.#optionsToggle.attr("aria-expanded", String(open));
        this.element.toggleClass("replay-options-open", open);
        $(".replay-options-chevron", this.#optionsToggle).text(open ? "▴" : "▾");
    }

    /**
     * A press steps at once and repeats while held. The click that ends a press is that press's own, so it does not
     * step again; a click with no press before it (the keyboard's Enter or Space) steps once, and a held key steps
     * only once. A press that disabled its own button (Next at the end) gets no click, so its end forgets it.
     */
    #bindHold(name, step) {
        const button = this.#buttons[name];
        button.on("pointerdown", (event) => {
            if ((event.button ?? 0) !== 0) {
                return;
            }
            this.#pressed.add(name);
            this.#startHold(step);
        });
        button.on("pointerleave pointercancel", (event) => {
            if (event.type === "pointercancel") {
                this.#pressed.delete(name);
            }
            this.#stopHold();
        });
        button.on("keydown", (event) => {
            this.#pressed.delete(name);
            const pressKey = event.key === "Enter" || event.key === " ";
            if (pressKey && event.originalEvent?.repeat) {
                event.preventDefault();
            }
        });
        button.on("click", () => {
            if (!this.#pressed.delete(name)) {
                step.move(this.#viewer);
            }
        });
    }

    #startHold(step) {
        this.#stopHold();
        this.#holding = true;
        this.#showBusy(this.#viewer.state);
        this.#holdStep(step, HOLD_DELAY_MS);
    }

    #holdStep(step, delay) {
        step.move(this.#viewer);
        if (this.#viewer.isAtStop() || !step.canMove(this.#viewer.state)) {
            this.#stopHold();
            return;
        }
        this.#holdTimer = setTimeout(() => this.#holdStep(step, HOLD_REPEAT_MS), delay);
    }

    #stopHold() {
        clearTimeout(this.#holdTimer);
        this.#holdTimer = null;
        this.#holding = false;
        for (const name of this.#pressed) {
            if (this.#buttons[name].prop("disabled")) {
                this.#pressed.delete(name);
            }
        }
        if (this.#viewer !== null) {
            this.#showBusy(this.#viewer.state);
        }
    }

    /**
     * Hold the live region while Back or Next repeats and while autoplay runs faster than slow, so a screen reader
     * announces where they stop rather than every step.
     */
    #showBusy(state) {
        const held = this.#holding || this.#keyHeld;
        const busy = held || (state.playing && state.speed !== AUTOPLAY_SPEED.SLOW);
        if (busy) {
            this.#action.attr("aria-busy", "true");
        } else {
            this.#action.removeAttr("aria-busy");
        }
    }

    /**
     * The seats as the shown round names them, the viewpoint's selected, the speed and the hidden-hands switch; a move to
     * another position closes the options, and a round list in the info's place, unless autoplay made it.
     */
    #showOptions(state) {
        if (this.#seatsRound !== state.round) {
            const round = this.#replay.rounds[state.round];
            const seats = Array.from({ length: SEATS }, (_, seat) =>
                $("<option>")
                    .val(seat)
                    .text(seatName(round, seat, this.#replay.players[seat])),
            );
            this.#seat.empty().append(seats);
            this.#seatsRound = state.round;
        }
        this.#seat.val(String(state.seat));
        this.#speed.val(state.speed);
        this.#hideHands.prop("checked", !state.openHands);
        $(".replay-options-view", this.#optionsToggle).text(
            t("replay.options.view", { player: this.#replay.players[state.seat] }),
        );
        $(".replay-options-speed", this.#optionsToggle).text(speedName(state.speed));
        const position = `${state.round}/${state.step}/${state.page}`;
        if (position !== this.#shownPosition) {
            this.#shownPosition = position;
            if (!state.playing) {
                this.#setOptionsOpen(false);
                if (this.#rounds.isInStrip()) {
                    this.#rounds.setOpen(false);
                }
            }
        }
    }

    #showInfo(state) {
        const round = this.#replay.rounds[state.round];
        const info = this.element;
        this.#showAction(lastAction(this.#replay, state));
        $(".replay-final", info).toggleClass("hide", !round.final);
        const step = stepText(round, state);
        $(".replay-step", info)
            .text(step)
            .toggleClass("hide", step === "");
        const warning = wallWarning(state);
        $(".replay-wall-low", info)
            .text(warning)
            .toggleClass("hide", warning === "");
        $(".replay-ended", info).text(state.endedEarly ? cutOffText() : "");
    }

    /** Write the action line only when it changes, so its live region announces each action once. */
    #showAction(parts) {
        const text = plainText(parts);
        if (this.#action.text() === text) {
            return;
        }
        this.#action.empty().append(actionNodes(parts)).attr("title", text);
    }
}
