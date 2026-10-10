#!/usr/bin/env python3
"""Compare two Endfield DATA jsons (generated vs reference, or old vs new build).

usage: diff_endfield.py [A] [B] [--examples N] [--field SUBSTR] [--json report.json] [--changes]
A defaults to ../out/endfield.json, B to the reference extracted from the simulator HTML.
Per top-level section: counts, missing/extra ids, per-field (normalised path) mismatch counts
with examples. Lists of dicts are aligned by 'id' / 'level' / 'stage' / 'potential' / 'count' /
'rank' when unique, otherwise by index. Numeric tolerance 1e-6 (abs or rel).
--changes prints a concrete per-entity change list (for old->new build comparisons)."""
import json, argparse, os
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument('a', nargs='?', default=os.path.join(HERE, '..', 'out', 'endfield.json'))
ap.add_argument('b', nargs='?', default=os.path.join(HERE, '..', '..', 'schema', 'endfield_embedded_DATA.json'))
ap.add_argument('--examples', type=int, default=3)
ap.add_argument('--field', default=None)
ap.add_argument('--json', default=None)
ap.add_argument('--changes', action='store_true')
ap.add_argument('--ignore', action='append', default=[], help='path prefixes to skip (e.g. meta.generated_at)')
args = ap.parse_args()
A = json.load(open(args.a)); B = json.load(open(args.b))
TOL = 1e-6
KEYS = ('id', 'level', 'stage', 'potential', 'count', 'rank', 'termId', 'attrIndex', 'source')

def num_eq(x, y):
    return abs(x - y) <= TOL or abs(x - y) <= TOL * max(abs(x), abs(y))

def eq(o, r):
    if isinstance(o, bool) or isinstance(r, bool): return o is r
    if isinstance(o, (int, float)) and isinstance(r, (int, float)): return num_eq(o, r)
    if isinstance(o, list) and isinstance(r, list):
        return len(o) == len(r) and all(eq(x, y) for x, y in zip(o, r))
    if isinstance(o, dict) and isinstance(r, dict):
        return set(o) == set(r) and all(eq(o[k], r[k]) for k in o)
    return o == r

def keyof(lst):
    for k in KEYS:
        if lst and all(isinstance(e, dict) and k in e for e in lst):
            v = [json.dumps(e[k]) for e in lst]
            if len(set(v)) == len(v): return k
    return None

def short(v, n=180):
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + '…'

class Acc:
    def __init__(s): s.checked = Counter(); s.bad = Counter(); s.ex = defaultdict(list); s.changes = []
    def add(s, path, ok, where, o, r):
        if any(path.startswith(i) for i in args.ignore): return
        s.checked[path] += 1
        if not ok:
            s.bad[path] += 1
            s.changes.append((where, path, o, r))
            if len(s.ex[path]) < args.examples: s.ex[path].append((where, o, r))

def walk(o, r, path, where, acc):
    if isinstance(o, dict) and isinstance(r, dict):
        for k in list(r) + [k for k in o if k not in r]:
            p = f'{path}.{k}' if path else k
            if k not in o: acc.add(p, False, where, '<missing key>', short(r[k])); continue
            if k not in r: acc.add(p, False, where, short(o[k]), '<absent in B>'); continue
            walk(o[k], r[k], p, where, acc)
        return
    if isinstance(o, list) and isinstance(r, list):
        k = keyof(r) or keyof(o)
        if k and keyof(o) == k and keyof(r) == k:
            om = {json.dumps(e[k]): e for e in o}; rm = {json.dumps(e[k]): e for e in r}
            for kk in rm:
                if kk not in om: acc.add(path + '[]', False, f'{where}/{kk}', '<missing item>', short(rm[kk]))
                else: walk(om[kk], rm[kk], path + '[]', f'{where}/{json.loads(kk)}', acc)
            for kk in om:
                if kk not in rm: acc.add(path + '[]', False, f'{where}/{kk}', short(om[kk]), '<extra item>')
            return
        if len(o) != len(r) or all(not isinstance(e, (dict, list)) for e in o + r):
            acc.add(path, eq(o, r), where, short(o), short(r)); return
        for i, (x, y) in enumerate(zip(o, r)): walk(x, y, path + '[]', f'{where}#{i}', acc)
        return
    acc.add(path, eq(o, r), where, short(o), short(r))

def as_map(v):
    if isinstance(v, list) and keyof(v) == 'id': return {e['id']: e for e in v}
    return None

report = {}
for sec in list(B) + [k for k in A if k not in B]:
    if sec not in A: print(f'\n=== {sec}: MISSING in A'); continue
    if sec not in B: print(f'\n=== {sec}: only in A'); continue
    a, b = A[sec], B[sec]
    acc = Acc()
    ma, mb = as_map(a), as_map(b)
    if ma is None and isinstance(a, dict) and isinstance(b, dict) and sec not in ('meta', 'constants', 'composites') \
            and all(isinstance(v, dict) for v in list(a.values()) + list(b.values())):
        ma, mb = a, b
    if ma is not None and mb is not None:
        miss = sorted(set(mb) - set(ma)); extra = sorted(set(ma) - set(mb)); shared = [k for k in mb if k in ma]
        for k in shared: walk(ma[k], mb[k], '', k, acc)
        full = sum(1 for k in shared if eq(ma[k], mb[k]))
        print(f'\n=== {sec}: A={len(ma)} B={len(mb)} shared={len(shared)} fully-equal={full}')
        print(f'  only in B ({len(miss)}): {miss[:40]}')
        print(f'  only in A ({len(extra)}): {extra[:40]}')
    else:
        walk(a, b, '', sec, acc); miss = extra = []; full = None
        print(f'\n=== {sec}')
    rows = []
    for p in sorted(acc.checked):
        c, bad = acc.checked[p], acc.bad[p]
        rows.append({'field': p, 'checked': c, 'mismatch': bad})
        if args.field and args.field not in p: continue
        if bad:
            print(f'  {p:60s} {c - bad:6d}/{c:<6d} ok ({100 * (1 - bad / c):6.2f}%)')
            for w, o, r in acc.ex[p]: print(f'      @{w}\n        A={o}\n        B={r}')
    tot = sum(acc.checked.values()); bad = sum(acc.bad.values())
    print(f'  leaf match: {tot - bad}/{tot} ({100 * (1 - bad / max(tot, 1)):.2f}%)')
    if args.changes and acc.changes:
        print('  -- changes:')
        for w, p, o, r in acc.changes[:400]: print(f'    {w} :: {p}: {r} -> {o}')
    report[sec] = {'onlyInB': miss, 'onlyInA': extra, 'fullyEqual': full, 'fields': rows}
if args.json: json.dump(report, open(args.json, 'w'), ensure_ascii=False, indent=1)
