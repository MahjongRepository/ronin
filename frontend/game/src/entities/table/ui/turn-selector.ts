import { type TemplateResult } from "lit-html";

import { type TurnInfo } from "@/entities/table/model/navigation-index";

import { type DropdownItem, DropdownSelect } from "./dropdown-select";

interface TurnSelectorProps {
    currentStep: number;
    isOpen: boolean;
    onSelect: (stepIndex: number) => void;
    onToggle: () => void;
    turns: TurnInfo[];
}

/**
 * Finds the nearest turn to the current step — the last turn whose actionStepIndex
 * is less than or equal to currentStep. Returns undefined if no turns match.
 */
function findNearestTurn(turns: TurnInfo[], currentStep: number): TurnInfo | undefined {
    let nearest: TurnInfo | undefined = undefined;
    for (const turn of turns) {
        if (turn.actionStepIndex <= currentStep) {
            nearest = turn;
        } else {
            break;
        }
    }
    return nearest;
}

/** Builds the trigger label: "Turn N" for the nearest turn, or "Turns" if none. */
function triggerLabel(turns: TurnInfo[], currentStep: number): string {
    const nearest = findNearestTurn(turns, currentStep);
    if (!nearest) {
        return "Turns";
    }
    return `Turn ${nearest.turnNumber}`;
}

/** Maps TurnInfo[] to DropdownItem[] for the shared DropdownSelect component. */
function mapTurnsToItems(turns: TurnInfo[], currentStep: number): DropdownItem[] {
    const nearest = findNearestTurn(turns, currentStep);
    return turns.map((turn) => ({
        isCurrent: turn.actionStepIndex === nearest?.actionStepIndex,
        label: `Turn ${turn.turnNumber} \u2014 ${turn.playerName}`,
        stepIndex: turn.actionStepIndex,
    }));
}

/**
 * Stateless turn selector component. Maps TurnInfo[] to dropdown items and
 * delegates rendering to DropdownSelect.
 */
function TurnSelector(props: TurnSelectorProps): TemplateResult {
    const { currentStep, isOpen, onSelect, onToggle, turns } = props;

    return DropdownSelect({
        isOpen,
        items: mapTurnsToItems(turns, currentStep),
        onSelect,
        onToggle,
        triggerLabel: triggerLabel(turns, currentStep),
    });
}

export { TurnSelector, findNearestTurn };
export type { TurnSelectorProps };
