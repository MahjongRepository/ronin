import { fetchPageHtml } from "@/api";

const NOTICE_SELECTOR = "[data-browser-notice]";

function serverContent(main: Element): Node[] {
    return [...main.childNodes].filter(
        (node) => !(node instanceof Element && node.matches(NOTICE_SELECTOR)),
    );
}

function swapContent(main: HTMLElement, page: Document): boolean {
    const fetchedMain = page.querySelector("main");
    if (fetchedMain === null) {
        return false;
    }
    const notice = main.querySelector(NOTICE_SELECTOR);
    const content = serverContent(fetchedMain).map((node) => document.importNode(node, true));
    main.replaceChildren(...(notice ? [notice] : []), ...content);
    document.title = page.title;
    return true;
}

export function startLegalSwap(main: HTMLElement): () => void {
    let latestSwap = 0;

    async function swap(swapId: number): Promise<void> {
        const text = await fetchPageHtml(window.location.href);
        if (text === null || swapId !== latestSwap) {
            return;
        }
        const page = new DOMParser().parseFromString(text, "text/html");
        if (!swapContent(main, page)) {
            console.error("legal page refetch held no main content");
        }
    }

    return () => {
        latestSwap += 1;
        void swap(latestSwap);
    };
}
