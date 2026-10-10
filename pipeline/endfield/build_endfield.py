#!/usr/bin/env python3
"""Rebuild the Endfield simulator DATA json from rmxlinux/EndfieldData.

usage: build_endfield.py --src REPO [--ref PREV.json] [--out OUT.json]

Everything that is a fact in the repo (tables, blackboards, skill timelines, text) is computed
here. A few naming conventions of the original builder are not present in the repo at all
(attribute key names / short CN labels, weapon-type labels, element->attribute slots, the
documented assumption strings); they live in endfield_conventions.py as constants.
Interpretive skill fields (which description params are damage multipliers, warnings, variant
labels, reviewed mechanics) are reused from --ref when the skill's source fingerprint (blackboard,
params, costs, damage units) is unchanged; otherwise endfield_skillparse.py produces them and
marks the skill with an "自动解析" warning.
"""
import argparse, hashlib, json, os, re, subprocess, sys, datetime
from collections import OrderedDict, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import endfield_conventions as CONV
import endfield_skillparse as SP

ap = argparse.ArgumentParser()
ap.add_argument('--src', default=os.path.join(os.path.dirname(os.path.dirname(HERE)), 'zmd-EndfieldData-8c5305b'))   # clone of rmxlinux/EndfieldData @8c5305b (not committed)
ap.add_argument('--ref', default=os.path.join(os.path.dirname(os.path.dirname(HERE)), 'schema', 'endfield_embedded_DATA.json'),
                help='previous build to reuse interpretive skill fields from ("" = none)')
ap.add_argument('--out', default=os.path.join(HERE, '..', 'out', 'endfield.json'))
ap.add_argument('--generated-at', default=None)
args = ap.parse_args()
TC = os.path.join(args.src, 'TableCfg')
SKD = os.path.join(args.src, 'Json', 'SkillData')
READ = set()

def tab(name):
    p = os.path.join(TC, name + '.json'); READ.add(p)
    return json.load(open(p, encoding='utf-8'))

I18N = tab('I18nTextTable_CN')

def T(o):
    if o is None: return ''
    if isinstance(o, dict):
        t = I18N.get(str(o.get('id')))
        return t if t is not None else (o.get('text') or '')
    return str(o)

# ------------------------------------------------------------------ constants / attributes
BC = tab('BattleConst')
constants = OrderedDict((k, BC[k]) for k in sorted(BC))
AMT = tab('AttributeMetaTable')
attributes = OrderedDict(); attr_meta = OrderedDict(); attr_icons = OrderedDict()
for k in sorted(AMT, key=int):
    m = AMT[k]
    key, cn = CONV.ATTR_NAMES.get(int(k), (f'attr{k}', f'attr{k}'))
    attributes[k] = OrderedDict([('key', key), ('cn', cn), ('icon', m.get('iconName', '')),
                                 ('default', m.get('defaultValue')),
                                 ('min', m['minValue'] if m.get('hasMinValue') else None),
                                 ('max', m['maxValue'] if m.get('hasMaxValue') else None)])
    attr_meta[k] = OrderedDict([('key', key), ('cn', cn)])
    attr_icons[k] = m.get('iconName', '')
# enum name -> index (enum names are the PascalCase form of the convention keys; first wins)
ENUM = {}
for k in sorted(AMT, key=int):
    nm = attributes[k]['key']; ENUM.setdefault(nm[0].upper() + nm[1:], int(k))
ENUM.update(CONV.ENUM_INDEX)
composites = OrderedDict()
for name, v in tab('CompositeAttributeTable').items():
    composites[name] = [ENUM[x] for x in v['list'] if x in ENUM]
composites['Main'] = 'main'; composites['Sub'] = 'sub'

CTT = tab('CharTypeTable')
elements = OrderedDict()
for eid, e in CTT.items():
    elements[eid] = OrderedDict([('cn', T(e['name'])), ('damageType', e['damageType']), ('color', e['color']),
                                 ('icon', e['icon']), ('attrs', OrderedDict([
                                     ('increase', ENUM.get(f'{eid}DamageIncrease')),
                                     ('resistance', ENUM.get(f'{eid}Resistance')),
                                     ('taken', ENUM.get(f'{eid}DamageTakenScalar'))]))])
