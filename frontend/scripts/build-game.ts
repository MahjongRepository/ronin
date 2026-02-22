/**
 * Build the game client with content-hashed assets and version metadata.
 *
 * Reads APP_VERSION and GIT_COMMIT from environment variables.
 * Falls back to "dev" / git short SHA for local development.
 */

import { readdirSync, writeFileSync } from "fs";

function gitShortSha(): string {
    const result = Bun.spawnSync(["git", "rev-parse", "--short", "HEAD"], {
        stderr: "ignore",
    });
    return result.stdout.toString().trim() || "dev";
}

const appVersion = process.env.APP_VERSION || "dev";
const gitCommit = process.env.GIT_COMMIT || gitShortSha();

const result = await Bun.build({
    entrypoints: ["./index.html"],
    outdir: "dist",
    minify: true,
    define: {
        "globalThis.APP_VERSION": JSON.stringify(appVersion),
        "globalThis.GIT_COMMIT": JSON.stringify(gitCommit),
        "process.env.NODE_ENV": JSON.stringify("production"),
    },
});

if (!result.success) {
    console.error("Build failed:");
    for (const log of result.logs) {
        console.error(log);
    }
    process.exit(1);
}

// Generate manifest.json mapping logical names to content-hashed filenames
const files = readdirSync("dist");
const jsFiles = files.filter((f) => f.endsWith(".js"));
const cssFiles = files.filter((f) => f.endsWith(".css"));

if (jsFiles.length !== 1) {
    throw new Error(`Expected exactly 1 .js file in dist/, found ${jsFiles.length}: ${jsFiles.join(", ")}`);
}
if (cssFiles.length !== 1) {
    throw new Error(`Expected exactly 1 .css file in dist/, found ${cssFiles.length}: ${cssFiles.join(", ")}`);
}

const manifest = { js: jsFiles[0], css: cssFiles[0] };
writeFileSync("dist/manifest.json", JSON.stringify(manifest));

console.log(`Built game client v${appVersion} (${gitCommit})`);
