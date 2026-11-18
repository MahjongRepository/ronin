import { BOARD_MOTION, type MotionRect, type TileMotion } from "@/entities/table/lib/board-motion";
import { type TileQuad, quadWarp, unwarpPoint, warpPoint } from "@/entities/table/lib/tile-quad";
import { SEAT_TURNS } from "@/entities/table/model/board-types";

import { type TileSnapshot } from "./board-motion-snapshot";

const PARTED_SLOT = "hand-tile--parted";

const SHIFT_TOLERANCE = 0.5;

/** Where a reflowing tile starts: its bounding box and its corners on the screen. */
export interface ReflowSource {
    readonly rect: MotionRect;
    readonly quad: TileQuad;
}

/** How a reflowing slot moves: its start offset in its frame (px) and its timing. */
interface SlotShift {
    readonly delay: number;
    readonly duration: number;
    readonly across: number;
    readonly down: number;
}

interface TileReflow {
    readonly animation: Animation;
    readonly effect: KeyframeEffect;
    readonly opensGap: boolean;
    readonly shift: SlotShift;
    hand: HTMLElement | null;
    target: TileSnapshot;
    visible: MotionRect;
}

/** Where the camera shows a tile's centre: its bounding box's centre, moved as its corners taper. */
function shownCentre({ quad, rect }: ReflowSource): {
    readonly left: number;
    readonly top: number;
} {
    const centre = warpPoint(quadWarp(rect, quad), { left: 0, top: 0 });
    return {
        left: rect.left + rect.width / 2 + centre.left,
        top: rect.top + rect.height / 2 + centre.top,
    };
}

/**
 * How far a tile starts from its slot in its frame (px): the screen's offset between the two shown centres taken back
 * through the slot's camera (so a tilted strip's rows keep their spacing), unscaled and turned to its seat.
 */
function localOffset(source: ReflowSource, target: TileSnapshot): readonly [number, number] {
    const angle = (SEAT_TURNS[target.seat] * Math.PI) / 180;
    const from = shownCentre(source);
    const centre = {
        left: target.rect.left + target.rect.width / 2,
        top: target.rect.top + target.rect.height / 2,
    };
    const laid = unwarpPoint(quadWarp(target.rect, target.quad), {
        left: from.left - centre.left,
        top: from.top - centre.top,
    });
    const dx = laid.left / target.scales.across;
    const dy = laid.top / target.scales.down;
    return [
        dx * Math.cos(angle) + dy * Math.sin(angle),
        dy * Math.cos(angle) - dx * Math.sin(angle),
    ];
}

function reflowFrames(
    [localX, localY]: readonly [number, number],
    source: ReflowSource,
    target: TileSnapshot,
): Keyframe[] {
    if (target.region === "melds" || target.region === "dora") {
        const scale = source.rect.width / target.rect.width;
        return [
            { transform: `translate(${localX}px, ${localY}px) scale(${scale})` },
            { transform: "translate(0px, 0px) scale(1)" },
        ];
    }
    if (target.region === "discards") {
        return [
            { transform: `translate(${localX}px, ${localY}px)` },
            { transform: "translate(0px, 0px)" },
        ];
    }
    return [{ translate: `${localX}px ${localY}px` }, { translate: "0px 0px" }];
}

/** `quad` carried along as its bounding box moves and scales from `from` to `to`. */
function movedQuad(quad: TileQuad, from: MotionRect, to: MotionRect): TileQuad {
    const [across, down] = [to.width / (from.width || 1), to.height / (from.height || 1)];
    const [first, second, third, fourth] = quad.map(({ left, top }) => ({
        left: to.left + (left - from.left) * across,
        top: to.top + (top - from.top) * down,
    }));
    return first && second && third && fourth ? [first, second, third, fourth] : quad;
}

function handOf(tile: TileSnapshot): HTMLElement | null {
    return tile.element.parentElement?.closest<HTMLElement>(".hand") ?? null;
}

function sameShift(first: SlotShift | undefined, second: SlotShift | undefined): boolean {
    if (first === undefined || second === undefined) {
        return first === second;
    }
    return (
        first.delay === second.delay &&
        first.duration === second.duration &&
        Math.abs(first.across - second.across) < SHIFT_TOLERANCE &&
        Math.abs(first.down - second.down) < SHIFT_TOLERANCE
    );
}

/**
 * The slots of a sliding hand whose covering neighbour (the next one down the screen) moves apart from them, so the
 * felt between them would show the end their covered body leaves out.
 */
function partedSlots(
    hand: HTMLElement,
    turn: number,
    shifts: ReadonlyMap<Element, SlotShift>,
): HTMLElement[] {
    const slots = [...hand.children].filter((slot) => slot instanceof HTMLElement);
    return slots.filter((slot, index) => {
        const cover = slots[turn === SEAT_TURNS.right ? index - 1 : index + 1];
        return cover !== undefined && !sameShift(shifts.get(slot), shifts.get(cover));
    });
}

