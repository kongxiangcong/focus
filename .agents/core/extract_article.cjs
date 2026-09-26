// Readability operates on inert saved HTML. jsdom never runs scripts or loads resources.
const fs = require('node:fs');
const { JSDOM, VirtualConsole } = require('jsdom');
const { Readability } = require('@mozilla/readability');

const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const dom = new JSDOM(input.html, {
  url: input.url || 'https://saved-article.invalid/',
  virtualConsole: new VirtualConsole(),
});
const article = new Readability(dom.window.document, {
  charThreshold: 80,
  keepClasses: true,
  maxElemsToParse: 100000,
}).parse();
if (!article) {
  process.stdout.write(JSON.stringify({ error: 'article_boundary_ambiguous' }));
} else {
  process.stdout.write(JSON.stringify({ content: article.content, title: article.title, byline: article.byline }));
}
dom.window.close();
