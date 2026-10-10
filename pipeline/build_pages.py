#!/usr/bin/env python3
"""Build the static simulator pages for dist/.

  python3 build_pages.py [--hsr-data out/hsr.json] [--endfield-data out/endfield.json] [--dist ../dist] [--no-avatars endfield]

For each game it:
  1. Takes the original single-file page, cuts the inline DATA literal out of the engine bundle and
     replaces it with a reference to globalThis.__SIM_DATA__ (engine/__modules stay inline).
  2. Turns the engine and app <script>s into inert <script type="text/x-sim-deferred"> blocks and appends
     a small loader. The loader fetches ../data/<game>.json, checks it (JSON, required keys, version),
     sets window.__SIM_DATA__, executes the deferred scripts in order, then calls window.__uiReady(). Any
     failure calls window.__uiError(msg). Both calls are guarded by typeof, so the page also works without the theme.
  3. Adds data-confidence="low" + title=<lowReason> markers in the UI (see LOW_* patches below).
  4. Writes dist/<game>/index.html and runs frontend/apply-theme.py on it.
  5. Copies the data JSON into dist/data/ and writes dist/nginx.conf.example (only if absent).
The ww page (dist/ww/, dist/assets/ww-engine.js, dist/assets/ww-worker.js, dist/data/ww.json) is built by
pipeline/ww/page/build_page.py; select games with --games hsr,endfield,ww (default: all).
Only dist/hsr/, dist/endfield/, dist/ww/, dist/assets/ww-*.js, dist/data/ (and nginx.conf.example if missing) are written.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ATT = os.path.join(ROOT, 'frontend', 'original') + os.sep   # original single-file pages (DATA literal stripped)
ap = argparse.ArgumentParser()
ap.add_argument('--hsr-html', default=ATT + '370b9374672a310be9560ad791b17b4795ca2f8cfc21b5c832a95848d894118f.html')
ap.add_argument('--endfield-html', default=ATT + 'endfield.html')
ap.add_argument('--hsr-data', default=os.path.join(HERE, 'out', 'hsr.json'))
ap.add_argument('--endfield-data', default=os.path.join(HERE, 'out', 'endfield.json'))
ap.add_argument('--ww-data', default=os.path.join(HERE, 'out', 'ww.json'))
ap.add_argument('--games', default='endfield', help='comma list of games to build (hsr,endfield,ww)')
ap.add_argument('--dist', default=os.path.join(ROOT, 'dist'))
ap.add_argument('--theme-script', default=os.path.join(ROOT, 'frontend', 'apply-theme.py'))
ap.add_argument('--layout', choices=['shared', 'per-game'], default='per-game',
                help='shared: dist/<game>/index.html + dist/assets + dist/data (pages use ../); '
                     'per-game: self-contained dist/<game>/{index.html,assets/,data/} (pages use assets/, data/), see dist3/LAYOUT.md')
ap.add_argument('--no-avatars', default='', help='comma list of games whose avatar fields are all null and no avatar files are copied (e.g. endfield, pending licensing); default: include all')
args = ap.parse_args()
NO_AVATARS = {g.strip() for g in args.no_avatars.split(',') if g.strip()}
# default layout: legacy `dist` (ROOT/dist) keeps the shared layout; any other dist (dist3, …) is per-game (lead 17:10)
if args.layout is None:
    args.layout = 'shared' if os.path.realpath(args.dist) == os.path.realpath(os.path.join(ROOT, 'dist')) else 'per-game'
    print(f'layout: {args.layout} (default for --dist {args.dist})')
PER_GAME = args.layout == 'per-game'
THEME_SRC = os.path.join(ROOT, 'frontend', 'theme')


def pkg_root(game):
    """directory that holds assets/ and data/ for a game page: the game's own package (per-game) or dist/ (shared)"""
    return os.path.join(args.dist, game) if PER_GAME else args.dist


def rel():
    """URL prefix from dist/<game>/index.html to its assets/ and data/"""
    return '' if PER_GAME else '../'


