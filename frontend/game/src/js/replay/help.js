import $ from "jquery";

import { t } from "../../i18n/index.js";

import { CLOSE_KEY, COMMAND, KEY_NAMES, ariaKeys, commandKeys, shownKeys } from "./keys.js";
import { COARSE_POINTER_MEDIA } from "./media.js";
import { panelHead } from "./panel.js";

const HELP_ID = "replay-help";
const HELP_TITLE_ID = "replay-help-title";

/** The keyboard part of the help: each row's commands, whose keys it lists side by side, and its text's key. */
const KEY_HELP = Object.freeze([
    { commands: [COMMAND.BACK, COMMAND.NEXT], text: "replay.help.back_next" },
    { commands: [COMMAND.PREV_ROUND, COMMAND.NEXT_ROUND], text: "replay.help.rounds" },
    { commands: [COMMAND.FIRST, COMMAND.LAST], text: "replay.help.first_last" },
    { commands: [COMMAND.PLAY], text: "replay.help.play" },
    { commands: [COMMAND.NEXT_SEAT], text: "replay.help.next_seat" },
    { commands: [COMMAND.HIDE_HANDS], text: "replay.help.hide_hands" },
    { commands: [COMMAND.HELP], text: "replay.help.help" },
]);

function shown(keys) {
    return keys.map((key) => KEY_NAMES[key].shown).join(" ");
}

const LIST_MOVES = shown(["ArrowUp", "ArrowDown", "Home", "End"]);
const LIST_SCROLLS = shown(["PageUp", "PageDown"]);

/** The pointer part of the help: what each place on the page does when clicked, tapped, held or scrolled over. */
function pointerHelp() {
    return [
        { place: t("replay.help.wheel_place"), text: t("replay.help.wheel") },
        { place: t("replay.help.hold_place"), text: t("replay.help.hold") },
        { place: t("replay.help.nameplate_place"), text: t("replay.help.nameplate") },
        {
            place: t("replay.help.round_name_place"),
            text: t("replay.help.round_list", { moves: LIST_MOVES, scrolls: LIST_SCROLLS }),
        },
        { place: t("replay.help.standings_place"), text: t("replay.help.standings") },
    ];
}

/** The help's toggle, a round "?" on the info's round line. */
function helpToggle() {
    return $('<button type="button" class="replay-help-toggle" aria-expanded="false">')
        .attr({
            "aria-controls": HELP_ID,
            "aria-label": t("replay.help.toggle_label"),
            "aria-keyshortcuts": ariaKeys(COMMAND.HELP),
            title: t("replay.help.toggle_title", { keys: shownKeys(COMMAND.HELP) }),
        })
        .append($('<span aria-hidden="true">').text("?"));
}

/** Keys side by side, each key group after the first offered as an alternative: "↑ ↓ or PgUp PgDn". */
function keysTerm(groups) {
    const term = $("<dt>");
    groups.forEach((keys, index) => {
        if (index > 0) {
            term.append(document.createTextNode(` ${t("replay.help.or")} `));
        }
        keys.forEach((key, at) => {
            term.append(at > 0 ? " " : null, $("<kbd>").text(KEY_NAMES[key].shown));
        });
    });
    return term;
}

/** A row's commands' keys grouped by rank: the first key of each, then the second of each. */
function keyGroups(commands) {
    const lists = commands.map(commandKeys);
    const ranks = Math.max(...lists.map((keys) => keys.length));
    return Array.from({ length: ranks }, (_, rank) =>
        lists.map((keys) => keys[rank]).filter(Boolean),
    );
}

function helpRow(term, text) {
    return $('<div class="replay-help-row">').append(term, $("<dd>").text(text));
}

function helpSection(title, rows) {
    return [$("<h3>").text(title), $('<dl class="replay-help-list">').append(rows)];
}

/**
 * The help: every key and what the pointer does where, its body the one part that scrolls (and takes the focus, so
 * the keys scroll it); on a touch screen what a tap does comes first.
 */
function helpMarkup() {
    const keys = helpSection(t("replay.help.keyboard"), [
        ...KEY_HELP.map(({ commands, text }) => helpRow(keysTerm(keyGroups(commands)), t(text))),
        helpRow(keysTerm([[CLOSE_KEY]]), t("replay.help.close_panels")),
    ]);
    const pointer = helpSection(
        t("replay.help.pointer"),
        pointerHelp().map(({ place, text }) => helpRow($("<dt>").text(place), text)),
    );
    const sections = window.matchMedia(COARSE_POINTER_MEDIA).matches
        ? [...pointer, ...keys]
        : [...keys, ...pointer];
    return $(`<section class="replay-help" id="${HELP_ID}" role="dialog">`)
        .attr("aria-labelledby", HELP_TITLE_ID)
        .append(
            panelHead(HELP_TITLE_ID, t("replay.help.title"), t("replay.help.close")),
            $('<div class="replay-help-body" tabindex="-1">').append(sections),
        );
}

/**
 * The help: its toggle (`button`, for the info's round line) and its popover (`element`). It opens from the toggle or its
 * key, first calling `beforeOpen` to close what it would cover, with the keyboard focus on its scrolling body; it closes
 * from them, its ✕, Escape (through the strip), or a press or the keyboard focus anywhere outside it, so a control the
 * keyboard reaches never opens hidden under it. Closing hands a focus it held back to where it was before.
 */
export class ReplayHelp {
    #beforeOpen;
    #focusBefore = null;

    constructor({ beforeOpen }) {
        this.#beforeOpen = beforeOpen;
        this.button = helpToggle();
        this.element = helpMarkup();
    }

    bind() {
        this.button.on("click", () => this.toggleOpen());
        $(".replay-panel-close", this.element).on("click", () => this.setOpen(false));
        $(document)
            .off(".replay-help")
            .on("pointerdown.replay-help focusin.replay-help", (event) => {
                const inside = this.contains(event.target) || this.button[0].contains(event.target);
                if (this.isOpen && !inside) {
                    this.setOpen(false);
                }
            });
    }

    get isOpen() {
        return this.button.attr("aria-expanded") === "true";
    }

    contains(element) {
        return this.element[0].contains(element);
    }

    toggleOpen() {
        this.setOpen(!this.isOpen);
    }

    setOpen(open) {
        if (open === this.isOpen) {
            return;
        }
        if (open) {
            this.#beforeOpen();
            this.#focusBefore = document.activeElement;
        }
        const focused = this.contains(document.activeElement);
        this.button.attr("aria-expanded", String(open));
        this.element.toggleClass("replay-help-open", open);
        if (open) {
            $(".replay-help-body", this.element).trigger("focus");
        } else if (focused) {
            this.#restoreFocus();
        }
    }

    /** The focus goes back where it was before the help opened: the page itself, a control still there, or the "?". */
    #restoreFocus() {
        const before = this.#focusBefore;
        this.#focusBefore = null;
        if (before === null || before === document.body) {
            document.activeElement?.blur();
        } else if (before.isConnected && !before.disabled) {
            before.focus();
        } else {
            this.button.trigger("focus");
        }
    }
}