DT2EL = {e['damageType']: k for k, e in CTT.items()}
weapon_types = OrderedDict((k, {'cn': v}) for k, v in CONV.WEAPON_TYPE_CN.items())
damage_taken = [OrderedDict([('level', v['damageTakenLevel']), ('scalar', v['damageTakenScalar'])])
                for _, v in sorted(tab('EnemyDamageTakenLevelTable').items(), key=lambda x: int(x[0]))]

# ------------------------------------------------------------------ skills (patch table)
SPT = tab('SkillPatchTable')

def bb_of(lv):
    return OrderedDict((b['key'], b['valueStr'] if b.get('valueStr') else b['value']) for b in lv.get('blackboard', []))

def fmt_keys(desc):
    out = OrderedDict()
    for m in re.finditer(r'\{([^{}:]+)(?::([^{}]*))?\}', desc or ''):
        key = m.group(1).strip()
        if re.fullmatch(r'[A-Za-z_]\w*', key):  # expressions such as a*b or 1-x are rendered by the engine
            out.setdefault(key, (m.group(2) or '').strip())
    return out

def passive_skill(sid):
    lvls = SPT.get(sid, {}).get('SkillPatchDataBundle', [])
    if not lvls: return None
    desc = T(lvls[0].get('description'))
    keys = sorted({k for lv in lvls for k in bb_of(lv)})
    return OrderedDict([('id', sid), ('keys', keys),
                        ('levels', [OrderedDict([('level', lv['level']), ('bb', bb_of(lv))]) for lv in lvls]),
                        ('desc', desc), ('format', fmt_keys(desc))]), lvls

def is_conditional(desc):
    return bool(re.search(CONV.CONDITIONAL_RE, re.sub(r'<[^>]*>', '', desc or '')))

# ------------------------------------------------------------------ weapons + progression
ITEM = tab('ItemTable')
WB = tab('WeaponBasicTable'); WBT = tab('WeaponBreakThroughTemplateTable'); WTT = tab('WeaponTalentTemplateTable')
WUP = tab('WeaponUpgradeTemplateTable')
weapons = []; prog_weapons = OrderedDict()
for wid, w in WB.items():
    lvl_tpl = WUP[w['levelTemplateId']]['list']
    base_atk = [x['baseAtk'] for x in sorted(lvl_tpl, key=lambda x: x['weaponLv'])][:w['maxLv']]
    bts = WBT[w['breakthroughTemplateId']]['list']
    skills = []; tags = []
    for sid in w['weaponSkillList']:
        ps = passive_skill(sid)
        if not ps: continue
        s, lvls = ps
        s['conditional'] = (not sid.startswith('wpn_')) and is_conditional(s['desc'])
        s['statOnly'] = sid.startswith('wpn_')
        skills.append(s)
        tags.append(OrderedDict([('id', sid), ('tagId', lvls[0].get('tagId', '')), ('name', T(lvls[0].get('skillName')))]))
    weapons.append(OrderedDict([
        ('id', wid), ('name', T(ITEM.get(wid, {}).get('name'))), ('engName', T(w['engName'])),
        ('rarity', w['rarity']), ('type', w['weaponType']), ('maxLevel', w['maxLv']), ('baseAtkByLevel', base_atk),
        ('breakthroughs', [OrderedDict([('stage', i), ('breakthroughLv', b['breakthroughLv']),
                                        ('skillLevelBounds', b['skillLevelBounds'])]) for i, b in enumerate(bts)]),
        ('skills', skills), ('desc', T(w['weaponDesc'])),
    ]))
    tl = WTT[w['talentTemplateId']]['list']
    zero = [OrderedDict([('lowerBound', 0), ('upperBound', 0)]) for _ in tags]
    prog_weapons[wid] = OrderedDict([
        ('skillTags', tags),
        ('breakthroughs', [OrderedDict([('stage', i), ('requiredLevel', b['breakthroughLv']),
                                        ('levelCap', bts[i + 1]['breakthroughLv'] if i + 1 < len(bts) else w['maxLv']),
                                        ('skillLevelBounds', b['skillLevelBounds'])]) for i, b in enumerate(bts)]),
        ('talentLevels', [OrderedDict([('potential', 0), ('skillLevelExtraBounds', zero)])] +
         [OrderedDict([('potential', t['talentLv']), ('skillLevelExtraBounds', t['skillLevelExtraBounds'])]) for t in tl]),
    ])