def apply_theme(game, src, dst):
    """frontend/apply-theme.py with the layout's theme prefix (it also injects the game tab bar gamenav.js). Per-game packages
    carry their own copy of the theme directory (frontend/theme/* → <game>/assets/theme/); the shared layout's dist/assets/theme
    is synced by frontend and not written here."""
    subprocess.check_call([sys.executable, args.theme_script, game, src, dst, '--prefix', rel() + 'assets/theme/'])
    if PER_GAME:
        td = os.path.join(pkg_root(game), 'assets', 'theme')
        os.makedirs(td, exist_ok=True)
        for f in sorted(os.listdir(THEME_SRC)):
            if os.path.isfile(os.path.join(THEME_SRC, f)):
                shutil.copyfile(os.path.join(THEME_SRC, f), os.path.join(td, f))


# ----------------------------------------------------------------------------- avatars
ICON_SRC = os.path.join(ROOT, 'assets-src', 'icons')


def attach_avatars(game, chars, page_dir):
    """Official avatars (scraper output assets-src/icons/<game>/<id>.webp + optional manifest.json {"<id>": {"src", "file"}}, may hold
    aliases). Copies only the referenced files to <page_dir>/assets/avatars/<id>.webp (the directory is rebuilt, so no stale/unreferenced
    files — release/package.py check_avatars) and sets c['avatar'] = 'assets/avatars/<id>.webp' (relative to the page) or None on every
    character. Missing source dir/manifest → all None. Returns the list of characters without an avatar."""
    sd = os.path.join(ICON_SRC, game)
    man = {}
    mp = os.path.join(sd, 'manifest.json')
    if os.path.isfile(mp):
        try:
            man = json.load(open(mp, encoding='utf-8')) or {}
        except (OSError, ValueError) as e:
            print(f'[{game}] avatars: manifest.json unreadable ({e}); falling back to <id>.webp', file=sys.stderr)
            man = {}
    ad = os.path.join(page_dir, 'assets', 'avatars')
    if os.path.isdir(ad):
        shutil.rmtree(ad)
    missing, n = [], 0
    if game in NO_AVATARS:   # --no-avatars <game>: every avatar null, no files copied
        for c in chars:
            c['avatar'] = None
        print(f'{game}: avatars disabled (--no-avatars), 0/{len(chars)}')
        return [str(c.get('id')) for c in chars]
    for c in chars:
        cid = str(c.get('id'))
        ent = man.get(cid) if isinstance(man, dict) and not cid.startswith('_') else None   # manifest keys starting with '_' (e.g. _missing) are metadata
        cands = [ent.get('file')] if isinstance(ent, dict) and ent.get('file') else []
        cands.append(cid + '.webp')
        src = None
        for f in cands:
            f = str(f)
            if '..' in f.replace('\\', '/').split('/') or os.path.isabs(f):
                continue
            fp = os.path.join(sd, f)
            if f.lower().endswith('.webp') and os.path.isfile(fp):
                src = fp
                break
        if src:
            os.makedirs(ad, exist_ok=True)
            shutil.copyfile(src, os.path.join(ad, cid + '.webp'))
            c['avatar'] = 'assets/avatars/' + cid + '.webp'
            n += 1
        else:
            c['avatar'] = None
            missing.append(f"{cid} {c.get('name', '')}".strip())
    total = n + len(missing)
    print(f'{game}: avatars {n}/{total}' + ('' if os.path.isdir(sd) else f' (no source dir {sd})') +
          (f'; missing {len(missing)}: ' + ', '.join(missing) if missing else ''))
    return missing


LOW_FALLBACK = '自动解析，待人工复核'


def must_replace(s, old, new, label, count=1):
    n = s.count(old)
    if n != count:
        sys.exit(f'[{label}] patch anchor found {n}x (expected {count}): {old[:90]!r}')
    return s.replace(old, new)


