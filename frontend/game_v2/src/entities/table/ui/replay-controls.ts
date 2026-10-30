import { type TemplateResult, html, nothing, svg } from "lit-html";

import {
    type ReplayDisplay,
    type ReplayIncompleteness,
    type ReplayMoves,
} from "@/entities/table/lib/replay-display";
import { type ReplayCursor } from "@/entities/table/model/replay-cursor";

/** The round list's element id, which its toggle controls. */
export const REPLAY_ROUND_LIST_ID = "replay-round-list";

/** How the replay plays and is seen: autoplay, its speed, the seat at the bottom and the next one, the other hands. */
export interface ReplayPlayback {
    readonly playing: boolean;
    readonly speed: number;
    readonly viewName: string;
    readonly nextViewName: string;
    readonly hideHands: boolean;
}

/** A step button pressed by a pointer, which may be held to repeat. */
export type StepDirection = "next" | "prev";

/** The attribute naming a step button's direction, by which the view takes Enter and Space on it as that step. */
export const STEP_BUTTON_ATTRIBUTE = "data-step";

export interface ReplayControlsProps {
    readonly display: Pick<
        ReplayDisplay,
        | "endNotice"
        | "honbaLabel"
        | "incomplete"
        | "moves"
        | "narration"
        | "roundName"
        | "roundTitle"
        | "step"
    >;
    readonly playback: ReplayPlayback;
    readonly roundListOpen: boolean;
    readonly onToggleRoundList: () => void;
    readonly onMove: (cursor: ReplayCursor) => void;
    /** A pointer pressed a step button: it steps from the press and repeats while held. */
    readonly onStepPress: (direction: StepDirection, event: PointerEvent) => void;
    /** A step button was clicked, which the view drops when it ends a press that stepped already. */
    readonly onStepClick: (direction: StepDirection, event: MouseEvent) => void;
    readonly onTogglePlay: () => void;
    readonly onCycleSpeed: () => void;
    readonly onSwitchView: () => void;
    readonly onToggleHands: () => void;
}

type MoveName = keyof ReplayMoves;

const MOVE_ICONS: Readonly<Record<MoveName, string>> = {
    first: "M7 5v14M18 5l-7 7 7 7",
    last: "M17 5v14M6 5l7 7-7 7",
    next: "M9 5l7 7-7 7",
    nextRound: "M5 5l7 7-7 7M12 5l7 7-7 7",
    prev: "M15 5l-7 7 7 7",
    prevRound: "M12 5l-7 7 7 7M19 5l-7 7 7 7",
};

const MOVE_LABELS: Readonly<Record<MoveName, string>> = {
    first: "First deal",
    last: "Last step",
    next: "Next step",
    nextRound: "Next round",
    prev: "Previous step",
    prevRound: "Previous round",
};

const MOVE_ORDER: readonly MoveName[] = ["first", "prevRound", "prev", "next", "nextRound", "last"];

const OPTION_ICONS = {
    hands: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
    handsHidden: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM4 4l16 16",
    pause: "M9 5v14M15 5v14",
    play: "M8 5l11 7-11 7z",
    view: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM16.2 7.8l-2.1 6.3-6.3 2.1 2.1-6.3z",
} as const;

function MoveIcon(path: string): TemplateResult {
    return html`<svg class="replay-controls__icon" viewBox="0 0 24 24" aria-hidden="true">${svg`<path d=${path} />`}</svg>`;
}

/** The moves a held pointer repeats. */
function isStepDirection(name: MoveName): name is StepDirection {
    return name === "next" || name === "prev";
}

/** A step's button, which steps from a pointer's press and repeats while held; the view takes its click. */
function StepButton(
    direction: StepDirection,
    target: ReplayCursor | null,
    props: ReplayControlsProps,
): TemplateResult {
    return html`<button
        type="button"
        class="replay-controls__move replay-controls__move--${direction}"
        data-step=${direction}
        aria-label=${MOVE_LABELS[direction]}
        title=${MOVE_LABELS[direction]}
        ?disabled=${target === null}
        @pointerdown=${(event: PointerEvent) => props.onStepPress(direction, event)}
        @click=${(event: MouseEvent) => props.onStepClick(direction, event)}
    >${MoveIcon(MOVE_ICONS[direction])}</button>`;
}

function MoveButton(
    name: MoveName,
    target: ReplayCursor | null,
    props: ReplayControlsProps,
): TemplateResult {
    if (isStepDirection(name)) {
        return StepButton(name, target, props);
    }
    return html`<button
        type="button"
        class="replay-controls__move replay-controls__move--${name}"
        aria-label=${MOVE_LABELS[name]}
        title=${MOVE_LABELS[name]}
        ?disabled=${target === null}
        @click=${() => {
            if (target !== null) {
                props.onMove(target);
            }
        }}
    >${MoveIcon(MOVE_ICONS[name])}</button>`;
}

