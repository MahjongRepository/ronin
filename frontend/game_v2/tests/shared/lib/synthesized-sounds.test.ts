import { describe, expect, expectTypeOf, it } from "vitest";

import { type SoundSamples, synthesizeDecision } from "@/shared/lib";

describe("synthesized sounds", () => {
    it.each([{ duration: 0.18, name: "decision", synthesize: synthesizeDecision }])(
        "makes a short, audible $name without clipping or abrupt edges",
        ({ synthesize, duration }) => {
            const clip = synthesize();
            expectTypeOf(clip).toEqualTypeOf<SoundSamples>();
            expect(clip.samples.length / clip.sampleRate).toBeCloseTo(duration, 4);
            expect(clip.samples[0]).toBeCloseTo(0, 6);
            expect(clip.samples.at(-1)).toBeCloseTo(0, 6);
            expect(clip.samples.every(Number.isFinite)).toBe(true);
            expect(Math.max(...clip.samples.map(Math.abs))).toBeLessThan(1);
            expect(
                Math.sqrt(
                    clip.samples.reduce((sum, sample) => sum + sample ** 2, 0) /
                        clip.samples.length,
                ),
            ).toBeGreaterThan(0.05);
            expect(
                Math.max(
                    ...clip.samples.slice(1).map((sample, i) => Math.abs(sample - clip.samples[i])),
                ),
            ).toBeLessThan(0.2);
        },
    );
});
