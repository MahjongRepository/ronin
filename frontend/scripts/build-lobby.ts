/**
 * Build the lobby CSS with a content-hashed filename.
 *
 * Compiles SCSS via sass, hashes the output, writes to dist/ as lobby-{hash}.css,
 * and adds a "lobby_css" entry to the existing dist/manifest.json.
 */

import { readFileSync, renameSync, writeFileSync } from "fs";

const tmpFile = "dist/_lobby.css";

// Compile sass to a temporary file
const sass = Bun.spawnSync(
    ["bunx", "sass", "src/styles/lobby-app.scss", tmpFile, "--no-source-map", "--style=compressed"],
    { stderr: "inherit" },
);

if (sass.exitCode !== 0) {
    console.error("Sass compilation failed");
    process.exit(1);
}

// Content-hash the output and rename
const css = readFileSync(tmpFile);
const hasher = new Bun.CryptoHasher("md5");
hasher.update(css);
const hash = hasher.digest("hex").slice(0, 8);
const filename = `lobby-${hash}.css`;

renameSync(tmpFile, `dist/${filename}`);

// Update the manifest with the lobby CSS entry
const manifest = JSON.parse(readFileSync("dist/manifest.json", "utf-8"));
manifest.lobby_css = filename;
writeFileSync("dist/manifest.json", JSON.stringify(manifest));

console.log(`Built lobby CSS: ${filename}`);
