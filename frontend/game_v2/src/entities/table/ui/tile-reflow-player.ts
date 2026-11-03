import { type MotionRect, type TileMotion } from "@/entities/table/lib/board-motion";

import { SEAT_TURNS, type TileSnapshot } from "./board-motion-snapshot";

interface TileReflow {
    readonly animation: Animation;
    readonly effect: KeyframeEffect;
    target: TileSnapshot;
    visible: MotionRect;
}

function reflowFrames(source: MotionRect, target: TileSnapshot): Keyframe[] {
    const angle = (SEAT_TURNS[target.seat] * Math.PI) / 180;
    const dx = source.left + source.width / 2 - target.rect.left - target.rect.width / 2;
    const dy = source.top + source.height / 2 - target.rect.top - target.rect.height / 2;
    const localX = (dx * Math.cos(angle) + dy * Math.sin(angle)) / target.scale;
    const localY = (dy * Math.cos(angle) - dx * Math.sin(angle)) / target.scale;
    if (target.region === "melds") {
        const scale = source.width / target.rect.width;
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
            throw new Error("Tile reflow requires a keyframe effect");
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
