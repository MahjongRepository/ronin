import { type TemplateResult } from "lit-html";

import { formatRoundName } from "@/entities/table/lib/round-name";
import { windName } from "@/entities/table/lib/wind-name";
import { type RoundInfo } from "@/entities/table/model/navigation-index";

import { type DropdownItem, DropdownSelect } from "./dropdown-select";

interface RoundSelectorProps {
    currentRound: RoundInfo | undefined;
    isOpen: boolean;
    onSelect: (stepIndex: number) => void;
    onToggle: () => void;
    rounds: RoundInfo[];
}

/** Formats a round's label for display in the dropdown: "East 2, 1 honba — Tsumo by Alice". */
function formatRoundLabel(round: RoundInfo): string {
    const name = formatRoundName(round.wind, round.roundNumber, round.honba);
    return round.resultDescription ? `${name} \u2014 ${round.resultDescription}` : name;
}

/** Builds the trigger label from the current round: "East 2" or "Rounds" if none. */
function triggerLabel(currentRound: RoundInfo | undefined): string {
    if (!currentRound) {
        return "Rounds";
    }
    return `${windName(currentRound.wind)} ${currentRound.roundNumber}`;
}

/** Maps RoundInfo[] to DropdownItem[] for the shared DropdownSelect component. */
function mapRoundsToItems(
    rounds: RoundInfo[],
    currentRound: RoundInfo | undefined,
): DropdownItem[] {
    return rounds.map((round) => ({
        isCurrent: round.actionStepIndex === currentRound?.actionStepIndex,
        label: formatRoundLabel(round),
        stepIndex: round.actionStepIndex,
    }));
}

/**
 * Stateless round selector component. Maps RoundInfo[] to dropdown items and
 * delegates rendering to DropdownSelect.
 */
function RoundSelector(props: RoundSelectorProps): TemplateResult {
    const { currentRound, isOpen, onSelect, onToggle, rounds } = props;

    return DropdownSelect({
        isOpen,
        items: mapRoundsToItems(rounds, currentRound),
        onSelect,
        onToggle,
        triggerLabel: triggerLabel(currentRound),
    });
}

export { RoundSelector, formatRoundLabel };
export type { RoundSelectorProps };
