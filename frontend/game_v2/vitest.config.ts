import { resolve } from "path";

import { defineConfig } from "vitest/config";

export default defineConfig({
    resolve: {
        alias: {
            "@": resolve(import.meta.dirname, "src"),
        },
    },
    test: {
        coverage: {
            include: ["src/**/*.ts"],
            provider: "v8",
        },
        environment: "happy-dom",
        include: ["tests/**/*.test.ts"],
    },
});
