/**
 * Build the lobby CSS and TypeScript with content-hashed filenames.
 *
 * Compiles SCSS via sass, hashes the output, writes to dist/ as lobby-{hash}.css.
 * Builds lobby TypeScript via Bun.build, writes to dist/ as lobby-{hash}.js.
 * Adds "lobby_css" and "lobby_js" entries to the existing dist/manifest.json.
 */

import { readFileSync, renameSync, writeFileSync } from "fs";

const tmpFile = "dist/_lobby.css";

// Compile sass to a temporary file
const sass = Bun.spawnSync(
    ["bunx", "sass", "--load-path=node_modules", "src/styles/lobby-app.scss", tmpFile, "--no-source-map", "--style=compressed"],
    { stderr: "inherit" },
);

if (sass.exitCode !== 0) {
    console.error("Sass compilation failed");
    process.exit(1);
}

// Content-hash the CSS output and rename
const css = readFileSync(tmpFile);
const cssHasher = new Bun.CryptoHasher("md5");
cssHasher.update(css);
const cssHash = cssHasher.digest("hex").slice(0, 8);
const cssFilename = `lobby-${cssHash}.css`;

renameSync(tmpFile, `dist/${cssFilename}`);
console.log(`Built lobby CSS: ${cssFilename}`);

// Build lobby TypeScript
const tsResult = await Bun.build({
    entrypoints: ["./src/lobby/index.ts"],
    outdir: "dist",
    naming: "lobby-[hash].[ext]",
    minify: true,
    define: {
        "process.env.NODE_ENV": JSON.stringify("production"),
    },
});

if (!tsResult.success) {
    console.error("TypeScript build failed:");
    for (const log of tsResult.logs) {
        console.error(log);
    }
    process.exit(1);
}

const jsOutput = tsResult.outputs.find((o) => o.path.endsWith(".js"));
if (!jsOutput) {
    console.error("No .js output found from lobby TypeScript build");
    process.exit(1);
}

const jsFilename = jsOutput.path.split("/").pop()!;
console.log(`Built lobby JS: ${jsFilename}`);

// Update the manifest with lobby CSS and JS entries
const manifest = JSON.parse(readFileSync("dist/manifest.json", "utf-8"));
manifest.lobby_css = cssFilename;
manifest.lobby_js = jsFilename;
writeFileSync("dist/manifest.json", JSON.stringify(manifest));