function findPartedSlots(running: Iterable<TileReflow>): Set<HTMLElement> {
    const shifts = new Map<Element, SlotShift>();
    const hands = new Map<HTMLElement, number>();
    for (const { hand, shift, target } of running) {
        const slot = target.element.parentElement;
        if (hand !== null && slot !== null) {
            shifts.set(slot, shift);
            hands.set(hand, SEAT_TURNS[target.seat]);
        }
    }
    return new Set([...hands].flatMap(([hand, turn]) => partedSlots(hand, turn, shifts)));
}

function animateSlot(
    slot: HTMLElement,
    frames: Keyframe[],
    { delay, duration }: Pick<TileMotion, "delay" | "duration">,
): { readonly animation: Animation; readonly effect: KeyframeEffect } {
    const animation = slot.animate(frames, {
        delay,
        duration,
        easing: BOARD_MOTION.slotEasing,
        fill: "both",
    });
    if (!(animation.effect instanceof KeyframeEffect)) {
        animation.cancel();
        throw new Error("Tile reflow requires a keyframe effect");
    }
    return { animation, effect: animation.effect };
}

export class TileReflowPlayer {
    private readonly running = new Map<string, TileReflow>();

    private readonly parted = new Set<HTMLElement>();

    get suspended(): boolean {
        return [...this.running.values()].some(({ effect }) => effect.target === null);
    }

    prepareRender(): void {
        for (const active of this.running.values()) {
            if (active.effect.target !== null) {
                active.visible = active.target.element.getBoundingClientRect();
                active.effect.target = null;
            }
        }
    }

    source(tile: TileSnapshot): TileSnapshot {
        const active = this.running.get(tile.key);
        if (active === undefined) {
            return tile;
        }
        const quad = movedQuad(tile.quad, tile.rect, active.visible);
        if (active.opensGap) {
            return { ...tile, painted: active.visible, paintedQuad: quad };
        }
        const scale = tile.rect.width > 0 ? active.visible.width / tile.rect.width : 1;
        return {
            ...tile,
            painted: active.visible,
            paintedQuad: quad,
            pose: {
                ...tile.pose,
                height: tile.pose.height * scale,
                width: tile.pose.width * scale,
            },
            quad,
            rect: active.visible,
        };
    }

    reconcile(after: ReadonlyMap<string, TileSnapshot>, plan: readonly TileMotion[]): void {
        const changing = new Set(plan.map((motion) => motion.target));
        for (const [key, active] of this.running) {
            this.rebind(key, active, changing.has(key) ? undefined : after.get(key));
        }
        this.markPartedSlots();
    }

    private rebind(key: string, active: TileReflow, next: TileSnapshot | undefined): void {
        if (next === undefined) {
            this.stop(key);
            return;
        }
        active.target = next;
        active.hand = handOf(next);
        active.effect.target = next.element.parentElement;
    }

    play(motion: TileMotion, source: ReflowSource, target: TileSnapshot): void {
        const slot = target.element.parentElement;
        if (slot === null) {
            return;
        }
        const offset = localOffset(source, target);
        const { animation, effect } = animateSlot(
            slot,
            reflowFrames(offset, source, target),
            motion,
        );
        this.running.set(motion.target, {
            animation,
            effect,
            hand: handOf(target),
            opensGap: false,
            shift: {
                across: offset[0],
                delay: motion.delay,
                down: offset[1],
                duration: motion.duration,
            },
            target,
            visible: source.rect,
        });
        this.markPartedSlots();
        animation.onfinish = () => {
            this.stop(motion.target);
            this.markPartedSlots();
        };
    }

    openGap(motion: TileMotion, target: TileSnapshot): void {
        const slot = target.element.parentElement;
        if (slot === null) {
            return;
        }
        const timing = {
            delay: motion.delay + BOARD_MOTION.landing,
            duration: BOARD_MOTION.gapSlide,
        };
        const { animation, effect } = animateSlot(
            slot,
            [{ offset: 0, translate: "0px 0px" }],
            timing,
        );
        this.running.set(motion.target, {
            animation,
            effect,
            hand: null,
            opensGap: true,
            shift: { ...timing, across: 0, down: 0 },
            target,
            visible: target.rect,
        });
        animation.onfinish = () => this.stop(motion.target);
    }

    private stop(key: string): void {
        const active = this.running.get(key);
        if (active !== undefined) {
            active.animation.onfinish = null;
            active.animation.cancel();
            this.running.delete(key);
        }
    }

    cancel(): void {
        for (const key of this.running.keys()) {
            this.stop(key);
        }
        this.markPartedSlots();
    }

    private markPartedSlots(): void {
        const parted = findPartedSlots(this.running.values());
        for (const slot of this.parted) {
            if (!parted.has(slot)) {
                slot.classList.remove(PARTED_SLOT);
                this.parted.delete(slot);
            }
        }
        for (const slot of parted) {
            slot.classList.add(PARTED_SLOT);
            this.parted.add(slot);
        }
    }
}
