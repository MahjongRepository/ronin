import { describe, expect, it, onTestFinished, vi } from "vitest";

import { type SoundOutput, createSoundPlayer } from "@/shared/lib";

/** An output whose loads wait until the test settles them and whose starts fail with `errors` in turn, then succeed. */
function fakeOutput(errors: readonly Error[]): {
    readonly output: SoundOutput<string>;
    readonly loads: Map<string, { resolve: () => void; reject: (error: Error) => void }>;
    readonly started: (readonly [string, number])[];
} {
    const loads = new Map<string, { resolve: () => void; reject: (error: Error) => void }>();
    const started: (readonly [string, number])[] = [];
    let starts = 0;
    const output: SoundOutput<string> = {
        load: (url) =>
            new Promise((resolve, reject) => {
                loads.set(url, { reject, resolve: () => resolve(`clip:${url}`) });
            }),
        start: (clip, volume) => {
            started.push([clip, volume]);
            const error = errors[starts++];
            return error === undefined ? Promise.resolve() : Promise.reject(error);
        },
    };
    return { loads, output, started };
}

/** Run `act`, then let every promise it settled run its handlers. */
async function settleLoads(act: () => void): Promise<void> {
    act();
    await new Promise((resolve) => {
        setTimeout(resolve, 0);
    });
}

const SOURCES = { gong: { url: "/gong.wav", volume: 1 }, ron: { url: "/ron.wav", volume: 0.2 } };

describe("createSoundPlayer", () => {
    it("starts every play of a loaded sound at its volume, skips one still loading or blocked before the first gesture, and reports any other failure", async () => {
        const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
        onTestFinished(() => consoleError.mockRestore());
        const [loadFailure, startFailure] = [new Error("404"), new DOMException("x", "AbortError")];
        const { loads, output, started } = fakeOutput([
            new DOMException("no gesture", "NotAllowedError"),
            startFailure,
        ]);
        const player = createSoundPlayer(SOURCES, output);

        player.play("ron");
        await settleLoads(() => {
            loads.get("/ron.wav")?.resolve();
            loads.get("/gong.wav")?.reject(loadFailure);
        });
        await settleLoads(() => (["ron", "ron", "ron", "gong"] as const).forEach(player.play));

        expect([started, consoleError.mock.calls]).toEqual([
            [
                ["clip:/ron.wav", 0.2],
                ["clip:/ron.wav", 0.2],
                ["clip:/ron.wav", 0.2],
            ],
            [
                ['The sound "gong" failed to load:', loadFailure],
                ['The sound "ron" failed to play:', startFailure],
            ],
        ]);
    });
});
