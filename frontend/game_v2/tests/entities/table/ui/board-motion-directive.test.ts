import { html, nothing, render } from "lit-html";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LYING_Y_SHARE } from "@/entities/table/lib/board-constants";
import { tableStateToDisplayState } from "@/entities/table/lib/board-mapper";
import { BOARD_MOTION, planTileMotion } from "@/entities/table/lib/board-motion";
import {
    type BoardMotionCue,
    type BoardPerspective,
    type SeatPosition,
} from "@/entities/table/model/board-types";
import {
    createInitialPlayerState,
    createInitialTableState,
} from "@/entities/table/model/initial-state";
import { type TableState } from "@/entities/table/model/types";
import { animateBoard } from "@/entities/table/ui/board-motion-directive";
import { BoardMotionPlayer } from "@/entities/table/ui/board-motion-player";
import { snapshotTiles } from "@/entities/table/ui/board-motion-snapshot";
import { GameBoard } from "@/entities/table/ui/game-board";
import { Discards, Hand, type HandTile, Meld } from "@/entities/tile";

let host = document.createElement("div");
let animations: Animation[] = [];
const frameRequests = new Map<number, FrameRequestCallback>();
let frameRequestCount = 0;
const { animate: nativeAnimate } = HTMLElement.prototype;
const perspective: BoardPerspective = { bottomSeat: 0, reveal: "all" };

function table(dealt: boolean): TableState {
    return {
        ...createInitialTableState(),
        gameId: "motion",
        players: [0, 1, 2, 3].map((seat) => ({
            ...createInitialPlayerState({
                isAiPlayer: false,
                name: `Seat ${seat}`,
                score: 25_000,
                seat,
            }),
            tiles: dealt ? Array.from({ length: 13 }, (_unused, index) => seat * 32 + index) : [],
        })),
    };
}

function drawn(state: TableState): TableState {
    return {
        ...state,
        players: state.players.map((player) =>
            player.seat === 0
                ? { ...player, drawnTileId: 120, tiles: [...player.tiles, 120] }
                : player,
        ),
    };
}

function discardDraw(state: TableState, riichi = false): TableState {
    return {
        ...state,
        lastDiscardSeat: 0,
        players: state.players.map((player) =>
            player.seat === 0
                ? {
                      ...player,
                      discards: [{ isRiichi: riichi, isTsumogiri: true, tileId: 120 }],
                  }
                : player,
        ),
    };
}

function opponentDrew(state: TableState, seat = 1): TableState {
    return {
        ...state,
        lastDiscardSeat: null,
        players: state.players.map((player) =>
            player.seat === seat
                ? {
                      ...player,
                      concealedCount: player.concealedCount + 1,
                      drawnConcealed: true,
                  }
                : player,
        ),
    };
}

const bottomOnly: BoardPerspective = { bottomSeat: 0, reveal: "bottom" };

interface ShowOptions {
    readonly view?: BoardPerspective;
    readonly animationsOn?: boolean;
}

function draw(
    state: TableState,
    cue: BoardMotionCue,
    { animationsOn = true, view = perspective }: ShowOptions = {},
): void {
    render(
        GameBoard({
            animationsOn,
            debug: false,
            motion: cue,
            state: tableStateToDisplayState(state, view),
        }),
        host,
    );
}

const LATEST_GAP = 7;

function paintsGap(tile: HTMLElement): boolean {
    const slot = tile.parentElement;
    return (
        slot?.classList.contains("discard-tile--last") === true &&
        slot.style.getPropertyValue("translate") !== "none"
    );
}

function getBox(element: HTMLElement): DOMRect {
    if (element.classList.contains("game-board")) {
        return DOMRect.fromRect({ height: 800, width: 1200 });
    }
    const area = element.closest<HTMLElement>("[data-area]")?.dataset.area ?? "";
    const siblings = element.parentElement?.parentElement?.querySelectorAll("[data-tile-id]") ?? [];
    const index = [...siblings].indexOf(element.parentElement!);
    const gap = paintsGap(element) ? LATEST_GAP : 0;
    return new DOMRect(100 + index * 32 + gap, (area.endsWith("hand") ? 600 : 300) + gap, 30, 40);
}

function runFrames(count = 2): void {
    for (let frame = 0; frame < count; frame += 1) {
        const due = [...frameRequests.values()];
        frameRequests.clear();
        for (const callback of due) {
            callback(performance.now());
        }
    }
}

async function show(
    state: TableState,
    cue: BoardMotionCue,
    options: ShowOptions = {},
): Promise<void> {
    draw(state, cue, options);
    await Promise.resolve();
    runFrames();
}

function finishAll(): void {
    for (const animation of animations) {
        animation.finish();
    }
}

function getAnimationFrames(animation: Animation): ComputedKeyframe[] {
    if (!(animation.effect instanceof KeyframeEffect)) {
        throw new Error("Expected a keyframe animation");
    }
    return animation.effect.getKeyframes();
}

function translateOf(animation: Animation): number[] {
    const transform = String(getAnimationFrames(animation)[0].transform);
    const match = /translate\((?<x>[^p]+)px, (?<y>[^p]+)px\)/u.exec(transform);
    if (match?.groups === undefined) {
        throw new Error(`Expected a translate in ${transform}`);
    }
    return [Number(match.groups.x), Number(match.groups.y)];
}

function hiddenTiles(): number {
    return host.querySelectorAll(".tile[style*='hidden']").length;
}

function tileBoxReads(): number {
    return vi
        .mocked(HTMLElement.prototype.getBoundingClientRect)
        .mock.contexts.filter(
            (element) => element instanceof HTMLElement && element.matches(".tile"),
        ).length;
}

function renderHand(
    tiles: readonly HandTile[],
    onTile: (id: number) => void,
    seat: SeatPosition = "bottom",
): void {
    render(html`<div data-area=${`${seat}-hand`}>${Hand({ onTile, tiles })}</div>`, host);
}

