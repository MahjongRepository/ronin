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

    play(key: string, target: HTMLElement, ms: number): void {
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
