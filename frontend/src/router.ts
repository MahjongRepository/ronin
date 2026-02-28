import { type TemplateResult, render } from "lit-html";
import { getLobbyUrl } from "@/env";

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
    window.addEventListener("popstate", () => resolve());
    resolve();
}

export function navigate(path: string): void {
    history.pushState(null, "", path);
    resolve();
}

function resolve(): void {
    if (!container) {
        return;
    }
    const path = window.location.pathname;
    const matched = findMatchingRoute(path);
    runRouteCleanup();
    if (matched) {
        activeRoute = matched.route;
        render(matched.route.handler(matched.params), container);
    } else {
        activeRoute = null;
        window.location.replace(getLobbyUrl());
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
