import { type TemplateResult, render } from "lit-html";

/** Undo a route's mount: cancel its timers, IO and listeners. */
export type Unmount = () => void;

export interface MountedView {
    readonly rerender: () => void;
    readonly unmount: Unmount;
}

export type Mount = (
    host: HTMLElement,
    params: Record<string, string>,
    url: URL,
) => Unmount | MountedView;

export interface Route {
    readonly pattern: RegExp;
    readonly mount: Mount;
}

export interface NavigateOptions {
    readonly replace?: boolean;
}

export interface Router {
    readonly navigate: (url: string, options?: NavigateOptions) => void;
    readonly rerender: () => void;
}

/** A mount that renders a template once and owns nothing to undo. */
export function staticMount(view: () => TemplateResult): Mount {
    return (host) => {
        render(view(), host);
        return () => {};
    };
}

function asMountedView(mounted: Unmount | MountedView): MountedView {
    return typeof mounted === "function" ? { rerender: () => {}, unmount: mounted } : mounted;
}

/**
 * A route whose mount loads with its module on first use, so its code and styles ship in a chunk of their own. An
 * unmount before the load settles drops it. A load that fails or a mount that throws, either way, says so on the page
 * and on the console, unless the route was unmounted meanwhile.
 */
export function lazyRoute(
    pattern: RegExp,
    load: () => Promise<Mount>,
    failed: () => TemplateResult,
): Route {
    return {
        mount(host, params, url) {
            let mounted: MountedView | null = null;
            let disposed = false;
            async function mountLoaded(): Promise<void> {
                const mount = await load();
                if (!disposed) {
                    mounted = asMountedView(mount(host, params, url));
                }
            }
            mountLoaded().catch((error: unknown) => {
                if (disposed) {
                    return;
                }
                const detail = error instanceof Error ? error.message : String(error);
                console.error(`Route failed to load: ${detail}`);
                render(failed(), host);
            });
            return {
                rerender: () => mounted?.rerender(),
                unmount: () => {
                    disposed = true;
                    mounted?.unmount();
                },
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

function isRegisteredUrl(routes: readonly Route[], url: URL): boolean {
    return url.origin === window.location.origin && matchRoute(routes, url.pathname) !== undefined;
}

function moveInPlace(target: URL, replace: boolean): void {
    if (replace || target.href === window.location.href) {
        history.replaceState(null, "", target.href);
    } else {
        history.pushState(null, "", target.href);
    }
    window.scrollTo(0, 0);
}

/**
 * Mount the route matching the location into `host`, unmounting the previous one first, and again on every
 * history navigation; a path no route matches goes to `onUnmatched`.
 */
export function startRouter(
    host: HTMLElement,
    routes: readonly Route[],
    onUnmatched: () => void,
): Router {
    let mounted: MountedView | null = null;

    function resolve(): void {
        mounted?.unmount();
        mounted = null;
        const matched = matchRoute(routes, window.location.pathname);
        if (!matched) {
            onUnmatched();
            return;
        }
        const url = new URL(window.location.href);
        mounted = asMountedView(matched.route.mount(host, matched.params, url));
    }

    function navigate(url: string, options: NavigateOptions = {}): void {
        const target = new URL(url, window.location.href);
        if (!isRegisteredUrl(routes, target)) {
            if (options.replace) {
                window.location.replace(target.href);
            } else {
                window.location.assign(target.href);
            }
            return;
        }
        moveInPlace(target, options.replace ?? false);
        resolve();
    }

    window.addEventListener("popstate", resolve);
    resolve();
    return { navigate, rerender: () => mounted?.rerender() };
}

function isPlainLeftClick(event: MouseEvent): boolean {
    const modified = event.altKey || event.ctrlKey || event.metaKey || event.shiftKey;
    return !event.defaultPrevented && event.button === 0 && !modified;
}

function clickedLink(event: MouseEvent): HTMLAnchorElement | null {
    const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
    return link instanceof HTMLAnchorElement ? link : null;
}

function opensInPlace(link: HTMLAnchorElement): boolean {
    const fragmentOnly = link.getAttribute("href")?.startsWith("#") ?? false;
    const target = link.target.toLowerCase();
    const inSameWindow = target === "" || target === "_self";
    return inSameWindow && !link.hasAttribute("download") && !fragmentOnly;
}

function interceptedUrl(event: MouseEvent, routes: readonly Route[]): URL | null {
    const link = isPlainLeftClick(event) ? clickedLink(event) : null;
    if (link === null || !opensInPlace(link)) {
        return null;
    }
    const url = new URL(link.href);
    return isRegisteredUrl(routes, url) ? url : null;
}

export function interceptLinks(
    router: Router,
    routes: readonly Route[],
    root: Document | Element = document,
): void {
    root.addEventListener("click", (event) => {
        if (!(event instanceof MouseEvent)) {
            return;
        }
        const url = interceptedUrl(event, routes);
        if (url === null) {
            return;
        }
        event.preventDefault();
        router.navigate(url.href);
    });
}
