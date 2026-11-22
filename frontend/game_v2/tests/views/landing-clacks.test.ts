import { describe, expect, it } from "vitest";

import { ManualClock, steadyClockOn } from "#tests/fixtures/clock";
import { type SoundCue } from "@/entities/client";
import { DISCARD_LANDING_MS, DRAW_HOLD_MS } from "@/entities/table";
import { LandingClacks } from "@/views/landing-clacks";

function heardBy(
    clock: ManualClock,
    played: readonly SoundCue[],
    times: readonly number[],
): readonly SoundCue[][] {
    return times.map((at) => {
        clock.advanceTo(at);
        return [...played];
    });
}

describe("LandingClacks", () => {
    it.each([
        [true, DISCARD_LANDING_MS],
        [false, 0],
    ])(
        "ticks a draw that follows a discard only once the hold after its clack passes (clack at landing: %s)",
        (atLanding, clackAt) => {
            const clock = new ManualClock();
            const played: SoundCue[] = [];
            const clacks = new LandingClacks(steadyClockOn(clock), {
                play: (cue) => played.push(cue),
                setting: { load: () => ({ sound_on: true }), save: () => {} },
            });

            clacks.play(["discard"], atLanding);
            clacks.play(["draw"], atLanding);

            expect(
                heardBy(clock, played, [
                    clackAt,
                    clackAt + DRAW_HOLD_MS - 1,
                    clackAt + DRAW_HOLD_MS,
                ]),
            ).toEqual([["discard"], ["discard"], ["discard", "draw"]]);
        },
    );
});
