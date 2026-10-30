import {
    type PlayerState,
    type RoundEndResult,
    createInitialPlayerState,
    extractRoundEndResult,
} from "@/entities/table";
import { type RoundEndEvent, parseRoundEnd } from "@/shared/protocol";

interface ResultSource {
    /** The generated replay fixture (`src/fixtures/replays/`) whose round end this is. */
    readonly fixture: string;
    readonly key: string;
    readonly label: string;
    readonly dealerSeat: number;
    readonly doraIndicators: readonly number[];
    readonly names: readonly string[];
    /** The riichi stick value its fixture's recorded settings (`gs`) name. */
    readonly riichiStickValue: number;
    /** The round end's wire line as the fixture records it. */
    readonly roundEnd: string;
}

/**
 * The round results the board storybook shows over its board: each the wire round end of a generated replay fixture,
 * with the dealer, dora indicators and names of its round and its game's riichi stick value, parsed and read as the
 * table reads it. A copy, so the storybook's chunk carries one line of each fixture rather than the whole file; a test
 * fails when a copy no longer reads as its fixture's round end does.
 */
const RESULT_SOURCES = [
    {
        dealerSeat: 0,
        doraIndicators: [109],
        fixture: "riichi",
        key: "tsumo",
        label: "Tsumo",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 0, "ws": 1, "hr": {"han": 5, "fu": 20, "yk": [{"yi": 0, "han": 1}, {"yi": 1, "han": 1}, {"yi": 12, "han": 1}, {"yi": 121, "han": 1}, {"yi": 122, "han": 1}], "pt": 80}, "scs": {"0": 250, "1": 240, "2": 250, "3": 240}, "sch": {"0": -40, "1": 100, "2": -20, "3": -20}, "rc": 2, "ct": [0, 4, 8, 48, 52, 56, 60, 64, 68, 80, 84, 104, 105], "ml": [], "wt": 89, "ud": [65]}',
    },
    {
        dealerSeat: 0,
        doraIndicators: [120],
        fixture: "ron_riichi_discard",
        key: "ron",
        label: "Ron",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 1, "ws": 1, "ls": 2, "wt": 49, "hr": {"han": 7, "fu": 30, "yk": [{"yi": 3, "han": 1}, {"yi": 8, "han": 2}, {"yi": 12, "han": 1}, {"yi": 27, "han": 2}, {"yi": 121, "han": 1}], "pt": 120}, "scs": {"0": 250, "1": 240, "2": 250, "3": 250}, "sch": {"0": 0, "1": 130, "2": -120, "3": 0}, "rc": 1, "ct": [0, 4, 8, 12, 16, 20, 24, 28, 32, 40, 44, 72, 73], "ml": [], "ud": [131]}',
    },
    {
        dealerSeat: 0,
        doraIndicators: [116],
        fixture: "double_ron",
        key: "double_ron",
        label: "Double ron",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 2, "ls": 0, "wt": 50, "wn": [{"ws": 1, "hr": {"han": 7, "fu": 30, "yk": [{"yi": 3, "han": 1}, {"yi": 8, "han": 2}, {"yi": 12, "han": 1}, {"yi": 27, "han": 2}, {"yi": 121, "han": 1}], "pt": 120}, "sch": {"0": -120, "1": 140, "2": 0, "3": 0}, "rc": 2, "ct": [0, 4, 8, 12, 16, 20, 24, 28, 32, 40, 44, 72, 73], "ml": [], "ud": [130]}, {"ws": 2, "hr": {"han": 4, "fu": 30, "yk": [{"yi": 3, "han": 1}, {"yi": 8, "han": 2}, {"yi": 12, "han": 1}], "pt": 80}, "sch": {"0": -80, "1": 0, "2": 80, "3": 0}, "rc": 0, "ct": [5, 9, 13, 33, 34, 53, 57, 85, 89, 93, 94, 97, 101], "ml": [], "ud": [130]}], "scs": {"0": 250, "1": 240, "2": 240, "3": 250}, "sch": {"0": -200, "1": 140, "2": 80, "3": 0}}',
    },
    {
        dealerSeat: 2,
        doraIndicators: [9],
        fixture: "eager_game",
        key: "dealer",
        label: "Dealer",
        names: ["Alice", "Charlie", "Bob", "Diana"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 0, "ws": 2, "hr": {"han": 5, "fu": 25, "yk": [{"yi": 0, "han": 1}, {"yi": 13, "han": 1}, {"yi": 34, "han": 2}, {"yi": 121, "han": 1}], "pt": 120}, "scs": {"0": 230, "1": 210, "2": 230, "3": 330}, "sch": {"0": -40, "1": -40, "2": 120, "3": -40}, "rc": 0, "ct": [11, 21, 55, 64, 77, 79, 85, 87, 88, 65, 89, 53, 10], "ml": [], "wt": 23}',
    },
    {
        dealerSeat: 0,
        doraIndicators: [107],
        fixture: "head_bump",
        key: "head_bump",
        label: "Head bump",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 1, "ws": 1, "ls": 0, "wt": 46, "hr": {"han": 8, "fu": 40, "yk": [{"yi": 11, "han": 5}, {"yi": 27, "han": 2}, {"yi": 121, "han": 1}], "pt": 160}, "scs": {"0": 250, "1": 250, "2": 250, "3": 250}, "sch": {"0": -160, "1": 160, "2": 0, "3": 0}, "rc": 0, "ct": [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 124, 125], "ml": [], "hbs": [2]}',
    },
    {
        dealerSeat: 0,
        doraIndicators: [102, 103, 104, 107],
        fixture: "kans",
        key: "sanbaiman",
        label: "Sanbaiman",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 0, "ws": 3, "hr": {"han": 11, "fu": 60, "yk": [{"yi": 0, "han": 1}, {"yi": 5, "han": 1}, {"yi": 120, "han": 8}, {"yi": 121, "han": 1}], "pt": 240}, "scs": {"0": 250, "1": 250, "2": 250, "3": 250}, "sch": {"0": -120, "1": -60, "2": -60, "3": 240}, "rc": 0, "ct": [4, 8, 12, 52, 56, 60, 92, 96, 100, 32], "ml": [24363], "wt": 33}',
    },
    {
        dealerSeat: 0,
        doraIndicators: [112],
        fixture: "kazoe",
        key: "kazoe",
        label: "Kazoe",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 0, "ws": 0, "hr": {"han": 15, "fu": 20, "yk": [{"yi": 0, "han": 1}, {"yi": 3, "han": 1}, {"yi": 8, "han": 2}, {"yi": 12, "han": 1}, {"yi": 13, "han": 1}, {"yi": 38, "han": 3}, {"yi": 39, "han": 6}], "pt": 480}, "scs": {"0": 240, "1": 250, "2": 250, "3": 250}, "sch": {"0": 490, "1": -160, "2": -160, "3": -160}, "rc": 1, "ct": [40, 44, 45, 48, 49, 53, 54, 56, 57, 60, 61, 64, 65], "ml": [], "wt": 41, "ud": [131]}',
    },
    {
        dealerSeat: 0,
        doraIndicators: [112],
        fixture: "chankan_added",
        key: "chankan",
        label: "Chankan",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 1, "ws": 2, "ls": 1, "wt": 59, "hr": {"han": 6, "fu": 30, "yk": [{"yi": 4, "han": 1}, {"yi": 12, "han": 1}, {"yi": 27, "han": 2}, {"yi": 121, "han": 2}], "pt": 120}, "scs": {"0": 250, "1": 250, "2": 250, "3": 250}, "sch": {"0": 0, "1": -120, "2": 120, "3": 0}, "rc": 0, "ct": [0, 4, 8, 12, 16, 20, 24, 28, 32, 48, 52, 72, 73], "ml": [], "rk": {"s": 1, "ti": 59, "kty": "added"}}',
    },
    {
        dealerSeat: 0,
        doraIndicators: [109],
        fixture: "chankan_closed_kokushi",
        key: "yakuman",
        label: "Yakuman",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 1, "ws": 2, "ls": 1, "wt": 35, "hr": {"han": 13, "fu": 0, "yk": [{"yi": 100, "han": 13}], "pt": 320}, "scs": {"0": 250, "1": 250, "2": 250, "3": 250}, "sch": {"0": 0, "1": -320, "2": 320, "3": 0}, "rc": 0, "ct": [0, 1, 36, 68, 72, 104, 108, 112, 116, 120, 124, 128, 132], "ml": [], "rk": {"s": 1, "ti": 35, "kty": "closed"}}',
    },
    {
        dealerSeat: 0,
        doraIndicators: [106],
        fixture: "pao",
        key: "pao",
        label: "Pao",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 0, "ws": 1, "hr": {"han": 13, "fu": 40, "yk": [{"yi": 103, "han": 13}], "pt": 320}, "scs": {"0": 250, "1": 250, "2": 250, "3": 250}, "sch": {"0": -320, "1": 320, "2": 0, "3": 0}, "rc": 0, "ct": [0, 4, 8, 12], "ml": [20733, 20869, 21021], "wt": 13, "ps": 0}',
    },
    {
        dealerSeat: 0,
        doraIndicators: [116],
        fixture: "exhaustive_tenpai",
        key: "exhaustive",
        label: "Exhaustive",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 3, "ts": [1, 2], "ns": [0, 3], "th": [{"s": 1, "ct": [37, 41, 45, 49, 53, 57, 61, 65, 69, 73, 74, 75, 135], "ml": []}, {"s": 2, "ct": [6, 10, 14, 18, 22, 26, 82, 86, 90, 94, 98, 102, 131], "ml": []}], "scs": {"0": 250, "1": 240, "2": 250, "3": 250}, "sch": {"0": -15, "1": 15, "2": 15, "3": -15}}',
    },
    {
        dealerSeat: 3,
        doraIndicators: [32],
        fixture: "full_game",
        key: "all_noten",
        label: "All noten",
        names: ["Wanjirou", "Ojisan", "Ichihime", "Akagi"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 3, "ts": [], "ns": [0, 1, 2, 3], "th": [], "scs": {"0": 250, "1": 250, "2": 250, "3": 250}, "sch": {"0": 0, "1": 0, "2": 0, "3": 0}}',
    },
    {
        dealerSeat: 0,
        doraIndicators: [120],
        fixture: "nagashi",
        key: "nagashi",
        label: "Nagashi",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 5, "qs": [1], "ts": [3], "ns": [0, 1, 2], "th": [{"s": 3, "ct": [7, 11, 15, 19, 23, 27, 79, 83, 87, 91, 95, 99, 127], "ml": []}], "scs": {"0": 250, "1": 250, "2": 250, "3": 250}, "sch": {"0": -40, "1": 80, "2": -20, "3": -20}}',
    },
    {
        dealerSeat: 0,
        doraIndicators: [110],
        fixture: "kyuushu",
        key: "kyuushu",
        label: "Kyuushu",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 4, "rn": "nine_terminals", "scs": {"0": 250, "1": 250, "2": 250, "3": 250}, "sch": {"0": 0, "1": 0, "2": 0, "3": 0}, "s": 1}',
    },
    {
        dealerSeat: 0,
        doraIndicators: [114],
        fixture: "four_riichi",
        key: "four_riichi",
        label: "4 riichi",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 4, "rn": "four_riichi", "scs": {"0": 240, "1": 240, "2": 240, "3": 240}, "sch": {"0": 0, "1": 0, "2": 0, "3": 0}}',
    },
    {
        dealerSeat: 0,
        doraIndicators: [107],
        fixture: "triple_ron",
        key: "triple_ron",
        label: "Triple ron",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 4, "rn": "triple_ron", "scs": {"0": 250, "1": 250, "2": 250, "3": 250}, "sch": {"0": 0, "1": 0, "2": 0, "3": 0}, "rcl": [1, 2, 3]}',
    },
    {
        dealerSeat: 0,
        doraIndicators: [115],
        fixture: "four_winds_riichi",
        key: "four_winds",
        label: "4 winds",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 4, "rn": "four_winds", "scs": {"0": 250, "1": 250, "2": 250, "3": 250}, "sch": {"0": 0, "1": 0, "2": 0, "3": 0}}',
    },
    {
        dealerSeat: 0,
        doraIndicators: [116, 119, 120, 121, 124],
        fixture: "four_kans",
        key: "four_kans",
        label: "4 kans",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd:
            '{"t": 4, "rt": 4, "rn": "four_kans", "scs": {"0": 250, "1": 250, "2": 250, "3": 250}, "sch": {"0": 0, "1": 0, "2": 0, "3": 0}}',
    },
] as const satisfies readonly ResultSource[];