def split_scripts(html):
    """-> list of (start_of_open_tag, end_of_open_tag, end_of_body, open_tag) for inline scripts."""
    out = []
    for m in re.finditer(r'<script(\s[^>]*)?>', html):
        if 'src=' in (m.group(1) or ''):
            continue
        e = html.find('</script>', m.end())
        out.append((m.start(), m.end(), e, m.group(0)))
    return out


def cut_data(engine_js, label):
    m = re.search(r'const DATA = ', engine_js)
    if not m:
        sys.exit(f'[{label}] DATA literal not found')
    obj, end = json.JSONDecoder().raw_decode(engine_js, m.end())
    js = engine_js[:m.end()] + "(typeof globalThis !== 'undefined' ? globalThis : self).__SIM_DATA__" + engine_js[end:]
    if 'const DATA = {' in js:
        sys.exit(f'[{label}] more than one DATA literal')
    return js, obj


def loader(cfg):
    return '<script>\n/* sim data loader (generated by pipeline/build_pages.py) */\n(function () {\n"use strict";\nvar CFG = ' + \
        json.dumps(cfg, ensure_ascii=False) + r''';
function ui(name, arg) {
  function go() {
    var f = window[name];
    if (typeof f === 'function') { try { f(arg); } catch (e) { /* theme hook failure must not break the page */ } return; }
    if (name === '__uiError') {  // no theme: plain inline message
      var d = document.createElement('div');
      d.setAttribute('role', 'alert'); d.id = 'sim-load-error';
      d.style.cssText = 'position:fixed;left:0;right:0;top:0;z-index:9999;padding:16px 20px;background:#3a1515;color:#ffd7d7;font:14px/1.5 sans-serif;white-space:pre-wrap';
      d.textContent = '加载失败：' + arg;
      (document.body || document.documentElement).appendChild(d);
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go); else go();
}
function fail(msg) { window.__SIM_LOAD_ERROR__ = msg; ui('__uiError', msg); }
function pick(o, path) { for (var i = 0; i < path.length; i++) { if (o == null) return undefined; o = o[path[i]]; } return o; }
function boot() {
  var errs = [];
  function onerr(ev) { errs.push(ev && ev.message || String(ev)); }
  window.addEventListener('error', onerr);
  var ss = document.querySelectorAll('script[type="text/x-sim-deferred"]');
  for (var i = 0; i < ss.length; i++) {
    var s = document.createElement('script');
    s.setAttribute('data-sim-run', ss[i].getAttribute('data-sim') || '');
    s.text = ss[i].textContent;
    ss[i].parentNode.insertBefore(s, ss[i].nextSibling);  // inline script: runs synchronously
  }
  window.removeEventListener('error', onerr);
  if (!window[CFG.engineGlobal]) { fail('引擎初始化失败：' + (errs[0] || ('未找到 ' + CFG.engineGlobal))); return; }
  if (errs.length) { fail('界面初始化出错：' + errs[0]); return; }
  ui('__uiReady');
}
if (typeof fetch !== 'function') { fail('浏览器不支持 fetch，无法加载数据'); return; }
fetch(CFG.url, { credentials: 'same-origin' }).then(function (r) {
  if (!r.ok) throw new Error('数据请求失败：HTTP ' + r.status + '（' + CFG.url + '）');
  return r.text();
}, function (e) { throw new Error('数据请求失败：' + (e && e.message || e) + '（' + CFG.url + '）'); }).then(function (text) {
  var data;
  try { data = JSON.parse(text); } catch (e) { throw new Error('数据 JSON 解析失败：' + (e && e.message || e)); }
  if (!data || typeof data !== 'object') throw new Error('数据格式错误：顶层不是对象');
  var missing = CFG.requiredKeys.filter(function (k) { return !(k in data); });
  if (missing.length) throw new Error('数据缺少字段：' + missing.join(', '));
  var got = pick(data, CFG.versionPath);
  if (got !== CFG.version) throw new Error('数据版本不匹配：页面需要 ' + CFG.versionPath.join('.') + ' = ' + CFG.version + '，实际为 ' + got + '（可能是缓存的旧数据，请强制刷新）');
  window.__SIM_DATA__ = data;
  window.__SIM_DATA_TEXT__ = CFG.keepText ? text : null;
  boot();
}).catch(function (e) { fail(e && e.message || String(e)); });
})();
</script>
'''


