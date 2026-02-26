import { resolve } from "path";
import { defineConfig } from "vite";

export default defineConfig(({ command }) => ({
    // Production: assets served at /game-assets/ by Starlette StaticFiles.
    // Dev: Vite serves from its own root.
    base: command === "build" ? "/game-assets/" : "/",
    publicDir: false, // Python backend serves frontend/public/ at /static/ separately
    build: {
        manifest: true,
        outDir: "dist",
        emptyOutDir: true,
        rollupOptions: {
            input: {
                game: resolve(__dirname, "src/index.ts"),
                lobby: resolve(__dirname, "src/lobby/index.ts"),
            },
        },
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
        port: parseInt(process.env.VITE_PORT || "5173", 10),
        // CSS injected via <style> tags (Vite HMR) resolves url() against the
        // document origin, not the Vite dev server.  Setting origin ensures all
        // asset URLs use absolute paths like http://localhost:5173/src/assets/...
        // so they resolve correctly even when the page is served from a different
        // port (the Python backend on 8710).
        origin: `http://localhost:${process.env.VITE_PORT || "5173"}`,
        strictPort: true,
        cors: true,
    },
}));
