import { type BoardMotionCue, type SeatPosition } from "@/entities/table/model/board-types";

const FLIGHT = 120;
const GHOSTS = [
    { alpha: 0.125, delay: 0 },
    { alpha: 0.25, delay: 12 },
    { alpha: 0.125, delay: 24 },
] as const;

export const BOARD_MOTION = {
    drawHold: 300,
    flight: FLIGHT,
    gapSlide: 120,
    ghosts: GHOSTS,
    handClose: 300,
    landing: GHOSTS[1].delay + FLIGHT,
    maxTravel: 300,
    meldShift: 200,
    meldSpeed: 0.06,
    minTravel: 80,
    revealTile: 30,
    slotEasing: "cubic-bezier(0.16, 1, 0.3, 1)",
} as const;

export const DISCARD_LANDING_MS = BOARD_MOTION.landing;

export interface MotionRect {
    readonly left: number;
    readonly top: number;
    readonly width: number;
    readonly height: number;
}

export interface MotionTile {
    readonly key: string;
    readonly id: string;
    readonly seat: SeatPosition;
    readonly region: "hand" | "discards" | "melds" | "dora";
    readonly index: number;
    readonly drawn: boolean;
    readonly concealed: boolean;
    readonly tsumogiri: boolean;
    readonly latest: boolean;
    readonly rect: MotionRect;
    readonly painted: MotionRect;
}

export interface TileMotion {
    readonly target: string;
    readonly source: string | null;
    readonly kind: "flight" | "hold" | "reflow" | "reveal";
    readonly duration: number;
    readonly delay: number;
}

export function travelDuration(from: MotionRect, to: MotionRect, speed: number): number {
    const distance = Math.hypot(to.left - from.left, to.top - from.top);
    const tileWidth = Math.max(1, Math.min(to.width, to.height));
    return Math.min(
        BOARD_MOTION.maxTravel,
        Math.max(BOARD_MOTION.minTravel, Math.round(distance / (tileWidth * speed))),
    );
}

function samePlace(first: MotionTile, second: MotionTile): boolean {
    return first.seat === second.seat && first.region === second.region;
}

function findSource(target: MotionTile, before: readonly MotionTile[]): MotionTile | undefined {
    const identified = target.id === "" ? [] : before.filter((tile) => tile.id === target.id);
    return (
        identified.find((tile) => samePlace(tile, target)) ??
        identified[0] ??
        before.find((tile) => tile.key === target.key)
    );
}

function concealedSource(
    target: MotionTile,
    before: readonly MotionTile[],
): MotionTile | undefined {
    const hand = before.filter(
        (tile) => tile.seat === target.seat && tile.region === "hand" && tile.concealed,
    );
    return target.tsumogiri
        ? hand.find((tile) => tile.drawn)
        : hand.findLast((tile) => !tile.drawn);
}

function hasChangedRect(first: MotionRect, second: MotionRect): boolean {
    return (
        Math.abs(first.left - second.left) > 0.5 ||
        Math.abs(first.top - second.top) > 0.5 ||
        Math.abs(first.width - second.width) > 0.5 ||
        Math.abs(first.height - second.height) > 0.5
    );
}

function isGapReturn(source: MotionTile, target: MotionTile): boolean {
    return source.latest && !target.latest && hasChangedRect(source.painted, source.rect);
}

interface MoveContext {
    readonly before: readonly MotionTile[];
    readonly discarding: boolean;
    readonly mode: BoardMotionCue["mode"];
    readonly used: Set<string>;
}

function findMoveSource(target: MotionTile, { before, used }: MoveContext): MotionTile | undefined {
    const source = findSource(target, before);
    if (source !== undefined) {
        return source;
    }
    if (target.region === "discards" || target.region === "melds") {
        return concealedSource(
            target,
            before.filter((tile) => !used.has(tile.key)),
        );
    }
    if (target.region === "hand" && !target.concealed) {
        return before.find(
            (tile) =>
                tile.region === "hand" &&
                tile.seat === target.seat &&
                tile.index === target.index &&
                tile.concealed,
        );
    }
    return undefined;
}

function planInPlace(source: MotionTile, target: MotionTile): TileMotion | null {
    const motion = { source: source.key, target: target.key };
    if (target.region === "hand" && source.concealed && !target.concealed) {
        return {
            ...motion,
            delay: target.index * BOARD_MOTION.revealTile,
            duration: 1,
            kind: "reveal",
        };
    }
    return isGapReturn(source, target)
        ? { ...motion, delay: 0, duration: BOARD_MOTION.gapSlide, kind: "reflow" }
        : null;
}

function isConcealedSettle(flight: boolean, target: MotionTile): boolean {
    return !flight && target.region === "hand" && target.concealed;
}

function planMove(target: MotionTile, context: MoveContext): TileMotion | null {
    const source = findMoveSource(target, context);
    if (source === undefined) {
        return context.mode === "step" &&
            target.region === "hand" &&
            target.drawn &&
            target.concealed &&
            target.seat !== "bottom"
            ? { delay: 0, duration: 0, kind: "hold", source: null, target: target.key }
            : null;
    }
    const flight = !samePlace(source, target);
    const inPlace = flight ? null : planInPlace(source, target);
    if (inPlace !== null) {
        return inPlace;
    }
    if (isConcealedSettle(flight, target) || !hasChangedRect(source.rect, target.rect)) {
        return null;
    }
    return {
        delay: !flight && target.region === "hand" && context.discarding ? BOARD_MOTION.landing : 0,
        duration: moveDuration(source, target),
        kind: flight ? "flight" : "reflow",
        source: source.key,
        target: target.key,
    };
}

function moveDuration(source: MotionTile, target: MotionTile): number {
    if (!samePlace(source, target) && target.region === "melds") {
        return travelDuration(source.rect, target.rect, BOARD_MOTION.meldSpeed);
    }
    if (!samePlace(source, target) || target.region === "discards") {
        return BOARD_MOTION.flight;
    }
    return target.region === "hand" ? BOARD_MOTION.handClose : BOARD_MOTION.meldShift;
}

export function planTileMotion(
    before: readonly MotionTile[],
    after: readonly MotionTile[],
    mode: BoardMotionCue["mode"] = "step",
): readonly TileMotion[] {
    if (before.every((tile) => tile.region !== "hand")) {
        return [];
    }
    const context: MoveContext = {
        before,
        discarding: after.some(
            (tile) => tile.region === "discards" && findSource(tile, before)?.region !== "discards",
        ),
        mode,
        used: new Set(),
    };
    return after.flatMap((target) => {
        const motion = planMove(target, context);
        if (motion?.kind === "flight" && motion.source !== null) {
            context.used.add(motion.source);
        }
        return motion === null ? [] : [motion];
    });
}
