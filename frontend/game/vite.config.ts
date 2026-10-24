import { resolve } from "path";
import { defineConfig } from "vite";

const port = parseInt(process.env.GAME_VITE_PORT || "5174", 10);

export default defineConfig({
    base: "/game-assets/",
    resolve: {
        alias: {
            "@": resolve(__dirname, "src"),
        },
    },
    publicDir: false,
    build: {
        outDir: "dist",
        emptyOutDir: true,
    },
    css: {
        preprocessorOptions: {
            scss: {
                loadPaths: ["node_modules"],
                quietDeps: true,
            },
        },
    },
    server: {
        port,
        strictPort: true,
        hmr: { clientPort: port },
    },
});