interface OptionProps {
    readonly kind: string;
    readonly label: string;
    readonly title?: string;
    /** A switch's state; omitted for a button that only acts. */
    readonly pressed?: boolean;
    readonly disabled?: boolean;
    readonly onClick: () => void;
    readonly content: TemplateResult | string;
}

function OptionButton(props: OptionProps): TemplateResult {
    return html`<button
        type="button"
        class="replay-controls__option replay-controls__option--${props.kind}"
        aria-label=${props.label}
        title=${props.title ?? props.label}
        aria-pressed=${props.pressed === undefined ? nothing : String(props.pressed)}
        ?disabled=${props.disabled === true}
        @click=${props.onClick}
    >${props.content}</button>`;
}

/** Autoplay and its speed, then the seat at the bottom and whether the other hands show. */
function PlaybackOptions(props: ReplayControlsProps): TemplateResult {
    const { playback } = props;
    const speed = `${playback.speed}\u00D7`;
    return html`<div class="replay-controls__options" role="group" aria-label="Play and view">
        ${OptionButton({
            content: MoveIcon(playback.playing ? OPTION_ICONS.pause : OPTION_ICONS.play),
            disabled: !playback.playing && props.display.moves.next === null,
            kind: "play",
            label: "Autoplay",
            onClick: props.onTogglePlay,
            pressed: playback.playing,
        })}
        ${OptionButton({
            content: speed,
            kind: "speed",
            label: `Autoplay speed ${speed}, change`,
            onClick: props.onCycleSpeed,
            title: "Autoplay speed",
        })}
        ${OptionButton({
            content: MoveIcon(OPTION_ICONS.view),
            kind: "view",
            label: `Viewing from ${playback.viewName}; view from ${playback.nextViewName}`,
            onClick: props.onSwitchView,
            title: `View from ${playback.nextViewName}`,
        })}
        ${OptionButton({
            content: MoveIcon(playback.hideHands ? OPTION_ICONS.handsHidden : OPTION_ICONS.hands),
            kind: "hands",
            label: "Hide the other hands",
            onClick: props.onToggleHands,
            pressed: playback.hideHands,
        })}
    </div>`;
}

/** Why the replay is not the whole game, and at its last stop that it ends there, which the label says always. */
function IncompleteNote(
    incomplete: ReplayIncompleteness | null,
    endNotice: string | null,
): TemplateResult | typeof nothing {
    if (incomplete === null) {
        return nothing;
    }
    const atEnd = endNotice !== null;
    return html`<p
        class="replay-controls__incomplete ${atEnd ? "replay-controls__incomplete--end" : ""}"
        role="status"
        title=${incomplete.detail}
    >
        <strong class="replay-controls__incomplete-label">${incomplete.label}</strong>
        <span class="replay-controls__incomplete-detail">${endNotice ?? incomplete.detail}</span>
    </p>`;
}

/** The note folded into the round's toggle as a mark where the column is too narrow for it, which the end words. */
function roundMarkClass(incomplete: ReplayIncompleteness | null, endNotice: string | null): string {
    if (incomplete === null) {
        return "";
    }
    return endNotice === null
        ? "replay-controls__round--incomplete"
        : "replay-controls__round--end";
}

/**
 * The replay's controls beside its board: a replay that is not the whole game says so, and where it ends at its last
 * stop, the round and step open the round list, the narration tells what the stop shows (read out by a live region
 * that stays silent while autoplay runs), autoplay and the view have their switches, and the moves step, jump a
 * round, or go to either end; a move that cannot go anywhere is disabled.
 */
export function ReplayControls(props: ReplayControlsProps): TemplateResult {
    const { display } = props;
    const { step } = display;
    return html`
        ${IncompleteNote(display.incomplete, display.endNotice)}
        <button
            type="button"
            class="replay-controls__round ${roundMarkClass(display.incomplete, display.endNotice)}"
            aria-expanded=${props.roundListOpen ? "true" : "false"}
            aria-controls=${REPLAY_ROUND_LIST_ID}
            aria-label="Rounds: ${display.roundName}, step ${step.index} of ${step.count}"
            @click=${props.onToggleRoundList}
        >
            <span class="replay-controls__round-name"
                >${display.roundTitle}${
                    display.honbaLabel === null
                        ? nothing
                        : html`<span class="replay-controls__honba">, ${display.honbaLabel}</span>`
                }</span
            >
            <span class="replay-controls__step"
                ><span class="replay-controls__step-word">Step </span>${step.index}/${step.count}</span
            >
        </button>
        <div class="replay-controls__narration-room"><p class="replay-controls__narration">${display.narration}</p></div>
        <p class="replay-controls__announcer" aria-live="polite">
            ${props.playback.playing ? "" : display.narration}
        </p>
        ${PlaybackOptions(props)}
        <div class="replay-controls__moves" role="group" aria-label="Move through the replay">
            ${MOVE_ORDER.map((name) => MoveButton(name, display.moves[name], props))}
        </div>
    `;
}
