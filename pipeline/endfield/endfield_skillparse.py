"""Character-skill interpretation for build_endfield.py.

* fingerprint_matches/from_reference: reuse interpretive fields of an unchanged skill.
* parse: best-effort heuristic for new/changed skills (flagged with an 自动解析 warning).
"""
import re
from collections import OrderedDict

AUTO_WARNING = '自动解析：技能源数据与参考构建不同或为新增，倍率/命中归属由启发式生成，需人工复核'
FALLBACK_ELEMENT = '本技能未读取到可确认的直接生命伤害属性，当前按干员元素回退；投射物/召唤物等间接伤害需另行核实'
MIXED_ELEMENT = '已读取伤害动作包含混合属性，当前按干员元素回退；投射物/召唤物等间接伤害需另行核实'
BB_FALLBACK = '没有直接伤害描述，使用聚合黑板倍率回退（取最大 atk_scale 值）；命中次数和互斥状态未核实'
HIT_COUNT_WARNING = re.compile(r'次数.*未确认|层数.*未确认|尚未可靠关联|普通攻击次数未建模')
BLACKBOARD_WARNING = re.compile(r'聚合黑板倍率回退')

INTERP_SKILL = ['kind', 'attackIndex', 'variant', 'variantCn', 'alternate', 'name', 'aoe', 'reviewedMechanics',
                'requiresBroken', 'usesTextMultipliers', 'paramLabels', 'hitCount', 'hits', 'desc', 'conditional']
INTERP_LEVEL = ['atkScale', 'multipliers', 'multiplierLabels', 'excludedMultiplierLabels', 'totalMultiplier',
                'poise', 'poiseLabels', 'excludedPoiseLabels', 'atb', 'usp', 'duration']
SKILL_ORDER = ['id', 'kind', 'attackIndex', 'variant', 'variantCn', 'alternate', 'name', 'castTime', 'durationFrame',
               'aoe', 'attackRangeType', 'damageElement', 'damageElementEvidence', 'reviewedMechanics', 'requiresBroken',
               'usesTextMultipliers', 'paramLabels', 'hitCount', 'hits', 'desc', 'conditional', 'warnings', 'levels']
LEVEL_ORDER = ['level', 'atkScale', 'multipliers', 'multiplierLabels', 'excludedMultiplierLabels', 'totalMultiplier',
               'poise', 'poiseLabels', 'excludedPoiseLabels', 'cooldown', 'costType', 'costValue', 'atb', 'usp',
               'duration', 'bb', 'params']
CN_NUM = {'0': '0', '1': '一', '2': '二', '3': '三', '4': '四', '5': '五'}
CN_TOK = {'end': '收尾', 'floating': '空中', 'loop': '循环', 'start': '起手', 'block': '格挡'}
KIND_CN = {'attack': '普攻', 'normal': '战技', 'combo': '连携技', 'ultimate': '终结技', 'power': '处决攻击',
           'dash': '冲刺攻击', 'plunge': '下落攻击', 'passive': '被动', 'other': 'other'}
ORDINAL = {1: '第一段', 2: '第二段', 3: '第三段', 4: '第四段', 5: '第五段'}


def _eqnum(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) <= 1e-6
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_eqnum(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_eqnum(x, y) for x, y in zip(a, b))
    return a == b


def element_of(facts):
    types = {e['damageType'] for e in facts['evidence']}
    return types


def resolve_element(facts, dt2el):
    types = element_of(facts)
    if len(types) == 1 and next(iter(types)) in dt2el:
        return dt2el[next(iter(types))], None
    # reference leaves damageElement null on fallback; the engine then uses the operator element
    return None, (MIXED_ELEMENT if len(types) > 1 else FALLBACK_ELEMENT)


def fingerprint_matches(facts, ref):
    if ref.get('durationFrame') != facts['durationFrame'] or ref.get('attackRangeType') != facts['attackRangeType']:
        return False
    if [(e['pointer'], e['damageType']) for e in ref.get('damageElementEvidence', [])] != \
       [(e['pointer'], e['damageType']) for e in facts['evidence']]:
        return False
    if len(ref['levels']) != len(facts['levels']):
        return False
    for a, b in zip(ref['levels'], facts['levels']):
        for k in ('level', 'cooldown', 'costType', 'costValue', 'bb', 'params'):
            if not _eqnum(a.get(k), b.get(k)):
                return False
    return True


def _assemble(facts, interp, lvl_interp, warnings, dt2el):
    el, el_warn = resolve_element(facts, dt2el)
    s = OrderedDict()
    s['id'] = facts['id']
    s.update(interp)
    s['castTime'] = round(facts['durationFrame'] / 60.0, 4) if facts['durationFrame'] is not None else None
    s['durationFrame'] = facts['durationFrame']
    s['attackRangeType'] = facts['attackRangeType']
    s['damageElement'] = el
    s['damageElementEvidence'] = facts['evidence']
    s['warnings'] = warnings
    levels = []
    for lv, li in zip(facts['levels'], lvl_interp):
        L = OrderedDict(lv); L.update(li)
        levels.append(OrderedDict((k, L.get(k)) for k in LEVEL_ORDER))
    s['levels'] = levels
    return OrderedDict((k, s.get(k)) for k in SKILL_ORDER)


def from_reference(facts, ref, dt2el):
    interp = OrderedDict((k, ref.get(k)) for k in INTERP_SKILL)
    lvl = [OrderedDict((k, L.get(k)) for k in INTERP_LEVEL) for L in ref['levels']]
    return _assemble(facts, interp, lvl, list(ref.get('warnings', [])), dt2el)


