  // ---- v3.2 engine events & API (injected by pipeline/build_pages.py; contract: frontend/ww/COMPONENTS.md) ----
  function __efDetail(res, cfg) {
    var by = {};
    (res.timeline || []).forEach(function (t) {
      if (!t || !t.damage) return;
      var k = (t.opIndex != null ? t.opIndex : t.charName) + '|' + (t.skillName || t.skillId || '');
      if (!by[k]) by[k] = { member: t.charId || (cfg && cfg.team[t.opIndex] || {}).charId || null, opIndex: t.opIndex != null ? t.opIndex : null, name: t.charName || null, skillName: t.skillName || null, skillId: t.skillId || null, count: 0, damage: 0, zones: null };
      by[k].count += 1; by[k].damage += t.damage;
    });
    // v3.3: endfield rotation.mode 'auto' (beam search) / 'greedy' (automatic heuristic) → searched true, rotationSource 'search';
    // 'manual' → rotationSource 'manual' (presets and share links use the page's own normalized config, there is no fixed preset sequence)
    var __rm = ((cfg && cfg.rotation) || {}).mode || 'auto';
    return __SIM.clone({
      searched: __rm !== 'manual', rotationSource: __rm === 'manual' ? 'manual' : 'search',
      dataVersion: ((window.__SIM_DATA__ || {}).meta || {}).source_commit || null, config: cfg,
      summary: { total: res.totalDamage, dps: res.dps, duration: res.duration, simulatedTime: res.simulatedTime, hitCount: res.hitCount,
        byElement: res.byElement || null, bySkillKind: res.bySkillKind || null },
      members: (res.byCharacter || []).map(function (c, i) { return { id: c.charId || c.id || (cfg && cfg.team[i] || {}).charId || null, name: c.name || c.charName || null, damage: c.damage, share: c.share != null ? c.share : null }; }),
      timeline: (res.timeline || []).map(function (t, i) { return { index: i, t: t.t, endT: t.endT, member: t.charId || (cfg && t.opIndex != null && cfg.team[t.opIndex] || {}).charId || null, opIndex: t.opIndex != null ? t.opIndex : null,
        actor: t.charName || null, skillName: t.skillName || null, skillId: t.skillId || null, kind: t.kind || null, damage: t.damage || 0 }; }),
      breakdown: { bySkill: Object.keys(by).map(function (k) { return by[k]; }).sort(function (a, b) { return b.damage - a.damage; }), zones: null }
    });
  }
  function __efFindMissing(cfg) {
    var D = window.__SIM_DATA__ || {}, out = [];
    function ids(list) { var o = {}; (list || []).forEach(function (x) { if (x && x.id != null) o[x.id] = 1; }); return o; }
    var C = ids(D.characters), W = ids(D.weapons), Q = ids(D.equipItems);
    function miss(kind, id, tab) { if (id != null && id !== '' && !tab[id]) out.push(kind + ':' + id); }
    ((cfg && cfg.team) || []).forEach(function (m) {
      if (!m) return;
      miss('character', m.charId, C);
      if (m.weapon) miss('weapon', m.weapon.weaponId, W);
      (m.equips || []).forEach(function (q) { if (q) miss('equip', q.itemId, Q); });
    });
    return out.filter(function (x, i) { return out.indexOf(x) === i; });
  }
  window.__simFindMissingIds = __efFindMissing;
  window.__simApply = function (config, opts) {
    opts = opts || {};
    var q = __SIM.request(opts.runId);
    try {
      if (opts.lockRotation) throw new Error('lockRotation 仅鸣潮页面支持（终末地请用 config.rotation.mode = "manual"）');
      var miss = __efFindMissing(config);
      if (miss.length) throw new Error('数据中不存在：' + miss.join(', '));
      var __in = __SIM.clone(config);
      if (opts.search) { __in.rotation = Object.assign({}, __in.rotation || {}, { mode: 'auto' }); }   // v3.3 opts.search: force the beam search
      var next = readConfig(__in);
      if (state.timer) { clearTimeout(state.timer); state.timer = null; }
      state.config = next; state.expanded = {}; state.sourcesOpen = {}; state.colors = [];
      syncAll(); saveStored(state.config);
    } catch (e) { __SIM.abort(q.runId, e && e.message || e); return q.promise; }
    runCompute();
    return q.promise;
  };
