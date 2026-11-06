import { type DrawKind } from "@/entities/table/model/types";
import { type MessageKey, t } from "@/shared/i18n";

const DRAW_NAMES: Readonly<Record<DrawKind, MessageKey>> = {
    exhaustive: "draw.exhaustive",
    four_kans: "draw.four_kans",
    four_riichi: "draw.four_riichi",
    four_winds: "draw.four_winds",
    nagashi_mangan: "draw.nagashi",
    nine_terminals: "draw.nine_terminals",
    triple_ron: "draw.triple_ron",
};

export function drawName(kind: DrawKind): string {
    return t(DRAW_NAMES[kind]);
}

/** Whether the draw aborted the round before the wall ran out. */
export function isAbortiveDraw(kind: DrawKind): boolean {
    return kind !== "exhaustive" && kind !== "nagashi_mangan";
}