function movingHand(seat: SeatPosition = "bottom") {
    const onTile = vi.fn();
    const tiles: HandTile[] = [
        { face: "1m", show: "face", state: "selectable", tileId: 0 },
        { face: "2m", show: "face", state: "selectable", tileId: 4 },
    ];
    renderHand(tiles, onTile, seat);
    const before = snapshotTiles(host);
    renderHand(tiles.toReversed(), onTile, seat);
    const after = snapshotTiles(host);
    const player = new BoardMotionPlayer(host);
    player.play(planTileMotion(before, after), before, after);
    return { onTile, player, target: after[1] };
}

function discardSecondOfFour(seat: SeatPosition): BoardMotionPlayer {
    const tiles: HandTile[] = [0, 4, 8, 12].map((tileId) => ({
        face: "1m",
        show: "face",
        state: "selectable",
        tileId,
    }));
    renderHand(tiles, vi.fn(), seat);
    const before = snapshotTiles(host);
    renderHand(tiles.toSpliced(1, 1), vi.fn(), seat);
    const after = snapshotTiles(host);
    const player = new BoardMotionPlayer(host);
    player.play(planTileMotion(before, after), before, after);
    return player;
}

async function showMovingHand(
    tiles: readonly HandTile[],
    sequence: number,
    mode: BoardMotionCue["mode"] = "step",
): Promise<void> {
    const state = tableStateToDisplayState(table(true), perspective);
    render(
        html`<div
      class="game-board"
      ${animateBoard(state, { mode, sequence }, true)}
    >
      <div data-area="bottom-hand">${Hand({ tiles })}</div>
    </div>`,
        host,
    );
    await Promise.resolve();
}

function getMovingFace(): HTMLElement {
    const face = host.querySelector<HTMLElement>(".hand-tile[data-tile-id='4'] > .tile");
    if (face === null) {
        throw new Error("Expected a moving tile");
    }
    return face;
}

function renderRiichiFlight(discarded: boolean): void {
    const held: HandTile = {
        face: "2m",
        show: "face",
        state: "selectable",
        tileId: 4,
    };
    const tiles: readonly HandTile[] = discarded
        ? [held]
        : [{ face: "1m", show: "face", state: "selectable", tileId: 0 }, held];
    render(
        html`<div class="board-local" data-area="bottom-hand">
        ${Hand({ standing: true, tiles })}
      </div>
      <div data-area="bottom-discards">
        ${Discards(discarded ? [{ face: "1m", riichi: true, tileId: 0 }] : [])}
      </div>`,
        host,
    );
}

function measureFlightTile(this: HTMLElement): DOMRect {
    if (!this.classList.contains("tile")) {
        return getBox(this);
    }
    if (this.closest("[data-area='bottom-hand']") !== null) {
        return new DOMRect(100, 600, 48, 64);
    }
    const gap = paintsGap(this) ? LATEST_GAP : 0;
    return new DOMRect(100 + gap, 300 + gap, 48, 36 * LYING_Y_SHARE);
}

function renderSideDiscard(discarded: boolean): void {
    const held: HandTile = {
        face: "2m",
        show: "face",
        state: "selectable",
        tileId: 4,
    };
    render(
        html`<div class="board-local" data-area="bottom-hand">
        ${Hand({ standing: true, tiles: discarded ? [held] : [{ face: "1m", show: "face", state: "selectable", tileId: 0 }, held] })}
      </div>
      <div data-area="left-discards">
        ${Discards(discarded ? [{ face: "1m", tileId: 0 }] : [], "wrap", 90)}
      </div>`,
        host,
    );
}

function startRiichiFlight(): BoardMotionPlayer {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(measureFlightTile);
    renderRiichiFlight(false);
    const before = snapshotTiles(host);
    renderRiichiFlight(true);
    const after = snapshotTiles(host);
    const player = new BoardMotionPlayer(host);
    player.play(planTileMotion(before, after), before, after);
    return player;
}

const KEYFRAME_TIMING = new Set(["composite", "computedOffset", "easing", "offset"]);

function animatedProperties(frame: ComputedKeyframe): readonly string[] {
    return Object.keys(frame)
        .filter((name) => !KEYFRAME_TIMING.has(name))
        .toSorted();
}

function riverCourse(animation: Animation): readonly unknown[] {
    const frames = getAnimationFrames(animation);
    expect(frames.at(-1)?.translate).not.toBe(frames[0]?.translate);
    return frames.map((frame) => [
        frame.computedOffset,
        animatedProperties(frame),
        frame.easing,
        frame.opacity,
    ]);
}

function flightPoses(): readonly Record<string, string>[] {
    return [...host.querySelectorAll<HTMLElement>(".board-motion__tile")].map((image) =>
        Object.fromEntries(
            [
                "--motion-across",
                "--motion-angle",
                "--motion-down",
                "--motion-height",
                "--motion-width",
            ].map((name) => [name, image.style.getPropertyValue(name)]),
        ),
    );
}

function renderResizingMeld(small: boolean): void {
    render(
        html`<div data-area="right-hand">
        ${Hand({ tiles: [{ face: "1m", show: "face", tileId: 0 }] })}
      </div>
      <div data-area="right-melds" data-small=${String(small)}>
        ${Meld([
            { face: "2m", kind: "upright", tileId: 4 },
            { face: "2m", kind: "sideways", tileId: 5 },
            { face: "2m", kind: "upright", tileId: 6 },
        ])}
      </div>`,
        host,
    );
}

function measureMeldTile(this: HTMLElement): DOMRect {
    const area = this.closest<HTMLElement>("[data-area='right-melds']");
    if (area === null) {
        return getBox(this);
    }
    const small = area.dataset.small === "true";
    const id = Number(this.parentElement?.dataset.tileId);
    const sideways = id === 5;
    const scale = small ? 0.8 : 1;
    return new DOMRect(
        small ? 308 : 300,
        200 - (id - 4) * 40 * scale,
        (sideways ? 30 : 40) * scale,
        (sideways ? 40 : 30) * scale,
    );
}

function startResizingMeld(): BoardMotionPlayer {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(measureMeldTile);
    host.insertAdjacentHTML(
        "beforeend",
        "<style>.tile { width: 30px; } .meld-tile-sideways > .tile { width: 40px; }</style>",
    );
    renderResizingMeld(false);
    const before = snapshotTiles(host);
    renderResizingMeld(true);
    const after = snapshotTiles(host);
    const player = new BoardMotionPlayer(host);
    player.play(planTileMotion(before, after), before, after);
    return player;
}

