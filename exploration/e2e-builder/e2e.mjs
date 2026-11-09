// End-to-end test of the onto-builder against the REAL backend and frontend (no mocked requests).
// Run with bun: bun exploration/e2e-builder/e2e.mjs  (backend on :8123 with ONSET_CONFIG=exploration/e2e-builder/config.json,
// frontend dev server on :5199). Screenshots and results.json are written next to this script.
import puppeteer from '/home/bkantz/.claude/skills/puppeteer/node_modules/puppeteer/lib/puppeteer/puppeteer.js'
import { writeFileSync } from 'node:fs'
import { dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const OUT = dirname(fileURLToPath(import.meta.url))
const BACKEND = 'http://localhost:8123'
const FRONT = 'http://localhost:5199'
const BUILDER = 'e2e'
const results = []
const log = (...a) => console.log(...a)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const record = (step, pass, data = {}) => {
    results.push({ step, pass, ...data })
    log(pass ? 'PASS' : 'FAIL', step, JSON.stringify(data))
}
let shot_n = 0
const shot = async (name) => {
    const file = `${String(++shot_n).padStart(2, '0')}-${name}.png`
    await page.screenshot({ path: `${OUT}/${file}` })
    log('  screenshot', file)
    return file
}
const api = async (path, init) => {
    const r = await fetch(`${BACKEND}/onto-builder/${BUILDER}${path}`, init)
    return r.json()
}

const browser = await puppeteer.launch({ args: ['--no-sandbox', '--disable-setuid-sandbox'] })
const page = await browser.newPage()
await page.setViewport({ width: 1600, height: 1000 })
const console_errors = []
page.on('console', (m) => m.type() == 'error' && console_errors.push(`${m.text()} ${m.location()?.url ?? ''}`))
page.on('response', (r) => r.status() >= 400 && console_errors.push(`HTTP ${r.status()} ${r.request().method()} ${r.url()}`))
page.on('pageerror', (e) => console_errors.push(`pageerror: ${e.message}`))

const clickText = async (selector, text) => {
    const ok = await page.$$eval(selector, (els, text) => {
        const el = els.find((e) => e.textContent.trim() == text || e.textContent.trim().startsWith(text))
        if (!el) return false
        el.click()
        return true
    }, text)
    if (!ok) throw new Error(`no ${selector} with text ${text}`)
}
const statusText = () => page.$eval('.builder_status', (e) => e.textContent.replace(/\s+/g, ' ').trim()).catch(() => '')
const waitBuild = async (sid, { timeout = 600_000 } = {}) => {
    const t0 = Date.now()
    // the build may not have started yet: wait for it to run, then to finish
    while (Date.now() - t0 < timeout) {
        const s = (await api(`/sessions/${sid}`)).status
        if (!s.running && s.processed == s.total && s.total > 0) return { ...s, seconds: Math.round((Date.now() - t0) / 1000) }
        await sleep(1000)
    }
    throw new Error('build did not finish')
}

// ---------- 1. builder list ----------
await page.goto(`${FRONT}/onto-builder`, { waitUntil: 'networkidle2' })
await page.waitForSelector('.builder_card')
const cards = await page.$$eval('.builder_card', (e) => e.map((x) => x.textContent.trim()))
await shot('builder-list')
record('1 builder list shows the e2e builder', cards.some((c) => c.includes('E2E Enron mini')), { cards })

// ---------- 2. open it: a new session ----------
await clickText('.builder_card', 'E2E Enron mini')
await page.waitForSelector('.onto_editor', { timeout: 20000 })
await sleep(1000)
const sid = await page.evaluate((b) => localStorage.getItem(`onset:builder:${b}:session`), BUILDER)
await shot('new-session')
record('2 new session opened', !!sid && (await page.$$('.onto_card')).length == 0, { sid })

// ---------- 3. ontology via the UI: two classes and a link, then a field and the link name ----------
for (const name of ['Person', 'Company']) {
    await page.type('.onto_add input', name)
    await page.keyboard.press('Enter')
    await sleep(400)
}
await page.click('.onto_card:nth-of-type(1) button[title^="Add a link"]').catch(async () => {
    const btns = await page.$$('.onto_card button[title^="Add a link"]')
    await btns[0].click()
})
await sleep(200)
const company = (await page.$$('.onto_card'))[1]
await company.click()
await sleep(1500)
let st = await api(`/sessions/${sid}`)
// the field (a role) and a readable link name: via the API, as the agent or an import would
st.ontology.classes.find((c) => c.id == 'Person').fields.push({ name: 'role', type: 'string', description: 'job title' })
// (the UI names a new link "has Company" with the id hasCompany; renaming keeps the id, so set both)
Object.assign(st.ontology.links[0], { id: 'worksFor', label: 'works for' })
st = await api(`/sessions/${sid}/ontology`, { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(st.ontology) })
await sleep(2500)
const card_titles = await page.$$eval('.onto_card .onto_card_title', (e) => e.map((x) => x.textContent))
const link_labels = await page.$$eval('.onto_link .link_text', (e) => e.map((x) => x.textContent))
await shot('ontology-defined')
record('3 ontology defined (UI classes + link, API field)', card_titles.join() == 'Person,Company' && link_labels.includes('works for'),
    { card_titles, link_labels, status: await statusText() })

// ---------- 4. pan, zoom, fit ----------
const view = async () => {
    const t = await page.$eval('.onto_canvas', (el) => el.style.transform)
    const n = t.match(/-?\d+(?:\.\d+)?(?:e-?\d+)?/g).map(Number)
    return { x: +n[0].toFixed(1), y: +n[1].toFixed(1), k: +n[2].toFixed(3) }
}
const vp = await page.$eval('.onto_viewport', (el) => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height } })
const v0 = await view()
await page.mouse.move(vp.x + vp.w * 0.5, vp.y + vp.h * 0.6)
for (let i = 0; i < 3; i++) { await page.mouse.wheel({ deltaY: -120 }); await sleep(100) }
await sleep(300)
const v1 = await view()
await shot('zoomed')
// pan: drag an empty spot of the background
const bg = await page.evaluate((vp) => {
    for (let fy = 0.95; fy > 0.1; fy -= 0.05) for (let fx = 0.05; fx < 0.6; fx += 0.05) {
        const x = Math.round(vp.x + vp.w * fx), y = Math.round(vp.y + vp.h * fy)
        const e = document.elementFromPoint(x, y)
        if (e && !e.closest('.onto_card, .onto_link, .onto_overlay') && e.closest('.onto_viewport')) return { x, y }
    }
    return null
}, vp)
await page.mouse.move(bg.x, bg.y)
await page.mouse.down()
await page.mouse.move(bg.x + 60, bg.y - 40, { steps: 8 })
await page.mouse.move(bg.x + 120, bg.y - 80, { steps: 8 })
await page.mouse.up()
await sleep(300)
const v2 = await view()
await shot('panned')
await page.click('button[title="Fit the ontology to the view"]')
await sleep(800)
const v3 = await view()
const in_view = await page.$$eval('.onto_card', (els, vp) => els.every((e) => {
    const r = e.getBoundingClientRect()
    return r.x >= vp.x - 1 && r.y >= vp.y - 1 && r.right <= vp.x + vp.w + 1 && r.bottom <= vp.y + vp.h + 1
}), vp)
await shot('fit')
record('4 pan/zoom/fit', v1.k > v0.k && Math.abs(v2.x - v1.x - 120) < 2 && Math.abs(v2.y - v1.y + 80) < 2 && in_view,
    { initial: v0, zoomed: v1, panned: v2, fit: v3, cards_inside_after_fit: in_view })

