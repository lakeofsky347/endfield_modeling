# Endfield DATA builder

    python3 build_endfield.py --src ../../zmd-EndfieldData-8c5305b [--ref REF.json|''] [--out ../out/endfield.json] [--generated-at ISO]
    python3 diff_endfield.py [A.json] [B.json] [--examples N] [--changes] [--ignore meta.generated_at] [--json]

Files
- build_endfield.py: reads TableCfg/*.json (CN I18n) and Json/SkillData/<skill>.json.
- endfield_skillparse.py: interprets character skills. It reuses the reference's interpretation
  when a skill's fingerprint is unchanged (durationFrame, attackRangeType, damage-unit pointers,
  and per-level bb/params/cd/cost). Otherwise it applies a heuristic and adds an "自动解析" warning.
- endfield_conventions.py: labels that the repo does not contain, extracted once from the reference:
  attribute key/cn names, the composite enum→index map, weapon-type short names, the
  level.extra exclusion set {12,50..55}, and the assumption/policy strings.

Derived rules (all verified against the reference)
- characters: sorted by playable, then rarity desc, then id. Levels are capped at the max
  CharBreakStageTable.maxCharLevel (90), one row per level. Duplicate names get （男）/（女）/（endmin）.
- skills: castTime = durationFrame/60, rounded to 4 places. If durationFrame is 0 or the JSON is
  missing, it falls back to defaultCastFrames[kind], or 120 when that value is 0.
  - With no enabled HP damage unit, hits = [blackboard atk_scale].
  - damageElement is set only when the enabled HP units have a single damage type; otherwise
    null + warning.
  - skillWarningCounts is counted per skill.
- weapons: sorted by rarity desc, then id. format comes from `{key:fmt}`; keys are stripped and
  expression keys (a*b, 1-x) are skipped. The potential-0 talent row has one zero bound per
  weapon skill.
- equipItems: sorted by tier desc, then partType, then id. The first modifier per attrIndex wins.
- dummyPresets: variants without level data inherit from the longest existing prefix template
  (inheritedFrom).

source_digest: the reference's method is unknown. These were tried and none matched:
- sha256 of the commit or tree id;
- git archive tar/zip;
- sha256sum-style, path:hash, JSON map and path\0data\0 manifests over the files read, TableCfg,
  TableCfg+SkillData, and the whole repo, with and without the prefix `data/upstream/EndfieldData/`.

This builder writes its own sha256 over (relpath\0bytes\0) of the files it read, sorted.
