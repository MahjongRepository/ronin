import { describe, expect, test } from "vitest";

import { ManualClock } from "#tests/fixtures/clock";
import { createThrottledWriter } from "@/shared/lib";

function writerOn(clock: ManualClock): {
    written: string[];
    writer: ReturnType<typeof createThrottledWriter<string>>;
} {
    const written: string[] = [];
    return {
        writer: createThrottledWriter(clock, 500, (value: string) => written.push(value)),
        written,
    };
}

describe("createThrottledWriter", () => {
    test("writes at once, then the latest value given within the interval once it passes", () => {
        const clock = new ManualClock();
        const { writer, written } = writerOn(clock);

        writer.write("a");
        clock.advanceTo(100);
        writer.write("b");
        writer.write("c");
        clock.advanceTo(499);
        expect(written).toEqual(["a"]);

        clock.advanceTo(500);
        expect(written).toEqual(["a", "c"]);
    });

    test("writes a waiting value on flush, and nothing after cancel", () => {
        const clock = new ManualClock();
        const { writer, written } = writerOn(clock);
        writer.write("a");
        writer.write("b");

        writer.flush();
        writer.write("c");
        writer.cancel();
        clock.advanceTo(10_000);
        writer.write("d");

        expect(written).toEqual(["a", "b"]);
    });
});