async function startRevealingHand(): Promise<{
    state: TableState;
    view: BoardPerspective;
}> {
    const view = { bottomSeat: 0, reveal: "bottom" } as const;
    const dealt = table(true);
    await show(dealt, { mode: "reset", sequence: 0 }, { view });
    const state = { ...dealt, revealedSeats: [1] };
    await show(state, { mode: "step", sequence: 1 }, { view });
    return { state, view };
}

async function showPanel(matchResult: boolean, held: boolean): Promise<void> {
    render(
        GameBoard({
            debug: false,
            matchResult,
            overlay: html`<p>${matchResult ? "Standings" : "Win result"}</p>`,
            overlayHeld: held,
            state: null,
        }),
        host,
    );
    await Promise.resolve();
}

function recordAnimations(pauses: (element: HTMLElement) => boolean): void {
    vi.spyOn(HTMLElement.prototype, "animate").mockImplementation(function animateRecorded(
        this: HTMLElement,
        frames,
        options,
    ) {
        const animation = nativeAnimate.call(this, frames, options);
        void animation.finished.catch((error: unknown) => {
            expect(error).toMatchObject({ name: "AbortError" });
        });
        if (pauses(this)) {
            animation.pause();
        }
        animations.push(animation);
        return animation;
    });
}

beforeEach(() => {
    host = document.createElement("div");
    document.body.append(host);
    animations = [];
    frameRequests.clear();
    vi.spyOn(globalThis, "requestAnimationFrame").mockImplementation((callback) => {
        frameRequestCount += 1;
        frameRequests.set(frameRequestCount, callback);
        return frameRequestCount;
    });
    vi.spyOn(globalThis, "cancelAnimationFrame").mockImplementation((id) => {
        frameRequests.delete(id);
    });
    recordAnimations(() => true);
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(
        function measureTile(this: HTMLElement) {
            return getBox(this);
        },
    );
});

describe("moving hand feedback", () => {
    it("updates disabled and selected feedback without restarting a tile's movement", async () => {
        const tiles = [
            { face: "1m", show: "face", state: "waiting", tileId: 0 },
            { face: "2m", show: "face", state: "waiting", tileId: 4 },
        ] as const satisfies readonly HandTile[];
        host.insertAdjacentHTML(
            "beforeend",
            `<style>
            .hand-tile--disabled .tile { filter: grayscale(1) brightness(0.82); }
            .hand-tile--selected .tile { outline: 3px solid red; outline-offset: 2px; }
        </style>`,
        );
        await showMovingHand(tiles, 0);
        await showMovingHand(tiles.toReversed(), 1);
        const moving = getMovingFace();
        animations.forEach((animation) => {
            animation.currentTime = 60;
        });
        await showMovingHand(
            tiles.toReversed().map((tile) => ({ ...tile, state: "disabled" })),
            1,
        );
        expect(getComputedStyle(moving).filter).toBe("grayscale(1) brightness(0.82)");
        await showMovingHand(
            tiles.toReversed().map((tile) => ({ ...tile, state: "selected" })),
            1,
        );
        expect([
            getMovingFace(),
            getComputedStyle(moving).filter,
            getComputedStyle(moving).outline,
            getComputedStyle(moving).outlineOffset,
            animations.map((animation) => animation.currentTime),
            hiddenTiles(),
            host.querySelector(".board-motion"),
        ]).toEqual([moving, "", "red solid 3px", "2px", [60, 60], 0, null]);
    });
});

describe("match result motion", () => {
    it("fades standings after a winning result without restarting the copied panel's opening delay", async () => {
        await showPanel(false, true);
        await showPanel(true, false);
        await showPanel(false, false);
        const leaving = host.querySelector(".board-overlay--leaving");
        expect(leaving).not.toBeNull();
        expect([
            leaving?.textContent?.trim(),
            leaving?.classList.contains("board-overlay--held"),
            host
                .querySelector(".board-overlay:not(.board-overlay--leaving)")
                ?.classList.contains("board-overlay--held"),
        ]).toEqual(["Standings", false, true]);
        expect(animations).toHaveLength(1);
        finishAll();
        expect(host.querySelector(".board-overlay--leaving")).toBeNull();
    });
});

afterEach(() => {
    render(nothing, host);
    host.remove();
    vi.restoreAllMocks();
    vi.useRealTimers();
});

describe("shared tile depth", () => {
    it("resizes a laid meld's upright and sideways tiles inside their shared shadow", () => {
        const player = startResizingMeld();
        expect([animations.length, hiddenTiles(), host.querySelector(".board-motion")]).toEqual([
            3,
            0,
            null,
        ]);
        expect(animations.map((animation) => getAnimationFrames(animation)[0].transform)).toEqual([
            expect.stringContaining("scale(1.25)"),
            expect.stringContaining("scale(1.25)"),
            expect.stringContaining("scale(1.25)"),
        ]);
        expect(animations.map((animation) => translateOf(animation))).toEqual([
            [expect.closeTo(-3.75), expect.closeTo(-5)],
            [expect.closeTo(5), expect.closeTo(-6.25)],
            [expect.closeTo(16.25), expect.closeTo(-5)],
        ]);
        expect(animations.map((animation) => getAnimationFrames(animation)[1].transform)).toEqual([
            "translate(0px, 0px) scale(1)",
            "translate(0px, 0px) scale(1)",
            "translate(0px, 0px) scale(1)",
        ]);
        player.cancel();
        expect(animations.every((animation) => animation.playState === "idle")).toBe(true);
    });

    it("stages a revealed hand inside its native slots and keeps its timing through redraws", async () => {
        const { state, view } = await startRevealingHand();
        expect([
            animations.length,
            host.querySelectorAll(".hand-tile > .board-reveal-back").length,
            host.querySelector(".board-motion"),
        ]).toEqual([13, 13, null]);
        animations[0].finish();
        animations[5].currentTime = 90;
        await show(state, { mode: "step", sequence: 1 }, { view });
        expect([
            animations.length,
            animations[5].currentTime,
            host.querySelectorAll(".hand-tile > .board-reveal-back").length,
        ]).toEqual([13, 90, 12]);
        render(nothing, host);
        expect(animations.map((animation) => animation.playState)).toEqual(Array(13).fill("idle"));
    });
});

