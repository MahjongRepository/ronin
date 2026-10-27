import { resolve } from "path";

import { defineConfig } from "vitest/config";

export default defineConfig({
    resolve: {
        alias: {
            "@": resolve(__dirname, "src"),
        },
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
