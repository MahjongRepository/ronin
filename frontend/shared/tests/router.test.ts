import { type Route, interceptLinks, lazyRoute, startRouter } from "@ronin/shared/router";
import { type TemplateResult, html, render } from "lit-html";
import { afterEach, describe, expect, it, vi } from "vitest";

const PATTERN = /^\/lazy$/;

function failedView(): TemplateResult {
    return html`<p class="route-error">Failed.</p>`;
}

function linksRoot(): HTMLElement {
    const root = document.createElement("div");
    render(
        html`<a href="/rooms/1"><span>Jade Crane</span></a><a href="/rooms/2" target="replay">Replay</a>`,
        root,
    );
    return root;
}

function clickRecordingIntercepts(root: HTMLElement, selectors: readonly string[]): boolean[] {
    const intercepted: boolean[] = [];
    root.addEventListener("click", (event) => {
        intercepted.push(event.defaultPrevented);
        event.preventDefault();
    });
    for (const selector of selectors) {
        root.querySelector(selector)?.dispatchEvent(
            new MouseEvent("click", { bubbles: true, button: 0, cancelable: true }),
        );
    }
    return intercepted;
}

afterEach(() => {
    vi.restoreAllMocks();
    history.replaceState(null, "", "/");
});

describe("lazyRoute", () => {
    it("drops a mount whose route was unmounted before its module loaded", async () => {
        const mount = vi.fn(() => () => {});
        const loaded = Promise.resolve(mount);
        const route = lazyRoute(PATTERN, () => loaded, failedView);

        const mounted = route.mount(document.createElement("div"), {}, new URL(location.href));
        if (typeof mounted === "function") {
            mounted();
        } else {
            mounted.unmount();
        }
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
        const url = new URL(location.href);

        lazyRoute(PATTERN, () => failed, failedView).mount(hosts[0], {}, url);
        lazyRoute(PATTERN, () => throwing, failedView).mount(hosts[1], {}, url);
        await vi.waitFor(() => expect(error).toHaveBeenCalledTimes(2));

        expect(hosts.map((host) => host.querySelector(".route-error")?.textContent)).toEqual([
            "Failed.",
            "Failed.",
        ]);
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

    it("leaves for an unregistered path with a document navigation", () => {
        const assign = vi.spyOn(window.location, "assign").mockImplementation(() => {});
        const replace = vi.spyOn(window.location, "replace").mockImplementation(() => {});
        history.replaceState(null, "", "/history");
        const routes = [{ mount: vi.fn(() => () => {}), pattern: /^\/history$/ }];
        const router = startRouter(document.createElement("div"), routes, vi.fn());

        router.navigate("/terms");
        router.navigate("/privacy", { replace: true });

        expect(assign).toHaveBeenCalledExactlyOnceWith(`${location.origin}/terms`);
        expect(replace).toHaveBeenCalledExactlyOnceWith(`${location.origin}/privacy`);
        expect(location.pathname).toBe("/history");
    });

    it("remounts the route on a navigation that changes only the query", () => {
        const unmount = vi.fn();
        const mount = vi.fn<Route["mount"]>(() => unmount);
        history.replaceState(null, "", "/admin/monitoring");
        const router = startRouter(
            document.createElement("div"),
            [{ mount, pattern: /^\/admin\/monitoring$/ }],
            vi.fn(),
        );

        router.navigate("/admin/monitoring?range=7d");

        expect(unmount).toHaveBeenCalledOnce();
        expect(mount.mock.calls.map((call) => call[2].search)).toEqual(["", "?range=7d"]);
    });

    it("redraws the mounted view in place on rerender", () => {
        const view = { rerender: vi.fn(), unmount: vi.fn() };
        const mount = vi.fn<Route["mount"]>(() => view);
        history.replaceState(null, "", "/settings");
        const router = startRouter(
            document.createElement("div"),
            [{ mount, pattern: /^\/settings$/ }],
            vi.fn(),
        );

        router.rerender();

        expect(view.rerender).toHaveBeenCalledOnce();
        expect(view.unmount).not.toHaveBeenCalled();
        expect(mount).toHaveBeenCalledOnce();
    });
});

describe("interceptLinks", () => {
    it("navigates in place on a plain click inside a registered link and leaves a named-target link to the browser", () => {
        history.replaceState(null, "", "/");
        const mount = vi.fn<Route["mount"]>(() => () => {});
        const routes = [{ mount, pattern: /^\/(?:rooms\/\d+)?$/ }];
        const root = linksRoot();
        interceptLinks(startRouter(document.createElement("div"), routes, vi.fn()), routes, root);

        expect(clickRecordingIntercepts(root, ["span", "[target]"])).toEqual([true, false]);
        expect(location.pathname).toBe("/rooms/1");
        expect(mount).toHaveBeenCalledTimes(2);
    });
});
