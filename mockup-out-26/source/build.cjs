const fs = require('node:fs')
const path = require('node:path')
const dependencies = '/Users/deniscivkunov/Projects/WMS/frontend/node_modules'
const esbuild = require(path.join(dependencies, 'esbuild'))
const root = path.resolve(__dirname, '..')
fs.mkdirSync(path.join(root, 'assets'), { recursive: true })
esbuild.buildSync({ entryPoints: [path.join(__dirname, 'App.tsx')], outfile: path.join(root, 'assets/app.js'), bundle: true, format: 'iife', jsx: 'automatic', minify: true, nodePaths: [dependencies], define: { 'process.env.NODE_ENV': '"production"' }, logLevel: 'warning' })
fs.copyFileSync(path.join(__dirname, '../../frontend/public/portal-logo-ff.png'), path.join(root, 'assets/logo.png'))
for (const [name, variant, title] of [['index.html', 0, 'Короба WB FBO · макеты WMS'], ['variant-1.html', 1, 'Вариант 1 · Действия в разделе коробов'], ['variant-2.html', 2, 'Вариант 2 · Действия в шапке отгрузки']]) {
  fs.writeFileSync(path.join(root, name), `<!doctype html>\n<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${title}</title><style>html{color-scheme:light}body{margin:0}button,a{touch-action:manipulation}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style></head><body data-variant="${variant}"><div id="root"></div><script defer src="./assets/app.js"></script></body></html>\n`)
}
function shirt(color) { return `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96"><rect width="96" height="96" rx="12" fill="#f1f5f9"/><path d="M31 20l-17 14 10 17 10-6v32h28V45l10 6 10-17-17-14-9 5H40z" fill="${color}" stroke="#94a3b8" stroke-width="1.5"/><path d="M40 21q8 13 16 0" fill="none" stroke="#94a3b8" stroke-width="2"/></svg>` }
fs.writeFileSync(path.join(root, 'assets/tshirt.svg'), shirt('#ede8de'))
fs.writeFileSync(path.join(root, 'assets/graphite.svg'), shirt('#475569'))
fs.writeFileSync(path.join(root, 'assets/socks.svg'), '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96"><rect width="96" height="96" rx="12" fill="#f1f5f9"/><path d="M31 18h16v35l-7 16-17 7q-14-2-7-14l15-8z" fill="#cbd5e1" stroke="#94a3b8" stroke-width="2"/><path d="M55 22h16v35l-7 16-17 7q-14-2-7-14l15-8z" fill="#e2e8f0" stroke="#94a3b8" stroke-width="2"/></svg>')
console.log('Static mockup built:', root)