# ----------------------------------------------------------------------------- HSR UI patches
HSR_HELPERS = r'''
// ---- low-confidence markers (injected by pipeline/build_pages.py) ----
var __LOW_FALLBACK = %s;
var __LOW_BY_KEY = null;
function __lowIdx() {
  if (__LOW_BY_KEY) return __LOW_BY_KEY;
  __LOW_BY_KEY = {};
  (function walk(o) {
    if (!o || typeof o !== 'object') return;
    if (Array.isArray(o)) { for (var i = 0; i < o.length; i++) walk(o[i]); return; }
    if (o.confidence === 'low' && o.key) __LOW_BY_KEY[o.key] = o.lowReason || __LOW_FALLBACK;
    for (var k in o) if (k.charAt(0) !== '_' && o[k] && typeof o[k] === 'object') walk(o[k]);
  })(window.__SIM_DATA__);
  return __LOW_BY_KEY;
}
function __lowReason(x) { return (x && x.lowReason) || (x && x.key && __lowIdx()[x.key]) || __LOW_FALLBACK; }
function __lowList(o) {
  var r = [];
  if (!o) return r;
  (o.hits || []).concat(o.effects || []).forEach(function (x) { if (x && x.confidence === 'low') { var t = __lowReason(x); if (r.indexOf(t) < 0) r.push(t); } });
  return r;
}
function __lowAttrs(reasons) { return reasons && reasons.length ? { 'data-confidence': 'low', title: reasons.join('\n') } : {}; }
function __charRaw(cid) { var d = window.__SIM_DATA__; return d && d.characters && d.characters[cid] || null; }
function __findBy(list, f, v) { list = list || []; for (var i = 0; i < list.length; i++) if (list[i] && String(list[i][f]) === String(v)) return list[i]; return null; }
// one span per hit; a hit is marked when the raw DATA hit at the same index is low-confidence.
// If the engine changed the hit list (override), the whole line is marked instead.
function __hitLine(attrs, hits, raw, fmt) {
  var rh = raw && raw.hits || [];
  var aligned = rh.length === hits.length;
  var line = h('div', aligned ? attrs : Object.assign({}, attrs, __lowAttrs(__lowList({ hits: rh }))));
  hits.forEach(function (x, i) {
    if (i) add(line, ' ｜ ');
    var low = aligned && rh[i] && rh[i].confidence === 'low';
    add(line, h('span', low ? { class: 'hit', 'data-confidence': 'low', title: __lowReason(rh[i]) } : { class: 'hit' }, fmt(x)));
  });
  return line;
}
// ---- avatars (.gava placeholder; filled by the theme avatar script) ----
function __gava(id, size, name) {
  var c = (typeof CHAR_BY !== 'undefined' && CHAR_BY[id]) || {}, raw = __charRaw(id) || {};
  return h('span', { class: 'gava ' + (size || 'md'), 'data-icon': raw.avatar || null, 'data-el': c.element || raw.element || '', 'data-name': name || c.name || raw.name || String(id || '') });
}
''' % json.dumps(LOW_FALLBACK, ensure_ascii=False)

HIT_FMT = "function (x) { return (TYPE_ZH[x.dmgType] || x.dmgType) + '·' + (SCALING_ZH[x.scaling] || x.scaling || '') + (typeof x.multiplier === 'number' ? ' ' + pct(x.multiplier, 1).replace('.0%', '%') : '') + '·' + (HIT_TARGET_ZH[x.target] || x.target || '') + (x.count > 1 ? '×' + x.count + '次' : ''); }"


