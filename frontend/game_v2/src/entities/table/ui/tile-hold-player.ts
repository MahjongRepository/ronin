import { type TileSnapshot } from "./board-motion-snapshot";

interface TileHold {
    readonly animation: Animation;
    readonly effect: KeyframeEffect;
}

export class TileHoldPlayer {
    private readonly running = new Map<string, TileHold>();

    get suspended(): boolean {
        return [...this.running.values()].some(({ effect }) => effect.target === null);
    }

    prepareRender(): void {
        for (const { effect } of this.running.values()) {
            effect.target = null;
        }
    }

    reconcile(after: ReadonlyMap<string, TileSnapshot>): void {
        for (const [key, active] of this.running) {
            const next = after.get(key);
            if (next === undefined) {
                this.stop(key);
            } else {
                active.effect.target = next.element;
            }
        }
    }

    /** Hides the tile at `key` until its plan starts the hold. */
    play(key: string, target: HTMLElement, ms: number): Animation {
        this.stop(key);
        const animation = target.animate([{ visibility: "hidden" }, { visibility: "hidden" }], {
            duration: ms,
            fill: "both",
        });
        if (!(animation.effect instanceof KeyframeEffect)) {
            animation.cancel();
            throw new Error("Tile hold requires a keyframe effect");
        }
        animation.pause();
        animation.currentTime = 0;
        this.running.set(key, { animation, effect: animation.effect });
        animation.onfinish = () => this.stop(key);
        return animation;
    }

    /** Keeps the tile hidden for `ms` from `at`, or shows it now when no wait is left. */
    start(animation: Animation, ms: number, at: number): void {
        const [key, active] =
            [...this.running].find(([, hold]) => hold.animation === animation) ?? [];
        if (key === undefined || active === undefined) {
            return;
        }
        if (ms <= 0) {
            this.stop(key);
            return;
        }
        active.effect.updateTiming({ duration: ms });
        animation.startTime = at;
    }

    private stop(key: string): void {
        const active = this.running.get(key);
        if (active === undefined) {
            return;
        }
        active.animation.onfinish = null;
        active.animation.cancel();
        this.running.delete(key);
    }

    cancel(): void {
        for (const key of this.running.keys()) {
            this.stop(key);
        }
    }
}
