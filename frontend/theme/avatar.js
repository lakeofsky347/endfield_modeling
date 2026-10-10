/* 角色头像占位 .gava：引擎输出 <span class="gava" data-icon="assets/avatars/<id>.webp" data-el="spectro" data-name="守岸人"></span>
   有图就叠一张 <img>，没图或加载失败退回徽章（属性色底 + 名字首字）。无依赖，ES5。约定见 ../ww/COMPONENTS.md */
(function () {
  'use strict';
  if (window.__gava) return;
  var SEL = '.gava';
  /* 属性别名 -> 规范键。按当前主题优先查，再查通用表；查不到 = 中性灰 */
  var ALIAS = {
    hsr: { physical: 'physical', '物理': 'physical', fire: 'fire', '火': 'fire', ice: 'ice', '冰': 'ice',
      thunder: 'lightning', lightning: 'lightning', '雷': 'lightning', wind: 'wind', '风': 'wind',
      quantum: 'quantum', '量子': 'quantum', imaginary: 'imaginary', '虚数': 'imaginary' },
    endfield: { physical: 'physical', '物理': 'physical', fire: 'heat', heat: 'heat', '灼热': 'heat',
      cryst: 'cryo', cryo: 'cryo', cold: 'cryo', ice: 'cryo', '寒冷': 'cryo',
      pulse: 'electric', electric: 'electric', '电磁': 'electric',
      natural: 'nature', nature: 'nature', '自然': 'nature' },
    ww: { glacio: 'glacio', '冷凝': 'glacio', fusion: 'fusion', '热熔': 'fusion', electro: 'electro', '导电': 'electro',
      aero: 'aero', '气动': 'aero', spectro: 'spectro', '衍射': 'spectro', havoc: 'havoc', '湮灭': 'havoc',
      physical: 'physical', '物理': 'physical',
      ice: 'glacio', fire: 'fusion', heat: 'fusion', thunder: 'electro', lightning: 'electro', wind: 'aero' }
  };
  function theme() { return document.documentElement.getAttribute('data-theme') || ''; }
  function normEl(v) {
    if (!v) return '';
    var k = String(v).replace(/^\s+|\s+$/g, ''), lk = k.toLowerCase(), t = ALIAS[theme()], g;
    if (t && (t[lk] || t[k])) return t[lk] || t[k];
    for (g in ALIAS) if (ALIAS.hasOwnProperty(g) && (ALIAS[g][lk] || ALIAS[g][k])) return ALIAS[g][lk] || ALIAS[g][k];
    return '';
  }
  /* 首个字素：跳过开头的括号/标点/空白；拉丁字母转大写 */
  var seg = null;
  try { if (window.Intl && Intl.Segmenter) seg = new Intl.Segmenter(undefined, { granularity: 'grapheme' }); } catch (e) {}
  var SKIP = /^[\s\u00b7\u30fb\u2027·・.,，。:：;；'"“”‘’「」『』《》〈〉()（）\[\]【】{}<>\-–—_~!?！？#*]$/;
  function firstGlyph(name) {
    name = String(name || '');
    var parts = [], i, it, r, cc;
    if (seg) { it = seg.segment(name)[Symbol.iterator](); while (!(r = it.next()).done) { parts.push(r.value.segment); if (parts.length > 8) break; } }
    else {
      for (i = 0; i < name.length && parts.length <= 8; i++) {
        cc = name.charCodeAt(i);
        if (cc >= 0xd800 && cc <= 0xdbff && i + 1 < name.length) { parts.push(name.substr(i, 2)); i++; }
        else parts.push(name.charAt(i));
      }
    }
    for (i = 0; i < parts.length; i++) if (!SKIP.test(parts[i])) return parts[i].toUpperCase();
    return '?';
  }
  function badge(el, glyph) {
    var t = document.createElement('b');
    t.className = 'gava-t'; t.setAttribute('aria-hidden', 'true'); t.textContent = glyph;
    return t;
  }
  function fill(el) {
    var icon = el.getAttribute('data-icon') || '', name = el.getAttribute('data-name') || '',
      rawEl = el.getAttribute('data-el') || '', key = icon + '|' + name + '|' + rawEl + '|' + theme();
    if (el.getAttribute('data-gava') === key) return;          // 已处理且没变
    el.setAttribute('data-gava', key);
    var ne = normEl(rawEl);
    if (ne) el.setAttribute('data-gava-el', ne); else el.removeAttribute('data-gava-el');
    el.setAttribute('role', 'img');
    if (name) { el.setAttribute('aria-label', name); if (!el.getAttribute('title')) el.setAttribute('title', name); }
    while (el.firstChild) el.removeChild(el.firstChild);
    el.appendChild(badge(el, firstGlyph(name)));
    el.classList.remove('gava-img'); el.classList.remove('gava-loaded'); el.classList.remove('gava-err');
    if (!icon) return;
    var img = document.createElement('img');
    img.alt = name; img.setAttribute('loading', 'lazy'); img.setAttribute('decoding', 'async'); img.draggable = false;
    img.onload = function () { if (img.parentNode === el) el.classList.add('gava-loaded'); };
    img.onerror = function () {
      if (img.parentNode !== el) return;
      el.removeChild(img); el.classList.remove('gava-img'); el.classList.remove('gava-loaded'); el.classList.add('gava-err');
    };
    el.classList.add('gava-img');
    el.appendChild(img);
    img.src = icon;
  }
  function scan(root) {
    root = root || document;
    if (root.nodeType === 1 && root.matches && root.matches(SEL)) fill(root);
    if (!root.querySelectorAll) return;
    var list = root.querySelectorAll(SEL), i;
    for (i = 0; i < list.length; i++) fill(list[i]);
  }
  var pending = [], queued = false;
  function flush() {
    queued = false;
    var p = pending; pending = [];
    for (var i = 0; i < p.length; i++) if (p[i].isConnected !== false) scan(p[i]);
  }
  function push(n) { pending.push(n); if (!queued) { queued = true; (window.requestAnimationFrame || setTimeout)(flush); } }
  function start() {
    scan(document);
    if (!window.MutationObserver) return;
    new MutationObserver(function (ms) {
      for (var i = 0; i < ms.length; i++) {
        var m = ms[i], j, n;
        if (m.type === 'attributes') {
          if (m.target === document.documentElement) push(document);       // 切主题：重新归一属性
          else if (m.target.matches && m.target.matches(SEL)) push(m.target);
        } else for (j = 0; j < m.addedNodes.length; j++) { n = m.addedNodes[j]; if (n.nodeType === 1) push(n); }
      }
    }).observe(document.documentElement, { childList: true, subtree: true, attributes: true,
      attributeFilter: ['data-icon', 'data-name', 'data-el', 'class', 'data-theme'] });
  }
  window.__gava = { refresh: function (root) { scan(root || document); }, normEl: normEl, firstGlyph: firstGlyph };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
