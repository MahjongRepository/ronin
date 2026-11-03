import { type TemplateResult, html } from "lit-html";

interface StorybookPage {
    path: string;
    title: string;
}

const STORYBOOK_INDEX = "/play/storybook";

const STORYBOOK_PAGES: StorybookPage[] = [
    { path: STORYBOOK_INDEX, title: "Index" },
    { path: "/play/storybook/board", title: "Board" },
    { path: "/play/storybook/decisions", title: "Decisions" },
    { path: "/play/storybook/discards", title: "Discards" },
    { path: "/play/storybook/hand", title: "Hand" },
    { path: "/play/storybook/melds", title: "Melds" },
    { path: "/play/storybook/replay", title: "Replay" },
    { path: "/play/storybook/rotate", title: "Rotate" },
    { path: "/play/storybook/sounds", title: "Sounds" },
];

/**
 * A storybook page's link (a path, with its own query or none) carrying the current page's client version (`v` of
 * `search`), so a link from the v2 storybook stays on it; no other parameter of the current page carries over.
 */
function storybookHref(target: string, search: string): string {
    const version = new URLSearchParams(search).get("v");
    if (version === null) {
        return target;
    }
    const url = new URL(target, window.location.origin);
    url.searchParams.set("v", version);
    return `${url.pathname}${url.search}${url.hash}`;
}

/** The storybook index's link from the current page, for a story's Back button. */
function storybookIndexHref(): string {
    return storybookHref(STORYBOOK_INDEX, window.location.search);
}

/** Renders the storybook header with a row of badge links.
 * The badge matching `currentPath` gets the `active` class. */
function storybookNav(currentPath: string): TemplateResult {
    const { search } = window.location;
    return html`
        <h1>Game Storybook</h1>
        <nav class="storybook-nav">
            ${STORYBOOK_PAGES.map((page) => {
                const cls =
                    page.path === currentPath ? "storybook-badge active" : "storybook-badge";
                const href = storybookHref(page.path, search);
                return html`<a href="${href}" class="${cls}">${page.title}</a>`;
            })}
        </nav>
    `;
}

export { storybookHref, storybookIndexHref, storybookNav, STORYBOOK_PAGES };
