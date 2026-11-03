import { type MotionRect, type TileMotion } from "@/entities/table/lib/board-motion";

import { type TileSnapshot } from "./board-motion-snapshot";

interface HandReflow {
    readonly animation: Animation;
    readonly effect: KeyframeEffect;
    target: TileSnapshot;
    visible: MotionRect;
}

function reflowFrames(source: MotionRect, target: TileSnapshot): Keyframe[] {
    const angle = (target.pose.angle * Math.PI) / 180;
    const dx = source.left - target.rect.left;
    const dy = source.top - target.rect.top;
    const localX = (dx * Math.cos(angle) + dy * Math.sin(angle)) / target.scale;
    const localY = (dy * Math.cos(angle) - dx * Math.sin(angle)) / target.scale;
    return [
        { left: `${localX}px`, top: `${localY}px` },
        { left: "0px", top: "0px" },
    ];
}

export class HandReflowPlayer {
    private readonly running = new Map<string, HandReflow>();

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
        return active === undefined ? tile : { ...tile, rect: active.visible };
    }

    reconcile(after: ReadonlyMap<string, TileSnapshot>, plan: readonly TileMotion[]): void {
        const changing = new Set(plan.map((motion) => motion.target));
        for (const [key, active] of this.running) {
            this.rebind(key, active, changing.has(key) ? undefined : after.get(key));
        }
    }

    private rebind(key: string, active: HandReflow, next: TileSnapshot | undefined): void {
        if (next === undefined) {
            this.stop(key);
            return;
        }
        active.target = next;
        active.effect.target = next.element.parentElement;
    }

    play(motion: TileMotion, source: MotionRect, target: TileSnapshot): void {
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
            throw new Error("Hand reflow requires a keyframe effect");
        }
        this.running.set(motion.target, {
            animation,
            effect: animation.effect,
            target,
            visible: source,
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
