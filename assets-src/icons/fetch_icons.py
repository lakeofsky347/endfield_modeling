#!/usr/bin/env python3
"""Fetch official character head icons for the three simulators -> 128x128 webp.

Usage:
  python3 fetch_icons.py   # needs Pillow [--game ww|hsr|endfield|all] [--force]

Incremental: an id whose <id>.webp exists and is already in manifest.json is skipped.
--force re-downloads (ignores raw cache) and re-encodes.
Network: public sources only, single thread, >=1.1 s between requests, no auth.
Rosters are read-only: <repo>/dist/<game>/data/<game>.json.
Outputs (per game dir): <id>.webp, manifest.json ({id:{src,file,name,fetched}, "_missing":[...]}), sources.json.
Raw downloads cached under raw/<game>/.
"""
import argparse, datetime, io, json, os, re, sys, time, urllib.request, urllib.error
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
GD = os.path.dirname(os.path.dirname(ROOT))   # repo root
UA = 'gamedata-icons/1.0 (single-threaded, 1 req/s; Skylake damage-sim asset pack)'
SIZE, QUALITY, MAX_BYTES = 128, 80, 15 * 1024
COPYRIGHT = '头像版权归各游戏厂商所有（鸣潮：库洛游戏 Kuro Games；崩坏：星穹铁道：米哈游 HoYoverse；明日方舟：终末地：上海鹰角网络 Hypergryph/Gryphline）。随包分发前需要 Skylake 自己评估。'
_last = [0.0]
LOG = []

def now(): return datetime.datetime.now().astimezone().isoformat(timespec='seconds')

def _log(url, status):
    LOG.append({'t': now(), 'url': url, 'status': status})
    os.makedirs(os.path.join(ROOT, 'raw'), exist_ok=True)
    with open(os.path.join(ROOT, 'raw', 'requests.log'), 'a') as f: f.write(f'{now()} {status} {url}\n')

def fetch(url):
    wait = 1.1 - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    _last[0] = time.time()
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read(); ctype = r.headers.get('Content-Type', '')
        _log(url, 200)
        if 'text/html' in ctype and not url.endswith('.html'):
            raise RuntimeError('HTML 页面而非图片/数据（可能是验证码或登录墙）')
        return data
    except urllib.error.HTTPError as e:
        _log(url, e.code); raise RuntimeError(f'HTTP {e.code}')

def cached(game, url, name, force):
    d = os.path.join(ROOT, 'raw', game); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    if os.path.exists(p) and not force:
        return open(p, 'rb').read(), None
    data = fetch(url); open(p, 'wb').write(data)
    open(p + '.retrieved', 'w').write(now() + ' ' + url + '\n')
    return data, now()

def raw_time(game, name):
    p = os.path.join(ROOT, 'raw', game, name + '.retrieved')
    return open(p).read().split()[0] if os.path.exists(p) else None

