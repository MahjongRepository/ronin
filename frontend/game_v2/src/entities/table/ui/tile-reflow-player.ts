import { BOARD_MOTION, type MotionRect, type TileMotion } from "@/entities/table/lib/board-motion";
import { SEAT_TURNS, type SeatPosition } from "@/entities/table/model/board-types";

import { type TileSnapshot } from "./board-motion-snapshot";

const PARTED_SLOT = "hand-tile--parted";

const SHIFT_TOLERANCE = 0.5;

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
    readonly shift: SlotShift;
    hand: HTMLElement | null;
    target: TileSnapshot;
    visible: MotionRect;
}

interface ReleaseGroup {
    readonly members: Set<TileReflow>;
    readonly timer: ReturnType<typeof setTimeout>;
}

/** One played plan's pending releases, a group per planned delay, so the slots sharing a delay start together. */
export type SlotReleases = Map<number, ReleaseGroup>;

export interface ReflowScene {
    readonly after: ReadonlyMap<string, TileSnapshot>;
    readonly releases: SlotReleases;
}

/** How far a tile starts from its slot in its frame (px): the screen's offset of their centres, unscaled and turned. */
function localOffset(from: MotionRect, target: TileSnapshot): readonly [number, number] {
    const angle = (SEAT_TURNS[target.seat] * Math.PI) / 180;
    const dx =
        (from.left + from.width / 2 - target.rect.left - target.rect.width / 2) /
        target.scales.across;
    const dy =
        (from.top + from.height / 2 - target.rect.top - target.rect.height / 2) /
        target.scales.down;
    return [
        dx * Math.cos(angle) + dy * Math.sin(angle),
        dy * Math.cos(angle) - dx * Math.sin(angle),
    ];
}

function reflowFrames(
    [localX, localY]: readonly [number, number],
    from: MotionRect,
    target: TileSnapshot,
): Keyframe[] {
    if (target.region === "melds" || target.region === "dora") {
        const scale = from.width / target.rect.width;
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

function isConcealedHandTile(tile: TileSnapshot): boolean {
    return tile.region === "hand" && tile.concealed;
}

function handKeysOf(
    after: ReadonlyMap<string, TileSnapshot>,
    seat: SeatPosition,
): ReadonlySet<string> {
    return new Set(
        [...after.values()]
            .filter((tile) => tile.seat === seat && tile.region === "hand")
            .map((tile) => tile.key),
    );
}

function sameKeys(first: ReadonlySet<string>, second: ReadonlySet<string>): boolean {
    return first.size === second.size && [...first].every((key) => second.has(key));
}

function settles(kind: TileMotion["kind"]): boolean {
    return kind === "return" || kind === "close";
}

function animateSlot(
    slot: HTMLElement,
    frames: Keyframe[],
    { delay, duration, kind }: TileMotion,
): { readonly animation: Animation; readonly effect: KeyframeEffect } {
    const animation = slot.animate(frames, {
        delay: 0,
        duration,
        easing: settles(kind) ? BOARD_MOTION.settleEasing : BOARD_MOTION.slotEasing,
        fill: "both",
    });
    if (!(animation.effect instanceof KeyframeEffect)) {
        animation.cancel();
        throw new Error("Tile reflow requires a keyframe effect");
    }
    if (delay > 0) {
        animation.pause();
        animation.currentTime = 0;
    }
    return { animation, effect: animation.effect };
}

export class TileReflowPlayer {
    private readonly running = new Map<string, TileReflow>();

    private readonly parted = new Set<HTMLElement>();

    private readonly holeHands = new Map<SeatPosition, ReadonlySet<string>>();

    private readonly releases = new Set<ReleaseGroup>();

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
        const scale = tile.rect.width > 0 ? active.visible.width / tile.rect.width : 1;
        return {
            ...tile,
            painted: active.visible,
            pose: {
                ...tile.pose,
                height: tile.pose.height * scale,
                width: tile.pose.width * scale,
            },
            rect: active.visible,
        };
    }

    reconcile(after: ReadonlyMap<string, TileSnapshot>, plan: readonly TileMotion[]): void {
        this.endChangedHoles(after);
        const changing = new Set(plan.map((motion) => motion.target));
        for (const [key, active] of this.running) {
            this.rebind(key, active, changing.has(key) ? undefined : after.get(key));
        }
        this.markPartedSlots();
    }

    private endChangedHoles(after: ReadonlyMap<string, TileSnapshot>): void {
        for (const [seat, keys] of this.holeHands) {
            if (!sameKeys(keys, handKeysOf(after, seat))) {
                for (const [key, active] of this.running) {
                    if (active.target.seat === seat && isConcealedHandTile(active.target)) {
                        this.stop(key);
                    }
                }
                this.holeHands.delete(seat);
            }
        }
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

    play(motion: TileMotion, from: MotionRect, { after, releases }: ReflowScene): void {
        const target = after.get(motion.target);
        const slot = target?.element.parentElement ?? null;
        if (target === undefined || slot === null) {
            return;
        }
        this.keepHoleHand(target, after);
        const offset = localOffset(from, target);
        const { animation, effect } = animateSlot(slot, reflowFrames(offset, from, target), motion);
        this.track(
            {
                animation,
                effect,
                hand: handOf(target),
                shift: {
                    across: offset[0],
                    delay: motion.delay,
                    down: offset[1],
                    duration: motion.duration,
                },
                target,
                visible: from,
            },
            releases,
        );
    }

    private track(active: TileReflow, releases: SlotReleases): void {
        const { key } = active.target;
        this.running.set(key, active);
        if (active.shift.delay > 0) {
            this.releaseGroup(releases, active.shift.delay).members.add(active);
        }
        this.markPartedSlots();
        active.animation.onfinish = () => {
            this.stop(key);
            this.markPartedSlots();
        };
    }

    private releaseGroup(releases: SlotReleases, delay: number): ReleaseGroup {
        const pending = releases.get(delay);
        if (pending !== undefined) {
            return pending;
        }
        const group: ReleaseGroup = {
            members: new Set(),
            timer: setTimeout(() => this.release(group), delay),
        };
        releases.set(delay, group);
        this.releases.add(group);
        return group;
    }

    private release(group: ReleaseGroup): void {
        this.releases.delete(group);
        for (const member of group.members) {
            if (this.running.get(member.target.key) === member) {
                member.animation.play();
            }
        }
        group.members.clear();
    }

    private keepHoleHand(target: TileSnapshot, after: ReadonlyMap<string, TileSnapshot>): void {
        if (isConcealedHandTile(target) && !this.holeHands.has(target.seat)) {
            this.holeHands.set(target.seat, handKeysOf(after, target.seat));
        }
    }

    private stop(key: string): void {
        const active = this.running.get(key);
        if (active !== undefined) {
            active.animation.onfinish = null;
            active.animation.cancel();
            this.running.delete(key);
            this.leaveRelease(active);
        }
    }

    private leaveRelease(active: TileReflow): void {
        for (const group of this.releases) {
            if (group.members.delete(active) && group.members.size === 0) {
                clearTimeout(group.timer);
                this.releases.delete(group);
            }
        }
    }

    cancel(): void {
        for (const key of this.running.keys()) {
            this.stop(key);
        }
        for (const group of this.releases) {
            clearTimeout(group.timer);
        }
        this.releases.clear();
        this.holeHands.clear();
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
