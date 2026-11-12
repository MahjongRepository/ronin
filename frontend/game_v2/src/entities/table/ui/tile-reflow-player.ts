import { type MotionRect, type TileMotion } from "@/entities/table/lib/board-motion";
import { type TileQuad, quadWarp, unwarpPoint, warpPoint } from "@/entities/table/lib/tile-quad";

import { SEAT_TURNS, type TileSnapshot } from "./board-motion-snapshot";

/** Where a reflowing tile starts: its bounding box and its corners on the screen. */
export interface ReflowSource {
    readonly rect: MotionRect;
    readonly quad: TileQuad;
}

interface TileReflow {
    readonly animation: Animation;
    readonly effect: KeyframeEffect;
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

function reflowFrames(source: ReflowSource, target: TileSnapshot): Keyframe[] {
    const [localX, localY] = localOffset(source, target);
    if (target.region === "melds") {
        const scale = source.rect.width / target.rect.width;
        return [
            { transform: `translate(${localX}px, ${localY}px) scale(${scale})` },
            { transform: "translate(0px, 0px) scale(1)" },
        ];
    }
    return [
        { left: `${localX}px`, top: `${localY}px` },
        { left: "0px", top: "0px" },
    ];
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

export class TileReflowPlayer {
    private readonly running = new Map<string, TileReflow>();

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
            pose: {
                ...tile.pose,
                height: tile.pose.height * scale,
                width: tile.pose.width * scale,
            },
            quad: movedQuad(tile.quad, tile.rect, active.visible),
            rect: active.visible,
        };
    }

    reconcile(after: ReadonlyMap<string, TileSnapshot>, plan: readonly TileMotion[]): void {
        const changing = new Set(plan.map((motion) => motion.target));
        for (const [key, active] of this.running) {
            this.rebind(key, active, changing.has(key) ? undefined : after.get(key));
        }
    }

    private rebind(key: string, active: TileReflow, next: TileSnapshot | undefined): void {
        if (next === undefined) {
            this.stop(key);
            return;
        }
        active.target = next;
        active.effect.target = next.element.parentElement;
    }

    play(motion: TileMotion, source: ReflowSource, target: TileSnapshot): void {
        const slot = target.element.parentElement;
        if (slot === null) {
            return;
        }
        const animation = slot.animate(reflowFrames(source, target), {
            delay: motion.delay,
            duration: motion.duration,
            easing: "linear",
            fill: "both",
        });
        if (!(animation.effect instanceof KeyframeEffect)) {
            animation.cancel();
            throw new Error("Tile reflow requires a keyframe effect");
        }
        this.running.set(motion.target, {
            animation,
            effect: animation.effect,
            target,
            visible: source.rect,
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
    }
}
