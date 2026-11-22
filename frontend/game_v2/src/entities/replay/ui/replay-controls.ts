import { type TemplateResult, html, nothing, svg } from "lit-html";

import {
    type ReplayDisplay,
    type ReplayIncompleteness,
    type ReplayMoves,
} from "@/entities/replay/lib/replay-display";
import { type ReplayCursor } from "@/entities/replay/model/replay-cursor";
import { type ReplayHandCopy, type StepDirection } from "@/entities/replay/model/replay-page";
import { type MessageKey, t } from "@/shared/i18n";

/** The round list's element id, which its toggle controls. */
export const REPLAY_ROUND_LIST_ID = "replay-round-list";

/** The focus key the round list's toggle renders, so the page focuses it back as the list closes. */
export const ROUND_LIST_TOGGLE_FOCUS_KEY = "round-list-toggle";

/** What the round list's toggle renders, so a click on it is told from one outside the list that closes it. */
export const ROUND_LIST_TOGGLE_SELECTOR = "[data-round-list-toggle]";

/** The tools' menu's element id, which its toggle controls. */
export const REPLAY_TOOLS_ID = "replay-tools";

/** The focus key the tools' toggle renders, so the page focuses it back as the menu closes. */
export const TOOLS_TOGGLE_FOCUS_KEY = "replay-tools-toggle";

/** What the tools' toggle renders, so a click on it is told from one outside the menu that closes it. */
export const TOOLS_TOGGLE_SELECTOR = "[data-replay-tools-toggle]";

/** How the replay plays: autoplay. */
export interface ReplayPlayback {
    readonly playing: boolean;
}

/** The attribute naming a step button's direction, by which the view takes Enter and Space on it as that step. */
export const STEP_BUTTON_ATTRIBUTE = "data-step";

export interface ReplayControlsProps {
    readonly observing: boolean;
    readonly moves: ReplayMoves;
    readonly playback: ReplayPlayback;
    readonly roundListOpen: boolean;
    readonly onToggleRoundList: () => void;
    readonly toolsOpen: boolean;
    readonly onToggleTools: () => void;
    readonly onMove: (cursor: ReplayCursor) => void;
    /** A pointer pressed a step button: it steps from the press and repeats while held. */
    readonly onStepPress: (direction: StepDirection, event: PointerEvent) => void;
    /** A step button was clicked, which the view drops when it ends a press that stepped already. */
    readonly onStepClick: (direction: StepDirection) => void;
    readonly onTogglePlay: () => void;
    /** The next seat round the table takes the bottom. */
    readonly onNextView: () => void;
}

export interface ReplayStatusProps {
    readonly display: Pick<
        ReplayDisplay,
        "endNotice" | "incomplete" | "roundName" | "step" | "stream"
    >;
    readonly handCopy: ReplayHandCopy["outcome"] | null;
    /** This game's saved replay, which the status links once an observed game is gone from the server. */
    readonly replayUrl: string;
}

/** The moves with a button of their own; either end is the keys' and the round list's. */
type MoveName = Exclude<keyof ReplayMoves, "first" | "last">;

const MOVE_ICONS: Readonly<Record<MoveName, string>> = {
    next: "M9 5l7 7-7 7",
    nextRound: "M17 5v14M6 5l7 7-7 7",
    nextTurn: "M5 5l7 7-7 7M12 5l7 7-7 7",
    prev: "M15 5l-7 7 7 7",
    prevRound: "M7 5v14M18 5l-7 7 7 7",
    prevTurn: "M12 5l-7 7 7 7M19 5l-7 7 7 7",
};

const MOVE_LABELS: Readonly<Record<MoveName, MessageKey>> = {
    next: "replay.jump.next",
    nextRound: "replay.jump.next_round",
    nextTurn: "replay.jump.next_turn",
    prev: "replay.jump.prev",
    prevRound: "replay.jump.prev_round",
    prevTurn: "replay.jump.prev_turn",
};

/** The key each move's tip names beside its label. */
const MOVE_KEYS: Readonly<Record<MoveName, string>> = {
    next: "→",
    nextRound: "PgDn",
    nextTurn: "↓",
    prev: "←",
    prevRound: "PgUp",
    prevTurn: "↑",
};

