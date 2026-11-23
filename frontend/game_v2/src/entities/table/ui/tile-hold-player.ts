import { type TileSnapshot } from "./board-motion-snapshot";
import { startAt } from "./tile-reflow-player";

interface TileHold {
    readonly animation: Animation;
    readonly effect: KeyframeEffect;
}

/** A hold waiting for its plan's start: its tile's key and its animation. */
export interface HeldTile {
    readonly key: string;
    readonly animation: Animation;
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

    /** Hides the tile at `key` for `ms`. */
    play(key: string, target: HTMLElement, ms: number): HeldTile {
        this.stop(key);
        const animation = target.animate([{ visibility: "hidden" }, { visibility: "hidden" }], {
            duration: ms,
            fill: "both",
        });
        if (!(animation.effect instanceof KeyframeEffect)) {
            animation.cancel();
            throw new Error("Tile hold requires a keyframe effect");
        }
        this.running.set(key, { animation, effect: animation.effect });
        animation.onfinish = () => this.stop(key);
        return { animation, key };
    }

    /** Keeps the tile hidden for `ms` from `at` (now when null), or shows it now when no wait is left. */
    start({ animation, key }: HeldTile, ms: number, at: number | null): void {
        const active = this.running.get(key);
        if (active?.animation !== animation) {
            return;
        }
        if (ms <= 0) {
            this.stop(key);
            return;
        }
        active.effect.updateTiming({ duration: ms });
        startAt(animation, at);
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