# ---------------------------------------------------------------- heuristic
def naming(sid):
    tail = sid.split('_', 2)[2]
    tail = tail.split('_', 1)[1] if '_' in tail else ''
    m = re.match(r'attack(\d+)(?:_(.*))?$', tail)
    if m:
        idx = int(m.group(1)); var = m.group(2) or ''
        return 'attack', idx, var
    for pre, kind in (('combo_skill', 'combo'), ('normal_skill', 'normal'), ('ultimate_skill', 'ultimate'),
                      ('power_attack', 'power'), ('dash_attack', 'dash'), ('plunging_attack', 'plunge'),
                      ('passive', 'passive')):
        if tail.startswith(pre):
            return kind, None, tail[len(pre):].lstrip('_')
    return 'other', None, tail


def variant_cn(var):
    toks = [t for t in re.split(r'_', var) if t and t not in ('combo', 'skill')]
    out = []
    for t in toks:
        m = re.match(r'([a-z]+)(\d*)$', t)
        if t in CN_NUM: out.append(CN_NUM[t])
        elif m and m.group(1) in CN_TOK: out.append(CN_TOK[m.group(1)])
        elif m: out.append(m.group(1))
        else: out.append(t)
    return '·'.join(out)


def _num(v):
    try:
        return float(str(v).strip().rstrip('%'))
    except ValueError:
        return None


EFFECT_WORDS = re.compile(r'提升|提高|增加|脆弱|降低|减少|加成')
MULT_WORDS = re.compile(r'倍率|伤害')


def parse(facts, dt2el):
    sid = facts['id']
    kind, idx, var = naming(sid)
    vcn = variant_cn(var)
    if kind == 'attack' and idx in ORDINAL and not var:
        name = f'普攻·{ORDINAL[idx]}'
    elif kind == 'attack':
        name = '·'.join(x for x in ('普攻', ORDINAL.get(idx, ''), vcn) if x)
    else:
        name = '·'.join(x for x in (KIND_CN[kind], vcn) if x)
    warnings = [AUTO_WARNING]
    lvl_interp = []
    labels0 = [p['name'] for p in facts['levels'][0]['params']] if facts['levels'] else []
    uses_text = False
    for lv in facts['levels']:
        bb = lv['bb']
        mults, mlabels, xm, poise, plabels, xp = [], [], [], 0.0, [], []
        for p in lv['params']:
            v = _num(p['value'])
            if v is None: continue
            if '失衡' in p['name']:
                poise += v; plabels.append(p['name'])
            elif str(p['value']).strip().endswith('%') and MULT_WORDS.search(p['name']):
                if EFFECT_WORDS.search(p['name']): xm.append(p['name'])
                else: mults.append(round(v / 100.0, 6)); mlabels.append(p['name'])
        if mults: uses_text = True
        atk = bb.get('atk_scale')
        if not mults and isinstance(atk, (int, float)):
            mults = [round(max(v for k, v in bb.items() if 'atk_scale' in k and isinstance(v, (int, float))), 6)]
        lvl_interp.append(OrderedDict([
            ('atkScale', atk), ('multipliers', mults), ('multiplierLabels', mlabels), ('excludedMultiplierLabels', xm),
            ('totalMultiplier', round(sum(mults), 6)), ('poise', poise if plabels else bb.get('poise')),
            ('poiseLabels', plabels), ('excludedPoiseLabels', xp),
            ('atb', bb.get('atb')), ('usp', bb.get('usp')), ('duration', bb.get('duration'))]))
    if not uses_text and any(L['multipliers'] for L in lvl_interp):
        warnings.append(BB_FALLBACK)
    if not facts['evidence']:
        warnings.append(FALLBACK_ELEMENT)
    interp = OrderedDict([
        ('kind', kind), ('attackIndex', idx), ('variant', var), ('variantCn', vcn),
        ('alternate', 'ult' in var), ('name', name), ('aoe', facts['attackRangeType'] == 1),
        ('reviewedMechanics', None), ('requiresBroken', kind == 'power'), ('usesTextMultipliers', uses_text),
        ('paramLabels', labels0), ('hitCount', len(facts['units'])), ('hits', facts['units']),
        ('desc', ''), ('conditional', False)])
    s = _assemble(facts, interp, lvl_interp, warnings, dt2el)
    # extra marker fields (only on heuristically parsed skills; absent from reused/reference skills)
    s['confidence'] = 'low'
    s['lowReason'] = AUTO_WARNING
    return s


def warning_counts(skills):
    """counted per skill (a skill with two matching warnings counts once)."""
    rules = OrderedDict([
        ('nonDamageLabels', lambda w: '是效果参数' in w),
        ('ordinaryBranches', lambda w: '分支' in w or w.startswith('默认')),
        ('unresolvedHitCounts', lambda w: bool(HIT_COUNT_WARNING.search(w))),
        ('unresolvedPoiseCounts', lambda w: '失衡' in w and '未确认' in w),
        ('blackboardFallback', lambda w: bool(BLACKBOARD_WARNING.search(w)))])
    return OrderedDict((k, sum(1 for s in skills if any(f(w) for w in s['warnings']))) for k, f in rules.items())


def element_coverage(skills, policy):
    conf = sum(1 for s in skills if len({e['damageType'] for e in s['damageElementEvidence']}) == 1)
    return OrderedDict([('confirmedFromEnabledHpUnits', conf), ('fallback', len(skills) - conf), ('policy', policy)])
