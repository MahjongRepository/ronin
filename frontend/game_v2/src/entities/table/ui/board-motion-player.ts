import {
    BOARD_MOTION,
    type MotionRect,
    type TileMotion,
    drawHoldAfterLanding,
} from "@/entities/table/lib/board-motion";
import { type SeatPosition } from "@/entities/table/model/board-types";

import { type TilePose, type TileSnapshot, snapshotTiles } from "./board-motion-snapshot";
import { type HeldTile, TileHoldPlayer } from "./tile-hold-player";
import {
    type ReflowScene,
    type SlotReleases,
    TileReflowPlayer,
    holdAtStart,
    startAt,
} from "./tile-reflow-player";
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

interface HeldDraw {
    readonly held: HeldTile;
    readonly motion: TileMotion;
    readonly seat: SeatPosition;
}

/** What a played plan starts together: its flight copies, river landings, held draws, returns and slots. */
interface PlanStart {
    readonly waits: boolean;
    readonly sprites: RunningSprite[];
    readonly landings: TileMotion[];
    readonly holds: HeldDraw[];
    readonly returns: TileMotion[];
    readonly releases: SlotReleases;
}

interface Scene extends ReflowScene {
    readonly before: ReadonlyMap<string, TileSnapshot>;
    readonly box: MotionRect;
    readonly start: PlanStart;
}

function newPlanStart(waits: boolean): PlanStart {
    return { holds: [], landings: [], releases: new Map(), returns: [], sprites: [], waits };
}

