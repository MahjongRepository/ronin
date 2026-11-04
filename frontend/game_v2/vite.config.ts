import { resolve } from "path";

import { deprecations } from "sass";
import { defineConfig } from "vite";

const activeSassDeprecations = Object.values(deprecations).filter((d) => d.status === "active");

const port = parseInt(process.env.GAME_V2_VITE_PORT || "5175", 10);

export default defineConfig({
    appType: "mpa",
    base: "/game-assets/v2/",
    build: {
        emptyOutDir: true,
        outDir: "dist",
    },
    css: {
        preprocessorOptions: {
            scss: {
                fatalDeprecations: activeSassDeprecations,
            },
        },
    },
    publicDir: "legal",
    resolve: {
        alias: {
            "@": resolve(import.meta.dirname, "src"),
        },
    },
    server: {
        hmr: { clientPort: port },
        port,
        strictPort: true,
    },
});