describe("board motion", () => {
    it("keeps a rearranging hand tile visible and clickable through its native button", () => {
        const { onTile, player, target } = movingHand();
        expect([target.id, hiddenTiles(), host.querySelector(".board-motion")]).toEqual([
            "0",
            0,
            null,
        ]);
        target.element.closest("button")?.click();
        expect(onTile).toHaveBeenCalledExactlyOnceWith(0);
        player.cancel();
        expect(target.element.closest("button")?.style.pointerEvents).toBe("");
        expect(animations.every((animation) => animation.playState === "idle")).toBe(true);
    });

    it.each([
        { name: "the game's first deal", previous: table(false), round: 0 },
        { name: "a later round's deal", previous: drawn(table(true)), round: 1 },
    ])(
        "holds the dealer's first draw rendered in the same task as $name for the draw hold",
        async ({ previous, round }) => {
            await show(previous, { mode: "reset", sequence: 0 });
            const dealt = { ...table(true), roundNumber: round };
            draw(dealt, { mode: "step", sequence: 1 });
            await show(drawn(dealt), {
                mode: "step",
                sequence: 2,
            });
            const hold = animations.at(-1);
            expect([animations.length, targetOf(hold), hold?.effect?.getTiming().duration]).toEqual(
                [
                    1,
                    host.querySelector("[data-area='bottom-hand'] .hand-drawn-gap > .tile"),
                    BOARD_MOTION.drawHold,
                ],
            );
        },
    );

    it("clears old flights and shows a new round immediately even when it reuses tile ids", async () => {
        const dealt = table(true);
        await show(drawn(dealt), { mode: "reset", sequence: 0 });
        await show(discardDraw(dealt), { mode: "step", sequence: 1 });
        expect(hiddenTiles()).toBe(1);
        await show({ ...dealt, roundNumber: dealt.roundNumber + 1 }, { mode: "step", sequence: 2 });
        expect([
            hiddenTiles(),
            animations.length,
            animations.every((animation) => animation.playState === "idle"),
        ]).toEqual([0, 3, true]);
    });

    it.each([
        { mode: "step", nextState: "paused" },
        { mode: "replay", nextState: "idle" },
    ] as const)(
        "keeps a discard flight through redraws and handles the next $mode update",
        async ({ mode, nextState }) => {
            const dealt = table(true);
            await show(drawn(dealt), { mode, sequence: 0 });
            const after = discardDraw(dealt);
            await show(after, { mode, sequence: 1 });
            expect(animations.length).toBe(3);
            await show(after, { mode, sequence: 1 });
            expect(animations.every((animation) => animation.playState === "paused")).toBe(true);
            await show({ ...after, doraIndicators: [24] }, { mode, sequence: 2 });
            expect([
                animations.length,
                animations.every((animation) => animation.playState === nextState),
                hiddenTiles(),
            ]).toEqual([3, true, mode === "replay" ? 0 : 1]);
        },
    );

    it("snaps a reconnect without replaying it and restores every hidden tile", async () => {
        const dealt = table(true);
        await show(drawn(dealt), { mode: "reset", sequence: 0 });
        await show(discardDraw(dealt), { mode: "step", sequence: 1 });
        expect(hiddenTiles()).toBe(1);
        await show(discardDraw(dealt), { mode: "reset", sequence: 2 });
        expect([
            animations.length,
            hiddenTiles(),
            animations.every((animation) => animation.playState === "idle"),
        ]).toEqual([3, 0, true]);
    });

    it("cancels a flight on replay jumps or viewpoint changes and starts no new flights", async () => {
        const dealt = table(true);
        await show(drawn(dealt), { mode: "step", sequence: 0 });
        await show(discardDraw(dealt), { mode: "step", sequence: 1 });
        expect(animations.length).toBe(3);
        draw(drawn(dealt), { mode: "step", sequence: 8 });
        await show(
            discardDraw(dealt),
            { mode: "step", sequence: 9 },
            { view: { bottomSeat: 1, reveal: "all" } },
        );
        expect([animations.length, hiddenTiles()]).toEqual([3, 0]);
    });

    it("cancels every flight when its board unmounts", async () => {
        await show(drawn(table(true)), { mode: "reset", sequence: 0 });
        await show(discardDraw(table(true)), { mode: "step", sequence: 1 });
        expect(animations.length).toBe(3);
        render(nothing, host);
        expect(animations.every((animation) => animation.playState === "idle")).toBe(true);
        expect(host.querySelector(".board-motion")).toBeNull();
    });

    it("shows the destination immediately without reading a tile when reduced motion is requested", async () => {
        const media = matchMedia("(prefers-reduced-motion: reduce)");
        vi.spyOn(media, "matches", "get").mockReturnValue(true);
        vi.spyOn(window, "matchMedia").mockReturnValue(media);
        await show(drawn(table(true)), { mode: "reset", sequence: 0 });
        vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockClear();
        await show(discardDraw(table(true)), { mode: "step", sequence: 1 });
        expect([animations.length, hiddenTiles(), tileBoxReads()]).toEqual([0, 0, 0]);
    });
});

async function showHeldDraw(): Promise<TableState> {
    const view = { view: bottomOnly };
    const dealt = table(true);
    await show(drawn(dealt), { mode: "reset", sequence: 0 }, view);
    await show(discardDraw(dealt), { mode: "step", sequence: 1 }, view);
    const after = opponentDrew(discardDraw(dealt));
    await show(after, { mode: "step", sequence: 2 }, view);
    return after;
}

function heldTile(): Element | null {
    return host.querySelector("[data-area='right-hand'] .hand-drawn-gap > .tile");
}

function targetOf(animation: Animation | undefined): Element | null | undefined {
    return animation?.effect instanceof KeyframeEffect ? animation.effect.target : undefined;
}