weapons.sort(key=lambda w: (-w['rarity'], w['id']))
GEN = tab('GemEnhanceTable')
gem_max = OrderedDict((k, len(v['list']) + 1) for k, v in sorted(GEN.items(), key=lambda x: int(x[0])))
gem_terms = OrderedDict()
for gid, g in tab('GemTable').items():
    gem_terms[gid] = OrderedDict([('id', gid), ('tagId', g['tagId']), ('name', T(g['tagName'])),
                                  ('termType', g['termType']), ('isSkillTerm', g['isSkillTerm']),
                                  ('maxLevel', gem_max.get(str(g['termType'])))])
gem_presets = OrderedDict()
for gid, g in tab('GemPresetTable').items():
    gem_presets[gid] = OrderedDict([('id', gid), ('rarity', g['rarity']),
                                    ('terms', [OrderedDict([('level', t['level']), ('termId', t['termId'])]) for t in g['termList']])])
progression = OrderedDict([('schemaVersion', 1), ('weapons', prog_weapons), ('gemTerms', gem_terms),
                           ('gemPresets', gem_presets), ('gemMaxLevelsByType', gem_max),
                           ('sources', CONV.PROGRESSION_SOURCES), ('rule', CONV.PROGRESSION_RULE),
                           ('labels', CONV.PROGRESSION_LABELS)])

# ------------------------------------------------------------------ equipment
ET = tab('EquipTable')
equip_items = []
for iid, e in ET.items():
    comp = {}
    for d in [e.get('displayBaseAttrModifier')] + e.get('displayAttrModifiers', []):
        if d: comp.setdefault(d['attrIndex'], d.get('compositeAttr', ''))
    mods = []; seen = set()
    for m in e['equipAttrModifiers']:
        if m['attrIndex'] in seen: continue
        seen.add(m['attrIndex'])
        mods.append(OrderedDict([('attrIndex', m['attrIndex']), ('attrType', m['attrType']),
                                 ('modifierType', m['modifierType']), ('compositeAttr', comp.get(m['attrIndex'], '')),
                                 ('modifyAttributeType', m.get('modifyAttributeType', 0)),
                                 ('values', m['attrValues']), ('value', m['attrValues'][0] if m['attrValues'] else None)]))
    tier = int(re.search(r'_t(\d+)_', iid).group(1)) if re.search(r'_t(\d+)_', iid) else None
    equip_items.append(OrderedDict([('id', iid), ('name', T(ITEM.get(iid, {}).get('name'))), ('partType', e['partType']),
                                    ('tier', tier), ('minWearLv', e['minWearLv']), ('suitId', e.get('suitID', '')),
                                    ('modifiers', mods)]))
equip_items.sort(key=lambda x: (-(x['tier'] or 0), x['partType'], x['id']))
equip_suits = []
for sid, s in tab('EquipSuitTable').items():
    pieces = []
    for p in s['list']:
        ps = passive_skill(p['skillID'])
        piece = OrderedDict([('count', p['equipCnt']), ('skillId', p['skillID']), ('skillLv', p['skillLv']),
                             ('name', T(p['suitName']))])
        if ps:
            sk, _ = ps
            piece['desc'] = sk['desc']; piece['format'] = sk['format']
            piece['conditional'] = is_conditional(sk['desc']); piece['keys'] = sk['keys']; piece['levels'] = sk['levels']
        pieces.append(piece)
    equip_suits.append(OrderedDict([('id', sid), ('name', pieces[0]['name'] if pieces else ''),
                                    ('equipList', s['equipList']), ('pieces', pieces)]))

