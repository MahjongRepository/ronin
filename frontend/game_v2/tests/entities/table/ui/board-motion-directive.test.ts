import { html, nothing, render } from "lit-html";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { tableStateToDisplayState } from "@/entities/table/lib/board-mapper";
import { planTileMotion } from "@/entities/table/lib/board-motion";
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
import { Discards, Hand, type HandTile } from "@/entities/tile";

let host = document.createElement("div");
let animations: Animation[] = [];
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

function draw(state: TableState, cue: BoardMotionCue, view = perspective): void {
    render(
        GameBoard({
            debug: false,
            motion: cue,
            platePress: { kind: "pin", onPin: () => {}, pinned: null },
            state: tableStateToDisplayState(state, view),
        }),
        host,
    );
}

function getBox(element: HTMLElement): DOMRect {
    if (element.classList.contains("game-board")) {
        return DOMRect.fromRect({ height: 800, width: 1200 });
    }
    const area = element.closest<HTMLElement>("[data-area]")?.dataset.area ?? "";
    const siblings = element.parentElement?.parentElement?.querySelectorAll("[data-tile-id]") ?? [];
    const index = [...siblings].indexOf(element.parentElement!);
    return new DOMRect(100 + index * 32, area.endsWith("hand") ? 600 : 300, 30, 40);
}

