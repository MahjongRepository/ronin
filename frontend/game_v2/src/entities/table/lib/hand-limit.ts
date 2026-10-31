import { type HandValue } from "@/entities/table/model/types";

/** A limit hand's basic points, which every payment of it is a multiple of: 4x for a non-dealer, 6x for the dealer. */
const LIMITS = [
    { basicPoints: 8000, name: "Yakuman" },
    { basicPoints: 6000, name: "Sanbaiman" },
    { basicPoints: 4000, name: "Baiman" },
    { basicPoints: 3000, name: "Haneman" },
    { basicPoints: 2000, name: "Mangan" },
] as const;

const YAKUMAN_BASIC_POINTS = LIMITS[0].basicPoints;

const MULTIPLE_YAKUMAN_NAMES: Readonly<Record<number, string>> = {
    2: "Double Yakuman",
    3: "Triple Yakuman",
};

/** Whether the server scored a hand as a yakuman: a yaku of it is one, never inferred from its han or yaku ids. */
export function isYakumanHand(hand: HandValue): boolean {
    return hand.yaku.some((yaku) => yaku.isYakuman);
}

/** A yakuman's name for how many yakuman it counts: "Yakuman", "Double Yakuman", … */
export function yakumanName(multiple: number): string {
    if (multiple <= 1) {
        return "Yakuman";
    }
    return MULTIPLE_YAKUMAN_NAMES[multiple] ?? `${multiple}x Yakuman`;
}

/**
 * The limit a winning hand was paid at (Mangan … Yakuman, "Kazoe Yakuman" for 13 han of ordinary yaku), or null below
 * mangan. It reads the limit from the hand value the server paid, never from han alone, so it follows the game's
 * rules as the server applied them: kiriage mangan, kazoe yakuman or capped at sanbaiman, double yakuman or not, and
 * the yakuman cap. A non-dealer's hand is worth 4x its basic points, a dealer's 6x, and no hand below mangan reaches
 * 4x 2000.
 */
export function handLimitName(hand: HandValue, isDealer: boolean): string | null {
    const basicPoints = hand.points / (isDealer ? 6 : 4);
    if (basicPoints >= YAKUMAN_BASIC_POINTS) {
        if (!isYakumanHand(hand)) {
            return "Kazoe Yakuman";
        }
        return yakumanName(Math.floor(basicPoints / YAKUMAN_BASIC_POINTS));
    }
    return LIMITS.find((limit) => basicPoints >= limit.basicPoints)?.name ?? null;
}
