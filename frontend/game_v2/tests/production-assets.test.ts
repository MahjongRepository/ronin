import { build } from "vite";
import { describe, expect, it } from "vitest";

import { createProductionAssetCheck } from "#scripts/production-assets";

const ENTRY = "/src/index.ts";
const REPLAY = "/src/replay-entry.ts";
const SHARED = "/src/shared.ts";
const STORYBOOK = "/src/views/storybook.ts";

interface BuildFixture {
    readonly modules: Readonly<Record<string, string>>;
    readonly css?: string;
    readonly mode?: string;
}

async function buildFixture({ modules, css, mode = "production" }: BuildFixture): Promise<void> {
    await build({
        build: { rolldownOptions: { input: ENTRY }, write: false },
        configFile: false,
        logLevel: "silent",
        mode,
        plugins: [
            {
                enforce: "pre",
                generateBundle() {
                    if (css !== undefined) {
                        this.emitFile({ fileName: "assets/style.css", source: css, type: "asset" });
                    }
                },
                load: (id) => modules[id] ?? null,
                name: "build-fixture",
                resolveId: (id) => (Object.hasOwn(modules, id) ? id : null),
            },
            createProductionAssetCheck(),
        ],
        publicDir: false,
    });
}

describe("production assets", () => {
    it("rejects storybook modules even behind a dynamic import", async () => {
        await expect(
            buildFixture({
                modules: {
                    [ENTRY]: `void import("${STORYBOOK}");`,
                    [STORYBOOK]: 'console.info("development page");',
                },
            }),
        ).rejects.toThrow("Development modules");
    });

    it("rejects storybook styles emitted by another plugin", async () => {
        await expect(
            buildFixture({
                css: ".storybook-nav { display: flex; }",
                modules: { [ENTRY]: 'console.info("app");' },
            }),
        ).rejects.toThrow("Development content");
    });

    it("rejects development markup left in application code", async () => {
        await expect(
            buildFixture({ modules: { [ENTRY]: 'console.info("game-board--debug");' } }),
        ).rejects.toThrow("Development content");
    });

    it("rejects replay modules reached through a shared static dependency", async () => {
        await expect(
            buildFixture({
                modules: {
                    [ENTRY]: `import "${SHARED}";`,
                    [REPLAY]: 'console.info("replay");',
                    [SHARED]: `import "${REPLAY}";`,
                },
            }),
        ).rejects.toThrow("Eager replay modules");
    });

    it("allows replay modules behind a dynamic import", async () => {
        await expect(
            buildFixture({
                modules: {
                    [ENTRY]: `void import("${REPLAY}");`,
                    [REPLAY]: 'console.info("replay");',
                },
            }),
        ).resolves.toBeUndefined();
    });

    it("keeps storybook available in development builds", async () => {
        await expect(
            buildFixture({
                css: ".storybook-nav { display: flex; }",
                mode: "development",
                modules: {
                    [ENTRY]: `import "${STORYBOOK}";`,
                    [STORYBOOK]: 'console.info("storybook");',
                },
            }),
        ).resolves.toBeUndefined();
    });
});