# ------------------------------------------------------------------ enemies
EAT = tab('EnemyAttributeTemplateTable'); EDI = tab('EnemyTemplateDisplayInfoTable'); DET = tab('DisplayEnemyTypeTable')
dummies = []
for tid in sorted(EAT):
    a = EAT[tid]; inherited = ''
    lv_src = a.get('levelDependentAttributes')
    if not lv_src:
        parts = tid.split('_')
        for n in range(len(parts) - 1, 1, -1):
            p = '_'.join(parts[:n])
            if p in EAT and EAT[p].get('levelDependentAttributes'):
                inherited = p; lv_src = EAT[p]['levelDependentAttributes']; break
    levels = []
    for L in lv_src or []:
        at = {x['attrType']: x['attrValue'] for x in L['attrs']}
        levels.append(OrderedDict([('level', int(at.get(0, 0))), ('maxHp', at.get(1)), ('atk', at.get(2)), ('def', at.get(3))]))
    di = EDI.get(tid)
    dt = di['displayType'] if di else None
    dummies.append(OrderedDict([
        ('id', tid), ('name', T(di['name']) if di else tid), ('displayType', dt),
        ('displayTypeCn', T(DET[str(dt)]['name']) if dt is not None and str(dt) in DET else ''),
        ('inheritedFrom', inherited),
        ('physicalResistance', a['physicalResistance']), ('fireResistance', a['fireResistance']),
        ('pulseResistance', a['pulseResistance']), ('crystResistance', a['crystResistance']),
        ('naturalResistance', a['naturalResistance']), ('maxResilience', a['maxResilience']),
        ('zeroPoiseSuperArmor', a['zeroPoiseSuperArmor']), ('superArmorWhenResilienceZero', a['superArmorWhenResilienceZero']),
        ('levels', levels)]))

# ------------------------------------------------------------------ characters
CT = tab('CharacterTable'); CPT = tab('CharacterPotentialTable'); PTE = tab('PotentialTalentEffectTable')
CPROF = tab('CharProfessionTable'); CWR = tab('CharWpnRecommendTable')
REF = json.load(open(args.ref, encoding='utf-8')) if args.ref and os.path.exists(args.ref) else None
REF_SKILL = {s['id']: s for c in (REF or {}).get('characters', []) for s in c['skills']}
reuse = defaultdict(int)

_skilldata_cache = {}
def skill_json(sid):
    if sid not in _skilldata_cache:
        p = os.path.join(SKD, sid + '.json')
        if os.path.exists(p):
            READ.add(p); _skilldata_cache[sid] = json.load(open(p, encoding='utf-8'))
        else:
            _skilldata_cache[sid] = None
    return _skilldata_cache[sid]

def damage_units(js, sid):
    """enabled hp damage units in document order -> (pointer, unit)."""
    out = []
    def walk(o, ptr, enabled):
        if isinstance(o, dict):
            if o.get('isEnable') is False: enabled = False
            for k, v in o.items():
                if k == 'damageUnits' and isinstance(v, list):
                    for i, u in enumerate(v):
                        if enabled and isinstance(u, dict) and u.get('damageAttributeType') == 0:
                            out.append((f'{ptr}/{k}/{i}', u))
                walk(v, f'{ptr}/{k}', enabled)
        elif isinstance(o, list):
            for i, v in enumerate(o): walk(v, f'{ptr}/{i}', enabled)
    if js: walk(js, '', True)
    return out

def potential_effects(eff_id):
    e = PTE.get(eff_id)
    if not e: return '', []
    effs = []
    for d in e['dataList']:
        mt = d['modifyType']
        bbm = d.get('skillBbModifier') or {}; am = d.get('attrModifier') or {}
        effs.append(OrderedDict([
            ('modifyType', mt), ('target', bbm.get('skillId', '') if mt == 3 else ''),
            ('bbKey', bbm.get('bbKey', '') if mt == 3 else ''), ('floatValue', bbm.get('floatValue', 0.0) if mt == 3 else 0.0),
            ('attrType', am.get('attrType', 0) if mt == 4 else 0), ('attrValue', am.get('attrValue', 0.0) if mt == 4 else 0.0),
            ('attrModifierType', am.get('modifierType', 0) if mt == 4 else 0),
            ('activeCondition', d.get('activeCondition', [])),
            ('attachBuffId', (d.get('attachBuff') or {}).get('buffId', '') if mt == 5 else '')]))
    return T(e.get('desc')), effs

