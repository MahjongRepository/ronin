import { type BoardMotionCue, type SeatPosition } from "@/entities/table/model/board-types";

const FLIGHT = 150;
const GHOSTS = [
    { alpha: 0.07, delay: 0 },
    { alpha: 0.2, delay: 12 },
    { alpha: 0.07, delay: 24 },
] as const;

export const BOARD_MOTION = {
    dealHold: 300,
    discardEasing: "linear",
    discardSolidFrom: 0.6,
    drawHold: 450,
    flight: FLIGHT,
    gapReturn: 240,
    ghosts: GHOSTS,
    handClose: 240,
    handReflow: 300,
    holeHold: 700,
    landing: GHOSTS[1].delay + FLIGHT,
    maxTravel: 300,
    meldShift: 200,
    meldSpeed: 0.055,
    minTravel: 80,
    returnHold: 330,
    revealTile: 35,
    settleEasing: "cubic-bezier(0.37, 0, 0.63, 1)",
    slotEasing: "cubic-bezier(0.16, 1, 0.3, 1)",
} as const;

export const DISCARD_LANDING_MS = BOARD_MOTION.landing;
export const DRAW_HOLD_MS = BOARD_MOTION.drawHold;

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
    readonly kind: "close" | "flight" | "hold" | "reflow" | "return" | "reveal";
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

function concealedHand(target: MotionTile, before: readonly MotionTile[]): readonly MotionTile[] {
    return before.filter(
        (tile) => tile.seat === target.seat && tile.region === "hand" && tile.concealed,
    );
}

function middleSlot(kept: readonly MotionTile[]): number {
    return Math.floor((kept.length - 1) / 2);
}

function concealedSource(
    target: MotionTile,
    before: readonly MotionTile[],
): MotionTile | undefined {
    const hand = concealedHand(target, before);
    if (target.tsumogiri) {
        return hand.find((tile) => tile.drawn);
    }
    const kept = hand.filter((tile) => !tile.drawn);
    return kept[middleSlot(kept)];
}