function indicatorShift(animation: Animation | undefined): readonly unknown[] {
    const [start] = animation === undefined ? [] : getAnimationFrames(animation);
    return [targetOf(animation), start?.left, start?.top, start?.translate, start?.transform];
}

function measureShiftedIndicator(this: HTMLElement): DOMRect {
    if (!this.matches(".board-dora__tile > .tile")) {
        return getBox(this);
    }
    return new DOMRect(this.classList.contains("tile-back") ? 500 : 510, 100, 30, 40);
}

describe("opponent draw hold", () => {
    it("holds a round's opening draw shown after its deal for the draw hold", async () => {
        const dealt = table(true);
        await show(dealt, { mode: "reset", sequence: 0 }, { view: bottomOnly });
        await show(opponentDrew(dealt), { mode: "step", sequence: 1 }, { view: bottomOnly });
        const hold = animations.at(-1);
        expect([animations.length, targetOf(hold), hold?.effect?.getTiming().duration]).toEqual([
            1,
            heldTile(),
            BOARD_MOTION.drawHold,
        ]);
    });

    it("holds an opponent's draw after a discard through a redraw, ends the hold at the next cue and slides a moved indicator", async () => {
        vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(
            measureShiftedIndicator,
        );
        const after = await showHeldDraw();
        const hold = animations.at(-1);
        expect([animations.length, targetOf(hold)]).toEqual([5, heldTile()]);
        await show(after, { mode: "step", sequence: 2 }, { view: bottomOnly });
        expect([hold?.playState, targetOf(hold)]).toEqual(["paused", heldTile()]);
        await show(
            { ...after, doraIndicators: [24] },
            { mode: "step", sequence: 3 },
            { view: bottomOnly },
        );
        expect([animations.length, hold?.playState]).toEqual([6, "idle"]);
        expect(indicatorShift(animations.at(-1))).toEqual([
            host.querySelector(".board-dora__tile"),
            undefined,
            undefined,
            undefined,
            "translate(-10px, 0px) scale(1)",
        ]);
    });

    it("holds an opponent's draw committed with the discard until the discard lands and the pause passes", async () => {
        vi.spyOn(performance, "now").mockReturnValue(1000);
        const view = { view: bottomOnly };
        const dealt = table(true);
        await show(drawn(dealt), { mode: "reset", sequence: 0 }, view);
        draw(discardDraw(dealt), { mode: "step", sequence: 1 }, view);
        await show(opponentDrew(discardDraw(dealt)), { mode: "step", sequence: 2 }, view);
        const hold = animations.at(-1);
        expect([animations.length, hold?.effect?.getTiming().duration]).toEqual([
            4,
            BOARD_MOTION.landing + BOARD_MOTION.drawHold,
        ]);
    });
});

function anonymousOpponent(state: TableState): TableState {
    return {
        ...state,
        players: state.players.map((player) =>
            player.seat === 1 ? { ...player, concealedCount: 13, tiles: [] } : player,
        ),
    };
}

function opponentTedashi(state: TableState): TableState {
    return {
        ...state,
        lastDiscardSeat: 1,
        players: state.players.map((player) =>
            player.seat === 1
                ? {
                      ...player,
                      concealedCount: player.concealedCount - 1,
                      discards: [
                          ...player.discards,
                          { isRiichi: false, isTsumogiri: false, tileId: 121 },
                      ],
                      drawnConcealed: false,
                  }
                : player,
        ),
    };
}

function movesOpponentHandSlot(animation: Animation): boolean {
    const target = targetOf(animation);
    return target?.matches("[data-area='right-hand'] [data-tile-id]") === true;
}

async function showOpponentTedashi(): Promise<TableState> {
    const view = { view: bottomOnly };
    const dealt = anonymousOpponent(table(true));
    await show(dealt, { mode: "reset", sequence: 0 }, view);
    await show(opponentDrew(dealt), { mode: "step", sequence: 1 }, view);
    const discarded = opponentTedashi(opponentDrew(dealt));
    draw(discarded, { mode: "step", sequence: 2 }, view);
    await Promise.resolve();
    return discarded;
}

function flies(animation: Animation): boolean {
    return targetOf(animation)?.matches(".board-motion > *") === true;
}

function runFrameAt(now: number): void {
    vi.mocked(performance.now).mockReturnValue(now);
    runFrames(1);
}

async function paintThenStartOpponentTedashi() {
    const discarded = await showOpponentTedashi();
    const ghosts = animations.filter(flies);
    const played = [ghosts.map((animation) => animation.startTime), vi.getTimerCount()];
    runFrameAt(1016);
    const painted = [ghosts.map((animation) => animation.startTime), vi.getTimerCount()];
    for (const ghost of ghosts) {
        vi.spyOn(ghost, "play").mockImplementation(() => {});
    }
    runFrameAt(1033);
    return { discarded, ghosts, painted, played };
}

describe("opponent tedashi hole", () => {
    beforeEach(() => {
        vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
        vi.spyOn(performance, "now").mockReturnValue(1000);
    });

    it("starts the discard and arms its hole's close on the frame after the one that first paints them, keeps the hole through another seat's draw and closes it at once when the discarder draws again", async () => {
        const view = { view: bottomOnly };
        const { discarded, ghosts, painted, played } = await paintThenStartOpponentTedashi();
        const closes = animations.filter(movesOpponentHandSlot);
        expect([
            played[1],
            painted,
            ghosts.map((animation) => animation.startTime),
            closes.length > 1,
            closes[0]?.effect?.getTiming().easing,
            vi.getTimerCount(),
        ]).toEqual([
            0,
            played,
            BOARD_MOTION.ghosts.map(() => 1033),
            true,
            BOARD_MOTION.settleEasing,
            1,
        ]);
        const nextDrew = opponentDrew(discarded, 2);
        await show(nextDrew, { mode: "step", sequence: 3 }, view);
        expect([
            closes.filter((animation) => animation.playState === "idle"),
            vi.getTimerCount(),
        ]).toEqual([[], 2]);
        await show(opponentDrew(nextDrew), { mode: "step", sequence: 4 }, view);
        expect([
            closes.every((animation) => animation.playState === "idle"),
            animations.filter(
                (animation) => animation.playState !== "idle" && movesOpponentHandSlot(animation),
            ),
            vi.getTimerCount(),
        ]).toEqual([true, [], 1]);
    });
});