async function show(state: TableState, cue: BoardMotionCue, view = perspective): Promise<void> {
    draw(state, cue, view);
    await Promise.resolve();
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

function hiddenTiles(): number {
    return host.querySelectorAll(".tile[style*='hidden']").length;
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

function flyingHand() {
    const onTile = vi.fn();
    const tiles = [{ face: "1m", show: "face", state: "selectable", tileId: 0 }] as const;
    renderHand(tiles, onTile);
    const before = snapshotTiles(host);
    render(
        html`<div data-area="bottom-hand">${Hand({ drawnTile: { face: "2m", show: "face", state: "selectable", tileId: 4 }, onTile, tiles })}</div>`,
        host,
    );
    const after = snapshotTiles(host);
    const player = new BoardMotionPlayer(host);
    player.play(planTileMotion(before, after), before, after);
    return { onTile, player, target: after[1] };
}

async function showMovingHand(
    tiles: readonly HandTile[],
    sequence: number,
    mode: BoardMotionCue["mode"] = "step",
): Promise<void> {
    const state = tableStateToDisplayState(table(true), perspective);
    render(
        html`<div class="game-board" ${animateBoard(state, { mode, sequence })}>
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
    const tiles: readonly HandTile[] = discarded
        ? []
        : [{ face: "1m", show: "face", state: "selectable", tileId: 0 }];
    render(
        html`<div class="board-local" data-area="bottom-hand">${Hand({ tiles })}</div>
        <div data-area="bottom-discards">${Discards(discarded ? [{ face: "1m", riichi: true, tileId: 0 }] : [])}</div>`,
        host,
    );
}

function measureFlightTile(this: HTMLElement): DOMRect {
    if (!this.classList.contains("tile")) {
        return getBox(this);
    }
    return this.closest("[data-area='bottom-hand']") === null
        ? new DOMRect(100, 300, 48, 36)
        : new DOMRect(100, 600, 48, 64);
}

async function showPanel(matchResult: boolean, afterCall: boolean): Promise<void> {
    render(
        GameBoard({
            debug: false,
            matchResult,
            overlay: html`<p>${matchResult ? "Standings" : "Win result"}</p>`,
            overlayAfterCall: afterCall,
            platePress: { kind: "pin", onPin: () => {}, pinned: null },
            state: null,
        }),
        host,
    );
    await Promise.resolve();
}

beforeEach(() => {
    host = document.createElement("div");
    document.body.append(host);
    animations = [];
    const { animate } = HTMLElement.prototype;
    vi.spyOn(HTMLElement.prototype, "animate").mockImplementation(function animatePaused(
        this: HTMLElement,
        frames,
        options,
    ) {
        const animation = animate.call(this, frames, options);
        void animation.finished.catch((error: unknown) => {
            expect(error).toMatchObject({ name: "AbortError" });
        });
        animation.pause();
        animations.push(animation);
        return animation;
    });
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
            leaving?.classList.contains("board-overlay--after-call"),
            host
                .querySelector(".board-overlay:not(.board-overlay--leaving)")
                ?.classList.contains("board-overlay--after-call"),
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

    it("blocks moving tile taps when an overlay makes the table inert", () => {
        const { onTile, player, target } = flyingHand();
        expect(target.image.isConnected).toBe(true);
        host.setAttribute("inert", "");
        target.image.click();
        expect(onTile).not.toHaveBeenCalled();
        player.cancel();
    });

    it("shows starting hands immediately and animates the following draw without a deal delay", async () => {
        await show(table(false), { mode: "reset", sequence: 0 });
        const dealt = table(true);
        await show(dealt, { mode: "step", sequence: 1 });
        expect([animations.length, hiddenTiles()]).toEqual([0, 0]);
        await show(drawn(dealt), { mode: "step", sequence: 2 });
        expect([animations.length, hiddenTiles()]).toEqual([4, 1]);
        expect(animations[0].effect?.getTiming().delay).toBe(0);
    });

    it("shows a deal and first draw rendered in the same task immediately", async () => {
        await show(table(false), { mode: "reset", sequence: 0 });
        const dealt = table(true);
        draw(dealt, { mode: "step", sequence: 1 });
        await show(drawn(dealt), { mode: "step", sequence: 2 });
        expect([animations.length, hiddenTiles()]).toEqual([0, 0]);
        finishAll();
        expect(hiddenTiles()).toBe(0);
    });

    it("clears old flights and shows a new round immediately even when it reuses tile ids", async () => {
        const dealt = table(true);
        await show(dealt, { mode: "reset", sequence: 0 });
        await show(drawn(dealt), { mode: "step", sequence: 1 });
        expect(hiddenTiles()).toBe(1);
        await show({ ...dealt, roundNumber: dealt.roundNumber + 1 }, { mode: "step", sequence: 2 });
        expect([
            hiddenTiles(),
            animations.length,
            animations.every((animation) => animation.playState === "idle"),
        ]).toEqual([0, 4, true]);
    });

    it.each([
        { mode: "step", nextState: "paused" },
        { mode: "replay", nextState: "idle" },
    ] as const)(
        "keeps a draw through redraws and handles the next $mode update",
        async ({ mode, nextState }) => {
            const dealt = table(true);
            await show(dealt, { mode, sequence: 0 });
            const after = drawn(dealt);
            await show(after, { mode, sequence: 1 });
            expect(animations.length).toBe(4);
            await show(after, { mode, sequence: 1 });
            expect(animations.every((animation) => animation.playState === "paused")).toBe(true);
            await show({ ...after, doraIndicators: [24] }, { mode, sequence: 2 });
            expect([
                animations.length,
                animations.every((animation) => animation.playState === nextState),
                hiddenTiles(),
            ]).toEqual([4, true, mode === "replay" ? 0 : 1]);
        },
    );

    it("snaps a reconnect without replaying it and restores every hidden tile", async () => {
        const dealt = table(true);
        await show(dealt, { mode: "reset", sequence: 0 });
        await show(drawn(dealt), { mode: "step", sequence: 1 });
        expect(hiddenTiles()).toBe(1);
        await show(drawn(dealt), { mode: "reset", sequence: 2 });
        expect([
            animations.length,
            hiddenTiles(),
            animations.every((animation) => animation.playState === "idle"),
        ]).toEqual([4, 0, true]);
    });

    it("cancels a flight on replay jumps or viewpoint changes and starts no new flights", async () => {
        const dealt = table(true);
        await show(dealt, { mode: "step", sequence: 0 });
        await show(drawn(dealt), { mode: "step", sequence: 1 });
        expect(animations.length).toBe(4);
        draw(dealt, { mode: "step", sequence: 8 });
        await show(drawn(dealt), { mode: "step", sequence: 9 }, { bottomSeat: 1, reveal: "all" });
        expect([animations.length, hiddenTiles()]).toEqual([4, 0]);
    });

    it("cancels every flight when its board unmounts", async () => {
        await show(table(true), { mode: "reset", sequence: 0 });
        await show(drawn(table(true)), { mode: "step", sequence: 1 });
        expect(animations.length).toBe(4);
        render(nothing, host);
        expect(animations.every((animation) => animation.playState === "idle")).toBe(true);
        expect(host.querySelector(".board-motion")).toBeNull();
    });

    it("shows the destination immediately when reduced motion is requested", async () => {
        const media = matchMedia("(prefers-reduced-motion: reduce)");
        vi.spyOn(media, "matches", "get").mockReturnValue(true);
        vi.spyOn(window, "matchMedia").mockReturnValue(media);
        await show(table(false), { mode: "reset", sequence: 0 });
        await show(table(true), { mode: "step", sequence: 1 });
        expect([animations.length, hiddenTiles()]).toEqual([0, 0]);
    });
});

describe("tile flight material", () => {
    it("starts a riichi discard at hand size and rotates and shrinks it into the sideways river slot", () => {
        vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(
            measureFlightTile,
        );
        renderRiichiFlight(false);
        const before = snapshotTiles(host);
        renderRiichiFlight(true);
        const after = snapshotTiles(host);
        const player = new BoardMotionPlayer(host);
        player.play(planTileMotion(before, after), before, after);
        expect(getAnimationFrames(animations[0])).toMatchObject([
            {
                "--motion-angle": "0deg",
                "--motion-height": "64px",
                "--motion-standing": "1",
                "--motion-width": "48px",
            },
            {
                "--motion-angle": "90deg",
                "--motion-height": "48px",
                "--motion-standing": "0",
                "--motion-width": "36px",
            },
        ]);
        player.cancel();
    });
});

describe("side hand depth", () => {
    it.each(["left", "right"] as const)(
        "moves the %s hand in its rotated frame without lifting seam masks into a stacking context",
        (seat) => {
            const { player } = movingHand(seat);
            const [start, end] = getAnimationFrames(animations[0]);
            expect(animations).toHaveLength(2);
            expect([hiddenTiles(), host.querySelector(".board-motion")]).toEqual([0, null]);
            expect([start.translate, start.transform]).toEqual([undefined, undefined]);
            expect(Number.parseFloat(String(start.left))).toBeCloseTo(0);
            expect(Number.parseFloat(String(start.top))).toBeCloseTo(seat === "left" ? -32 : 32);
            expect(end).toMatchObject({ left: "0px", top: "0px" });
            player.cancel();
        },
    );
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
        expect(animations).toHaveLength(2);
        await showMovingHand(tiles, 2, "replay");
        expect(animations.map((animation) => animation.playState)).toEqual([
            "idle",
            "idle",
            "paused",
            "paused",
        ]);
        expect(getAnimationFrames(animations[2])[0]).toMatchObject({ left: "64px", top: "0px" });
        expect([hiddenTiles(), host.querySelector(".board-motion")]).toEqual([0, null]);
    });

    it("animates only the newest move when replay steps share a render task", async () => {
        await showMovingHand(tiles, 0, "replay");
        const pending = showMovingHand(tiles.toReversed(), 1, "replay");
        await showMovingHand([tiles[1], tiles[2], tiles[0]], 2, "replay");
        await pending;
        expect(animations).toHaveLength(2);
        expect(getAnimationFrames(animations[0])[0]).toMatchObject({ left: "32px", top: "0px" });
    });
});
