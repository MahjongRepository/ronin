import { deprecations } from "sass";
import { defineConfig } from "vite";

const activeSassDeprecations = Object.values(deprecations).filter((d) => d.status === "active");

const port = parseInt(process.env.GAME_VITE_PORT || "5174", 10);

export default defineConfig({
    base: "/game-assets/",
    appType: "mpa",
    build: {
        outDir: "dist",
        emptyOutDir: true,
    },
    css: {
        preprocessorOptions: {
            scss: {
                fatalDeprecations: activeSassDeprecations,
            },
        },
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