// ---------- 5. the build runs ----------
await sleep(1500)
const running_status = await statusText()
await shot('build-running')
const built = await waitBuild(sid)
await sleep(2000)
await shot('build-done')
record('5 initial build (default mode normalized)', built.processed == 8 && built.triples > 0 && built.errors == 0,
    { running_status, final_status: await statusText(), ...built })

// ---------- 6. merging settings: off, normalized, levenshtein, llm_judge ----------
await clickText('.onset_btn', 'Merging')
await page.waitForSelector('.builder_io .selection_group')
await sleep(500)
await shot('merging-popup')
const mergeState = async () => page.evaluate(() => {
    const box = [...document.querySelectorAll('.builder_io')].find((b) => b.textContent.includes('Merging names'))
    const counter = [...box.querySelectorAll('.toolbar span')].map((s) => s.textContent.trim()).find((t) => /merged/.test(t))
    return { counter, merges: [...box.querySelectorAll('.builder_merges li')].map((l) => l.textContent.replace(/\s+/g, ' ').trim()), message: box.querySelector('p.message:not(:first-of-type)')?.textContent }
})
const modes = [['off', 'Off'], ['normalized', 'Normalized'], ['levenshtein', 'Edit distance'], ['llm_judge', 'LLM judge']]
const mode_results = {}
for (const [mode, label] of modes) {
    const before = (await api(`/sessions/${sid}`)).status
    await clickText('.builder_io .selection_group .onset_btn', label)
    await sleep(300)
    await clickText('.builder_io .onset_btn', 'Apply')
    await sleep(1200)
    const restarted_status = await statusText()
    const after_apply = (await api(`/sessions/${sid}`)).status
    await shot(`merging-${mode}-applied`)
    const done = await waitBuild(sid)
    await sleep(3500) // a poll and the popup's merge refresh
    const ui = await mergeState()
    const server = await api(`/sessions/${sid}/disambiguation`)
    await shot(`merging-${mode}-done`)
    mode_results[mode] = {
        restarted_status, processed_right_after_apply: after_apply.processed, running_right_after_apply: after_apply.running,
        build_seconds: done.seconds, triples: done.triples, merged: server.merged, judged: server.judged,
        ui_counter: ui.counter, ui_merges: ui.merges, server_mode: server.settings.mode,
    }
    const restarted = after_apply.running || after_apply.processed < before.processed || restarted_status.includes('0/8')
    record(`6 merging ${mode}`, server.settings.mode == mode && restarted && done.processed == 8
        && (ui.counter ?? '').startsWith(`${server.merged} merged`) && ui.merges.length == Math.min(server.merges.length, 100),
        mode_results[mode])
}

