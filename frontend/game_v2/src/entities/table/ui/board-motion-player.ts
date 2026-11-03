import { BOARD_MOTION, type MotionRect, type TileMotion } from "@/entities/table/lib/board-motion";

import {
    type TilePose,
    type TileSnapshot,
    centerOrigin,
    refreshTileFeedback,
    snapshotTiles,
} from "./board-motion-snapshot";
import { HandReflowPlayer } from "./hand-reflow-player";

interface Flight {
    readonly fromPose: TilePose;
    readonly toPose: TilePose;
    readonly image: HTMLElement;
    readonly from: MotionRect;
    readonly to: MotionRect;
    readonly board: MotionRect;
    readonly motion: TileMotion;
    readonly target: HTMLElement | null;
}

interface Scene {
    readonly before: ReadonlyMap<string, TileSnapshot>;
    readonly after: ReadonlyMap<string, TileSnapshot>;
    readonly box: MotionRect;
    readonly board: HTMLElement;
}

function createFlight(motion: TileMotion, scene: Scene, target: TileSnapshot): Flight {
    const source = motion.source === null ? undefined : scene.before.get(motion.source);
    const origin = source?.rect ?? centerOrigin(scene.board, target);
    const reveal = motion.kind === "reveal";
    return {
        board: scene.box,
        from: origin,
        fromPose: (source ?? target).pose,
        image: reveal ? (source ?? target).image : target.image,
        motion,
        target: target.element,
        to: reveal ? origin : target.rect,
        toPose: reveal ? (source ?? target).pose : target.pose,
    };
}

function flightFrames({ from, fromPose, to, toPose }: Flight): Keyframe[] {
    const deltaX = from.left + from.width / 2 - to.left - to.width / 2;
    const deltaY = from.top + from.height / 2 - to.top - to.height / 2;
    const angle = fromPose.angle + (((toPose.angle - fromPose.angle + 540) % 360) - 180);
    return [
        { ...poseFrame(fromPose), translate: `${deltaX}px ${deltaY}px` },
        { ...poseFrame({ ...toPose, angle }), translate: "0px 0px" },
    ];
}

function poseFrame(pose: TilePose): Keyframe {
    return {
        "--motion-angle": `${pose.angle}deg`,
        "--motion-height": `${pose.height}px`,
        "--motion-standing": String(pose.standing),
        "--motion-width": `${pose.width}px`,
    };
}

function sampleFlight(tile: TileSnapshot, active: RunningTile): TileSnapshot {
    const { image } = active.flight;
    const style = getComputedStyle(image);
    const pose = {
        angle: Number.parseFloat(style.getPropertyValue("--motion-angle")),
        height: Number.parseFloat(style.getPropertyValue("--motion-height")),
        standing: Number.parseFloat(style.getPropertyValue("--motion-standing")),
        width: Number.parseFloat(style.getPropertyValue("--motion-width")),
    };
    return {
        ...tile,
        pose,
        rect: image.querySelector(".tile")?.getBoundingClientRect() ?? tile.rect,
    };
}

interface RunningTile {
    readonly rect: MotionRect;
    readonly flight: Flight;
    readonly animation: Animation;
    target: HTMLElement;
}

interface RunningSprite {
    readonly key: string;
    readonly animation: Animation;
    readonly image: HTMLElement;
}

function sameRect(first: MotionRect, second: MotionRect): boolean {
    return (
        Math.abs(first.left - second.left) < 0.5 &&
        Math.abs(first.top - second.top) < 0.5 &&
        Math.abs(first.width - second.width) < 0.5 &&
        Math.abs(first.height - second.height) < 0.5
    );
}

function showDestination(target: HTMLElement): void {
    target.style.removeProperty("visibility");
    target.closest("button")?.style.removeProperty("pointer-events");
}

function hideDestination(target: HTMLElement): void {
    target.style.visibility = "hidden";
    const control = target.closest("button");
    if (control !== null) {
        control.style.pointerEvents = "none";
    }
}

export class BoardMotionPlayer {
    private readonly board: HTMLElement;
    private layer: HTMLElement | null = null;
    private readonly hand = new HandReflowPlayer();
    private readonly sprites = new Set<RunningSprite>();
    private readonly running = new Map<string, RunningTile>();

    constructor(board: HTMLElement) {
        this.board = board;
    }

    play(
        plan: readonly TileMotion[],
        before: readonly TileSnapshot[],
        after: readonly TileSnapshot[],
    ): void {
        const box = this.board.getBoundingClientRect();
        if (box.width === 0 || box.height === 0) {
            this.cancel();
            return;
        }
        const scene: Scene = {
            after: new Map(after.map((tile) => [tile.key, tile])),
            before: this.currentSources(before),
            board: this.board,
            box,
        };
        this.reconcile(scene.after, plan);
        this.hand.reconcile(scene.after, plan);
        for (const motion of plan) {
            this.playTile(motion, scene);
        }
    }

    private currentSources(before: readonly TileSnapshot[]): ReadonlyMap<string, TileSnapshot> {
        return new Map(
            before.map((tile) => {
                const active = this.running.get(tile.key);
                return [
                    tile.key,
                    active === undefined ? this.hand.source(tile) : sampleFlight(tile, active),
                ];
            }),
        );
    }

