import { type HandValue } from "@/entities/table/model/types";
import { assertNever } from "@/shared/lib";
import { HAND_LIMIT } from "@/shared/protocol";

const MULTIPLE_YAKUMAN_NAMES: Readonly<Record<number, string>> = {
    2: "Double Yakuman",
    3: "Triple Yakuman",
};

/** Whether the server paid a hand as a yakuman: a yaku of it is one, never a kazoe yakuman's 13 han of ordinary yaku. */
export function isYakumanHand(hand: HandValue): boolean {
    return hand.limit === HAND_LIMIT.YAKUMAN;
}

/** A yakuman's name for how many yakuman it counts: "Yakuman", "Double Yakuman", … */
export function yakumanName(multiple: number): string {
    if (multiple <= 1) {
        return "Yakuman";
    }
    return MULTIPLE_YAKUMAN_NAMES[multiple] ?? `${multiple}x Yakuman`;
}

function yakumanCountOf(hand: HandValue): number {
    if (hand.yakumanCount === null) {
        throw new Error(`A ${hand.limit} hand names no yakuman count`);
    }
    return hand.yakumanCount;
}

/**
 * The limit a winning hand was paid at (Mangan … Yakuman, "Kazoe Yakuman" for 13 han of ordinary yaku), or null below
 * mangan: the server's limit (`limit`) and yakuman count, so it follows the game's rules as the server applied them
 * (kiriage mangan, kazoe yakuman or capped at sanbaiman, double yakuman or not), never worked back from the points.
 */
export function handLimitName(hand: HandValue): string | null {
    switch (hand.limit) {
        case HAND_LIMIT.NONE: {
            return null;
        }
        case HAND_LIMIT.MANGAN: {
            return "Mangan";
        }
        case HAND_LIMIT.HANEMAN: {
            return "Haneman";
        }
        case HAND_LIMIT.BAIMAN: {
            return "Baiman";
        }
        case HAND_LIMIT.SANBAIMAN: {
            return "Sanbaiman";
        }
        case HAND_LIMIT.YAKUMAN: {
            return yakumanName(yakumanCountOf(hand));
        }
        case HAND_LIMIT.KAZOE_YAKUMAN: {
            return "Kazoe Yakuman";
        }
        default: {
            return assertNever(hand.limit);
        }
    }
}
