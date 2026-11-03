import { type BoardMotionCue, type SeatPosition } from "@/entities/table/model/board-types";

export const BOARD_MOTION = {
    discardPause: 300,
    flight: 120,
    maxTravel: 300,
    meldSpeed: 0.06,
    minTravel: 80,
    reflow: 200,
    revealTile: 30,
    trail: 10,
} as const;

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
    readonly rect: MotionRect;
}

export interface TileMotion {
    readonly target: string;
    readonly source: string | null;
    readonly kind: "flight" | "reflow" | "reveal";
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

interface MoveContext {
    readonly before: readonly MotionTile[];
    readonly discarding: boolean;
    readonly discardPause: number;
    readonly used: Set<string>;
    readonly replacements: ReadonlyMap<string, MotionTile>;
}

function concealedReplacements(
    before: readonly MotionTile[],
    after: readonly MotionTile[],
): ReadonlyMap<string, MotionTile> {
    const replacements = new Map<string, MotionTile>();
    for (const discard of after.filter(
        (tile) =>
            tile.region === "discards" && !tile.tsumogiri && findSource(tile, before) === undefined,
    )) {
        const source = concealedSource(discard, before);
        const drawn = before.find(
            (tile) =>
                tile.region === "hand" &&
                tile.seat === discard.seat &&
                tile.drawn &&
                tile.concealed,
        );
        if (source !== undefined && drawn !== undefined) {
            replacements.set(source.key, drawn);
        }
    }
    return replacements;
}

function findMoveSource(
    target: MotionTile,
    { before, replacements, used }: MoveContext,
): MotionTile | undefined {
    const source = replacements.get(target.key) ?? findSource(target, before);
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

function planMove(target: MotionTile, context: MoveContext): TileMotion | null {
    const source = findMoveSource(target, context);
    if (source === undefined) {
        return target.region === "hand" && target.drawn
            ? {
                  delay: 0,
                  duration: BOARD_MOTION.flight,
                  kind: "flight",
                  source: null,
                  target: target.key,
              }
            : null;
    }
    const flight = !samePlace(source, target);
    if (target.region === "hand" && source.concealed && !target.concealed && !flight) {
        return {
            delay: target.index * BOARD_MOTION.revealTile,
            duration: 1,
            kind: "reveal",
            source: source.key,
            target: target.key,
        };
    }
    if (!hasChangedRect(source.rect, target.rect)) {
        return null;
    }
    return {
        delay:
            !flight && target.region === "hand" && context.discarding
                ? BOARD_MOTION.flight + context.discardPause
                : 0,
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
    return !samePlace(source, target) || target.region === "discards"
        ? BOARD_MOTION.flight
        : BOARD_MOTION.reflow;
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
        discardPause: mode === "replay" ? 0 : BOARD_MOTION.discardPause,
        discarding: after.some(
            (tile) => tile.region === "discards" && findSource(tile, before)?.region !== "discards",
        ),
        replacements: concealedReplacements(before, after),
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
