import {
    BOARD_MOTION,
    type MotionRect,
    type TileMotion,
    drawHoldAfterLanding,
} from "@/entities/table/lib/board-motion";

import { type TilePose, type TileSnapshot, snapshotTiles } from "./board-motion-snapshot";
import { TileHoldPlayer } from "./tile-hold-player";
import { TileReflowPlayer } from "./tile-reflow-player";
import { TileRevealPlayer } from "./tile-reveal-player";

interface Flight {
    readonly fromPose: TilePose;
    readonly toPose: TilePose;
    readonly image: HTMLElement;
    readonly from: MotionRect;
    readonly to: MotionRect;
    readonly board: MotionRect;
    readonly motion: TileMotion;
}

interface Scene {
    readonly before: ReadonlyMap<string, TileSnapshot>;
    readonly after: ReadonlyMap<string, TileSnapshot>;
    readonly box: MotionRect;
}

const [, MAIN_GHOST] = BOARD_MOTION.ghosts;

function createFlight(motion: TileMotion, scene: Scene, target: TileSnapshot): Flight | null {
    const source = motion.source === null ? undefined : scene.before.get(motion.source);
    if (source === undefined) {
        return null;
    }
    return {
        board: scene.box,
        from: target.latest ? source.rect : source.painted,
        fromPose: source.pose,
        image: target.image,
        motion,
        to: target.painted,
        toPose: target.pose,
    };
}

function flightFrames({ from, to }: Flight): Keyframe[] {
    const deltaX = from.left + from.width / 2 - to.left - to.width / 2;
    const deltaY = from.top + from.height / 2 - to.top - to.height / 2;
    return [{ translate: `${deltaX}px ${deltaY}px` }, { translate: "0px 0px" }];
}

function ghostFrames(
    flight: Flight,
    ghost: (typeof BOARD_MOTION.ghosts)[number],
    intoRiver: boolean,
): Keyframe[] {
    const [start, end] = flightFrames(flight);
    if (!intoRiver) {
        return [start, end];
    }
    const eased = { ...start, easing: BOARD_MOTION.discardEasing };
    if (ghost !== MAIN_GHOST) {
        return [eased, end];
    }
    return [
        { ...eased, opacity: ghost.alpha },
        { offset: BOARD_MOTION.discardSolidFrom, opacity: ghost.alpha },
        { ...end, opacity: 1 },
    ];
}

function placeImage({ board, image, to }: Flight): void {
    Object.assign(image.style, {
        left: `${to.left + to.width / 2 - board.left}px`,
        top: `${to.top + to.height / 2 - board.top}px`,
    });
    image.style.setProperty("--motion-across", `${to.width}px`);
    image.style.setProperty("--motion-down", `${to.height}px`);
}