function concealedShifts(
    before: readonly MotionTile[],
    after: readonly MotionTile[],
): ReadonlyMap<string, MotionTile> {
    const shifts = new Map<string, MotionTile>();
    for (const discard of after.filter(
        (tile) =>
            tile.region === "discards" && !tile.tsumogiri && findSource(tile, before) === undefined,
    )) {
        const hand = concealedHand(discard, before);
        const kept = hand.filter((tile) => !tile.drawn);
        const movers = [...kept.slice(middleSlot(kept) + 1), ...hand.filter((tile) => tile.drawn)];
        kept.slice(middleSlot(kept)).forEach((slot, index) => {
            const mover = movers[index];
            if (mover !== undefined) {
                shifts.set(slot.key, mover);
            }
        });
    }
    return shifts;
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
    readonly mode: BoardMotionCue["mode"];
    readonly opensRound: boolean;
    readonly shifts: ReadonlyMap<string, MotionTile>;
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

function planReveal(source: MotionTile, target: MotionTile): TileMotion | null {
    return target.region === "hand" && source.concealed && !target.concealed
        ? {
              delay: target.index * BOARD_MOTION.revealTile,
              duration: 1,
              kind: "reveal",
              source: source.key,
              target: target.key,
          }
        : null;
}

function planReturn(source: MotionTile, target: MotionTile): TileMotion | null {
    return source.latest && !target.latest && hasChangedRect(source.painted, source.rect)
        ? {
              delay: 0,
              duration: BOARD_MOTION.gapReturn,
              kind: "return",
              source: source.key,
              target: target.key,
          }
        : null;
}

function planConcealedShift(target: MotionTile, context: MoveContext): TileMotion | null {
    const mover = context.shifts.get(target.key);
    return mover === undefined
        ? null
        : {
              delay: BOARD_MOTION.landing + BOARD_MOTION.holeHold,
              duration: BOARD_MOTION.handClose,
              kind: "close",
              source: mover.key,
              target: target.key,
          };
}

function isHeldDraw(target: MotionTile, mode: BoardMotionCue["mode"]): boolean {
    const held =
        mode === "observe" || (mode === "step" && (target.concealed || target.seat === "bottom"));
    return held && target.region === "hand" && target.drawn;
}

function isOpeningDraw(target: MotionTile, mode: BoardMotionCue["mode"]): boolean {
    return (mode === "step" || mode === "observe") && target.region === "hand" && target.drawn;
}

function opensRound(after: readonly MotionTile[]): boolean {
    return after.every((tile) => tile.region !== "discards" && tile.region !== "melds");
}

function planHold(target: MotionTile, delay: number): TileMotion {
    return { delay, duration: 0, kind: "hold", source: null, target: target.key };
}

function planUnsourcedDraw(target: MotionTile, context: MoveContext): TileMotion | null {
    if (context.opensRound && isOpeningDraw(target, context.mode)) {
        return planHold(target, BOARD_MOTION.dealHold);
    }
    return isHeldDraw(target, context.mode) ? planHold(target, 0) : null;
}

function isConcealedSettle(flight: boolean, target: MotionTile): boolean {
    return !flight && target.region === "hand" && target.concealed;
}

function planMove(target: MotionTile, context: MoveContext): TileMotion | null {
    const source = findMoveSource(target, context);
    if (source === undefined) {
        return planUnsourcedDraw(target, context);
    }
    const flight = !samePlace(source, target);
    const inPlace = flight ? null : (planReveal(source, target) ?? planReturn(source, target));
    if (inPlace !== null) {
        return inPlace;
    }
    if (isConcealedSettle(flight, target) || !hasChangedRect(source.rect, target.rect)) {
        return null;
    }
    return {
        ...moveTiming(source, target, context.discarding),
        source: source.key,
        target: target.key,
    };
}

function moveTiming(
    source: MotionTile,
    target: MotionTile,
    discarding: boolean,
): Pick<TileMotion, "delay" | "duration" | "kind"> {
    const flight = !samePlace(source, target);
    if (!flight && target.region === "hand" && discarding) {
        return {
            delay: BOARD_MOTION.landing + BOARD_MOTION.returnHold,
            duration: BOARD_MOTION.handClose,
            kind: "close",
        };
    }
    return { delay: 0, duration: moveDuration(source, target), kind: flight ? "flight" : "reflow" };
}

function moveDuration(source: MotionTile, target: MotionTile): number {
    if (!samePlace(source, target) && target.region === "melds") {
        return travelDuration(source.rect, target.rect, BOARD_MOTION.meldSpeed);
    }
    if (!samePlace(source, target) || target.region === "discards") {
        return BOARD_MOTION.flight;
    }
    return target.region === "hand" ? BOARD_MOTION.handReflow : BOARD_MOTION.meldShift;
}

function planDeal(
    after: readonly MotionTile[],
    mode: BoardMotionCue["mode"],
): readonly TileMotion[] {
    if (!opensRound(after)) {
        return [];
    }
    return after
        .filter((tile) => isOpeningDraw(tile, mode))
        .map((tile) => planHold(tile, BOARD_MOTION.dealHold));
}

export function planTileMotion(
    before: readonly MotionTile[],
    after: readonly MotionTile[],
    mode: BoardMotionCue["mode"] = "step",
): readonly TileMotion[] {
    if (before.every((tile) => tile.region !== "hand")) {
        return planDeal(after, mode);
    }
    const context: MoveContext = {
        before,
        discarding: after.some(
            (tile) => tile.region === "discards" && findSource(tile, before)?.region !== "discards",
        ),
        mode,
        opensRound: opensRound(after),
        shifts: concealedShifts(before, after),
        used: new Set(),
    };
    return after.flatMap((target) => {
        const motion = planConcealedShift(target, context) ?? planMove(target, context);
        if (motion?.kind === "flight" && motion.source !== null) {
            context.used.add(motion.source);
        }
        return motion === null ? [] : [motion];
    });
}