def patch_hsr_app(app):
    L = 'hsr'
    app = must_replace(app, "var E = window.HSR2;\n", "var E = window.HSR2;\n" + HSR_HELPERS, L)
    # worker gets the data too (the engine source no longer embeds it)
    app = must_replace(app, "var code = src + '\\n;self.onmessage",
                       "var code = 'self.__SIM_DATA__ = ' + (window.__SIM_DATA_TEXT__ || 'null') + ';\\n' + src + '\\n;self.onmessage", L)
    # effect rows (自动解析效果 list): the row is the entry; the existing 低置信 tag gets the reason as tooltip
    app = must_replace(app, "var row = h('label', { class: 'eff' + (off || x.locked ? ' off' : ''), title: '效果键：' + e.key },",
                       "var row = h('label', { class: 'eff' + (off || x.locked ? ' off' : ''), 'data-confidence': e.confidence === 'low' ? 'low' : null, title: (e.confidence === 'low' ? __lowReason(e) + '\\n' : '') + '效果键：' + e.key },", L)
    app = must_replace(app, "e.confidence === 'low' ? h('span', { class: 'tag low' }, '低置信') : null,",
                       "e.confidence === 'low' ? h('span', { class: 'tag low', title: __lowReason(e) }, '低置信') : null,", L)
    # kit skills: per-hit spans; 低置信 tag from raw DATA hits (describeKit drops confidence)
    app = must_replace(app, "(kit.skills || []).forEach(function (s) {\n        add(body, h('div', { class: 'ks' },",
                       "(kit.skills || []).forEach(function (s) {\n        var __rs = __findBy((__charRaw(m.charId) || {}).skills, 'id', s.id), __lr = __lowList(__rs ? { hits: __rs.hits } : null);\n        add(body, h('div', { class: 'ks' },", L)
    app = must_replace(app, "(s.hits || []).some(function (x) { return x.confidence === 'low'; }) ? h('span', { class: 'tag low' }, '低置信') : null),",
                       "__lr.length ? h('span', { class: 'tag low', title: __lr.join('\\n') }, '低置信') : null),", L)
    app = must_replace(app, "(s.hits || []).length ? h('div', { class: 'mini dim', style: 'margin-top:3px' }, s.hits.map(" + HIT_FMT + ").join(' ｜ ')) : null));",
                       "(s.hits || []).length ? __hitLine({ class: 'mini dim', style: 'margin-top:3px' }, s.hits, __rs, " + HIT_FMT + ") : null));", L)
    # memosprite skills / traces / eidolons: hits are not rendered individually -> mark the entry
    app = must_replace(app, "ms.skills.forEach(function (s) {\n    add(body, h('div', { class: 'ks' },",
                       "ms.skills.forEach(function (s) {\n    add(body, h('div', Object.assign({ class: 'ks' }, __lowAttrs(__lowList(s))),", L)
    app = must_replace(app, "kit.traces.forEach(function (t) { add(body, h('div', { class: 'ks' },",
                       "kit.traces.forEach(function (t) { add(body, h('div', Object.assign({ class: 'ks' }, __lowAttrs(__lowList(__findBy((__charRaw(m.charId) || {}).traces, 'id', t.id)))),", L)
    app = must_replace(app, "kit.eidolons.forEach(function (e) { add(body, h('div', { class: 'ks' + (e.rank > m.eidolon ? ' locked' : '') },",
                       "kit.eidolons.forEach(function (e) { add(body, h('div', Object.assign({ class: 'ks' + (e.rank > m.eidolon ? ' locked' : '') }, __lowAttrs(__lowList(__findBy((__charRaw(m.charId) || {}).eidolons, 'rank', e.rank)))),", L)
    # avatars: picker items, team slots, member editor row, damage bars, rotation rows, timeline filter chips / rows, kit summaries
    app = must_replace(app, "ava: c.name.slice(0, 1), color: elColor(c.element), title: c.id + ' ' + c.name }; },",
                       "ava: c.name.slice(0, 1), gava: c.id, color: elColor(c.element), title: c.id + ' ' + c.name }; },", L)
    app = must_replace(app, "r.ava ? h('div', { class: 'ava', style: 'background:' + r.color }, r.ava) : null,",
                       "r.gava ? __gava(r.gava, 'md') : r.ava ? h('div', { class: 'ava', style: 'background:' + r.color }, r.ava) : null,", L)
    app = must_replace(app, "h('div', { class: 'ava', style: 'background:' + elColor(c.element) }, (c.name || '?').slice(0, 1)),",
                       "h('div', { style: 'margin-bottom:5px;line-height:0' }, __gava(m.charId, 'md', c.name)),", L)
    app = must_replace(app, "elDot(c.element), h('b', null, c.name), h('span', { class: 'muted mini' }, (EL_ZH[c.element] || c.element) + ' · ' + (PATH_ZH[c.path] || c.path) + ' · ' + m.charId),",
                       "__gava(m.charId, 'sm', c.name), h('b', null, c.name), h('span', { class: 'muted mini' }, (EL_ZH[c.element] || c.element) + ' · ' + (PATH_ZH[c.path] || c.path) + ' · ' + m.charId),", L)
    app = must_replace(app, "h('div', { class: 'nm' }, elDot((CHAR_BY[x.charId] || {}).element), x.name),",
                       "h('div', { class: 'nm' }, __gava(x.charId, 'sm', x.name), x.name),", L)
    app = must_replace(app, "h('div', null, elDot((CHAR_BY[id] || {}).element), charName(id)),",
                       "h('div', null, __gava(id, 'sm', charName(id)), charName(id)),", L)
    app = must_replace(app, "CHAR_BY[id] ? elDot(CHAR_BY[id].element) : null, CHAR_BY[id] ? charName(id)",
                       "CHAR_BY[id] ? __gava(id, 'sm') : null, CHAR_BY[id] ? charName(id)", L)
    app = must_replace(app, "h('td', null, elDot((CHAR_BY[t.charId] || {}).element), t.actor || charName(t.charId)),",
                       "h('td', null, t.charId ? __gava(t.charId, 'sm', t.actor || charName(t.charId)) : elDot((CHAR_BY[t.charId] || {}).element), t.actor || charName(t.charId)),", L)
    app = must_replace(app, "h('summary', null, elDot((CHAR_BY[m.charId] || {}).element), charName(m.charId),",
                       "h('summary', null, __gava(m.charId, 'sm', charName(m.charId)), charName(m.charId),", L)
    return app


