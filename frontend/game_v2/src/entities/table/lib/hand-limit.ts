import { type HandValue } from "@/entities/table/model/types";
import { type MessageKey, t } from "@/shared/i18n";
import { assertNever } from "@/shared/lib";
import { HAND_LIMIT } from "@/shared/protocol";

const YAKUMAN_NAMES: readonly MessageKey[] = [
    "game.score.yakuman_1",
    "game.score.yakuman_2",
    "game.score.yakuman_3",
    "game.score.yakuman_4",
    "game.score.yakuman_5",
    "game.score.yakuman_6",
];

/** Whether the server paid a hand as a yakuman: a yaku of it is one, never a kazoe yakuman's 13 han of ordinary yaku. */
export function isYakumanHand(hand: HandValue): boolean {
    return hand.limit === HAND_LIMIT.YAKUMAN;
}

export function yakumanName(multiple: number): string {
    return t(YAKUMAN_NAMES[multiple - 1] ?? "game.score.yakuman_1");
}

function yakumanCountOf(hand: HandValue): number {
    if (hand.yakumanCount === null) {
        throw new Error(`A ${hand.limit} hand names no yakuman count`);
    }
    return hand.yakumanCount;
}

export function handLimitName(hand: HandValue): string | null {
    switch (hand.limit) {
        case HAND_LIMIT.NONE: {
            return null;
        }
        case HAND_LIMIT.MANGAN: {
            return t("game.score.mangan");
        }
        case HAND_LIMIT.HANEMAN: {
            return t("game.score.haneman");
        }
        case HAND_LIMIT.BAIMAN: {
            return t("game.score.baiman");
        }
        case HAND_LIMIT.SANBAIMAN: {
            return t("game.score.sanbaiman");
        }
        case HAND_LIMIT.YAKUMAN: {
            return yakumanName(yakumanCountOf(hand));
        }
        case HAND_LIMIT.KAZOE_YAKUMAN: {
            return t("game.score.yakuman_1");
        }
        default: {
            return assertNever(hand.limit);
        }
    }
}
