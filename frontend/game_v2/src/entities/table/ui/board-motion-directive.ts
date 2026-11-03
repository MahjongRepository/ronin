import { nothing } from "lit-html";
import { AsyncDirective } from "lit-html/async-directive.js";
import { type ElementPart, type PartInfo, PartType, directive } from "lit-html/directive.js";

import { planTileMotion } from "@/entities/table/lib/board-motion";
import { type BoardDisplayState, type BoardMotionCue } from "@/entities/table/model/board-types";

import { BoardMotionPlayer } from "./board-motion-player";
import { type TileSnapshot, snapshotTiles } from "./board-motion-snapshot";

interface PendingMotion {
    readonly before: readonly TileSnapshot[];
    readonly enabled: boolean;
}

class AnimateBoard extends AsyncDirective {
    private board: HTMLElement | null = null;
    private state: BoardDisplayState | null = null;
    private cue: BoardMotionCue | undefined;
    private queued: PendingMotion | null = null;
    private player: BoardMotionPlayer | null = null;
    private media: MediaQueryList | null = null;
    private observer: ResizeObserver | null = null;
    private size = "";
    private renderVersion = 0;

    constructor(info: PartInfo) {
        super(info);
        if (info.type !== PartType.ELEMENT) {
            throw new Error("animateBoard belongs on an element");
        }
    }

    render(_state: BoardDisplayState | null, _cue?: BoardMotionCue): typeof nothing {
        return nothing;
    }

    override update(
        part: ElementPart,
        [state, cue]: [BoardDisplayState | null, BoardMotionCue | undefined],
    ): typeof nothing {
        if (!(part.element instanceof HTMLElement)) {
            return nothing;
        }
        this.board = part.element;
        this.player ??= new BoardMotionPlayer(part.element);
        this.player.prepareRender();
        this.updateState(state, cue);
        this.finishRender();
        return nothing;
    }

    private finishRender(): void {
        const version = ++this.renderVersion;
        queueMicrotask(() => {
            if (
                version === this.renderVersion &&
                this.isConnected &&
                this.board?.isConnected === true
            ) {
                this.player?.finishRender();
            }
        });
    }

    private updateState(state: BoardDisplayState | null, cue: BoardMotionCue | undefined): void {
        const previous = { cue: this.cue, state: this.state };
        this.state = state;
        this.cue = cue;
        if (
            previous.state?.motionContext !== state?.motionContext ||
            previous.cue?.sequence !== cue?.sequence ||
            previous.cue?.mode !== cue?.mode
        ) {
            this.schedule(previous.state, previous.cue);
        }
    }

    private schedule(
        previous: BoardDisplayState | null,
        priorCue: BoardMotionCue | undefined,
    ): void {
        const { board, cue, state } = this;
        const enabled =
            state !== null &&
            previous !== null &&
            (cue?.mode === "step" || cue?.mode === "replay") &&
            priorCue !== undefined &&
            cue.sequence === priorCue.sequence + 1 &&
            previous.motionContext === state.motionContext &&
            previous.motionRound === state.motionRound;
        if (!enabled || cue?.mode === "replay") {
            this.cancel();
        }
        const priorFrame =
            enabled && cue?.mode === "step" && this.queued?.enabled === true ? this.queued : null;
        const before =
            priorFrame?.before ?? (enabled && board !== null ? snapshotTiles(board) : []);
        const frame = { before, enabled };
        this.queued = frame;
        queueMicrotask(() => this.commit(frame));
    }

    private commit(frame: PendingMotion): void {
        if (frame !== this.queued || !this.isConnected || this.board?.isConnected !== true) {
            return;
        }
        this.queued = null;
        this.animate(frame);
    }

    private animate({ before, enabled }: PendingMotion): void {
        if (this.board === null) {
            return;
        }
        this.observe();
        if (
            !enabled ||
            this.state === null ||
            this.media?.matches === true ||
            typeof this.board.animate !== "function"
        ) {
            return;
        }
        const after = snapshotTiles(this.board);
        this.player?.play(planTileMotion(before, after, this.cue?.mode), before, after);
    }

    private observe(): void {
        if (this.media === null && typeof matchMedia === "function") {
            this.media = matchMedia("(prefers-reduced-motion: reduce)");
            this.media.addEventListener("change", this.cancel);
        }
        if (
            this.observer !== null ||
            this.board === null ||
            typeof ResizeObserver === "undefined"
        ) {
            return;
        }
        const box = this.board.getBoundingClientRect();
        this.size = `${box.width}:${box.height}`;
        this.observer = new ResizeObserver((entries) => {
            const rect = entries.at(-1)?.contentRect;
            if (rect === undefined) {
                return;
            }
            const next = `${rect.width}:${rect.height}`;
            if (this.size !== next) {
                this.size = next;
                this.cancel();
            }
        });
        this.observer.observe(this.board);
    }

    private readonly cancel = (): void => {
        this.player?.cancel();
    };

    protected override disconnected(): void {
        this.queued = null;
        this.cancel();
        this.observer?.disconnect();
        this.observer = null;
        this.media?.removeEventListener("change", this.cancel);
        this.media = null;
        this.cue = undefined;
    }
}

export const animateBoard = directive(AnimateBoard);
