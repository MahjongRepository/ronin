const YAKUMAN_KANJI: ReadonlyMap<number, string> = new Map([
    [100, "国士無双"],
    [101, "九蓮宝燈"],
    [102, "四暗刻"],
    [103, "大三元"],
    [104, "小四喜"],
    [105, "緑一色"],
    [106, "四槓子"],
    [107, "字一色"],
    [108, "清老頭"],
    [109, "大車輪"],
    [110, "大七星"],
    [111, "大四喜"],
    [112, "国士無双十三面"],
    [113, "四暗刻単騎"],
    [114, "純正九蓮宝燈"],
    [115, "天和"],
    [116, "地和"],
    [117, "人和"],
    [118, "差し込み"],
    [119, "八連荘"],
]);

const SEAL_MULTIPLES: readonly string[] = ["", "二倍", "三倍", "四倍", "五倍", "六倍"];

/**
 * A named yakuman's name in kanji, which the result sets large in every language as its seal's caption; null for an
 * id outside the yakuman, which then shows its translated name alone.
 */
export function yakumanKanji(yakuId: number): string | null {
    return YAKUMAN_KANJI.get(yakuId) ?? null;
}

/** The seal's text for a yakuman counting `multiple`: 役満, then 二倍役満 and on for a double and more. */
export function yakumanSeal(multiple: number): string {
    return `${SEAL_MULTIPLES[multiple - 1] ?? ""}役満`;
}