describe("own draw hold", () => {
    it("holds the viewer's draw committed with the left seat's discard until it lands and the own pause passes", async () => {
        vi.spyOn(performance, "now").mockReturnValue(1000);
        const view = { view: bottomOnly };
        const dealt = table(true);
        const discarded: TableState = {
            ...dealt,
            lastDiscardSeat: 3,
            players: dealt.players.map((player) =>
                player.seat === 3
                    ? {
                          ...player,
                          discards: [{ isRiichi: false, isTsumogiri: false, tileId: 100 }],
                          tiles: player.tiles.filter((tileId) => tileId !== 100),
                      }
                    : player,
            ),
        };
        await show(dealt, { mode: "reset", sequence: 0 }, view);
        draw(discarded, { mode: "step", sequence: 1 }, view);
        await show(drawn(discarded), { mode: "step", sequence: 2 }, view);
        const hold = animations.at(-1);
        expect([targetOf(hold), hold?.effect?.getTiming().duration]).toEqual([
            host.querySelector("[data-area='bottom-hand'] .hand-drawn-gap > .tile"),
            BOARD_MOTION.landing + BOARD_MOTION.ownDrawHold,
        ]);
    });
});

describe("animations switch", () => {
    it("cancels a running flight when the animations turn off and reads no tile and starts none while they stay off", async () => {
        await show(drawn(table(true)), { mode: "reset", sequence: 0 });
        await show(discardDraw(table(true)), { mode: "step", sequence: 1 });

        const off = { animationsOn: false };
        await show(discardDraw(table(true)), { mode: "step", sequence: 1 }, off);
        vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockClear();
        await show(drawn(table(true)), { mode: "step", sequence: 2 }, off);

        expect([
            animations.length,
            animations.every((animation) => animation.playState === "idle"),
            hiddenTiles(),
            host.querySelector(".game-board")?.getAttribute("data-motion"),
            tileBoxReads(),
        ]).toEqual([3, true, 0, "off", 0]);
    });
});

function finishGhost(animation: Animation | undefined): number {
    animation?.finish();
    return hiddenTiles();
}

describe("tile flight material", () => {
    it("flies a riichi discard as ghosts already in the sideways river slot's pose, its middle copy turning solid before it lands", () => {
        const player = startRiichiFlight();
        expect(animations).toHaveLength(BOARD_MOTION.ghosts.length);
        expect(flightPoses()).toEqual(
            BOARD_MOTION.ghosts.map(() => ({
                "--motion-across": "48px",
                "--motion-angle": "90deg",
                "--motion-down": `${36 * LYING_Y_SHARE}px`,
                "--motion-height": "48px",
                "--motion-width": "36px",
            })),
        );
        const trail = [
            [0, ["translate"], BOARD_MOTION.discardEasing, undefined],
            [1, ["translate"], "linear", undefined],
        ];
        expect(animations.map(riverCourse)).toEqual([
            trail,
            [
                [0, ["opacity", "translate"], BOARD_MOTION.discardEasing, "0.2"],
                [BOARD_MOTION.discardSolidFrom, ["opacity"], "linear", "0.2"],
                [1, ["opacity", "translate"], "linear", "1"],
            ],
            trail,
        ]);
        expect(host.querySelectorAll(".board-motion__tile > .tile--standing")).toHaveLength(0);
        expect(
            host
                .querySelector(".board-motion__tile > .tile > .tile__body > use")
                ?.getAttribute("href"),
        ).toBe("#body-lying-sideways");
        const [first, middle] = animations;
        expect([finishGhost(first), finishGhost(middle)]).toEqual([1, 0]);
        player.cancel();
    });
});

function ghostCentres(): readonly (readonly string[])[] {
    return [...host.querySelectorAll<HTMLElement>(".board-motion__tile")].map((image) => [
        image.style.left,
        image.style.top,
    ]);
}

function renderLatestRiver(tileIds: readonly number[]): void {
    render(
        html`<div data-area="bottom-hand">
        ${Hand({ tiles: [{ face: "1m", show: "face", tileId: 0 }] })}
      </div>
      <div data-area="bottom-discards">
        ${Discards(tileIds.map((tileId) => ({ face: "3m", last: tileId === 8, tileId })))}
      </div>`,
        host,
    );
}

function returnOf(animation: Animation | undefined): readonly unknown[] {
    const [start, end] = animation ? getAnimationFrames(animation) : [];
    const timing = animation?.effect?.getTiming();
    return [
        translationOf(start?.transform),
        end?.transform,
        timing?.delay,
        timing?.duration,
        timing?.easing,
    ];
}

function gapReturn(): readonly unknown[] {
    return [
        [LATEST_GAP, LATEST_GAP],
        "translate(0px, 0px)",
        0,
        BOARD_MOTION.gapReturn,
        BOARD_MOTION.settleEasing,
    ];
}

describe("latest discard gap", () => {
    it("moves a discard that stays the latest by its grid displacement alone, its gap left to the stylesheet", () => {
        renderLatestRiver([4, 8]);
        const before = snapshotTiles(host);
        renderLatestRiver([8]);
        const after = snapshotTiles(host);
        const player = new BoardMotionPlayer(host);
        player.play(planTileMotion(before, after), before, after);
        expect(
            animations.map((animation) =>
                translationOf(getAnimationFrames(animation)[0].transform),
            ),
        ).toEqual([[32, 0]]);
        player.cancel();
    });

    it("keeps a riichi discard's one flight and gap target when the next draw clears the mark mid-flight, and holds it at the gap until the draw shows", async () => {
        const now = vi.spyOn(performance, "now").mockReturnValue(1000);
        const view = { view: bottomOnly };
        const dealt = table(true);
        await show(drawn(dealt), { mode: "reset", sequence: 0 }, view);
        const riichi = discardDraw(dealt, true);
        await show(riichi, { mode: "step", sequence: 1 }, view);
        const flight = [...animations];
        now.mockReturnValue(1050);
        await show(opponentDrew(riichi), { mode: "step", sequence: 2 }, view);
        expect([
            animations.length,
            flight.map((animation) => animation.playState),
            returnOf(animations[flight.length]),
            animations.at(-1)?.effect?.getTiming().duration,
            ghostCentres(),
            hiddenTiles(),
        ]).toEqual([
            flight.length + 2,
            flight.map(() => "paused"),
            gapReturn(),
            BOARD_MOTION.landing + BOARD_MOTION.drawHold - 50,
            BOARD_MOTION.ghosts.map(() => [`${115 + LATEST_GAP}px`, `${320 + LATEST_GAP}px`]),
            1,
        ]);
    });
});

