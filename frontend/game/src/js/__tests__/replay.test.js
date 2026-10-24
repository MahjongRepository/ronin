import { afterEach, describe, expect, it, vi } from "vitest";

import { showReplay } from "../replay.js";

function stubFetch(response) {
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
}

describe("showReplay", () => {
    afterEach(() => vi.unstubAllGlobals());

    it("fetches the replay by game id and shows its raw text", async () => {
        const fetchMock = stubFetch(new Response('{"version":"1"}\n{"t":8}'));
        const root = document.createElement("main");

        await showReplay(root, "g 1");

        expect(fetchMock).toHaveBeenCalledWith("/api/replays/g%201");
        expect(root.querySelector(".replay-content").textContent).toBe('{"version":"1"}\n{"t":8}');
        expect(root.querySelector(".replay-status")).toBeNull();
    });

    it("tells a missing replay apart from a failed load", async () => {
        const root = document.createElement("main");

        stubFetch(new Response("", { status: 404 }));
        await showReplay(root, "g-1");
        expect(root.querySelector(".replay-status").textContent).toBe("Replay not found");

        stubFetch(new Response("", { status: 500 }));
        await showReplay(root, "g-1");
        expect(root.querySelector(".replay-status").textContent).toBe(
            "Failed to load replay (500)",
        );
    });
});
