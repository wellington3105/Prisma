// Text widths measured in HyperFrames' own Chrome, the way @remotion/layout-utils
// measureText does it (an inline-block, white-space:pre span; getBoundingClientRect).
// The Remotion templates break caption lines and fit headlines by MEASURED width, so
// the HyperFrames port must measure the same glyphs with the same fonts — an
// estimate per character changes where a line breaks.
//
//   node measure.mjs <puppeteer-core dir> <chrome exe> <page.html>
// stdin : one JSON request per line  {"items":[{"text","family","size","weight","letterSpacing"}]}
// stdout: one JSON line per request  {"widths":[...]}
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import readline from 'node:readline';

const [pptrDir, chrome, page] = process.argv.slice(2);
const require = createRequire(pptrDir + '/');
const puppeteer = require(pptrDir);

const browser = await puppeteer.launch({executablePath: chrome, headless: true, args: ['--allow-file-access-from-files']});
const tab = await browser.newPage();
await tab.goto(pathToFileURL(page).href, {waitUntil: 'load'});
await tab.evaluate(async () => { await document.fonts.ready; });

const rl = readline.createInterface({input: process.stdin});
for await (const line of rl) {
  if (!line.trim()) continue;
  const req = JSON.parse(line);
  const widths = await tab.evaluate(async (items) => {
    // load every face the texts need (unicode-range subsets load per character)
    const sample = [...new Set(items.map((it) => it.text).join(''))].join('') || ' ';
    const loads = new Set(items.map((it) => `${it.weight} 100px "${it.family}"`));
    await Promise.all([...loads].map((f) => document.fonts.load(f, sample)));
    return items.map((it) => {
      const n = document.createElement('span');
      n.style.fontFamily = `"${it.family}"`;
      n.style.display = 'inline-block';
      n.style.position = 'absolute';
      n.style.top = '-10000px';
      n.style.whiteSpace = 'pre';
      n.style.fontSize = `${it.size}px`;
      n.style.fontWeight = String(it.weight);
      if (it.letterSpacing) n.style.letterSpacing = it.letterSpacing;
      if (it.textTransform) n.style.textTransform = it.textTransform;
      n.innerText = it.text;
      document.body.appendChild(n);
      const w = n.getBoundingClientRect().width;
      document.body.removeChild(n);
      return w;
    });
  }, req.items);
  process.stdout.write(JSON.stringify({widths}) + '\n');
}
await browser.close();
