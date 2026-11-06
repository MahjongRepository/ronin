import { describe, expect, it, vi } from "vitest";

import { webAudioOutput } from "@/shared/lib";

class FakeAudioContext {
    state: AudioContextState = "suspended";
    resume(): Promise<void> {
        this.state = "running";
        return Promise.resolve();
    }
}

describe("webAudioOutput", () => {
    it("unlocks in a browser without navigator.userActivation, and waits for the first gesture in one that tracks it", async () => {
        vi.stubGlobal("OfflineAudioContext", vi.fn());
        vi.stubGlobal("AudioContext", FakeAudioContext);

        const untracked = await webAudioOutput(undefined).unlock();
        const beforeGesture = await webAudioOutput({
            hasBeenActive: false,
            isActive: false,
        }).unlock();

        expect([untracked, beforeGesture]).toEqual([true, false]);
    });
});
