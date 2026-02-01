import { type TemplateResult, render } from "lit-html";

interface Route {
    pattern: RegExp;
    handler: (params: Record<string, string>) => TemplateResult;
    cleanup?: () => void;
}

let routes: Route[] = [];
let container: HTMLElement | undefined = undefined;
let activeRoute: Route | null = null;

export function initRouter(el: HTMLElement, routeDefs: Route[]): void {
    container = el;
    routes = routeDefs;
    window.addEventListener("hashchange", () => resolve());
    resolve();
}

export function navigate(hash: string): void {
    window.location.hash = hash;
}

function resolve(): void {
    if (!container) {
        return;
    }
    const hash = window.location.hash.slice(1) || "/";
    const matched = findMatchingRoute(hash);
    runRouteCleanup();
    if (matched) {
        activeRoute = matched.route;
        render(matched.route.handler(matched.params), container);
    } else {
        activeRoute = null;
        navigate("/");
    }
}

function findMatchingRoute(
    hash: string,
): { params: Record<string, string>; route: Route } | undefined {
    for (const route of routes) {
        const match = hash.match(route.pattern);
        if (match) {
            const params: Record<string, string> = {};
            if (match.groups) {
                Object.assign(params, match.groups);
            }
            return { params, route };
        }
    }
    return undefined;
}

function runRouteCleanup(): void {
    if (activeRoute?.cleanup) {
        activeRoute.cleanup();
    }
}
