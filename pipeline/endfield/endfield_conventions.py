"""Naming conventions of the original Endfield builder that do NOT exist in rmxlinux/EndfieldData.

Extracted once from schema/endfield_embedded_DATA.json (the reference build). Everything numeric is
computed from the repo by build_endfield.py; only labels/strings below are taken as given.
  * ATTR_NAMES: attribute index -> (camelCase key, short CN label). The enum names in
    CompositeAttributeTable are PascalCase(key), which is how composites are resolved.
    Unknown/new indexes fall back to ("attrN", "attrN") exactly like the reference does for 0.
  * WEAPON_TYPE_CN: the simulator's short labels (game text says 施术单元/双手剑/长柄武器/手铳).
"""
import hashlib, os, subprocess
ATTR_NAMES = {1: ('maxHp', '生命值'),
 2: ('atk', '攻击力'),
 3: ('def', '防御力'),
 4: ('physicalDamageTakenScalar', '物理伤害减免'),
 5: ('fireDamageTakenScalar', '灼热伤害减免'),
 6: ('pulseDamageTakenScalar', '电磁伤害减免'),
 7: ('crystDamageTakenScalar', '寒冷伤害减免'),
 8: ('naturalDamageTakenScalar', 'naturalDamageTakenScalar'),
 9: ('critRate', '暴击率'),
 10: ('critDmg', '暴击伤害'),
 12: ('skillCharge', 'skillCharge'),
 17: ('normalAtkEfficiency', '普通攻击伤害加成'),
 25: ('levelScalarA', 'levelScalarA'),
 26: ('poiseEfficiency', '失衡效率加成'),
 28: ('ultimateSkillEfficiency', '终结技伤害加成'),
 29: ('healOutputIncrease', '治疗效率加成'),
 30: ('heal_taken_increase', '受治疗效率加成'),
 32: ('normalSkillEfficiency', '战技伤害加成'),
 33: ('comboSkillEfficiency', '连携技伤害加成'),
 35: ('fireBurstDamageIncrease', '灼热爆发伤害增加'),
 36: ('pulseBurstDamageIncrease', '电磁爆发伤害增加'),
 37: ('crystBurstDamageIncrease', '寒冷爆发伤害增加'),
 38: ('naturalBurstDamageIncrease', '自然爆发伤害增加'),
 39: ('str', '力量'),
 40: ('agi', '敏捷'),
 41: ('wisd', '智识'),
 42: ('will', '意志'),
 44: ('ultimateSpGainScalar', '终结技充能效率'),
 47: ('comboSkillCooldown', '连携技冷却缩减'),
 48: ('naturalDamageTakenScalarAlt', '自然伤害减免'),
 49: ('levelScalarB', '法术异常和爆发伤害'),
 50: ('physicalDamageIncrease', '物理伤害加成'),
 51: ('fireDamageIncrease', '灼热伤害加成'),
 52: ('pulseDamageIncrease', '电磁伤害加成'),
 53: ('crystDamageIncrease', '寒冷伤害加成'),
 54: ('naturalDamageIncrease', '自然伤害加成'),
 55: ('etherDamageTakenScalar', 'etherDamageTakenScalar'),
 56: ('fireAbnormalDamageIncrease', '燃烧异常增强'),
 57: ('pulseAbnormalDamageIncrease', '导电异常增强'),
 58: ('crystAbnormalDamageIncrease', '冻结异常增强'),
 59: ('naturalAbnormalDamageIncrease', '腐蚀异常增强'),
 60: ('etherDamageTakenScalarAlt', '超域伤害减免'),
 61: ('damageToBrokenUnitIncrease', '对失衡目标伤害加成'),
 80: ('physicalDamageTakenScalar', '物理抗性'),
 81: ('natural_damage_taken_scalar', '自然抗性'),
 82: ('crystDamageTakenScalar', '寒冷抗性'),
 83: ('pulseDamageTakenScalar', '电磁抗性'),
 84: ('fireDamageTakenScalar', '灼热抗性'),
 85: ('ether_damage_taken_scalar', '超域抗性'),
 87: ('originiumArts', '源石技艺强度'),
 94: ('physicalResistance', '物理抗性'),
 95: ('naturalResistance', '自然抗性'),
 96: ('crystResistance', '寒冷抗性'),
 97: ('pulseResistance', '电磁抗性'),
 98: ('fireResistance', '灼热抗性'),
 99: ('etherResistance', '超域抗性'),
 100: ('combo_skill_cooldown', 'combo_skill_cooldown')}