def encode(data, dst):
    im = Image.open(io.BytesIO(data)); im.load(); im = im.convert('RGBA')
    w, h = im.size; s = SIZE / max(w, h)
    im2 = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
    canvas = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    canvas.paste(im2, ((SIZE - im2.width) // 2, (SIZE - im2.height) // 2))
    for q in (QUALITY, 75, 70, 65, 60):
        buf = io.BytesIO(); canvas.save(buf, 'WEBP', quality=q, method=6, alpha_quality=90)
        if buf.tell() <= MAX_BYTES: break
    open(dst, 'wb').write(buf.getvalue())
    return {'bytes': buf.tell(), 'quality': q, 'orig_size': [w, h]}

strip = lambda s: re.sub(r'</?unbreak>', '', s or '').replace('•', '·').replace(' ', '')

# ---------------- per-game source adapters: return [(id, name, url, rawname, match_rule)] , unmatched ----------------
def src_ww(force):
    roster = json.load(open(f'{GD}/dist/ww/data/ww.json'))['resonators']
    cache = f'{GD}/cache/encore/3.7.8/api-v2.encore.moe__api__zh-Hans__character'
    if os.path.exists(cache) and not force:
        roles = json.load(open(cache))['roleList']; list_src = cache + '（本地 encore 缓存，只读）'
    else:
        roles = json.loads(cached('ww', 'https://api-v2.encore.moe/api/zh-Hans/character', '_character_list.json', force)[0])['roleList']
        list_src = 'https://api-v2.encore.moe/api/zh-Hans/character'
    by = {r['Id']: r for r in roles}; items, unm = [], []
    for r in roster:
        x = by.get(r['id'])
        if not x: unm.append({'id': r['id'], 'name': r['name'], 'reason': 'encore 角色表中无此 id'}); continue
        if strip(x['Name']) != strip(r['name']):
            unm.append({'id': r['id'], 'name': r['name'], 'reason': f"id 存在但名字不同（encore：{x['Name']}），按要求不猜"}); continue
        url = x['RoleHeadIcon']
        items.append((str(r['id']), r['name'], url, os.path.basename(url), 'id 一致且中文名一致'))
    return items, unm, list_src

def src_hsr(force):
    roster = json.load(open(f'{GD}/dist/hsr/data/hsr.json'))['characters']
    cache = f'{GD}/cache/nanoka/hsr/4.6.51/character.json'
    if os.path.exists(cache) and not force:
        chars = json.load(open(cache)); list_src = cache + '（本地 nanoka 缓存，只读；原 URL https://static.nanoka.cc/hsr/4.6.51/character.json）'
    else:
        chars = json.loads(cached('hsr', 'https://static.nanoka.cc/hsr/4.6.51/character.json', '_character.json', force)[0])
        list_src = 'https://static.nanoka.cc/hsr/4.6.51/character.json'
    items, unm = [], []
    for cid, v in roster.items():
        x = chars.get(cid)
        if not x: unm.append({'id': cid, 'name': v['name'], 'reason': 'nanoka 角色表中无此 id'}); continue
        z, n = strip(x.get('zh')), strip(v['name'])
        if z == n: rule = 'id 一致且中文名一致'
        elif re.sub(r'（[^）]*）$', '', n) == z: rule = f'id 一致；数据名去掉命途后缀后与 nanoka「{x.get("zh")}」一致'
        elif x.get('zh') == '{NICKNAME}' and n.startswith('开拓者'): rule = 'id 一致；nanoka 名为游戏昵称占位符 {NICKNAME}（开拓者）'
        else:
            unm.append({'id': cid, 'name': v['name'], 'reason': f"id 存在但名字不同（nanoka：{x.get('zh')}），按要求不猜"}); continue
        url = f'https://static.nanoka.cc/assets/hsr/avatarroundicon/{cid}.webp'
        items.append((cid, v['name'], url, f'{cid}.webp', rule))
    return items, unm, list_src

BAKER_SHA = '957bbd4180dc33a4b8fab6c12dbfcc143a1e9006'
def src_endfield(force):
    roster = json.load(open(f'{GD}/dist/endfield/data/endfield.json'))['characters']
    lst = json.loads(cached('endfield', f'https://api.github.com/repos/Wanye-7300/baker-dx/contents/assets/extracted/avatar/operator?ref={BAKER_SHA}', '_listing.json', force)[0])
    files = {re.sub(r'^icon_round_|\.png$', '', f['name']): f['name'] for f in lst if f['name'].endswith('.png')}
    items, unm = [], []
    for c in roster:
        fn = files.get(c['id'])
        if not fn:
            unm.append({'id': c['id'], 'name': c['name'], 'reason': 'baker-dx operator 头像中没有与此 id 同名的文件' + ('（数据中 playable=false）' if not c.get('playable') else '') + '，不套用其他 id 的图'}); continue
        url = f'https://raw.githubusercontent.com/Wanye-7300/baker-dx/{BAKER_SHA}/assets/extracted/avatar/operator/{fn}'
        items.append((c['id'], c['name'], url, fn, '文件名内含与数据完全相同的角色 id'))
    return items, unm, f'https://github.com/Wanye-7300/baker-dx/tree/{BAKER_SHA}/assets/extracted/avatar/operator'

SOURCES = {
 'ww': {'name': 'encore.moe（api.encore.moe 资源 + api-v2 角色表）', 'site': 'https://encore.moe',
        'robots': 'encore.moe/robots.txt：User-agent * 无 Disallow（只列 Allow）；api.encore.moe 与 api-v2.encore.moe 的 /robots.txt 返回 404（无 robots）。',
        'terms': 'https://encore.moe/terms（2026-07-24 更新）：要求合法、尊重地使用，不得滥用、干扰服务运行或绕过访问控制；未禁止批量下载或自动化访问。About 页注明提供公开 API，素材来自游戏解包（WW_Asset）。',
        'snapshot': 'raw/_robots/encore.moe_robots.txt, raw/_robots/encore_terms.html'},
 'hsr': {'name': 'nanoka.cc（static.nanoka.cc avatarroundicon）', 'site': 'https://hsr.nanoka.cc',
         'robots': 'hsr.nanoka.cc、nanoka.cc、static.nanoka.cc 的 /robots.txt 均返回 404（无 robots 限制）。',
         'terms': '未找到使用条款/服务条款页面；站点前端文案仅声明 “All game-related images and assets are copyrighted and trademarked by {厂商}”。未见禁止自动化访问的条文。',
         'snapshot': 'raw/_robots/hsr.nanoka.cc_index.html'},
 'endfield': {'name': 'GitHub Wanye-7300/baker-dx assets/extracted/avatar/operator（游戏/森空岛解包头像，156×156 PNG）', 'site': 'https://github.com/Wanye-7300/baker-dx',
              'robots': 'raw.githubusercontent.com/robots.txt 返回 404；目录列表用 GitHub 公开 REST API（未登录，1 次请求）。',
              'terms': '仓库 LICENSE 为 MIT（覆盖代码）；assets/extracted/README.md 声明：美术资源著作权归上海鹰角网络（Hypergryph）所有，仓库中的素材“仅供个人学习、研究参考之用，不涉及任何商业用途”，权利人通知即删除。GitHub 服务条款允许访问公开仓库内容。注意：该声明意味着随包再分发尤其需要评估。',
              'alternatives_considered': 'endfield.wiki.gg Category:Operator_icons（120×120，robots 允许，但 Content-Signal use=reference，且需按英文名对应、尺寸小于 128）；arknights.win 媒体包（按英文名命名，非商用）。选 baker-dx 是因为文件名直接带游戏角色 id，不需要按名字猜。',
              'snapshot': 'raw/_robots/bakerdx_LICENSE, raw/_robots/bakerdx_extracted_README.md, raw/_robots/gh_bakerdx_repo.json, raw/_robots/gh_bakerdx_commit.json, raw/_robots/endfield.wiki.gg_robots.txt'},
}
ADAPT = {'ww': src_ww, 'hsr': src_hsr, 'endfield': src_endfield}

def run(game, force):
    out = os.path.join(ROOT, game); os.makedirs(out, exist_ok=True)
    mp, sp = os.path.join(out, 'manifest.json'), os.path.join(out, 'sources.json')
    old = json.load(open(mp)) if os.path.exists(mp) else {}
    olds = json.load(open(sp)) if os.path.exists(sp) else {}
    items, unm, list_src = ADAPT[game](force)
    man, detail, errors = {}, dict(olds.get('files', {})), []
    for cid, name, url, rawname, rule in items:
        dst = os.path.join(out, f'{cid}.webp')
        if not force and os.path.exists(dst) and cid in old and old[cid].get('src') == url:
            man[cid] = old[cid]; continue
        try:
            data, t = cached(game, url, rawname, force)
        except Exception as e:
            errors.append({'id': cid, 'name': name, 'url': url, 'error': str(e)})
            unm.append({'id': cid, 'name': name, 'reason': f'下载失败已跳过：{e}'}); continue
        info = encode(data, dst)
        man[cid] = {'src': url, 'file': f'{cid}.webp', 'name': name, 'fetched': t or raw_time(game, rawname) or now()}
        detail[cid] = {**info, 'match_rule': rule}
    man['_missing'] = sorted({str(u['id']) for u in unm})
    json.dump(man, open(mp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    sizes = {k: os.path.getsize(os.path.join(out, v['file'])) for k, v in man.items() if k != '_missing'}
    for k in sizes: detail.setdefault(k, {})['bytes'] = sizes[k]
    detail = {k: v for k, v in detail.items() if k in sizes}
    big = max(sizes.items(), key=lambda kv: kv[1]) if sizes else (None, 0)
    srcs = {'source': {**SOURCES[game], 'roster_list': list_src}, 'copyright': COPYRIGHT,
            'output': {'size': f'{SIZE}x{SIZE}', 'format': 'webp RGBA（等比缩放居中，透明填充）', 'quality': f'{QUALITY}（超过 15KB 时依次降到 75/70/65/60）'},
            'stats': {'roster': len({str(i[0]) for i in items} | {str(u['id']) for u in unm}), 'matched': len(sizes),
                      'total_bytes': sum(sizes.values()), 'max_file': {'id': big[0], 'bytes': big[1]},
                      'over_15kb': sorted(k for k, v in sizes.items() if v > MAX_BYTES)},
            'unmatched': unm, 'errors': errors, 'files': detail,
            'request_log': 'raw/requests.log（累计）；每个原始文件旁有 .retrieved 记录下载时间与 URL', 'requests_this_run': len(LOG), 'updated_at': now()}
    json.dump(srcs, open(sp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    LOG.clear()
    print(f"{game}: matched {len(sizes)} / missing {len(man['_missing'])}; total {sum(sizes.values())} B; max {big}; >15KB {len(srcs['stats']['over_15kb'])}")

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--game', default='all', choices=['all', 'ww', 'hsr', 'endfield']); ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    for g in (['ww', 'hsr', 'endfield'] if a.game == 'all' else [a.game]): run(g, a.force)
