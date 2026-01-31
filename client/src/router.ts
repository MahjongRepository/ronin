import { render, TemplateResult } from "lit-html";

interface Route {
    pattern: RegExp;
    handler: (params: Record<string, string>) => TemplateResult;
    cleanup?: () => void;
}

let routes: Route[] = [];
let container: HTMLElement;
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
    const hash = window.location.hash.slice(1) || "/";
    for (const route of routes) {
        const match = hash.match(route.pattern);
        if (match) {
            // run cleanup for the previous route before rendering
            if (activeRoute && activeRoute.cleanup) {
                activeRoute.cleanup();
            }
            activeRoute = route;

            const params: Record<string, string> = {};
            if (match.groups) {
                Object.assign(params, match.groups);
            }
            render(route.handler(params), container);
            return;
        }
    }
    // fallback: run cleanup before redirecting to lobby
    if (activeRoute && activeRoute.cleanup) {
        activeRoute.cleanup();
    }
    activeRoute = null;
    navigate("/");
}
