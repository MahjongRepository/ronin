import { type DrawKind } from "@/entities/table/model/types";

const DRAW_NAMES: Readonly<Record<DrawKind, string>> = {
    exhaustive: "Exhaustive draw",
    four_kans: "Four kans",
    four_riichi: "Four riichi",
    four_winds: "Four winds",
    nagashi_mangan: "Nagashi Mangan",
    nine_terminals: "Nine terminals",
    triple_ron: "Triple ron",
};

export function drawName(kind: DrawKind): string {
    return DRAW_NAMES[kind];
}

/** Whether the draw aborted the round before the wall ran out. */
export function isAbortiveDraw(kind: DrawKind): boolean {
    return kind !== "exhaustive" && kind !== "nagashi_mangan";
}