const PENDING_RETURN_MS = BOARD_MOTION.landing + BOARD_MOTION.drawHold - 50;

function inBottomRiver(element: HTMLElement): boolean {
    return element.closest("[data-area='bottom-discards']") !== null;
}

function riverSlotAnimations(): Animation[] {
    return animations.filter((animation) => {
        const target = targetOf(animation);
        return target instanceof HTMLElement && inBottomRiver(target);
    });
}

async function startPendingReturn(sequence: number): Promise<() => Promise<void>> {
    const now = vi.spyOn(performance, "now").mockReturnValue(1000);
    const view = { view: bottomOnly };
    const riichi = discardDraw(table(true), true);
    await show(drawn(table(true)), { mode: "reset", sequence }, view);
    await show(riichi, { mode: "step", sequence: sequence + 1 }, view);
    now.mockReturnValue(1050);
    const cue = { mode: "step", sequence: sequence + 2 } as const;
    await show(opponentDrew(riichi), cue, view);
    return () => show(opponentDrew(riichi), cue, view);
}

async function cancelledReturnStates(): Promise<readonly (AnimationPlayState | undefined)[]> {
    await startPendingReturn(3);
    const pending = riverSlotAnimations().at(-1);
    const waiting = pending?.playState;
    render(nothing, host);
    vi.advanceTimersByTime(PENDING_RETURN_MS + 1);
    return [waiting, pending?.playState];
}

describe("delayed slot release", () => {
    beforeEach(() => {
        vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
        recordAnimations((element) => !inBottomRiver(element));
    });

    it("holds a delayed return paused at its start until its deadline, starts the same animation through a redraw at the timeline's time of release, and never releases one cancelled", async () => {
        const redraw = await startPendingReturn(0);
        const [pending] = riverSlotAnimations();
        const waiting = [
            pending?.effect?.getTiming().delay,
            pending?.currentTime,
            pending?.playState,
        ];
        vi.advanceTimersByTime(PENDING_RETURN_MS - 1);
        await redraw();
        const beforeDeadline = pending?.playState;
        vi.spyOn(pending!, "play").mockImplementation(() => {});
        vi.mocked(performance.now).mockReturnValue(1050 + PENDING_RETURN_MS);
        vi.advanceTimersByTime(1);
        expect([
            waiting,
            beforeDeadline,
            riverSlotAnimations(),
            [pending?.startTime, document.timeline.currentTime],
            await cancelledReturnStates(),
        ]).toEqual([
            [0, 0, "paused"],
            "paused",
            [pending],
            [1050 + PENDING_RETURN_MS, 1050 + PENDING_RETURN_MS],
            ["paused", "idle"],
        ]);
    });
});

function renderOwnPon(called: boolean, last: boolean): void {
    const pair: readonly HandTile[] = [
        { face: "3p", show: "face", state: "selectable", tileId: 10 },
        { face: "3p", show: "face", state: "selectable", tileId: 11 },
    ];
    const pon = Meld(
        [
            { face: "3p", kind: "sideways", tileId: 9 },
            { face: "3p", kind: "upright", tileId: 10 },
            { face: "3p", kind: "upright", tileId: 11 },
        ],
        { turn: 0 },
    );
    render(
        html`<div class="board-local">
        <div data-area="bottom-hand">
          ${Hand({ standing: true, tiles: called ? [] : pair })}
        </div>
        <div data-area="bottom-melds">${called ? pon : nothing}</div>
      </div>
      <div data-area="left-discards">
        ${Discards(called ? [] : [{ face: "3p", last, tileId: 9 }])}
      </div>`,
        host,
    );
}

const OWN_MELD_TILE_W = 36;

function measureLyingTile(this: HTMLElement): DOMRect {
    if (!this.classList.contains("tile")) {
        return getBox(this);
    }
    if (this.closest("[data-area='bottom-melds']") !== null) {
        const lyingWidth = LYING_Y_SHARE * OWN_MELD_TILE_W;
        return this.parentElement?.classList.contains("meld-tile-sideways") === true
            ? new DOMRect(100, 600, (OWN_MELD_TILE_W * 4) / 3, lyingWidth)
            : new DOMRect(150, 600, OWN_MELD_TILE_W, (lyingWidth * 4) / 3);
    }
    return measureFlightTile.call(this);
}

function startOwnPon(): BoardMotionPlayer {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(measureLyingTile);
    renderOwnPon(false, true);
    const before = snapshotTiles(host);
    renderOwnPon(true, false);
    const after = snapshotTiles(host);
    const player = new BoardMotionPlayer(host);
    player.play(planTileMotion(before, after), before, after);
    return player;
}

describe("own call flight", () => {
    it("flies a claimed tile from its shown gap and the hand's pair as the meld's own bodies and lands each at its slot's screen size", () => {
        const player = startOwnPon();

        const bodies = [...host.querySelectorAll(".board-motion__tile .tile__body > use")].map(
            (use) => use.getAttribute("href"),
        );
        const lyingWidth = LYING_Y_SHARE * OWN_MELD_TILE_W;
        expect(animations).toHaveLength(3 * BOARD_MOTION.ghosts.length);
        expect(new Set(bodies)).toEqual(new Set(["#body-lying-sideways", "#body-lying"]));
        expect(flightPoses()).toEqual(
            expect.arrayContaining([
                expect.objectContaining({
                    "--motion-across": `${(OWN_MELD_TILE_W * 4) / 3}px`,
                    "--motion-down": `${lyingWidth}px`,
                }),
                expect.objectContaining({
                    "--motion-across": `${OWN_MELD_TILE_W}px`,
                    "--motion-down": `${(lyingWidth * 4) / 3}px`,
                }),
            ]),
        );
        expect(getAnimationFrames(animations[0])[0].translate).toBe(
            `${LATEST_GAP}px ${300 + LATEST_GAP + (36 * LYING_Y_SHARE) / 2 - 600 - lyingWidth / 2}px`,
        );
        player.cancel();
    });
});