// ---------- 7. Query & results: a miniature is centred when expanded, stays open across refreshes ----------
// close the merging popup
await page.evaluate(() => {
    const box = [...document.querySelectorAll('.builder_io')].find((b) => b.textContent.includes('Merging names'))
    box?.querySelector('.toolbar .onset_btn')?.click()
})
await page.select('.builder_results_class', 'Person')
await page.waitForSelector('.result_instance_element .expandable_trigger svg rect.node', { timeout: 30000 })
await sleep(1500)
const n_minis = await page.$$eval('.result_instance_element .expandable_trigger', (e) => e.length)
await shot('results-miniatures')
const centre = () => page.evaluate(() => {
    const svg = document.querySelector('.expandable_content svg')
    if (!svg) return null
    const node = svg.querySelector('rect.node')
    const s = svg.getBoundingClientRect(), n = node.getBoundingClientRect()
    const g = svg.querySelector(':scope > g > g').getBoundingClientRect()
    const c = [s.x + s.width / 2, s.y + s.height / 2], m = [n.x + n.width / 2, n.y + n.height / 2], b = [g.x + g.width / 2, g.y + g.height / 2]
    return { svg_centre: c.map(Math.round), node_centre: m.map(Math.round), offset: [Math.round(m[0] - c[0]), Math.round(m[1] - c[1])],
        graph_bbox_offset: [Math.round(b[0] - c[0]), Math.round(b[1] - c[1])], n_nodes: svg.querySelectorAll('rect.node').length }
})
const minis = await page.$$('.result_instance_element .expandable_trigger')
await minis[Math.min(2, minis.length - 1)].click()
await page.waitForSelector('.expandable_content svg rect.node', { timeout: 10000 })
await sleep(800)
const c1 = await centre()
await shot('miniature-expanded')
const centred = (c) => c && Math.abs(c.offset[0]) <= 3 && Math.abs(c.offset[1]) <= 3
record('7a miniature centred on expand', centred(c1), { n_minis, on_expand: c1 })

