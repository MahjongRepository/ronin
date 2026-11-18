import { BOARD_MOTION, type MotionRect, type TileMotion } from "@/entities/table/lib/board-motion";
import { type TileQuad, quadWarp, rectQuad, warpTransform } from "@/entities/table/lib/tile-quad";

import {
    type TilePose,
    type TileSnapshot,
    snapshotTiles,
    standingOf,
} from "./board-motion-snapshot";
import { TileHoldPlayer } from "./tile-hold-player";
import { TileReflowPlayer } from "./tile-reflow-player";
import { TileRevealPlayer } from "./tile-reveal-player";

interface Flight {
    readonly fromPose: TilePose;
    readonly toPose: TilePose;
    readonly image: HTMLElement;
    readonly from: MotionRect;
    readonly fromQuad: TileQuad;
    readonly to: MotionRect;
    readonly toQuad: TileQuad;
    readonly board: MotionRect;
    readonly motion: TileMotion;
    readonly target: HTMLElement | null;
}

interface Scene {
    readonly before: ReadonlyMap<string, TileSnapshot>;
    readonly after: ReadonlyMap<string, TileSnapshot>;
    readonly box: MotionRect;
}

function createFlight(motion: TileMotion, scene: Scene, target: TileSnapshot): Flight | null {
    const source = motion.source === null ? undefined : scene.before.get(motion.source);
    if (source === undefined) {
        return null;
    }
    return {
        board: scene.box,
        from: source.rect,
        fromPose: source.pose,
        fromQuad: source.quad,
        image: target.image,
        motion,
        target: target.element,
        to: target.rect,
        toPose: target.pose,
        toQuad: target.quad,
    };
}

/**
 * A flight from its source's pose and place to its target's, its image warped onto the target tile's corners as the
 * camera shows them from the start (a tilted piece's taper and squash; none on a flat one), so it lands exactly as the
 * tile it stands for.
 */
function screenFace(rect: MotionRect, pose: TilePose, landing: TilePose): Keyframe {
    const quarters = Math.round((pose.angle - landing.angle) / 90);
    const turned = Math.abs(quarters) % 2 === 1;
    return {
        "--motion-across": `${turned ? rect.height : rect.width}px`,
        "--motion-down": `${turned ? rect.width : rect.height}px`,
    };
}

function flightFrames({ from, fromPose, to, toPose, toQuad }: Flight): Keyframe[] {
    const deltaX = from.left + from.width / 2 - to.left - to.width / 2;
    const deltaY = from.top + from.height / 2 - to.top - to.height / 2;
    const angle = fromPose.angle + (((toPose.angle - fromPose.angle + 540) % 360) - 180);
    const transform = `translate(-50%, -50%) ${warpTransform(quadWarp(to, toQuad))}`;
    const takeOff =
        fromPose.standing === toPose.standing
            ? fromPose
            : { ...fromPose, lying: toPose.lying, standing: toPose.standing };
    return [
        {
            ...poseFrame(takeOff),
            ...screenFace(from, fromPose, toPose),
            transform,
            translate: `${deltaX}px ${deltaY}px`,
        },
        {
            ...poseFrame({ ...toPose, angle }),
            ...screenFace(to, toPose, toPose),
            transform,
            translate: "0px 0px",
        },
    ];
}

function poseFrame(pose: TilePose): Keyframe {
    return {
        "--motion-angle": `${pose.angle}deg`,
        "--motion-height": `${pose.height}px`,
        "--motion-width": `${pose.width}px`,
    };
}

function hasSamePose(from: TilePose, to: TilePose): boolean {
    return (
        Math.abs(from.width - to.width) < 0.5 &&
        Math.abs(from.height - to.height) < 0.5 &&
        (from.angle - to.angle) % 360 === 0 &&
        from.standing === to.standing &&
        from.lying === to.lying
    );
}

