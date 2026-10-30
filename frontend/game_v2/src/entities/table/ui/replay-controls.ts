import { type TemplateResult, html, nothing, svg } from "lit-html";

import {
    type ReplayDisplay,
    type ReplayIncompleteness,
    type ReplayMoves,
} from "@/entities/table/lib/replay-display";
import { type ReplayCursor } from "@/entities/table/model/replay-cursor";

/** The round list's element id, which its toggle controls. */
export const REPLAY_ROUND_LIST_ID = "replay-round-list";

export interface ReplayControlsProps {
    readonly display: Pick<
        ReplayDisplay,
        "endNotice" | "incomplete" | "moves" | "narration" | "roundName" | "step"
    >;
    readonly roundListOpen: boolean;
    readonly onToggleRoundList: () => void;
    readonly onMove: (cursor: ReplayCursor) => void;
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

function MoveIcon(name: MoveName): TemplateResult {
    return html`<svg class="replay-controls__icon" viewBox="0 0 24 24" aria-hidden="true">${svg`<path d=${MOVE_ICONS[name]} />`}</svg>`;
}

function MoveButton(
    name: MoveName,
    target: ReplayCursor | null,
    onMove: ReplayControlsProps["onMove"],
): TemplateResult {
    return html`<button
        type="button"
        class="replay-controls__move replay-controls__move--${name}"
        aria-label=${MOVE_LABELS[name]}
        title=${MOVE_LABELS[name]}
        ?disabled=${target === null}
        @click=${() => {
            if (target !== null) {
                onMove(target);
            }
        }}
    >${MoveIcon(name)}</button>`;
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

/**
 * The replay's controls beside its board: a replay that is not the whole game says so, and where it ends at its last
 * stop, the round and step open the
 * round list, the narration tells what the stop shows, and the moves step, jump a round, or go to either end; a move
 * that cannot go anywhere is disabled.
 */
export function ReplayControls(props: ReplayControlsProps): TemplateResult {
    const { display } = props;
    const { step } = display;
    return html`
        ${IncompleteNote(display.incomplete, display.endNotice)}
        <button
            type="button"
            class="replay-controls__round"
            aria-expanded=${props.roundListOpen ? "true" : "false"}
            aria-controls=${REPLAY_ROUND_LIST_ID}
            aria-label="Rounds: ${display.roundName}, step ${step.index} of ${step.count}"
            @click=${props.onToggleRoundList}
        >
            <span class="replay-controls__round-name">${display.roundName}</span>
            <span class="replay-controls__step">Step ${step.index}/${step.count}</span>
        </button>
        <p class="replay-controls__narration" aria-live="polite">${display.narration}</p>
        <div class="replay-controls__moves" role="group" aria-label="Move through the replay">
            ${MOVE_ORDER.map((name) => MoveButton(name, display.moves[name], props.onMove))}
        </div>
    `;
}
