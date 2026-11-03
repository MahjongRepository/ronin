import { type TileMotion } from "@/entities/table/lib/board-motion";

import { type TileSnapshot } from "./board-motion-snapshot";

interface TileReveal {
    readonly animation: Animation;
    readonly effect: KeyframeEffect;
    readonly back: HTMLElement;
}

function copyBack(source: TileSnapshot): HTMLElement {
    const back = source.image.querySelector(".tile")?.cloneNode(true);
    if (!(back instanceof HTMLElement)) {
        throw new Error("A reveal requires a tile back");
    }
    back.classList.add("board-reveal-back");
    back.setAttribute("aria-hidden", "true");
    return back;
}

export class TileRevealPlayer {
    private readonly running = new Map<string, TileReveal>();

    get suspended(): boolean {
        return [...this.running.values()].some(({ effect }) => effect.target === null);
    }

    prepareRender(): void {
        for (const { back, effect } of this.running.values()) {
            effect.target = null;
            back.remove();
        }
    }

    reconcile(after: ReadonlyMap<string, TileSnapshot>, plan: readonly TileMotion[]): void {
        const changing = new Set(plan.map((motion) => motion.target));
        for (const [key, active] of this.running) {
            this.rebind(key, active, changing.has(key) ? undefined : after.get(key));
        }
    }

    private rebind(key: string, active: TileReveal, next: TileSnapshot | undefined): void {
        if (next === undefined) {
            this.stop(key);
            return;
        }
        active.effect.target = next.element;
        next.element.parentElement?.append(active.back);
    }

    play(motion: TileMotion, source: TileSnapshot, target: TileSnapshot): void {
        const back = copyBack(source);
        const animation = target.element.animate(
            [{ visibility: "hidden" }, { visibility: "hidden" }],
            { duration: motion.delay + motion.duration, fill: "both" },
        );
        if (!(animation.effect instanceof KeyframeEffect)) {
            animation.cancel();
            throw new Error("Tile reveal requires a keyframe effect");
        }
        target.element.parentElement?.append(back);
        this.running.set(motion.target, { animation, back, effect: animation.effect });
        animation.onfinish = () => this.stop(motion.target);
    }

    private stop(key: string): void {
        const active = this.running.get(key);
        if (active === undefined) {
            return;
        }
        active.animation.onfinish = null;
        active.animation.cancel();
        active.back.remove();
        this.running.delete(key);
    }

    cancel(): void {
        for (const key of this.running.keys()) {
            this.stop(key);
        }
    }
}
