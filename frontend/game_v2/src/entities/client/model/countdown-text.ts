import { assertNever } from "@/shared/lib";

import { type DecisionCountdown } from "./countdown";

/** The seconds left at which the countdown is announced to a screen reader, the largest first. */
const ANNOUNCED_SECONDS = [10, 5] as const;

/** What the player owes, as a sentence's start: "It is your turn". */
export function moveName(move: DecisionCountdown["move"]): string {
    switch (move) {
        case "turn": {
            return "It is your turn";
        }
        case "call": {
            return "You can call the last discard";
        }
        case "chankan": {
            return "You can rob the kan";
        }
        case "result": {
            return "The round's result awaits your OK";
        }
        default: {
            return assertNever(move);
        }
    }
}

/** What the server does once the move's time is up. */
export function expiryNote(move: DecisionCountdown["move"]): string {
    return move === "result" ? "the server deals the next round" : "the server makes the move";
}

/**
 * What the polite live region says: it changes only when the countdown crosses a threshold, a turn's base time runs
 * out into its bank, or it expires, so a screen reader is not read the seconds every second.
 */
export function countdownAnnouncement(countdown: DecisionCountdown | null): string {
    if (countdown?.kind === "expired") {
        return "Time is up";
    }
    if (countdown?.kind !== "running") {
        return "";
    }
    const crossed = ANNOUNCED_SECONDS.findLast((seconds) => countdown.secondsLeft <= seconds);
    if (crossed !== undefined) {
        return `${crossed} seconds or less left`;
    }
    return countdown.turn?.inBank === true ? "Your time bank is running" : "";
}
