import { build } from 'esbuild';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('.', import.meta.url));
await mkdir(new URL('dist/', import.meta.url), {recursive: true});
await build({absWorkingDir: root, entryPoints: ['web/host.js'], outfile: 'dist/host.js', bundle: true,
  platform: 'browser', format: 'esm', target: 'es2022', minify: true, legalComments: 'none'});
for (const name of ['index.html', 'style.css']) await writeFile(new URL(`dist/${name}`, import.meta.url), await readFile(new URL(`web/${name}`, import.meta.url)));
