import { resolve } from "path";

import { defineConfig } from "vitest/config";

const lobbyDir = import.meta.dirname;
const sharedDir = resolve(lobbyDir, "../shared");

export default defineConfig({
    resolve: {
        alias: {
            "@ronin/shared": resolve(sharedDir, "src"),
        },
        dedupe: ["lit-html", "vitest"],
    },
    root: lobbyDir,
    server: {
        fs: {
            allow: [lobbyDir, sharedDir],
        },
    },
    test: {
        coverage: {
            allowExternal: true,
            include: ["../shared/src/**/*.ts"],
            provider: "v8",
            reportsDirectory: "../shared/coverage",
        },
        environment: "happy-dom",
        include: ["../shared/tests/**/*.test.ts"],
    },
});