// refreshes while the KG grows: rebuild, expand a miniature as soon as one is there (its instance is already
// extracted), then let the build go on and finish (results refresh at most every 5 s and at the end)
await page.evaluate(() => document.querySelector('.expandable_frame')?.click())
await sleep(300)
await api(`/sessions/${sid}/rebuild`, { method: 'POST' })
let sparql_posts = 0
const count = (r) => r.url().endsWith('/sparql') && r.request().method() == 'POST' && sparql_posts++
const header = () => page.$eval('.expandable_header', (e) => e.textContent.replace(/\s+/g, ' ').trim()).catch(() => null)
let early = null
// the results shown are the old KG's until the first refresh of this build: wait for a few documents
// and then for a results query of the frontend
for (let i = 0; i < 600; i++) {
    await sleep(100)
    if ((await api(`/sessions/${sid}`)).status.processed >= 2) break
}
await page.waitForResponse((r) => r.url().endsWith('/sparql') && r.request().method() == 'POST', { timeout: 15000 }).catch(() => { })
await sleep(800)
{
    const s = (await api(`/sessions/${sid}`)).status
    if ((await page.$$('.result_instance_element .expandable_trigger svg rect.node')).length && s.running) {
        await page.$eval('.result_instance_element .expandable_trigger', (e) => e.click())
        early = s
    }
}
await page.waitForSelector('.expandable_content svg rect.node', { timeout: 5000 }).catch(() => { })
page.on('response', count)
const h_open = await header()
const c_mid = await centre()
await shot('miniature-expanded-during-build')
const done7 = await waitBuild(sid)
await sleep(7000)
page.off('response', count)
const c2 = await centre()
const h_after = await header()
await shot('miniature-after-refreshes')
record('7b expanded miniature stays open (and centred) across the growing-KG refreshes', !!early && centred(c_mid) && centred(c2) && h_after == h_open,
    { expanded_at: early && `${early.processed}/${early.total} docs, ${early.triples} triples`, header_on_open: h_open, header_after: h_after,
      sparql_queries_while_open: sparql_posts, final_triples: done7.triples, on_open: c_mid, after_refreshes: c2 })

// ---------- 8. sources from the expanded miniature header, then document viewer ----------
const src_buttons = await page.$$eval('.expandable_header .miniature_sources .onset_btn', (e) => e.map((x) => x.textContent.trim()))
if (src_buttons.length) {
    await page.$eval('.expandable_header .miniature_sources .onset_btn', (b) => b.click())
}
await page.waitForSelector('.instance_sources', { timeout: 10000 }).catch(() => { })
await sleep(1500)
const sources = await page.evaluate(() => {
    const a = document.querySelector('.instance_sources')
    if (!a) return null
    return { title: a.querySelector('.instance_sources_title')?.textContent, text: a.querySelector('.instance_sources_body')?.textContent.replace(/\s+/g, ' ').trim(), docs: [...a.querySelectorAll('.instance_sources_doc')].map((d) => d.textContent.replace(/\s+/g, ' ').trim()) }
})
await shot('sources-from-miniature')
record('8a sources panel from the miniature source button', !!sources && sources.docs.length > 0, { src_buttons, sources })
// close the expanded miniature (click its backdrop) and the sources panel before the next step
await page.evaluate(() => document.querySelector('.expandable_frame')?.click())
await page.evaluate(() => [...document.querySelectorAll('.instance_sources header .onset_btn')].pop()?.click())
await sleep(300)

