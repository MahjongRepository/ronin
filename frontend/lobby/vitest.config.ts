import { resolve } from "path";

import { defineConfig } from "vitest/config";

export default defineConfig({
    resolve: {
        alias: {
            "@": resolve(import.meta.dirname, "src"),
            "@ronin/shared": resolve(import.meta.dirname, "../shared/src"),
        },
        dedupe: ["lit-html"],
    },
    test: {
        coverage: {
            exclude: ["src/**/*.test.ts"],
            include: ["src/**/*.ts"],
            provider: "v8",
        },
        environment: "happy-dom",
        include: ["src/**/*.test.ts"],
    },
});
