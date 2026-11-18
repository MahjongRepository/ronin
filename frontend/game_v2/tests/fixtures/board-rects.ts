import { LYING_Y_SHARE, TILE_EDGE_SHARE } from "@/entities/table/lib/board-constants";
import { type BoardGeometry, type BoardRect } from "@/entities/table/lib/board-geometry";

export const RIVERS = ["river-bottom", "river-right", "river-top", "river-left"] as const;

export function riverReserves({
    lengths,
}: BoardGeometry): Record<(typeof RIVERS)[number], BoardRect> {
    function length(name: string): number {
        return lengths[name] ?? Number.NaN;
    }
    const [cx, cy, hx, h, gap, rh, drop] = [
        "cx",
        "cy",
        "hx",
        "h",
        "g",
        "rh",
        "latest-drop-gap",
    ].map(length);
    const edge = TILE_EDGE_SHARE * length("rw");
    const down = rh * LYING_Y_SHARE;
    const sideRow = 5 * length("rw") * LYING_Y_SHARE + down + drop;
    return {
        "river-bottom": {
            bottom: cy + h + gap + 3 * down + drop + edge,
            left: cx - hx,
            right: length("reach-bottom-right"),
            top: cy + h + gap,
        },
        "river-left": {
            bottom: cy - h + sideRow + edge,
            left: length("reach-left"),
            right: cx - hx - gap,
            top: cy - h,
        },
        "river-right": {
            bottom: cy + h - length("river-right-lift") + edge,
            left: cx + hx + gap,
            right: length("reach-right"),
            top: cy + h - length("river-right-lift") - sideRow,
        },
        "river-top": {
            bottom: cy - h - length("g-top") + edge,
            left: length("reach-top-left"),
            right: cx + hx,
            top: length("reach-top-row3") - down - drop,
        },
    };
}

export function cogSquare({ areas, lengths }: BoardGeometry): BoardRect | undefined {
    const slot = areas["corner"];
    if (slot === undefined) {
        return undefined;
    }
    const side = lengths["menu-size"] ?? Number.NaN;
    const middle = (slot.left + slot.right) / 2;
    return {
        bottom: slot.top + side,
        left: middle - side / 2,
        right: middle + side / 2,
        top: slot.top,
    };
}
