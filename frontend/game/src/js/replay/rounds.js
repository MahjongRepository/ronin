import $ from "jquery";

import { actionNodes, outcomeParts, roundName } from "./describe.js";
import { isModified } from "./keys.js";
import { UPRIGHT_PHONE_MEDIA } from "./media.js";
import { panelHead } from "./panel.js";

const ROUNDS_ID = "replay-rounds";
const ROUNDS_TITLE_ID = "replay-rounds-title";

/**
 * The layouts whose strip has the room to show the round list in the info's place, where a move closes it so the info
 * shows again: a short landscape screen and an upright phone (`_replay.scss`'s `$short-landscape` and `_theme.scss`'s
 * `$portrait-touch`, which the two must match).
 */
export const ROUNDS_IN_STRIP_MEDIA = `screen and (height <= 450px) and (orientation: landscape), ${UPRIGHT_PHONE_MEDIA}`;

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
            panelHead(ROUNDS_TITLE_ID, "Rounds", "Close the round list"),
            $('<ol class="replay-round-list">').append(entries),
        );
}

/**
 * The round list: its toggle (`button`, the round's name on the info's round line) and its panel (`element`), every
 * round with its outcome, the round shown marked. It opens from the toggle, first calling `beforeOpen` to close what it
 * would replace, at the round shown, and closes from the toggle, its ✕ or Escape (through the strip); `onOpenChange`
 * hears each change. ↑ and ↓, Home and End move between its rounds. A round picked there is shown from its deal, a
 * manual move that pauses autoplay.
 */
export class ReplayRounds {
    #beforeOpen;
    #onOpenChange;
    #listedRound = null;

    constructor(replay, { beforeOpen, onOpenChange }) {
        this.#beforeOpen = beforeOpen;
        this.#onOpenChange = onOpenChange;
        this.button = roundsToggle();
        this.element = roundsMarkup(replay);
    }

    bind(viewer) {
        this.button.on("click", () => {
            const open = !this.isOpen;
            this.setOpen(open);
            if (open) {
                this.#currentEntry().trigger("focus");
            }
        });
        $(".replay-panel-close", this.element).on("click", () => this.setOpen(false));
        this.element.on("click", ".replay-round-entry", (event) => {
            viewer.seek(Number(event.currentTarget.dataset.round), 0);
            if (this.isInStrip()) {
                this.setOpen(false);
            }
        });
        this.element.on("keydown", ".replay-round-entry", (event) => this.#moveFocus(event));
    }

    get isOpen() {
        return this.button.attr("aria-expanded") === "true";
    }

    contains(element) {
        return this.element[0].contains(element);
    }

    /** Whether the open round list takes the info's place, where a move closes it so the info shows again. */
    isInStrip() {
        return this.isOpen && window.matchMedia(ROUNDS_IN_STRIP_MEDIA).matches;
    }

    /** Open or close the round list; closing it hands the keyboard focus it held back to the round's name. */
    setOpen(open) {
        if (open) {
            this.#beforeOpen();
        }
        const focused = this.contains(document.activeElement);
        this.button.attr("aria-expanded", String(open));
        $(".replay-rounds-chevron", this.button).text(open ? "▴" : "▾");
        this.#onOpenChange(open);
        if (open) {
            this.#scrollToCurrentEntry("center");
        } else if (focused) {
            this.button.trigger("focus");
        }
    }

    /** Give the keyboard focus to the round's name. */
    focusToggle() {
        this.button.trigger("focus");
    }

    /** Name the round shown on the toggle, and mark it in the list, scrolled into view when the round changes. */
    show(state, round) {
        const name = roundName(round);
        $(".replay-round", this.button).text(name);
        this.button.attr("aria-label", `Round list, ${name}`);
        if (this.#listedRound === state.round) {
            return;
        }
        this.#listedRound = state.round;
        const entries = $(".replay-round-entry", this.element);
        entries.removeAttr("aria-current");
        entries.eq(state.round).attr("aria-current", "true");
        if (this.isOpen) {
            this.#scrollToCurrentEntry("nearest");
        }
    }

    /** ↑ and ↓ move the focus to the round above or below, Home and End to the first or last. */
    #moveFocus(event) {
        const native = event.originalEvent;
        if (isModified(native)) {
            return;
        }
        const entries = $(".replay-round-entry", this.element);
        const index = entries.index(event.currentTarget);
        const targets = {
            ArrowUp: index - 1,
            ArrowDown: index + 1,
            Home: 0,
            End: entries.length - 1,
        };
        if (!Object.hasOwn(targets, native.key)) {
            return;
        }
        event.preventDefault();
        const target = Math.min(Math.max(targets[native.key], 0), entries.length - 1);
        entries.eq(target).trigger("focus");
    }

    #currentEntry() {
        return $('.replay-round-entry[aria-current="true"]', this.element);
    }

    #scrollToCurrentEntry(block) {
        this.#currentEntry()[0]?.scrollIntoView?.({ block });
    }
}