WEAPON_TYPE_CN = {'1': '单手剑', '2': '浮游单元', '3': '大剑', '5': '长枪', '6': '手枪'}

FRAME_RATE = 60.0
ASSUMPTIONS = {'frameRate': 60.0,
 'defaultCastFrames': {'attack': 120,
                       'power': 154,
                       'normal': 150,
                       'combo': 122,
                       'ultimate': 215,
                       'dash': 110,
                       'plunge': 140,
                       'dodge': 40,
                       'passive': 0,
                       'talent': 0},
 'note': '帧率与缺失动作的默认时长未经游戏内实测标定，见 docs/MODEL_NOTES.md'}
SKILL_MULTIPLIER_POLICY = '排除增伤/暴伤/脆弱等效果参数；明确互斥分支采用常规分支；两项已审阅固定多段展开为逐段倍率，未确认次数/层数仅计一次并逐技能告警'
ELEMENT_POLICY = '仅使用已读取且启用的生命伤害单元的唯一属性；混合属性与未读取到的间接伤害按干员元素回退并告警'
PROGRESSION_SOURCES = ['WeaponBasicTable', 'WeaponBreakThroughTemplateTable', 'WeaponTalentTemplateTable', 'SkillPatchTable', 'GemTable', 'GemPresetTable', 'GemEnhanceTable']
PROGRESSION_RULE = '武器突破决定基础技能等级与上限，武器潜能同时增加指定技能等级与上限；匹配标签的基质词条增加技能等级并受该上限限制。'
PROGRESSION_LABELS = {'weaponPotential': '武器潜能', 'weaponBreakthrough': '武器突破', 'gem': '基质', 'equipmentEnhancement': '装备逐属性精锻'}
DEFAULT_CRIT_RATE = 0.05
DEFAULT_CRIT_DMG = 0.5
GENDER_SUFFIX = {'m': '男', 'f': '女'}
# weapon / suit passive is "conditional" when its text has a trigger clause
CONDITIONAL_RE = r'时|后|期间|每次|每当|若|如果|命中|施放|击败|处于.*状态时'

def source_digest(src, files):
    """Our own digest: sha256 over (relpath NUL bytes NUL) of every file the builder read, sorted.
    The reference's method could not be reproduced (README lists the variants tried)."""
    h = hashlib.sha256()
    for f in files:
        h.update(os.path.relpath(f, src).replace(os.sep, '/').encode()); h.update(b'\0')
        h.update(open(f, 'rb').read()); h.update(b'\0')
    return 'sha256:' + h.hexdigest()

# CompositeAttributeTable enum name -> attribute index (taken from the reference composites; the
# repo has no enum->index table). Unknown names fall back to PascalCase(ATTR_NAMES key).
ENUM_INDEX = {'ComboSkillDamageIncrease': 33,
 'CrystAbnormalDamageIncrease': 58,
 'CrystBurstDamageIncrease': 37,
 'CrystDamageIncrease': 53,
 'CrystDamageTakenScalar': 7,
 'EtherDamageTakenScalar': 55,
 'FireAbnormalDamageIncrease': 56,
 'FireBurstDamageIncrease': 35,
 'FireDamageIncrease': 51,
 'FireDamageTakenScalar': 5,
 'NaturalAbnormalDamageIncrease': 59,
 'NaturalBurstDamageIncrease': 38,
 'NaturalDamageIncrease': 54,
 'NaturalDamageTakenScalar': 8,
 'NormalSkillDamageIncrease': 32,
 'PhysicalDamageTakenScalar': 4,
 'PulseAbnormalDamageIncrease': 57,
 'PulseBurstDamageIncrease': 36,
 'PulseDamageIncrease': 52,
 'PulseDamageTakenScalar': 6,
 'UltimateSkillDamageIncrease': 28}
# attribute types the reference leaves out of characters[].levels[].extra (modelled elsewhere)
LEVEL_EXTRA_EXCLUDE = [12, 50, 51, 52, 53, 54, 55]