function startsNothing({ holds, landings, releases, sprites }: PlanStart): boolean {
    return (
        sprites.length === 0 && landings.length === 0 && holds.length === 0 && releases.size === 0
    );
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
    private readonly landedAt = new Map<string, number>();
    private readonly waiting: PlanStart[] = [];
    private startFrame: number | null = null;
    /** Told, as each discard's flight starts, how many ms from now it lands. */
    onDiscardLanding: ((inMs: number) => void) | undefined;

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
        const start = newPlanStart(this.waitsForStart(plan));
        const scene: Scene = {
            after: new Map(after.map((tile) => [tile.key, tile])),
            before: this.currentSources(before),
            box,
            releases: start.releases,
            start,
            waits: start.waits,
        };
        this.reconcileAll(scene.after, plan);
        this.playPlan(plan, scene);
    }

    private reconcileAll(
        after: ReadonlyMap<string, TileSnapshot>,
        plan: readonly TileMotion[],
    ): void {
        this.hold.cancel();
        this.reconcile(after, plan);
        this.reflow.reconcile(after, plan);
        this.reveal.reconcile(after, plan);
    }

    private waitsForStart(plan: readonly TileMotion[]): boolean {
        return (
            !document.hidden &&
            (this.startFrame !== null || plan.some(({ kind }) => kind === "flight"))
        );
    }

    private startLater(start: PlanStart): void {
        if (!start.waits) {
            this.startPlan(start, null);
            return;
        }
        if (startsNothing(start)) {
            return;
        }
        this.waiting.push(start);
        if (this.startFrame === null) {
            document.addEventListener("visibilitychange", this.startWhenHidden);
            this.startFrame = requestAnimationFrame(() => {
                this.startFrame = requestAnimationFrame((at) => this.start(at));
            });
        }
    }

    private readonly startWhenHidden = (): void => {
        if (document.hidden) {
            this.start(null);
        }
    };

    private playPlan(plan: readonly TileMotion[], scene: Scene): void {
        for (const motion of plan.filter(({ kind }) => kind !== "hold")) {
            this.playTile(this.timedNow(motion, scene.waits), scene);
        }
        for (const motion of plan.filter(({ kind }) => kind === "hold")) {
            this.playHold(motion, scene);
        }
        this.startLater(scene.start);
    }

    private start(at: number | null): void {
        this.stopWaiting();
        for (const start of this.waiting.splice(0)) {
            this.startPlan(start, at);
        }
    }

    private stopWaiting(): void {
        if (this.startFrame !== null) {
            cancelAnimationFrame(this.startFrame);
            this.startFrame = null;
        }
        document.removeEventListener("visibilitychange", this.startWhenHidden);
    }

    private startPlan(start: PlanStart, at: number | null): void {
        const now = at ?? performance.now();
        for (const sprite of start.sprites.filter((running) => this.sprites.has(running))) {
            startAt(sprite.animation, at);
        }
        for (const motion of start.landings) {
            this.land(motion, now);
        }
        for (const { held, motion, seat } of start.holds) {
            const ms = Math.max(motion.delay, this.remainingHold(drawHoldAfterLanding(seat), now));
            this.hold.start(held, ms, at);
        }
        this.reflow.start(start.releases, at, this.returnDelay(start.returns, now));
    }

    private timedNow(motion: TileMotion, waits: boolean): TileMotion {
        return motion.kind === "return" && !waits
            ? { ...motion, delay: this.returnDelay([motion], performance.now()) }
            : motion;
    }

    private land(motion: TileMotion, now: number): void {
        const landsIn = motion.delay + BOARD_MOTION.landing;
        this.discardLandingAt = now + landsIn;
        for (const [key, landed] of this.landedAt) {
            if (landed + BOARD_MOTION.drawHold < now) {
                this.landedAt.delete(key);
            }
        }
        this.landedAt.set(motion.target, now + landsIn);
        this.onDiscardLanding?.(landsIn);
    }

    private returnDelay(returns: readonly TileMotion[], now: number): number {
        const landings = returns.map(
            ({ target }) => this.landedAt.get(target) ?? Number.NEGATIVE_INFINITY,
        );
        return Math.max(0, ...landings.map((landed) => landed + BOARD_MOTION.drawHold - now));
    }

    private remainingHold(afterLanding: number, at = performance.now()): number {
        return this.discardLandingAt === null
            ? 0
            : Math.max(0, this.discardLandingAt + afterLanding - at);
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
            this.playMove(flight, target, scene);
        }
    }

    private playHold(motion: TileMotion, scene: Scene): void {
        const target = scene.after.get(motion.target);
        if (target === undefined) {
            return;
        }
        const ms = Math.max(motion.delay, this.remainingHold(drawHoldAfterLanding(target.seat)));
        const held = ms > 0 ? this.hold.play(motion.target, target.element, ms) : null;
        if (held !== null && scene.waits) {
            holdAtStart(held.animation);
            scene.start.holds.push({ held, motion, seat: target.seat });
        }
    }

    private playMove(flight: Flight, target: TileSnapshot, scene: Scene): void {
        if (flight.motion.kind === "flight") {
            this.playFlight(flight, target, scene);
            return;
        }
        if (
            target.region === "hand" ||
            ((target.region === "melds" || target.region === "dora") &&
                (flight.fromPose.angle - flight.toPose.angle) % 360 === 0) ||
            (target.region === "discards" && hasSamePose(flight.fromPose, flight.toPose))
        ) {
            this.reflow.play(flight.motion, flight.from, scene);
            if (flight.motion.kind === "return") {
                scene.start.returns.push(flight.motion);
            }
        }
    }

    private playReveal(motion: TileMotion, scene: Scene, target: TileSnapshot): void {
        const source = motion.source === null ? undefined : scene.before.get(motion.source);
        if (source !== undefined) {
            this.reveal.play(motion, source, target);
        }
    }

    private playFlight(flight: Flight, target: TileSnapshot, scene: Scene): void {
        hideDestination(target.element);
        placeImage(flight);
        const intoRiver = target.region === "discards";
        for (const ghost of BOARD_MOTION.ghosts) {
            const sprite = this.playGhost(flight, ghost, ghostFrames(flight, ghost, intoRiver));
            this.waitForStart(sprite, scene.start);
            if (ghost === MAIN_GHOST) {
                this.running.set(flight.motion.target, {
                    animation: sprite.animation,
                    rect: target.rect,
                    target: target.element,
                });
            }
        }
        if (intoRiver) {
            this.landLater(flight.motion, scene);
        }
    }

    private waitForStart(sprite: RunningSprite, start: PlanStart): void {
        if (start.waits) {
            holdAtStart(sprite.animation);
            start.sprites.push(sprite);
        }
    }

    private landLater(motion: TileMotion, scene: Scene): void {
        this.discardLandingAt = performance.now() + motion.delay + BOARD_MOTION.landing;
        scene.start.landings.push(motion);
    }

    private playGhost(
        { image: source, motion }: Flight,
        ghost: (typeof BOARD_MOTION.ghosts)[number],
        frames: Keyframe[],
    ): RunningSprite {
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
        return sprite;
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
        this.stopWaiting();
        this.waiting.length = 0;
        this.hold.cancel();
        this.discardLandingAt = null;
        this.landedAt.clear();
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