function copyImage(image: HTMLElement): HTMLElement {
    const copy = image.cloneNode(true);
    if (!(copy instanceof HTMLElement)) {
        throw new Error("A flight image must be an HTML element");
    }
    return copy;
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

interface RunningTile {
    readonly rect: MotionRect;
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
}

function hideDestination(target: HTMLElement): void {
    target.style.visibility = "hidden";
    const slot = target.parentElement;
    if (slot !== null) {
        slot.setAttribute("data-landing", "");
        landingSlots.set(target, slot);
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
        const returnDelay = this.remainingDrawHold();
        for (const motion of plan.filter(({ kind }) => kind !== "hold")) {
            this.playTile(
                motion.kind === "return" ? { ...motion, delay: returnDelay } : motion,
                scene,
            );
        }
        for (const motion of plan.filter(({ kind }) => kind === "hold")) {
            this.playHold(motion, scene);
        }
    }

    private remainingDrawHold(): number {
        return this.remainingHold(BOARD_MOTION.drawHold);
    }

    private remainingHold(afterLanding: number): number {
        return this.discardLandingAt === null
            ? 0
            : Math.max(0, this.discardLandingAt + afterLanding - performance.now());
    }

    private currentSources(before: readonly TileSnapshot[]): ReadonlyMap<string, TileSnapshot> {
        return new Map(
            before.map((tile) => [
                tile.key,
                this.running.has(tile.key) ? tile : this.reflow.source(tile),
            ]),
        );
    }

    private reconcile(after: ReadonlyMap<string, TileSnapshot>, plan: readonly TileMotion[]): void {
        const changing = new Set(
            plan.filter(({ kind }) => kind !== "return").map((motion) => motion.target),
        );
        for (const active of this.running.values()) {
            showDestination(active.target);
        }
        for (const [key, active] of this.running) {
            const next = after.get(key);
            if (next === undefined || changing.has(key) || !sameRect(active.rect, next.rect)) {
                this.landTile(key);
            } else {
                active.target = next.element;
                hideDestination(next.element);
            }
        }
    }

    private landTile(key: string): void {
        this.running.delete(key);
        for (const sprite of this.sprites) {
            if (sprite.key === key) {
                sprite.animation.onfinish = null;
                sprite.animation.cancel();
                sprite.image.remove();
                this.sprites.delete(sprite);
            }
        }
        this.removeIdleLayer();
    }

    private removeIdleLayer(): void {
        if (this.sprites.size === 0) {
            this.layer?.remove();
            this.layer = null;
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
            this.playMove(flight, target, scene.after);
        }
    }

    private playHold(motion: TileMotion, scene: Scene): void {
        const target = scene.after.get(motion.target);
        if (target === undefined) {
            return;
        }
        const ms = Math.max(motion.delay, this.remainingHold(drawHoldAfterLanding(target.seat)));
        if (ms > 0) {
            this.hold.play(motion.target, target.element, ms);
        }
    }

    private playMove(
        flight: Flight,
        target: TileSnapshot,
        after: ReadonlyMap<string, TileSnapshot>,
    ): void {
        if (flight.motion.kind === "flight") {
            this.playFlight(flight, target);
            return;
        }
        if (
            target.region === "hand" ||
            ((target.region === "melds" || target.region === "dora") &&
                (flight.fromPose.angle - flight.toPose.angle) % 360 === 0) ||
            (target.region === "discards" && hasSamePose(flight.fromPose, flight.toPose))
        ) {
            this.reflow.play(flight.motion, flight.from, after);
        }
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
        placeImage(flight);
        const intoRiver = target.region === "discards";
        for (const ghost of BOARD_MOTION.ghosts) {
            const animation = this.playGhost(flight, ghost, ghostFrames(flight, ghost, intoRiver));
            if (ghost === MAIN_GHOST) {
                this.running.set(motion.target, {
                    animation,
                    rect: target.rect,
                    target: target.element,
                });
            }
        }
        if (intoRiver) {
            this.discardLandingAt = performance.now() + motion.delay + BOARD_MOTION.landing;
        }
    }

    private playGhost(
        { image: source, motion }: Flight,
        ghost: (typeof BOARD_MOTION.ghosts)[number],
        frames: Keyframe[],
    ): Animation {
        const image = copyImage(source);
        image.style.opacity = String(ghost.alpha);
        this.createLayer().append(image);
        const animation = image.animate(frames, {
            delay: motion.delay + ghost.delay,
            duration: motion.duration,
            easing: "linear",
            fill: "both",
        });
        const sprite = { animation, image, key: motion.target };
        this.sprites.add(sprite);
        animation.onfinish = () => this.finish(sprite);
        return animation;
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

    private finish(sprite: RunningSprite): void {
        this.sprites.delete(sprite);
        sprite.animation.cancel();
        sprite.image.remove();
        const active = this.running.get(sprite.key);
        if (active?.animation === sprite.animation) {
            showDestination(active.target);
            this.running.delete(sprite.key);
        }
        this.removeIdleLayer();
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