// ---------- 9. SPARQL table: click an IRI cell, open a document ----------
await clickText('.builder_results .selection_group .onset_btn', 'SPARQL')
await page.waitForSelector('.builder_results_query textarea')
const q = 'SELECT ?person ?name ?company WHERE {\n  ?person a onto:Person ; rdfs:label ?name .\n  OPTIONAL { ?person onto:worksFor ?company }\n} ORDER BY ?name'
await page.$eval('.builder_results_query textarea', (t, q) => { t.value = q; t.dispatchEvent(new Event('input')) }, q)
await clickText('.builder_results_query .onset_btn', 'Apply')
await page.waitForSelector('.builder_results_table td.builder_results_instance', { timeout: 15000 })
await sleep(800)
const table = await page.$$eval('.builder_results_table tbody tr', (rows) => rows.map((r) => [...r.children].map((c) => c.textContent.trim())))
await shot('sparql-table')
// prefer an instance with aliases (a merged one)
const prov = await Promise.all((await page.$$eval('.builder_results_table td.builder_results_instance', (e) => e.map((x) => x.title.split('\n')[0])))
    .map(async (iri) => ({ iri, p: await api(`/sessions/${sid}/provenance?iri=${encodeURIComponent(iri)}`) })))
const target = prov.find((x) => x.p.aliases?.length && x.p.documents?.length > 1) ?? prov.find((x) => x.p.documents?.length) ?? prov[0]
await page.$$eval('.builder_results_table td.builder_results_instance', (els, iri) => els.find((e) => e.title.startsWith(iri)).click(), target.iri)
await page.waitForSelector('.instance_sources_doc', { timeout: 10000 })
await sleep(800)
const sources2 = await page.evaluate(() => {
    const a = document.querySelector('.instance_sources')
    return { title: a.querySelector('.instance_sources_title')?.textContent, text: a.querySelector('.instance_sources_body')?.textContent.replace(/\s+/g, ' ').trim(), docs: [...a.querySelectorAll('.instance_sources_doc')].map((d) => d.textContent.replace(/\s+/g, ' ').trim()) }
})
await shot('sources-from-iri-cell')
record('9a sources panel from an IRI cell', sources2.docs.length == target.p.documents.length && sources2.docs.length > 0,
    { iri: target.iri, label: target.p.label, aliases: target.p.aliases, sources: sources2 })
await page.$eval('.instance_sources_doc', (b) => b.click())
await page.waitForSelector('.document_viewer', { timeout: 10000 })
await sleep(800)
const viewer = await page.evaluate(() => {
    const v = document.querySelector('.document_viewer')
    return { title: v.querySelector('.document_viewer_title')?.textContent, path: v.querySelector('.document_viewer_path')?.textContent, marks: [...v.querySelectorAll('mark')].map((m) => m.textContent), header: v.querySelector('.panel_header')?.textContent.replace(/\s+/g, ' ').trim() }
})
await shot('document-viewer')
record('9b document viewer with highlights', viewer.marks.length > 0, viewer)
await page.keyboard.press('Escape')
await page.evaluate(() => document.querySelector('.document_viewer_backdrop')?.click())
await sleep(300)

// ---------- 10. reload: the settings persist ----------
const before_reload = await api(`/sessions/${sid}/disambiguation`)
await page.reload({ waitUntil: 'networkidle2' })
await page.waitForSelector('.onto_editor')
await sleep(2500)
const sid2 = await page.evaluate((b) => localStorage.getItem(`onset:builder:${b}:session`), BUILDER)
await clickText('.onset_btn', 'Merging')
await page.waitForSelector('.builder_io .selection_group')
await sleep(1000)
const selected = await page.$$eval('.builder_io .selection_group .onset_btn', (e) => e.filter((x) => /active|selected|toggled/.test(x.className)).map((x) => x.textContent.trim()))
const ui_after = await mergeState()
await shot('reload-settings-persist')
const after_reload = await api(`/sessions/${sid}/disambiguation`)
record('10 settings persist across reload', sid2 == sid && after_reload.settings.mode == 'llm_judge' && JSON.stringify(after_reload.settings) == JSON.stringify(before_reload.settings),
    { sid2, selected_buttons: selected, settings: after_reload.settings, ui_counter: ui_after.counter, n_merges: ui_after.merges.length })

writeFileSync(`${OUT}/results.json`, JSON.stringify({ session: sid, results, mode_results, console_errors }, null, 2))
log('console errors:', console_errors.length, console_errors.slice(0, 10))
await browser.close()
