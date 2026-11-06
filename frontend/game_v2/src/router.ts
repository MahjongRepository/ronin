import { type TemplateResult, html, render } from "lit-html";

import { t } from "@/shared/i18n";

/** Undo a route's mount: cancel its timers, IO and listeners. */
export type Unmount = () => void;

export interface Route {
    readonly pattern: RegExp;
    readonly mount: (host: HTMLElement, params: Record<string, string>) => Unmount;
}

type Mount = Route["mount"];

/** A mount that renders a template once and owns nothing to undo. */
export function staticMount(view: () => TemplateResult): Mount {
    return (host) => {
        render(view(), host);
        return () => {};
    };
}

/**
 * A route whose mount loads with its module on first use, so its code and styles ship in a chunk of their own. An
 * unmount before the load settles drops it. A load that fails or a mount that throws, either way, says so on the page
 * and on the console, unless the route was unmounted meanwhile.
 */
export function lazyRoute(pattern: RegExp, load: () => Promise<Mount>): Route {
    return {
        mount(host, params) {
            let unmount: Unmount | null = null;
            let disposed = false;
            async function mountLoaded(): Promise<void> {
                const mount = await load();
                if (!disposed) {
                    unmount = mount(host, params);
                }
            }
            mountLoaded().catch((error: unknown) => {
                if (disposed) {
                    return;
                }
                const detail = error instanceof Error ? error.message : String(error);
                console.error(`Route failed to load: ${detail}`);
                render(html`<p class="route-error">${t("common.page_failed")}</p>`, host);
            });
            return () => {
                disposed = true;
                unmount?.();
            };
        },
        pattern,
    };
}

/** A route's parameters as the path carries them percent-encoded, decoded; null for one that does not decode. */
function decodeParams(groups: Record<string, string> | undefined): Record<string, string> | null {
    try {
        return Object.fromEntries(
            Object.entries(groups ?? {}).map(([name, value]) => [name, decodeURIComponent(value)]),
        );
    } catch (error: unknown) {
        if (error instanceof URIError) {
            return null;
        }
        throw error;
    }
}

/** The first route matching `path`, with its decoded parameters; none when no route matches or they do not decode. */
function matchRoute(
    routes: readonly Route[],
    path: string,
): { params: Record<string, string>; route: Route } | undefined {
    for (const route of routes) {
        const match = path.match(route.pattern);
        if (match) {
            const params = decodeParams(match.groups);
            return params === null ? undefined : { params, route };
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