EF_HELPERS = r'''
  // ---- low-confidence markers (injected by pipeline/build_pages.py) ----
  var __LOW_FALLBACK = %s;
  function __efLowAttrs(sk) {
    var r = [];
    if (sk && sk.confidence === 'low') r.push(sk.lowReason || __LOW_FALLBACK);
    ((sk && sk.hits) || []).forEach(function (x) { if (x && x.confidence === 'low') { var t = x.lowReason || __LOW_FALLBACK; if (r.indexOf(t) < 0) r.push(t); } });
    return r.length ? { 'data-confidence': 'low', title: r.join('\n') } : {};
  }
  // ---- avatars (.gava placeholder; filled by the theme avatar script) ----
  var __EF_RAW = null;
  function __gava(id, size, name) {
    if (!__EF_RAW) { __EF_RAW = {}; ((window.__SIM_DATA__ || {}).characters || []).forEach(function (x) { if (x && x.id) __EF_RAW[x.id] = x; }); }
    var c = (typeof CHAR_BY_ID !== 'undefined' && CHAR_BY_ID.get(id)) || {}, raw = __EF_RAW[id] || {};
    return h('span', { class: 'gava ' + (size || 'md'), 'data-icon': raw.avatar || null, 'data-el': c.element || raw.element || '', 'data-name': name || c.name || raw.name || String(id || '') });
  }
''' % json.dumps(LOW_FALLBACK, ensure_ascii=False)


