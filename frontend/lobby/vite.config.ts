import { resolve } from "path";

import { deprecations } from "sass";
import { defineConfig } from "vite";

const activeSassDeprecations = Object.values(deprecations).filter((d) => d.status === "active");

export default defineConfig(({ command }) => ({
    base: command === "build" ? "/lobby-assets/" : "/",
    resolve: {
        alias: {
            "@": resolve(__dirname, "src"),
        },
    },
    publicDir: false,
    build: {
        manifest: true,
        outDir: "dist",
        emptyOutDir: true,
        rollupOptions: {
            input: {
                lobby: resolve(__dirname, "src/index.ts"),
            },
        },
    },
    css: {
        preprocessorOptions: {
            scss: {
                loadPaths: ["node_modules"],
                quietDeps: true,
                fatalDeprecations: activeSassDeprecations,
            },
        },
    },
    server: {
        port: parseInt(process.env.VITE_PORT || "5173", 10),
        origin: `http://localhost:${process.env.VITE_PORT || "5173"}`,
        strictPort: true,
        cors: true,
    },
}));
