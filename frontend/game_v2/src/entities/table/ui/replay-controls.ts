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
    readonly moves: ReplayMoves;
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

export interface ReplayStatusProps {
    readonly display: Pick<
        ReplayDisplay,
        "endNotice" | "honbaLabel" | "incomplete" | "narration" | "roundTitle" | "step"
    >;
    /** Autoplay runs, so the narration is not read out at each of its stops. */
    readonly playing: boolean;
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

const OPTION_ICONS = {
    hands: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
    handsHidden: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM4 4l16 16",
    pause: "M9 5v14M15 5v14",
    play: "M8 5l11 7-11 7z",
    rounds: "M9 6h11M9 12h11M9 18h11M4 6h1M4 12h1M4 18h1",
    view: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM16.2 7.8l-2.1 6.3-6.3 2.1 2.1-6.3z",
} as const;

function Icon(path: string): TemplateResult {
    return html`<svg class="replay-controls__icon" viewBox="0 0 24 24" aria-hidden="true">${svg`<path d=${path} />`}</svg>`;
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
    >${Icon(MOVE_ICONS[direction])}</button>`;
}

/** A jump's button: to a round's deal or either end. */
function JumpButton(name: MoveName, props: ReplayControlsProps): TemplateResult {
    const target = props.moves[name];
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
    >${Icon(MOVE_ICONS[name])}</button>`;
}

/** Autoplay's switch, the player's own action among the moves: the accent. */
function PlayButton(props: ReplayControlsProps): TemplateResult {
    const { playing } = props.playback;
    return html`<button
        type="button"
        class="replay-controls__play"
        aria-label="Autoplay"
        title="Autoplay"
        aria-pressed=${String(playing)}
        ?disabled=${!playing && props.moves.next === null}
        @click=${props.onTogglePlay}
    >${Icon(playing ? OPTION_ICONS.pause : OPTION_ICONS.play)}</button>`;
}

interface OptionProps {
    readonly kind: string;
    readonly label: string;
    readonly title?: string;
    /** A switch's state; omitted for a button that only acts. */
    readonly pressed?: boolean;
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
        @click=${props.onClick}
    >${props.content}</button>`;
}

function RoundsButton(props: ReplayControlsProps): TemplateResult {
    return html`<button
        type="button"
        class="replay-controls__option replay-controls__option--rounds"
        aria-label="Rounds"
        title="Rounds"
        aria-expanded=${props.roundListOpen ? "true" : "false"}
        aria-controls=${REPLAY_ROUND_LIST_ID}
        @click=${props.onToggleRoundList}
    >${Icon(OPTION_ICONS.rounds)}</button>`;
}

/**
 * The replay's controls over the foreground band: the moves in the play switches' place (a round back, a step back,
 * autoplay, a step on, a round on, and either end where the place holds them), and the options in the decisions'
 * place (autoplay's speed, the seat at the bottom, the other hands and the round list), two rows of two where the band
 * beside the own river's reach is too short for all four. A move that cannot go is disabled.
 */
export function ReplayControls(props: ReplayControlsProps): TemplateResult {
    const { playback } = props;
    const speed = `${playback.speed}×`;
    return html`
        <div class="replay-controls replay-controls__moves" role="group" aria-label="Move through the replay">
            ${JumpButton("first", props)}${JumpButton("prevRound", props)}${StepButton("prev", props.moves.prev, props)}${PlayButton(props)}${StepButton("next", props.moves.next, props)}${JumpButton("nextRound", props)}${JumpButton("last", props)}
        </div>
        <div class="replay-controls replay-controls__options" role="group" aria-label="Speed and view">
            ${OptionButton({
                content: speed,
                kind: "speed",
                label: `Autoplay speed ${speed}, change`,
                onClick: props.onCycleSpeed,
                title: "Autoplay speed",
            })}
            ${OptionButton({
                content: Icon(OPTION_ICONS.view),
                kind: "view",
                label: `Viewing from ${playback.viewName}; view from ${playback.nextViewName}`,
                onClick: props.onSwitchView,
                title: `View from ${playback.nextViewName}`,
            })}
            ${OptionButton({
                content: Icon(playback.hideHands ? OPTION_ICONS.handsHidden : OPTION_ICONS.hands),
                kind: "hands",
                label: "Hide the other hands",
                onClick: props.onToggleHands,
                pressed: playback.hideHands,
            })}
            ${RoundsButton(props)}
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
        ${atEnd ? html`<span class="replay-status__incomplete-end" aria-hidden="true">Ends here</span>` : nothing}
    </p>`;
}

/**
 * What the replay shows in the notices' place: the round and step, a replay that is not the whole game saying so (and
 * where it ends at its last stop), and the narration of the stop, read out once by a live region of its own that
 * stays empty while autoplay runs; the narration drawn is hidden from assistive technology, which reads that region.
 */
export function ReplayStatus({ display, playing }: ReplayStatusProps): TemplateResult {
    const { step } = display;
    return html`<div class="replay-status">
        <p class="replay-status__position">
            <span class="replay-status__round">${display.roundTitle}${
                display.honbaLabel === null
                    ? nothing
                    : html`<span class="replay-status__honba">, ${display.honbaLabel}</span>`
            }</span>
            <span class="replay-status__step">Step ${step.index} of ${step.count}</span>
        </p>
        ${IncompleteNote(display.incomplete, display.endNotice)}
        <p class="replay-status__narration" aria-hidden="true">${display.narration}</p>
        <p class="replay-status__announcer" aria-live="polite">${playing ? "" : display.narration}</p>
    </div>`;
}