function sampleFlight(tile: TileSnapshot, active: RunningTile): TileSnapshot {
    const { image } = active.flight;
    const style = getComputedStyle(image);
    const face = image.querySelector(":scope > .tile");
    const pose = {
        angle: Number.parseFloat(style.getPropertyValue("--motion-angle")),
        height: Number.parseFloat(style.getPropertyValue("--motion-height")),
        lying: active.flight.toPose.lying,
        standing: face === null ? tile.pose.standing : standingOf(face),
        width: Number.parseFloat(style.getPropertyValue("--motion-width")),
    };
    const rect = face?.getBoundingClientRect() ?? tile.rect;
    return { ...tile, pose, quad: rectQuad(rect), rect };
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

/** The slot each hidden destination marked as landing, kept so a tile a render swaps out still clears its slot. */
const landingSlots = new WeakMap<HTMLElement, HTMLElement>();

function showDestination(target: HTMLElement): void {
    target.style.removeProperty("visibility");
    (landingSlots.get(target) ?? target.parentElement)?.removeAttribute("data-landing");
    landingSlots.delete(target);
    target.closest("button")?.style.removeProperty("pointer-events");
}

function hideDestination(target: HTMLElement): void {
    target.style.visibility = "hidden";
    const slot = target.parentElement;
    if (slot !== null) {
        slot.setAttribute("data-landing", "");
        landingSlots.set(target, slot);
    }
    const control = target.closest("button");
    if (control !== null) {
        control.style.pointerEvents = "none";
    }
}

export class BoardMotionPlayer {
    private readonly board: HTMLElement;
    private layer: HTMLElement | null = null;
    private readonly hold = new TileHoldPlayer();
    private readonly reflow = new TileReflowPlayer();
    private readonly reveal = new TileRevealPlayer();
    private readonly sprites = new Set<RunningSprite>();
    private readonly running = new Map<string, RunningTile>();
    private discardLandingAt: number | null = null;

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
            box,
        };
        this.hold.cancel();
        this.reconcile(scene.after, plan);
        this.reflow.reconcile(scene.after, plan);
        this.reveal.reconcile(scene.after, plan);
        this.playPlan(plan, scene);
    }

    private playPlan(plan: readonly TileMotion[], scene: Scene): void {
        for (const motion of plan.filter(({ kind }) => kind !== "hold")) {
            this.playTile(motion, scene);
        }
        for (const motion of plan.filter(({ kind }) => kind === "hold")) {
            this.playHold(motion, scene);
        }
    }

    private currentSources(before: readonly TileSnapshot[]): ReadonlyMap<string, TileSnapshot> {
        return new Map(
            before.map((tile) => {
                const active = this.running.get(tile.key);
                return [
                    tile.key,
                    active === undefined ? this.reflow.source(tile) : sampleFlight(tile, active),
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
        if (motion.kind === "reveal") {
            this.playReveal(motion, scene, target);
            return;
        }
        const flight = createFlight(motion, scene, target);
        if (flight !== null) {
            this.playMove(flight, target);
        }
    }

    private playHold(motion: TileMotion, scene: Scene): void {
        const target = scene.after.get(motion.target);
        if (target === undefined || this.discardLandingAt === null) {
            return;
        }
        const ms = Math.max(0, this.discardLandingAt + BOARD_MOTION.drawHold - performance.now());
        if (ms > 0) {
            this.hold.play(motion.target, target.element, ms);
        }
    }

    private playMove(flight: Flight, target: TileSnapshot): void {
        if (
            flight.motion.kind === "reflow" &&
            (target.region === "hand" ||
                (target.region === "melds" &&
                    (flight.fromPose.angle - flight.toPose.angle) % 360 === 0) ||
                (target.region === "discards" && hasSamePose(flight.fromPose, flight.toPose)))
        ) {
            this.reflow.play(flight.motion, { quad: flight.fromQuad, rect: flight.from }, target);
            return;
        }
        this.playFlight(flight, target);
    }

    private playReveal(motion: TileMotion, scene: Scene, target: TileSnapshot): void {
        const source = motion.source === null ? undefined : scene.before.get(motion.source);
        if (source !== undefined) {
            this.reveal.play(motion, source, target);
        }
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
        if (motion.kind === "flight" && target.region === "discards") {
            this.discardLandingAt = performance.now() + motion.delay + BOARD_MOTION.landing;
        }
    }

    prepareRender(): void {
        this.hold.prepareRender();
        this.reveal.prepareRender();
        this.reflow.prepareRender();
    }

    finishRender(): void {
        if (this.reflow.suspended || this.reveal.suspended || this.hold.suspended) {
            const after = new Map(snapshotTiles(this.board).map((tile) => [tile.key, tile]));
            this.reflow.reconcile(after, []);
            this.reveal.reconcile(after, []);
            this.hold.reconcile(after);
        }
    }

    private playTrail(flight: Flight): void {
        for (const [index, opacity] of [0.06, 0.18, 0.06].entries()) {
            const ghost = flight.image.cloneNode(true);
            if (ghost instanceof HTMLElement) {
                ghost.classList.add("board-motion__tile--trail");
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
        Object.assign(image.style, {
            left: `${to.left + to.width / 2 - board.left}px`,
            top: `${to.top + to.height / 2 - board.top}px`,
        });
        this.createLayer().append(image);
        const animation = image.animate(flightFrames(flight), {
            delay: motion.delay,
            duration: motion.duration,
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
        this.hold.cancel();
        this.discardLandingAt = null;
        this.reveal.cancel();
        this.reflow.cancel();
        this.cancelFlights();
    }

    private cancelFlights(): void {
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
