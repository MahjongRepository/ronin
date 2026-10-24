import { defineConfig } from "vite";

const port = parseInt(process.env.GAME_VITE_PORT || "5174", 10);

export default defineConfig({
    base: "/game-assets/",
    build: {
        outDir: "dist",
        emptyOutDir: true,
    },
    server: {
        port,
        strictPort: true,
        hmr: { clientPort: port },
    },
    test: {
        include: ["src/**/*.test.js"],
        environment: "happy-dom",
    },
});