const OPTION_ICONS = {
    pause: "M9 5v14M15 5v14",
    play: "M8 5l11 7-11 7z",
    rounds: "M9 6h11M9 12h11M9 18h11M4 6h1M4 12h1M4 18h1",
    tools: "M4 7h9M17 7h3M15 5v4M4 17h3M11 17h9M9 15v4",
    view: "M4 11a8 8 0 0 1 14-5l2 2M20 4v4h-4M20 13a8 8 0 0 1-14 5l-2-2M4 20v-4h4",
} as const;

function Icon(path: string): TemplateResult {
    return html`<svg class="replay-controls__icon" viewBox="0 0 24 24" aria-hidden="true">${svg`<path d=${path} />`}</svg>`;
}

/** A control's tip, shown at once on hover and focus: what it does and the key that does it. */
function tip(label: string, key: string): string {
    return t("replay.tip", { key, label });
}

function moveTip(name: MoveName): string {
    return tip(t(MOVE_LABELS[name]), MOVE_KEYS[name]);
}

/** A step's button, which steps from a pointer's press and repeats while held; the view takes its click. */
function StepButton(direction: StepDirection, props: ReplayControlsProps): TemplateResult {
    return html`<button
        type="button"
        class="replay-controls__move replay-controls__move--${direction}"
        data-step=${direction}
        data-tip=${moveTip(direction)}
        aria-label=${t(MOVE_LABELS[direction])}
        ?disabled=${props.moves[direction] === null}
        @pointerdown=${(event: PointerEvent) => props.onStepPress(direction, event)}
        @click=${() => props.onStepClick(direction)}
    >${Icon(MOVE_ICONS[direction])}</button>`;
}

/** A jump's button: to the bottom seat's turn or a round's deal. */
function JumpButton(name: MoveName, props: ReplayControlsProps): TemplateResult {
    const target = props.moves[name];
    return html`<button
        type="button"
        class="replay-controls__move replay-controls__move--${name}"
        data-tip=${moveTip(name)}
        aria-label=${t(MOVE_LABELS[name])}
        ?disabled=${target === null}
        @click=${() => {
            if (target !== null) {
                props.onMove(target);
            }
        }}
    >${Icon(MOVE_ICONS[name])}</button>`;
}

/** Autoplay's switch, the player's own action among the moves: the accent. */
function PlayButton(props: ReplayControlsProps): TemplateResult {
    const { playing } = props.playback;
    return html`<button
        type="button"
        class="replay-controls__play"
        data-tip=${tip(t("replay.autoplay"), t("replay.key.space"))}
        aria-label=${t("replay.autoplay")}
        aria-pressed=${String(playing)}
        ?disabled=${!playing && props.moves.next === null}
        @click=${props.onTogglePlay}
    >${Icon(playing ? OPTION_ICONS.pause : OPTION_ICONS.play)}</button>`;
}

interface OptionProps {
    readonly kind: string;
    readonly label: string;
    readonly tip: string;
    /** A switch's state; omitted for a button that only acts. */
    readonly pressed?: boolean;
    readonly onClick: () => void;
    readonly content: TemplateResult | string;
}

function OptionButton(props: OptionProps): TemplateResult {
    return html`<button
        type="button"
        class="replay-controls__option replay-controls__option--${props.kind}"
        data-tip=${props.tip}
        aria-label=${props.label}
        aria-pressed=${props.pressed === undefined ? nothing : String(props.pressed)}
        @click=${props.onClick}
    >${props.content}</button>`;
}

function RoundsButton(props: ReplayControlsProps): TemplateResult {
    return html`<button
        type="button"
        class="replay-controls__option replay-controls__option--rounds"
        data-tip=${t("replay.rounds.title")}
        aria-label=${t("replay.rounds.title")}
        aria-expanded=${props.roundListOpen ? "true" : "false"}
        aria-controls=${REPLAY_ROUND_LIST_ID}
        data-focus-key=${ROUND_LIST_TOGGLE_FOCUS_KEY}
        data-round-list-toggle
        @click=${props.onToggleRoundList}
    >${Icon(OPTION_ICONS.rounds)}</button>`;
}

