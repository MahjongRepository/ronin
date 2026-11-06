import { describe, expect, it } from "vitest";

import { unlockOnGesture } from "@/shared/lib";

describe("unlockOnGesture", () => {
    it("tries inside each gesture until one unlocks, then no more, so a touch's pointerdown leaves its touchend to try", async () => {
        const target = new EventTarget();
        const answers = [false, true];
        const tried: string[] = [];
        let current = "";
        unlockOnGesture(target, async () => {
            tried.push(current);
            return answers.shift() ?? true;
        });

        async function gesture(type: string): Promise<void> {
            current = type;
            target.dispatchEvent(new Event(type));
            await Promise.resolve();
        }
        await gesture("pointerdown");
        await gesture("touchend");
        await gesture("keydown");

        expect(tried).toEqual(["pointerdown", "touchend"]);
    });
});
