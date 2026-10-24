import { describe, expect, test } from "vitest";

import { yakuName } from "@/entities/table/lib/yaku-names";

describe("yakuName", () => {
    test("returns correct names for situational yaku", () => {
        expect(yakuName(0)).toBe("Menzen Tsumo");
        expect(yakuName(1)).toBe("Riichi");
        expect(yakuName(3)).toBe("Ippatsu");
        expect(yakuName(8)).toBe("Double Riichi");
    });

    test("returns correct names for hand pattern yaku", () => {
        expect(yakuName(12)).toBe("Pinfu");
        expect(yakuName(13)).toBe("Tanyao");
        expect(yakuName(34)).toBe("Chiitoitsu");
        expect(yakuName(39)).toBe("Chinitsu");
    });

    test("returns correct names for yakuhai variants", () => {
        expect(yakuName(15)).toBe("Yakuhai (haku)");
        expect(yakuName(16)).toBe("Yakuhai (hatsu)");
        expect(yakuName(17)).toBe("Yakuhai (chun)");
        expect(yakuName(18)).toBe("Yakuhai (seat wind east)");
        expect(yakuName(22)).toBe("Yakuhai (round wind east)");
    });

    test("returns correct names for yakuman", () => {
        expect(yakuName(100)).toBe("Kokushi Musou");
        expect(yakuName(102)).toBe("Suu Ankou");
        expect(yakuName(103)).toBe("Daisangen");
        expect(yakuName(113)).toBe("Suu Ankou Tanki");
        expect(yakuName(115)).toBe("Tenhou");
    });

    test("returns correct names for dora", () => {
        expect(yakuName(120)).toBe("Dora");
        expect(yakuName(121)).toBe("Aka Dora");
        expect(yakuName(122)).toBe("Ura Dora");
    });

    test("returns 'Unknown yaku' for unrecognized IDs", () => {
        expect(yakuName(99)).toBe("Unknown yaku");
        expect(yakuName(-1)).toBe("Unknown yaku");
        expect(yakuName(200)).toBe("Unknown yaku");
    });
});
