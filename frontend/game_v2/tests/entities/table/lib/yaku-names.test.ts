import { afterEach, describe, expect, test, vi } from "vitest";

import { yakuName } from "@/entities/table/lib/yaku-names";
import { t } from "@/shared/i18n";

const SERVER_YAKU_IDS = [
    ...Array.from({ length: 40 }).keys(),
    ...[...Array.from({ length: 23 }).keys()].map((index) => 100 + index),
];

describe("yakuName", () => {
    afterEach(() => {
        document.documentElement.lang = "";
        vi.restoreAllMocks();
    });

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
        expect(yakuName(15)).toBe("Yakuhai Haku");
        expect(yakuName(16)).toBe("Yakuhai Hatsu");
        expect(yakuName(17)).toBe("Yakuhai Chun");
        expect(yakuName(18)).toBe("Seat Wind East");
        expect(yakuName(22)).toBe("Round Wind East");
    });

    test("returns correct names for yakuman", () => {
        expect(yakuName(100)).toBe("Kokushi Musou");
        expect(yakuName(102)).toBe("Suuankou");
        expect(yakuName(103)).toBe("Daisangen");
        expect(yakuName(113)).toBe("Suuankou Tanki");
        expect(yakuName(115)).toBe("Tenhou");
    });

    test("returns correct names for dora", () => {
        expect(yakuName(120)).toBe("Dora");
        expect(yakuName(121)).toBe("Aka Dora");
        expect(yakuName(122)).toBe("Ura Dora");
    });

    test.each([
        ["en", "Iipeikou"],
        ["ja", "一盃口"],
        ["ru", "Иипейко"],
    ])("names every server yaku id in %s without the generic fallback", (locale, iipeikou) => {
        document.documentElement.lang = locale;
        const report = vi.spyOn(console, "error").mockImplementation(() => undefined);

        const unnamed = SERVER_YAKU_IDS.filter(
            (id) => yakuName(id) === t("yaku.unknown", { id: String(id) }),
        );

        expect(unnamed).toEqual([]);
        expect(yakuName(14)).toBe(iipeikou);
        expect(report).not.toHaveBeenCalled();
    });

    test("names an unknown id by its number and reports it", () => {
        const report = vi.spyOn(console, "error").mockImplementation(() => undefined);

        expect(yakuName(99)).toBe("Yaku 99");
        expect(report).toHaveBeenCalledWith(
            "i18n error",
            expect.objectContaining({ key: "yaku.99" }),
        );
    });
});