function ToolsButton(props: ReplayControlsProps): TemplateResult {
    return html`<button
        type="button"
        class="replay-controls__option replay-controls__option--tools"
        data-tip=${t("replay.tools.title")}
        aria-label=${t("replay.tools.title")}
        aria-expanded=${props.toolsOpen ? "true" : "false"}
        aria-controls=${REPLAY_TOOLS_ID}
        data-focus-key=${TOOLS_TOGGLE_FOCUS_KEY}
        data-replay-tools-toggle
        @click=${props.onToggleTools}
    >${Icon(OPTION_ICONS.tools)}</button>`;
}

/**
 * The replay's controls, one group: the moves (a round back, the bottom seat's turn back, a step back, autoplay, a step
 * on, its turn on, a round on; a smaller board's keep the five between the rounds), then the options (the next seat's
 * view on a desktop's chrome, the round list and the tools' menu). A desktop stands them in one row over the own hand,
 * a phone or a small window at the right bar's foot, in two columns of paired moves where the bar is too short for
 * one; the board's geometry picks the form. A move that cannot go is disabled.
 * Each control's tip names it and its key. The seat at the bottom is the board's: pressing another seat's plate or
 * score views from it too.
 */
export function ReplayControls(props: ReplayControlsProps): TemplateResult {
    const view = OptionButton({
        content: Icon(OPTION_ICONS.view),
        kind: "view",
        label: t("replay.options.next_view"),
        onClick: props.onNextView,
        tip: tip(t("replay.options.next_view"), "V"),
    });
    if (props.observing) {
        return html`<div class="replay-controls__options" role="group" aria-label=${t("replay.controls.view")}>
            ${view}${ToolsButton(props)}
        </div>`;
    }
    return html`
        <div class="replay-controls__moves" role="group" aria-label=${t("replay.controls.moves")}>
            ${JumpButton("prevRound", props)}${JumpButton("prevTurn", props)}${StepButton("prev", props)}${PlayButton(props)}${StepButton("next", props)}${JumpButton("nextTurn", props)}${JumpButton("nextRound", props)}
        </div>
        <div class="replay-controls__options" role="group" aria-label=${t("replay.controls.view")}>
            ${view}${RoundsButton(props)}${ToolsButton(props)}
        </div>
    `;
}

/**
 * Why the replay is not the whole game, and at its last stop that it ends there; its detail in its title, and a short
 * mark of the end a compact status shows in place of the detail (the detail is what assistive technology reads).
 */
function IncompleteNote(
    incomplete: ReplayIncompleteness | null,
    endNotice: string | null,
): TemplateResult | typeof nothing {
    if (incomplete === null) {
        return nothing;
    }
    const atEnd = endNotice !== null;
    return html`<p
        class="replay-status__incomplete ${atEnd ? "replay-status__incomplete--end" : ""}"
        role="status"
        title=${incomplete.detail}
    >
        <strong class="replay-status__incomplete-label">${incomplete.label}</strong>
        <span class="replay-status__incomplete-detail">${endNotice ?? incomplete.detail}</span>
        ${atEnd ? html`<span class="replay-status__incomplete-end" aria-hidden="true">${t("replay.status.ends_here")}</span>` : nothing}
    </p>`;
}

/**
 * What the replay shows in the notices' place: the round and step for assistive technology alone (the centre shows the
 * round), a replay that is not the whole game saying so (and where it ends at its last stop, or that it is live), the
 * saved replay's link once an observed game is gone, and whether a copy of the hand went through.
 */
const HAND_COPY_NOTICES: Readonly<Record<ReplayHandCopy["outcome"], MessageKey>> = {
    copied: "replay.status.hand_copied",
    failed: "replay.status.hand_copy_failed",
};

export function ReplayStatus({ display, handCopy, replayUrl }: ReplayStatusProps): TemplateResult {
    const { step } = display;
    return html`<div class="replay-status">
        <p class="replay-status__position">
            <span>${display.roundName}</span>
            <span class="replay-status__step">${t("replay.step", { step: step.index, steps: step.count })}</span>
        </p>
        ${IncompleteNote(display.incomplete, display.endNotice)}
        ${
            display.stream === "gone"
                ? html`<p class="replay-status__replay">
                      <a href=${replayUrl} role="button" class="secondary">${t("replay.observe.replay_link")}</a>
                  </p>`
                : nothing
        }
        ${
            handCopy === null
                ? nothing
                : html`<p class="replay-status__copy replay-status__copy--${handCopy}" role="status">
                      ${t(HAND_COPY_NOTICES[handCopy])}
                  </p>`
        }
    </div>`;
}
