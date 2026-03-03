// Yaku ID → English name mapping for the mahjong Python library.
// IDs 0–11: situational, 12–39: hand patterns, 100–119: yakuman, 120–122: dora.
// eslint-disable-next-line sort-keys -- numeric ID order is more readable than string sort
const YAKU_NAMES: Record<number, string> = {
    // Situational yaku
    0: "Menzen Tsumo",
    1: "Riichi",
    2: "Open Riichi",
    3: "Ippatsu",
    4: "Chankan",
    5: "Rinshan Kaihou",
    6: "Haitei Raoyue",
    7: "Houtei Raoyui",
    8: "Double Riichi",
    9: "Double Open Riichi",
    10: "Nagashi Mangan",
    11: "Renhou",

    // Hand pattern yaku
    12: "Pinfu",
    13: "Tanyao",
    14: "Iipeiko",
    15: "Yakuhai (haku)",
    16: "Yakuhai (hatsu)",
    17: "Yakuhai (chun)",
    18: "Yakuhai (seat wind east)",
    19: "Yakuhai (seat wind south)",
    20: "Yakuhai (seat wind west)",
    21: "Yakuhai (seat wind north)",
    22: "Yakuhai (round wind east)",
    23: "Yakuhai (round wind south)",
    24: "Yakuhai (round wind west)",
    25: "Yakuhai (round wind north)",
    26: "Sanshoku Doujun",
    27: "Ittsu",
    28: "Chantai",
    29: "Honroutou",
    30: "Toitoi",
    31: "San Ankou",
    32: "San Kantsu",
    33: "Sanshoku Doukou",
    34: "Chiitoitsu",
    35: "Shou Sangen",
    36: "Honitsu",
    37: "Junchan",
    38: "Ryanpeikou",
    39: "Chinitsu",

    // Yakuman
    100: "Kokushi Musou",
    101: "Chuuren Poutou",
    102: "Suu Ankou",
    103: "Daisangen",
    104: "Shousuushii",
    105: "Ryuuiisou",
    106: "Suu Kantsu",
    107: "Tsuu Iisou",
    108: "Chinroutou",
    109: "Daisharin",
    110: "Daichisei",
    111: "Dai Suushii",
    112: "Kokushi Musou Juusanmen Matchi",
    113: "Suu Ankou Tanki",
    114: "Daburu Chuuren Poutou",
    115: "Tenhou",
    116: "Chiihou",
    117: "Renhou (yakuman)",
    118: "Sashikomi",
    119: "Paarenchan",

    // Dora
    120: "Dora",
    121: "Aka Dora",
    122: "Ura Dora",
};

export function yakuName(yakuId: number): string {
    return YAKU_NAMES[yakuId] ?? "Unknown yaku";
}