    private reconcile(after: ReadonlyMap<string, TileSnapshot>, plan: readonly TileMotion[]): void {
        const changing = new Set(plan.map((motion) => motion.target));
        for (const active of this.running.values()) {
            showDestination(active.target);
        }
        for (const [key, active] of this.running) {
            const next = after.get(key);
            if (next === undefined || changing.has(key) || !sameRect(active.rect, next.rect)) {
                this.stopTile(key);
            } else {
                active.target = next.element;
                hideDestination(next.element);
            }
        }
    }

    private stopTile(key: string): void {
        this.running.delete(key);
        for (const sprite of this.sprites) {
            if (sprite.key === key) {
                sprite.animation.onfinish = null;
                sprite.animation.cancel();
                sprite.image.remove();
                this.sprites.delete(sprite);
            }
        }
    }

    private createLayer(): HTMLElement {
        if (this.layer !== null) {
            return this.layer;
        }
        const layer = document.createElement("div");
        layer.className = "board-motion";
        layer.setAttribute("aria-hidden", "true");
        this.board.append(layer);
        this.layer = layer;
        return layer;
    }

    private playTile(motion: TileMotion, scene: Scene): void {
        const target = scene.after.get(motion.target);
        if (target === undefined) {
            return;
        }
        const flight = createFlight(motion, scene, target);
        if (motion.kind === "reflow" && target.region === "hand") {
            this.hand.play(motion, flight.from, target);
            return;
        }
        this.playFlight(flight, target);
    }

    private playFlight(flight: Flight, target: TileSnapshot): void {
        const { motion } = flight;
        hideDestination(target.element);
        const animation = this.animateTile(flight);
        this.running.set(motion.target, {
            animation,
            flight,
            rect: target.rect,
            target: target.element,
        });
        if (motion.kind === "flight") {
            this.playTrail(flight);
        }
        this.bindTileInput(flight);
    }

    private bindTileInput(flight: Flight): void {
        if (!flight.target?.closest("button")) {
            return;
        }
        flight.image.style.pointerEvents = "auto";
        flight.image.addEventListener("pointerdown", (event) => {
            const control = this.findControl(flight.motion.target);
            if (control !== null && event.isPrimary && event.button === 0) {
                control.focus({ preventScroll: true });
                control.setPointerCapture(event.pointerId);
            }
        });
        flight.image.addEventListener("click", () => {
            const control = this.findControl(flight.motion.target);
            if (control === null) {
                return;
            }
            control.focus({ preventScroll: true });
            control.click();
        });
    }

    private findControl(key: string): HTMLButtonElement | null {
        const active = this.running.get(key);
        const control = active?.target.closest("button") ?? null;
        if (control === null || control.closest("[inert]") !== null) {
            return null;
        }
        return control;
    }

    prepareRender(): void {
        this.hand.prepareRender();
    }

    finishRender(): void {
        if (this.hand.suspended) {
            this.hand.reconcile(
                new Map(snapshotTiles(this.board).map((tile) => [tile.key, tile])),
                [],
            );
        }
        this.refreshFeedback();
    }

    private refreshFeedback(): void {
        for (const { key, image } of this.sprites) {
            const target = this.running.get(key)?.target;
            if (target?.closest("button")) {
                refreshTileFeedback(target, image);
            }
        }
    }

    private playTrail(flight: Flight): void {
        for (const [index, opacity] of [0.06, 0.18, 0.06].entries()) {
            const ghost = flight.image.cloneNode(true);
            if (ghost instanceof HTMLElement) {
                ghost.style.opacity = String(opacity);
                this.animateTile({
                    ...flight,
                    image: ghost,
                    motion: {
                        ...flight.motion,
                        delay: flight.motion.delay + (index + 1) * BOARD_MOTION.trail,
                    },
                    target: null,
                });
            }
        }
    }

    private animateTile(flight: Flight): Animation {
        const { board, image, motion, to } = flight;
        const reveal = motion.kind === "reveal";
        Object.assign(image.style, {
            left: `${to.left + to.width / 2 - board.left}px`,
            top: `${to.top + to.height / 2 - board.top}px`,
        });
        this.createLayer().append(image);
        const animation = image.animate(flightFrames(flight), {
            delay: reveal ? 0 : motion.delay,
            duration: reveal ? motion.delay + motion.duration : motion.duration,
            easing: "linear",
            fill: "both",
        });
        const sprite = { animation, image, key: motion.target };
        this.sprites.add(sprite);
        animation.onfinish = () => this.finish(sprite, flight);
        return animation;
    }

    private finish(sprite: RunningSprite, flight: Flight): void {
        this.sprites.delete(sprite);
        sprite.animation.cancel();
        sprite.image.remove();
        const active = this.running.get(flight.motion.target);
        if (flight.target !== null && active?.animation === sprite.animation) {
            showDestination(active.target);
            this.running.delete(flight.motion.target);
        }
        if (this.sprites.size === 0) {
            this.layer?.remove();
            this.layer = null;
        }
    }

    cancel(): void {
        this.hand.cancel();
        for (const { animation } of this.sprites) {
            animation.onfinish = null;
            animation.cancel();
        }
        for (const active of this.running.values()) {
            showDestination(active.target);
        }
        this.sprites.clear();
        this.running.clear();
        this.layer?.remove();
        this.layer = null;
    }
}
