/** Sub-pixel slack for comparing layout boxes. */
export const EPSILON = 1;

/** The smallest decision button, leave button and play switch, in CSS pixels: a tap target. */
export const MIN_ACTION_SIZE = 40;

export interface Box {
    readonly left: number;
    readonly top: number;
    readonly width: number;
    readonly height: number;
}

export interface Size {
    readonly width: number;
    readonly height: number;
}

/** A box on the board and the area it belongs to; boxes of different areas must not intersect. */
export interface GroupedBox {
    readonly group: string;
    readonly box: Box;
}

export function contains(outer: Box, inner: Box): boolean {
    return (
        inner.left >= outer.left - EPSILON &&
        inner.top >= outer.top - EPSILON &&
        inner.left + inner.width <= outer.left + outer.width + EPSILON &&
        inner.top + inner.height <= outer.top + outer.height + EPSILON
    );
}

export function intersects(first: Box, second: Box): boolean {
    return (
        first.left + EPSILON < second.left + second.width &&
        second.left + EPSILON < first.left + first.width &&
        first.top + EPSILON < second.top + second.height &&
        second.top + EPSILON < first.top + first.height
    );
}

export function describeSize(size: Size): string {
    return `${Math.round(size.width)}x${Math.round(size.height)}`;
}

export function describeBox(box: Box): string {
    return `${describeSize(box)}@${Math.round(box.left)},${Math.round(box.top)}`;
}

/** Pairs of boxes from different areas that intersect, named by their areas. */
export function findOverlaps(grouped: readonly GroupedBox[]): string[] {
    const overlaps = new Set<string>();
    for (const [index, first] of grouped.entries()) {
        for (const second of grouped.slice(index + 1)) {
            if (first.group !== second.group && intersects(first.box, second.box)) {
                overlaps.add([first.group, second.group].toSorted().join(" x "));
            }
        }
    }
    return [...overlaps];
}

export function longSide(box: Box): number {
    return Math.max(box.width, box.height);
}

/** Whether two boxes come within `gap` of each other. */
export function near(first: Box, second: Box, gap: number): boolean {
    return (
        first.left < second.left + second.width + gap &&
        second.left < first.left + first.width + gap &&
        first.top < second.top + second.height + gap &&
        second.top < first.top + first.height + gap
    );
}

export function grown(target: Box, by: number): Box {
    return {
        height: target.height + 2 * by,
        left: target.left - by,
        top: target.top - by,
        width: target.width + 2 * by,
    };
}

export function sameBox(first: Box, second: Box): boolean {
    return (
        Math.abs(first.left - second.left) <= EPSILON &&
        Math.abs(first.top - second.top) <= EPSILON &&
        Math.abs(first.width - second.width) <= EPSILON &&
        Math.abs(first.height - second.height) <= EPSILON
    );
}
