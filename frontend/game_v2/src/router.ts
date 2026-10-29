import { type TemplateResult, render } from "lit-html";

/** Undo a route's mount: cancel its timers, IO and listeners. */
export type Unmount = () => void;

export interface Route {
    readonly pattern: RegExp;
    readonly mount: (host: HTMLElement, params: Record<string, string>) => Unmount;
}

/** A route that renders a template once and owns nothing to undo. */
export function staticRoute(pattern: RegExp, view: () => TemplateResult): Route {
    return {
        mount(host) {
            render(view(), host);
            return () => {};
        },
        pattern,
    };
}

function matchRoute(
    routes: readonly Route[],
    path: string,
): { params: Record<string, string>; route: Route } | undefined {
    for (const route of routes) {
        const match = path.match(route.pattern);
        if (match) {
            return { params: { ...match.groups }, route };
        }
    }
    return undefined;
}

/**
 * Mount the route matching the location into `host`, unmounting the previous one first, and again on every
 * history navigation; a path no route matches goes to `onUnmatched`.
 */
export function startRouter(
    host: HTMLElement,
    routes: readonly Route[],
    onUnmatched: () => void,
): void {
    let unmount: Unmount | null = null;

    function resolve(): void {
        unmount?.();
        unmount = null;
        const matched = matchRoute(routes, window.location.pathname);
        if (!matched) {
            onUnmatched();
            return;
        }
        unmount = matched.route.mount(host, matched.params);
    }

    window.addEventListener("popstate", resolve);
    resolve();
}