def patch_endfield_app(app):
    L = 'endfield'
    app = must_replace(app, "  var ZMD = window.ZMD;\n", "  var ZMD = window.ZMD;\n" + EF_HELPERS, L)
    # 技能伤害拆解 rows are the only per-skill entries the UI renders
    app = must_replace(app, "skillRows.append(h('div', { class: 'src-row' }, [",
                       "skillRows.append(h('div', Object.assign({ class: 'src-row' }, __efLowAttrs(sk)), [", L)
    # avatars: member card header, character select field, timeline lane labels
    app = must_replace(app, "h('span', { class: 'swatch', style: 'background:' + color, 'aria-hidden': 'true' }),\n        h('span', { class: 'mname', text: '#' + (idx + 1) + ' ' + safeText(char.name) }),",
                       "h('span', { class: 'swatch', style: 'background:' + color, 'aria-hidden': 'true' }),\n        __gava(char.id, 'md', char.name),\n        h('span', { class: 'mname', text: '#' + (idx + 1) + ' ' + safeText(char.name) }),", L)
    app = must_replace(app, "h('label', { for: p + 'char', text: '干员（名称 · 稀有度 · 属性 · 职业）' }),\n      charSel",
                       "h('label', { for: p + 'char', text: '干员（名称 · 稀有度 · 属性 · 职业）' }),\n      h('div', { style: 'display:flex;gap:8px;align-items:center' }, [__gava(m.charId, 'md'), charSel])", L)
    app = must_replace(app, "} }, [safeText(char && char.name), h('small', { text: '#' + (opIndex + 1) + ' · ' + laneItems.length + ' 个动作' })]), lane]));",
                       "} }, [__gava(member.charId, 'sm', char && char.name), safeText(char && char.name), h('small', { text: '#' + (opIndex + 1) + ' · ' + laneItems.length + ' 个动作' })]), lane]));", L)
    return app


GAMES = {
    'hsr': dict(engine_marker='HSR2 引擎打包产物', engine_global='HSR2', patch=patch_hsr_app, keep_text=True,
                required=['version', 'characters', 'lightcones', 'relicSets', 'monsters'], version_path=['version']),
    'endfield': dict(engine_marker='ZMD engine bundle', engine_global='ZMD', patch=patch_endfield_app, keep_text=False,
                     required=['meta', 'characters', 'weapons', 'equipItems', 'equipSuits', 'dummyPresets'],
                     version_path=['meta', 'source_commit']),
}


UNSHIPPED = {'data/zmd/kits.json': '源数据：EndfieldData kits（未随包发布）'}


def scrub_unshipped(js):
    # metadata/comments only (evidence `source` strings, `// source:` comments); calculations never read these
    for path, text in UNSHIPPED.items():
        js = js.replace(path, text)
    return js


def build(game, html_path, data_path):
    g = GAMES[game]
    html = open(html_path, encoding='utf-8').read()
    data_bytes = open(data_path, 'rb').read()
    data = json.loads(data_bytes)
    chars = data.get('characters') or {}
    attach_avatars(game, list(chars.values()) if isinstance(chars, dict) else list(chars), os.path.join(args.dist, game))
    data_bytes = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    version = data
    for k in g['version_path']:
        version = version[k]
    scripts = split_scripts(html)
    eng = [s for s in scripts if g['engine_marker'] in html[s[1]:s[1] + 300]]
    if len(eng) != 1:
        sys.exit(f'[{game}] engine script not found uniquely')
    ei = scripts.index(eng[0])
    app_s = scripts[ei + 1]
    engine_js, embedded = cut_data(html[eng[0][1]:eng[0][2]], game)
    app_js = g['patch'](html[app_s[1]:app_s[2]])
    digest = hashlib.sha256(data_bytes).hexdigest()[:12]
    cfg = {'game': game, 'url': f'{rel()}data/{game}.json?v={digest}', 'engineGlobal': g['engine_global'],
           'requiredKeys': g['required'], 'versionPath': g['version_path'], 'version': version, 'keepText': g['keep_text']}
    if game == 'endfield':
        # data/zmd/kits.json is a workspace file of the original page, not shipped: plain-text mention only, never a path/link
        engine_js = scrub_unshipped(engine_js)
        app_js = scrub_unshipped(app_js)
    out = (html[:eng[0][0]] + '<script type="text/x-sim-deferred" data-sim="engine">' + engine_js + '</script>' +
           html[eng[0][2] + 9:app_s[0]] + '<script type="text/x-sim-deferred" data-sim="app">' + app_js + '</script>\n' +
           loader(cfg) + html[app_s[2] + 9:])
    out_dir = os.path.join(args.dist, game)
    os.makedirs(out_dir, exist_ok=True)
    final = os.path.join(out_dir, 'index.html')
    with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8') as t:
        t.write(out)
    apply_theme(game, t.name, final)
    os.unlink(t.name)
    os.makedirs(os.path.join(pkg_root(game), 'data'), exist_ok=True)
    with open(os.path.join(pkg_root(game), 'data', f'{game}.json'), 'wb') as f:
        f.write(data_bytes)
    note = ''
    if json.dumps(embedded, sort_keys=True) != json.dumps({k: v for k, v in data.items()}, sort_keys=True):
        note = ' (data differs from the page\'s original embedded DATA)'
    print(f'{game}: {final} ({len(out) // 1024} KiB html, was {len(html) // 1024} KiB) + data/{game}.json '
          f'version={version} v={digest}{note}')


