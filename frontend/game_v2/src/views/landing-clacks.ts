import { type GameSound, type SoundCue } from "@/entities/client";
import { DISCARD_LANDING_MS, DRAW_HOLD_MS } from "@/entities/table";
import { type CancelTimer, type Clock } from "@/shared/clock";

interface PendingCues {
    readonly cancel: CancelTimer;
    readonly lead: SoundCue;
    readonly cues: Set<SoundCue>;
}

export class LandingClacks {
    private readonly clock: Clock;
    private readonly sound: GameSound;
    private pending: readonly PendingCues[] = [];
    private clackAt: number | null = null;

    constructor(clock: Clock, sound: GameSound) {
        this.clock = clock;
        this.sound = sound;
    }

    /** Play a step's cues, its draw's tick as its tile shows: the draw hold after the latest clack. */
    play(cues: readonly SoundCue[], clackAtLanding: boolean): void {
        for (const cue of cues) {
            const landing = this.pending.findLast((pending) => pending.lead === "discard");
            if (cue === "discard") {
                this.clack(clackAtLanding);
            } else if (cue === "draw") {
                this.drawAfterClack();
            } else if (cue === "decision" && landing !== undefined) {
                landing.cues.add(cue);
            } else {
                this.sound.play(cue);
            }
        }
    }

    cancelDecision(): void {
        for (const pending of this.pending) {
            pending.cues.delete("decision");
        }
    }

    landNow(): void {
        const landings = this.pending.filter((pending) => pending.lead === "discard");
        if (landings.length === 0) {
            return;
        }
        const waiting = this.pending.filter((pending) => pending.lead !== "discard");
        this.cancel();
        this.clackAt = this.clock.now();
        for (const landing of landings) {
            landing.cues.forEach(this.sound.play);
        }
        for (const pending of waiting) {
            pending.cues.forEach((cue) => this.playLater(DRAW_HOLD_MS, cue));
        }
    }

    cancel(): void {
        for (const pending of this.pending) {
            pending.cancel();
        }
        this.pending = [];
        this.clackAt = null;
    }

    private clack(atLanding: boolean): void {
        if (!atLanding) {
            this.clackAt = this.clock.now();
            this.sound.play("discard");
            return;
        }
        this.clackAt = this.clock.now() + DISCARD_LANDING_MS;
        this.playLater(DISCARD_LANDING_MS, "discard");
    }

    private drawAfterClack(): void {
        const wait = this.clackAt === null ? 0 : this.clackAt + DRAW_HOLD_MS - this.clock.now();
        if (wait > 0) {
            this.playLater(wait, "draw");
        } else {
            this.sound.play("draw");
        }
    }

    private playLater(delayMs: number, cue: SoundCue): void {
        const cues = new Set([cue]);
        const pending: PendingCues = {
            cancel: this.clock.setTimer(delayMs, () => {
                this.pending = this.pending.filter((other) => other !== pending);
                cues.forEach(this.sound.play);
            }),
            cues,
            lead: cue,
        };
        this.pending = [...this.pending, pending];
    }
}