names = defaultdict(list)
for cid, c in CT.items(): names[T(c['name'])].append(cid)

def char_name(cid, c):
    n = T(c['name'])
    if len(names[n]) > 1:
        stem = cid.split('_', 2)[2]
        others = [o.split('_', 2)[2] for o in names[n] if o != cid]
        base = min(others + [stem], key=len)
        suf = stem[len(base):] if stem.startswith(base) and stem != base else stem
        return f"{n}（{CONV.GENDER_SUFFIX.get(suf, suf)}）"
    return n

def build_skill(cid, sid, element):
    lvls = SPT[sid]['SkillPatchDataBundle']
    js = skill_json(sid)
    units = damage_units(js, sid)
    kind0 = SP.naming(sid)[0]
    dur = (js.get('durationFrame') if js else None) or CONV.ASSUMPTIONS['defaultCastFrames'].get(kind0) or CONV.ASSUMPTIONS['defaultCastFrames']['attack']
    levels = []
    for lv in lvls:
        levels.append(OrderedDict([('level', lv['level']), ('cooldown', lv.get('coolDown', 0.0)),
                                   ('costType', lv.get('costType', 0)), ('costValue', lv.get('costValue', 0.0)),
                                   ('bb', bb_of(lv)),
                                   ('params', [OrderedDict([('name', T(x['name'])), ('value', x.get('desc', ''))])
                                               for x in lv.get('subDescDataList', [])])]))
    hits = []
    evidence = []
    for ptr, u in units:
        a = u.get('atkScale') or {}
        if a.get('useBlackboardKey') and a.get('blackboardKey'):
            hits.append(OrderedDict([('source', 'blackboard'), ('key', a['blackboardKey']), ('damageType', u.get('damageType'))]))
        else:
            hits.append(OrderedDict([('source', 'literal'), ('value', a.get('value', 0.0)), ('damageType', u.get('damageType'))]))
        evidence.append(OrderedDict([('source', f'Json/SkillData/{sid}.json'), ('pointer', ptr),
                                     ('damageType', u.get('damageType')), ('damageAttributeType', u.get('damageAttributeType'))]))
    if not hits:  # no readable hp damage unit: one generic hit on the aggregate atk_scale
        hits = [OrderedDict([('source', 'blackboard'), ('key', 'atk_scale'), ('damageType', 0)])]
    facts = {'id': sid, 'durationFrame': dur, 'attackRangeType': js.get('attackRangeType', 0) if js else 0,
             'units': hits, 'evidence': evidence, 'levels': levels, 'element': element,
             'desc': T(lvls[0].get('description')), 'json': js}
    ref = REF_SKILL.get(sid)
    if ref is not None and SP.fingerprint_matches(facts, ref):
        reuse['skill:reused'] += 1
        return SP.from_reference(facts, ref, DT2EL)
    reuse['skill:parsed'] += 1
    return SP.parse(facts, DT2EL)

MAX_CHAR_LEVEL = max(v['maxCharLevel'] for v in tab('CharBreakStageTable').values())
characters = []
for cid, c in CT.items():
    pot = []
    for p in CPT.get(cid, {}).get('potentialUnlockBundle', []):
        desc, effs = potential_effects(p['potentialEffectId'])
        pot.append(OrderedDict([('level', p['level']), ('name', T(p['name'])), ('desc', desc), ('effects', effs)]))
    levels = []; seen = set()
    for a in c['attributes']:
        at = OrderedDict((x['attrType'], x['attrValue']) for x in a['Attribute']['attrs'])
        L = int(at.get(0, 0))
        if L in seen or L > MAX_CHAR_LEVEL: continue
        seen.add(L)
        extra = OrderedDict((str(k), v) for k, v in at.items() if k not in (0, 1, 2, 3, 39, 40, 41, 42, 9, 10) and k not in CONV.LEVEL_EXTRA_EXCLUDE)
        levels.append(OrderedDict([('level', L), ('maxHp', at.get(1)), ('atk', at.get(2)), ('def', at.get(3)),
                                   ('str', at.get(39)), ('agi', at.get(40)), ('wisd', at.get(41)), ('will', at.get(42)),
                                   ('critRate', at.get(9, CONV.DEFAULT_CRIT_RATE)), ('critDmg', at.get(10, CONV.DEFAULT_CRIT_DMG)),
                                   ('extra', extra)]))
    skill_ids = sorted(k for k in SPT if k.startswith(cid + '_'))
    skills = [build_skill(cid, sid, c['charTypeId']) for sid in skill_ids]
    characters.append(OrderedDict([
        ('id', cid), ('name', char_name(cid, c)), ('engName', c['engName']), ('rarity', c['rarity']),
        ('element', c['charTypeId']), ('profession', c['profession']),
        ('professionCn', T(CPROF[str(c['profession'])]['name']) if str(c['profession']) in CPROF else ''),
        ('weaponType', c['weaponType']), ('mainAttrType', c['mainAttrType']), ('subAttrType', c['subAttrType']),
        ('resilienceDeductionFactor', c['resilienceDeductionFactor']), ('maxLevel', max(seen) if seen else 0),
        ('playable', bool(skills)), ('levels', levels), ('skills', skills), ('potentials', pot), ('talents', []),
        ('recommendedWeapons', CWR.get(cid, {}).get('weaponIds1', [])),
    ]))