NGINX = r'''# Example nginx config for the static simulator build (dist/).
# Works at the site root or under a sub-path: all page/asset/data URLs are relative.
# Replace /sim/ and the alias path with your own values.

# gzip is usually set in the http{} block:
gzip on;
gzip_comp_level 6;
gzip_min_length 1024;
gzip_vary on;
gzip_types text/html text/css application/javascript text/javascript application/json;

server {
    listen 80;
    server_name _;

    # ---- served under a sub-path, e.g. https://example.com/sim/ ----
    location = /sim { return 301 $scheme://$http_host/sim/; }
    location /sim/ {
        alias /srv/sim/dist/;           # trailing slash required with alias
        index index.html;
        # /sim/hsr -> /sim/hsr/ (the pages fetch ../data/*.json, which needs the trailing slash)
        try_files $uri $uri/ =404;
        charset utf-8;
        charset_types application/json application/javascript text/css;

        # HTML: always revalidate so a new build is picked up immediately
        location ~* \.html$ { add_header Cache-Control "no-cache"; }
        # data: the pages request ../data/<game>.json?v=<sha256 prefix>, so a content change is a new URL;
        # keep a short max-age + revalidation in case the file is fetched without ?v
        location ~* /data/.*\.json$ { add_header Cache-Control "public, max-age=300, must-revalidate"; }
        # theme assets are not fingerprinted: cache for a day
        location ~* \.(css|js)$ { add_header Cache-Control "public, max-age=86400"; }
    }

    # ---- or at the site root: ----
    # root /srv/sim/dist;
    # location / { try_files $uri $uri/ =404; }
}
'''

if __name__ == '__main__':
    games = [g.strip() for g in args.games.split(',') if g.strip()]
    if 'hsr' in games:
        build('hsr', args.hsr_html, args.hsr_data)
    if 'endfield' in games:
        build('endfield', args.endfield_html, args.endfield_data)
    if 'ww' in games:  # engine-driven page: pipeline/ww/page/build_page.py (no attachment needed)
        sys.path.insert(0, os.path.join(HERE, 'ww', 'page'))
        import build_page as ww_page
        ww_page.build(args.dist, args.ww_data, args.theme_script, layout=args.layout, theme_apply=apply_theme, avatar_fn=attach_avatars)
    ng = os.path.join(args.dist, 'nginx.conf.example')
    if os.path.exists(ng):
        print('nginx.conf.example exists, left untouched')
    else:
        open(ng, 'w').write(NGINX if not PER_GAME else NGINX.replace('build (dist/).', 'build, per-game layout (dist3/: <game>/{index.html,assets/,data/}).')
                            .replace('../data/', 'data/').replace('/srv/sim/dist', '/srv/sim/dist3'))
        print('wrote', ng)