export type ResultStory = (typeof RESULT_SOURCES)[number]["key"];

export const RESULT_STORIES: readonly ResultStory[] = RESULT_SOURCES.map((source) => source.key);

function resultSource(story: ResultStory): ResultSource {
    const source = RESULT_SOURCES.find((candidate) => candidate.key === story);
    if (source === undefined) {
        throw new Error(`No result story ${story}`);
    }
    return source;
}

export function resultStoryLabel(story: ResultStory): string {
    return resultSource(story).label;
}

export interface ResultStoryTable {
    /** The replay fixture the story's round end comes from. */
    readonly fixture: string;
    readonly result: RoundEndResult;
    readonly players: readonly PlayerState[];
    readonly dealerSeat: number;
}

function parseWireRoundEnd(line: string): RoundEndEvent {
    const raw: unknown = JSON.parse(line);
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
        throw new Error(`A round end line is not a JSON object: ${line}`);
    }
    return parseRoundEnd(Object.fromEntries(Object.entries(raw)));
}

export function resultStoryTable(story: ResultStory): ResultStoryTable {
    const source = resultSource(story);
    const event = parseWireRoundEnd(source.roundEnd);
    const players = source.names.map((name, seat) =>
        createInitialPlayerState({
            isAiPlayer: false,
            name,
            score: event.scores[String(seat)] ?? 0,
            seat,
        }),
    );
    return {
        dealerSeat: source.dealerSeat,
        fixture: source.fixture,
        players,
        result: extractRoundEndResult(event, source),
    };
}