characters.sort(key=lambda c: (not c['playable'], -c['rarity'], c['id']))

# ------------------------------------------------------------------ meta
def git(*a):
    try: return subprocess.check_output(['git', '-C', args.src] + list(a), text=True).strip()
    except Exception: return ''

readme = open(os.path.join(args.src, 'README.md'), encoding='utf-8').read()
m = re.search(r'更新日期为(\d+)/(\d+)/(\d+)', readme)
rdate = f'{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}' if m else ''
m = re.search(r'已支持(.+?版本[^。\n]*)', readme)
rver = m.group(1) if m else ''
# reference style: a space between CJK and ASCII runs ("终末地 1.5 版本下半")
rver = re.sub(r'(?<=[\u4e00-\u9fff])(?=[0-9A-Za-z])|(?<=[0-9A-Za-z])(?=[\u4e00-\u9fff])', ' ', rver)
all_sk = [s for c in characters for s in c['skills']]
meta = OrderedDict([
    ('source_commit', git('rev-parse', 'HEAD')),
    ('source_digest', CONV.source_digest(args.src, sorted(READ))),
    ('source_readme_date', rdate), ('source_readme_version', rver),
    ('generated_at', args.generated_at or datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')),
    ('frameRate', CONV.FRAME_RATE),
    ('counts', OrderedDict([('characters', len(characters)), ('playable', sum(c['playable'] for c in characters)),
                            ('weapons', len(weapons)), ('equipItems', len(equip_items)), ('equipSuits', len(equip_suits)),
                            ('dummyPresets', len(dummies)), ('skills', len(all_sk))])),
    ('assumptions', CONV.ASSUMPTIONS),
    ('unparsedPotentialEffects', sum(1 for c in characters for p in c['potentials'] for e in p['effects']
                                     if e['modifyType'] not in (2, 3, 4, 5))),
    ('skillWarningCounts', SP.warning_counts(all_sk)),
    ('damageElementCoverage', SP.element_coverage(all_sk, CONV.ELEMENT_POLICY)),
    ('reviewedFixedHitSkills', sorted(s['id'] for s in all_sk if s.get('reviewedMechanics'))),
    ('skillMultiplierPolicy', CONV.SKILL_MULTIPLIER_POLICY),
])
data = OrderedDict([
    ('meta', meta), ('constants', constants), ('attributes', attributes), ('composites', composites),
    ('elements', elements), ('weaponTypes', weapon_types), ('damageTakenLevels', damage_taken),
    ('characters', characters), ('progression', progression), ('weapons', weapons), ('equipItems', equip_items),
    ('equipSuits', equip_suits), ('dummyPresets', dummies), ('attrMeta', attr_meta), ('attrIconNames', attr_icons),
])
os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
json.dump(data, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(f'wrote {args.out}: chars={len(characters)} skills={len(all_sk)} weapons={len(weapons)} '
      f'equip={len(equip_items)} suits={len(equip_suits)} dummies={len(dummies)}  {dict(reuse)}', file=sys.stderr)