describe("side river flight", () => {
    it("flies a discard onto a side river at its slot's screen box from take-off", () => {
        vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(
            function measureSideRiver(this: HTMLElement) {
                if (this.matches("[data-area='left-discards'] .tile")) {
                    return new DOMRect(300, 300, 60, 31);
                }
                return measureFlightTile.call(this);
            },
        );
        renderSideDiscard(false);
        const before = snapshotTiles(host);
        renderSideDiscard(true);
        const after = snapshotTiles(host);
        const player = new BoardMotionPlayer(host);
        player.play(planTileMotion(before, after), before, after);

        expect(flightPoses()).toEqual(
            BOARD_MOTION.ghosts.map(() =>
                expect.objectContaining({
                    "--motion-across": "60px",
                    "--motion-down": "31px",
                }),
            ),
        );
        player.cancel();
    });
});

describe("side hand depth", () => {
    it.each(["left", "right"] as const)(
        "moves the %s hand in its rotated frame on translate alone, leaving the lift's transform free",
        (seat) => {
            const { player } = movingHand(seat);
            const [start, end] = getAnimationFrames(animations[0]);
            expect(animations).toHaveLength(2);
            expect([hiddenTiles(), host.querySelector(".board-motion")]).toEqual([0, null]);
            expect([start.left, start.top, start.transform]).toEqual([
                undefined,
                undefined,
                undefined,
            ]);
            const [across, down] = String(start.translate).split(" ").map(Number.parseFloat);
            expect([across, down]).toEqual([
                expect.closeTo(0),
                expect.closeTo(seat === "left" ? -32 : 32),
            ]);
            expect(end.translate).toBe("0px 0px");
            player.cancel();
        },
    );
});

describe("side hand ends", () => {
    it.each([
        { parted: ["0"], seat: "left" },
        { parted: ["8"], seat: "right" },
    ] as const)(
        "shows the $seat hand's end only on the tile whose cover slides away from it",
        ({ parted, seat }) => {
            const player = discardSecondOfFour(seat);
            const marked = [...host.querySelectorAll<HTMLElement>(".hand-tile--parted")];
            expect(marked.map((slot) => slot.dataset.tileId)).toEqual(parted);
            finishAll();
            expect(host.querySelectorAll(".hand-tile--parted")).toHaveLength(0);
            player.cancel();
        },
    );
});

function translationOf(transform: unknown): readonly number[] {
    const match = /translate\((?<x>[^,]+)px, (?<y>[^)]+)px\)/u.exec(String(transform));
    return [Number(match?.groups?.x), Number(match?.groups?.y)];
}

describe("settling river depth", () => {
    it("slides the latest discard home from its gap at once when its mark ends after the draw hold", async () => {
        const now = vi.spyOn(performance, "now").mockReturnValue(1000);
        const dealt = table(true);
        await show(drawn(dealt), { mode: "reset", sequence: 0 });
        const discarded = discardDraw(dealt);
        await show(discarded, { mode: "step", sequence: 1 });
        finishAll();
        now.mockReturnValue(1000 + BOARD_MOTION.landing + BOARD_MOTION.drawHold + 500);
        await show(opponentDrew(discarded), { mode: "step", sequence: 2 });
        const slot = host.querySelector(".discard-tile[data-tile-id='120']");
        expect(returnOf(animations.findLast((animation) => targetOf(animation) === slot))).toEqual(
            gapReturn(),
        );
    });
});

describe("replay motion", () => {
    const tiles = [
        { face: "1m", show: "face", tileId: 0 },
        { face: "2m", show: "face", tileId: 4 },
        { face: "3m", show: "face", tileId: 8 },
    ] as const satisfies readonly HandTile[];

    it("settles the previous hand before measuring the next move", async () => {
        await showMovingHand(tiles, 0, "replay");
        await showMovingHand(tiles.toReversed(), 1, "replay");
        expect([animations.length, host.querySelectorAll(".hand-tile--parted").length]).toEqual([
            2, 2,
        ]);
        await showMovingHand(tiles, 2, "replay");
        expect(animations.map((animation) => animation.playState)).toEqual([
            "idle",
            "idle",
            "paused",
            "paused",
        ]);
        expect(getAnimationFrames(animations[2])[0].translate).toBe("64px 0px");
        expect([hiddenTiles(), host.querySelector(".board-motion")]).toEqual([0, null]);
        animations.forEach((animation) => {
            animation.finish();
        });
        await Promise.resolve();
        expect(host.querySelectorAll(".hand-tile--parted")).toHaveLength(0);
    });

    it("unmarks its parted slots on cancel though a moving slot's tile was replaced", async () => {
        await showMovingHand(tiles, 0, "replay");
        await showMovingHand(tiles.toReversed(), 1, "replay");
        const slot = host.querySelector(".hand-tile");
        host.querySelector(".hand-tile > .tile")?.replaceWith(document.createElement("span"));
        const marked = slot?.classList.contains("hand-tile--parted");
        render(nothing, host);
        expect([marked, slot?.classList.contains("hand-tile--parted")]).toEqual([true, false]);
    });

    it("animates only the newest move when replay steps share a render task", async () => {
        await showMovingHand(tiles, 0, "replay");
        const pending = showMovingHand(tiles.toReversed(), 1, "replay");
        await showMovingHand([tiles[1], tiles[2], tiles[0]], 2, "replay");
        await pending;
        expect(animations).toHaveLength(2);
        expect(getAnimationFrames(animations[0])[0].translate).toBe("32px 0px");
    });
});
