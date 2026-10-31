import { afterEach, describe, expect, it, vi } from "vitest";

import { localStore } from "@/shared/lib";

const KEY = "ronin.v2.test-store";

function countStore(): ReturnType<typeof localStore<number>> {
    return localStore(KEY, (stored) => (typeof stored === "number" ? stored : -1), 0);
}

afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
});

describe("localStore", () => {
    it("reads back what it saved through its reader, and gives the fallback for nothing stored or no JSON", () => {
        const store = countStore();
        const empty = store.load();
        store.save(3);
        const saved = store.load();
        localStorage.setItem(KEY, "{broken");

        expect([empty, saved, store.load()]).toEqual([0, 3, 0]);
    });

    it("gives the fallback and keeps nothing where storage is blocked", () => {
        vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
            throw new DOMException("blocked", "SecurityError");
        });
        const store = countStore();

        expect(() => store.save(3)).not.toThrow();
        expect(store.load()).toBe(0);
    });
});
