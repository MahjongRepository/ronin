import { resolve } from "path";

import { deprecations } from "sass";
import { defineConfig } from "vite";

const activeSassDeprecations = Object.values(deprecations).filter((d) => d.status === "active");

export default defineConfig(({ command }) => ({
    base: command === "build" ? "/lobby-assets/" : "/",
    build: {
        emptyOutDir: true,
        manifest: true,
        outDir: "dist",
        rollupOptions: {
            input: {
                lobby: resolve(__dirname, "src/index.ts"),
            },
        },
    },
    css: {
        preprocessorOptions: {
            scss: {
                fatalDeprecations: activeSassDeprecations,
                loadPaths: ["node_modules"],
                quietDeps: true,
            },
        },
    },
    publicDir: false,
    resolve: {
        alias: {
            "@": resolve(__dirname, "src"),
        },
    },
    server: {
        cors: true,
        origin: `http://localhost:${process.env.VITE_PORT || "5173"}`,
        port: parseInt(process.env.VITE_PORT || "5173", 10),
        strictPort: true,
    },
}));
