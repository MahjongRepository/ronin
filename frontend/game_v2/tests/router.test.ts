import { describe, expect, it, vi } from "vitest";

import { type Route, lazyRoute, startRouter } from "@/router";

const PATTERN = /^\/lazy$/;

describe("lazyRoute", () => {
    it("drops a mount whose route was unmounted before its module loaded", async () => {
        const mount = vi.fn(() => () => {});
        const loaded = Promise.resolve(mount);
        const route = lazyRoute(PATTERN, () => loaded);

        const unmount = route.mount(document.createElement("div"), {});
        unmount();
        await loaded;

        expect(mount).not.toHaveBeenCalled();
    });

    it("says on the page and the console that a module failed to load or its mount threw", async () => {
        const error = vi.spyOn(console, "error").mockImplementation(() => {});
        const failed = Promise.reject(new Error("chunk 404"));
        const throwing = Promise.resolve(() => {
            throw new Error("mount broke");
        });
        const hosts = [document.createElement("div"), document.createElement("div")];

        lazyRoute(PATTERN, () => failed).mount(hosts[0], {});
        lazyRoute(PATTERN, () => throwing).mount(hosts[1], {});
        await vi.waitFor(() => expect(error).toHaveBeenCalledTimes(2));

        expect(hosts.map((host) => host.querySelector(".route-error")?.textContent)).toEqual([
            "This page failed to load.",
            "This page failed to load.",
        ]);
        error.mockRestore();
    });
});

describe("startRouter", () => {
    it("hands a route its parameters decoded, and treats a path that does not decode as unmatched", () => {
        const mount = vi.fn<Route["mount"]>(() => () => {});
        const unmatched = vi.fn();
        const routes = [{ mount, pattern: /^\/play\/(?<gameId>[^/]+)$/ }];

        for (const path of ["/play/g%202", "/play/%E0%A4%A"]) {
            history.replaceState(null, "", path);
            startRouter(document.createElement("div"), routes, unmatched);
        }

        expect(mount.mock.calls.map(([, params]) => params)).toEqual([{ gameId: "g 2" }]);
        expect(unmatched).toHaveBeenCalledOnce();
    });
});
