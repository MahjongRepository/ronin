import { type MessageKey, t } from "@/shared/i18n";

import { type DecisionCountdown } from "./countdown";

/** The seconds left at which the countdown is announced to a screen reader, the largest first. */
const ANNOUNCED_SECONDS = [10, 5] as const;

const MOVE_NAMES: Readonly<Record<DecisionCountdown["move"], MessageKey>> = {
    call: "game.move.call",
    chankan: "game.move.chankan",
    result: "game.move.result",
    start: "game.move.start",
    turn: "game.move.turn",
};

const EXPIRY_NOTES: Readonly<Record<DecisionCountdown["move"], MessageKey>> = {
    call: "game.expiry.move",
    chankan: "game.expiry.move",
    result: "game.expiry.result",
    start: "game.expiry.start",
    turn: "game.expiry.move",
};

export function moveName(move: DecisionCountdown["move"]): string {
    return t(MOVE_NAMES[move]);
}

export function expiredSentence(move: DecisionCountdown["move"]): string {
    return t("game.countdown.expired", { expiry: t(EXPIRY_NOTES[move]), move: moveName(move) });
}

/**
 * What the polite live region says: it changes only when the countdown crosses a threshold, a turn's base time runs
 * out into its bank, or it expires, so a screen reader is not read the seconds every second.
 */
export function countdownAnnouncement(countdown: DecisionCountdown | null): string {
    if (countdown?.kind === "expired") {
        return t("game.countdown.time_is_up");
    }
    if (countdown?.kind !== "running") {
        return "";
    }
    const crossed = ANNOUNCED_SECONDS.findLast((seconds) => countdown.secondsLeft <= seconds);
    if (crossed !== undefined) {
        return t("game.countdown.seconds_or_less", { count: crossed });
    }
    return countdown.clock?.inBank === true ? t("game.countdown.bank_running") : "";
}
