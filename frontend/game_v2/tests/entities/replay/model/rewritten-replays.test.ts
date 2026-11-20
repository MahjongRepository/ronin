import { assert, describe, expect, test } from "vitest";

import { readReplay } from "@/entities/replay";
import { decodeReplayRecords } from "@/entities/table/model/replay-codec";

const REWRITTEN_DIR = "../../../../../../backend/game_v2/internal/wire/testdata/rewritten/";

const REWRITTEN_FILES = import.meta.glob(
    "../../../../../../backend/game_v2/internal/wire/testdata/rewritten/*.msgpack",
    { eager: true, import: "default", query: "?inline" },
);

const REWRITTEN: readonly (readonly [string, Uint8Array])[] = Object.entries(REWRITTEN_FILES).map(
    ([path, text]) => [
        path.slice(REWRITTEN_DIR.length, -".msgpack".length),
        Uint8Array.from(atob(String(text).split(",")[1]), (character) => character.charCodeAt(0)),
    ],
);

describe("a replay rewritten from replay version 0.4-dev", () => {
    test("is found among the committed rewrites", () => {
        expect(REWRITTEN.map(([name]) => name)).toContain("chankan_added");
    });

    test.each(REWRITTEN)("%s reads whole, every record a step", (_name, content) => {
        const read = readReplay(content);

        assert(read.ok);
        expect(read.replay.damage).toBeNull();
        expect(read.replay.events).toHaveLength([...decodeReplayRecords(content)].length - 1);
    });
});
