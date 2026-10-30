#!/usr/bin/env python3
"""给模拟器页面注入主题层（幂等，可重复执行）。

用法:
  apply-theme.py <hsr|endfield|ww> <输入.html> <输出.html> [--prefix assets/theme/] [--no-nav]
      [--preload URL ...] [--nav JSON]

注入内容:
  <html data-theme="...">；</head> 前加 preload、common.css、<主题>.css、interact.css、favicon、
  可选的 window.__SIM_NAV、gamenav.js、window.__themeV、gui.js、share.js、plans.js、avatar.js、presets.js
  （后两个 defer，--no-nav 也注入 avatar.js）；</body> 前加 bg-webgl.js。
  主题文件 URL 带 ?v=<sha256 前 12 位>（按 frontend/theme/ 文件内容）。
--prefix  主题资源的路径前缀，默认 "assets/theme/"（独立包：页面在包根目录，自带 assets/）。
          旧的共享结构用 "../assets/theme/"。页面里已有的旧前缀引用会被改写成新前缀。
--no-nav  不注入游戏切换标签栏（仍注入 __SIM_NAV / __themeV，若传入）。
--preload 重复传入。每个 URL 写成 <link rel="preload" as="fetch">，放在样式表之前。
--nav     紧凑 JSON，原样写入 window.__SIM_NAV（gamenav.js 用来覆盖 ../hsr/ 等默认链接）。
"""
import argparse, hashlib, json, os, re

ap = argparse.ArgumentParser()
ap.add_argument('theme', choices=['hsr', 'endfield', 'ww'])
ap.add_argument('src'); ap.add_argument('dst')
ap.add_argument('--prefix', default='assets/theme/')
ap.add_argument('--no-nav', action='store_true')
ap.add_argument('--preload', action='append', default=[])
ap.add_argument('--nav', default='')
a = ap.parse_args()
P = a.prefix if a.prefix.endswith('/') else a.prefix + '/'
THEME = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'theme')
s = open(a.src, encoding='utf-8').read()

def sha12(fn):
    return hashlib.sha256(open(os.path.join(THEME, fn), 'rb').read()).hexdigest()[:12]

def href(fn):
    return f'{P}{fn}?v={sha12(fn)}'

def exists(fn):
    return os.path.isfile(os.path.join(THEME, fn))

# 已有引用统一改写成新前缀（兼容旧的 ../assets/theme/、/assets/theme/、assets/theme/）
s = re.sub(r'(?:\.\./|/)?assets/theme/(?=[\w.-]+\.(?:css|js|svg)\b)', P, s)

head_open = re.search(r'<html\b[^>]*>', s)
if head_open and 'data-theme=' not in head_open.group(0):
    s = s.replace(head_open.group(0), head_open.group(0)[:-1] + f' data-theme="{a.theme}">', 1)

def has_tag(fn):
    """只认真正引用该文件的 <script src> / <link href>，注释或字符串里的文件名不算"""
    return re.search(r'<(?:script|link)\b[^>]*\b(?:src|href)=["\'][^"\']*' + re.escape(fn) + r'(?:[?#][^"\']*)?["\']', s) is not None

inj = []
for url in a.preload:
    tag = f'<link rel="preload" as="fetch" crossorigin="anonymous" href="{url}">'
    if tag not in s:
        inj.append(tag)
if not has_tag('common.css'): inj.append(f'<link rel="stylesheet" href="{href("common.css")}">')
if not has_tag(f'{a.theme}.css'): inj.append(f'<link rel="stylesheet" href="{href(a.theme + ".css")}">')
if exists('interact.css') and not has_tag('interact.css'):
    inj.append(f'<link rel="stylesheet" href="{href("interact.css")}">')
if 'rel="icon"' not in s: inj.append(f'<link rel="icon" type="image/svg+xml" href="{href("favicon-" + a.theme + ".svg")}">')
if a.nav and '__SIM_NAV' not in s:
    inj.append(f'<script>window.__SIM_NAV={a.nav};</script>')
if not a.no_nav and not has_tag('gamenav.js'): inj.append(f'<script src="{href("gamenav.js")}"></script>')
lazy = [fn for fn in ('breakdown.js', 'compare.js', 'plans-drawer.js') if exists(fn)]
if lazy and '__themeV' not in s:
    tv = {fn: sha12(fn) for fn in lazy}
    inj.append('<script>window.__themeV=' + json.dumps(tv, ensure_ascii=False, separators=(',', ':')) + ';</script>')
for fn in ('gui.js', 'share.js', 'plans.js'):
    if exists(fn) and not has_tag(fn):
        inj.append(f'<script src="{href(fn)}"></script>')
if not has_tag('avatar.js'): inj.append(f'<script defer src="{href("avatar.js")}"></script>')
if exists('presets.js') and not has_tag('presets.js'):
    inj.append(f'<script defer src="{href("presets.js")}"></script>')
if inj: s = s.replace('</head>', '\n'.join(inj) + '\n</head>', 1)
if not has_tag('bg-webgl.js'):
    s = s.replace('</body>', f'<script src="{href("bg-webgl.js")}"></script>\n</body>', 1)
open(a.dst, 'w', encoding='utf-8').write(s)
