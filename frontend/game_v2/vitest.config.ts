import { resolve } from "path";

import { defineConfig } from "vitest/config";

export default defineConfig({
    assetsInclude: ["**/*.msgpack"],
    resolve: {
        alias: {
            "@": resolve(import.meta.dirname, "src"),
            "@ronin/shared": resolve(import.meta.dirname, "../shared/src"),
        },
        dedupe: ["lit-html"],
    },
    server: {
        fs: {
            allow: [
                resolve(import.meta.dirname, ".."),
                resolve(import.meta.dirname, "../../backend/game_v2/internal/wire/testdata"),
            ],
        },
    },
    test: {
        coverage: {
            include: ["src/**/*.ts"],
            provider: "v8",
        },
        environment: "happy-dom",
        include: ["tests/**/*.test.ts"],
        setupFiles: ["./src/zod-setup.ts"],
    },
});
