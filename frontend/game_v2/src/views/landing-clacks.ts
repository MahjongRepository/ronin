import { type GameSound, type SoundCue } from "@/entities/client";
import { DISCARD_LANDING_MS } from "@/entities/table";
import { type CancelTimer, type Clock } from "@/shared/clock";

interface PendingLanding {
    readonly cancel: CancelTimer;
    readonly cues: SoundCue[];
}

export class LandingClacks {
    private readonly clock: Clock;
    private readonly sound: GameSound;
    private pending: readonly PendingLanding[] = [];

    constructor(clock: Clock, sound: GameSound) {
        this.clock = clock;
        this.sound = sound;
    }

    play(cues: readonly SoundCue[], clackAtLanding: boolean): void {
        for (const cue of cues) {
            const landing = this.pending.at(-1);
            if (clackAtLanding && cue === "discard") {
                this.clackAtLanding();
            } else if (cue === "decision" && landing !== undefined) {
                landing.cues.push(cue);
            } else {
                this.sound.play(cue);
            }
        }
    }

    landNow(): void {
        const landings = this.pending;
        this.cancel();
        for (const landing of landings) {
            landing.cues.forEach(this.sound.play);
        }
    }

    cancel(): void {
        for (const landing of this.pending) {
            landing.cancel();
        }
        this.pending = [];
    }

    private clackAtLanding(): void {
        const cues: SoundCue[] = ["discard"];
        const landing: PendingLanding = {
            cancel: this.clock.setTimer(DISCARD_LANDING_MS, () => {
                this.pending = this.pending.filter((pending) => pending !== landing);
                cues.forEach(this.sound.play);
            }),
            cues,
        };
        this.pending = [...this.pending, landing];
    }
}
