import { TILE_EDGE_SHARE } from "@/entities/table/lib/board-constants";
import { type BoardGeometry, type BoardRect } from "@/entities/table/lib/board-geometry";

export const RIVERS = ["river-bottom", "river-right", "river-top", "river-left"] as const;

/**
 * Each river's tiles' reserve on a board or a camera's plane, rebuilt from its lengths: a row of six with a sideways
 * riichi tile, the top and bottom rivers' third row run on (to `reach-top-left`, `reach-bottom-right`), the side rivers'
 * fourth wrapped (to `reach-left`, `reach-right`), the latest discard's gaps and the tile edge under the lowest tile. A
 * missing length leaves its edges not finite.
 */
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
    ].map(length) as [number, number, number, number, number, number, number];
    const edge = TILE_EDGE_SHARE * length("rw");
    const sideRow = 5 * length("rw") + rh + drop;
    return {
        "river-bottom": {
            bottom: cy + h + gap + 3 * rh + drop + edge,
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
            bottom: cy + h + edge,
            left: cx + hx + gap,
            right: length("reach-right"),
            top: cy + h - sideRow,
        },
        "river-top": {
            bottom: cy - h - length("g-top") + edge,
            left: length("reach-top-left"),
            right: cx + hx,
            top: length("reach-top-row3") - rh - drop,
        },
    };
}

/** The cog's own square on a flat board: `menu-size` from the corner slot's top, centred across it. */
export function cogSquare({ areas, lengths }: BoardGeometry): BoardRect | undefined {
    const slot = areas["corner"];
    if (slot === undefined) {
        return undefined;
    }
    const side = lengths["menu-size"] ?? 0;
    const middle = (slot.left + slot.right) / 2;
    return {
        bottom: slot.top + side,
        left: middle - side / 2,
        right: middle + side / 2,
        top: slot.top,
    };
}
