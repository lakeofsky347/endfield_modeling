#!/usr/bin/env python3
"""给模拟器页面注入主题层（幂等，可重复执行）。

用法:
  apply-theme.py <hsr|endfield|ww> <输入.html> <输出.html> [--prefix assets/theme/] [--no-nav]

注入内容:
  <html data-theme="...">；</head> 前加 common.css、<主题>.css、favicon、gamenav.js、avatar.js（defer，--no-nav 也注入）；</body> 前加 bg-webgl.js
--prefix  主题资源的路径前缀，默认 "assets/theme/"（独立包：页面在包根目录，自带 assets/）。
          旧的共享结构用 "../assets/theme/"。页面里已有的旧前缀引用会被改写成新前缀。
--no-nav  不注入游戏切换标签栏。
"""
import argparse, re

ap = argparse.ArgumentParser()
ap.add_argument('theme', choices=['hsr', 'endfield', 'ww'])
ap.add_argument('src'); ap.add_argument('dst')
ap.add_argument('--prefix', default='assets/theme/')
ap.add_argument('--no-nav', action='store_true')
a = ap.parse_args()
P = a.prefix if a.prefix.endswith('/') else a.prefix + '/'
s = open(a.src, encoding='utf-8').read()

# 已有引用统一改写成新前缀（兼容旧的 ../assets/theme/、/assets/theme/、assets/theme/）
s = re.sub(r'(?:\.\./|/)?assets/theme/(?=[\w.-]+\.(?:css|js|svg)\b)', P, s)

head_open = re.search(r'<html\b[^>]*>', s)
if head_open and 'data-theme=' not in head_open.group(0):
    s = s.replace(head_open.group(0), head_open.group(0)[:-1] + f' data-theme="{a.theme}">', 1)

def has_tag(fn):
    """只认真正引用该文件的 <script src> / <link href>，注释或字符串里的文件名不算"""
    return re.search(r'<(?:script|link)\b[^>]*\b(?:src|href)=["\'][^"\']*' + re.escape(fn) + r'(?:[?#][^"\']*)?["\']', s) is not None

inj = []
if not has_tag('common.css'): inj.append(f'<link rel="stylesheet" href="{P}common.css">')
if not has_tag(f'{a.theme}.css'): inj.append(f'<link rel="stylesheet" href="{P}{a.theme}.css">')
if 'rel="icon"' not in s: inj.append(f'<link rel="icon" type="image/svg+xml" href="{P}favicon-{a.theme}.svg">')
if not a.no_nav and not has_tag('gamenav.js'): inj.append(f'<script src="{P}gamenav.js"></script>')
if not has_tag('avatar.js'): inj.append(f'<script defer src="{P}avatar.js"></script>')
if inj: s = s.replace('</head>', '\n'.join(inj) + '\n</head>', 1)
if not has_tag('bg-webgl.js'):
    s = s.replace('</body>', f'<script src="{P}bg-webgl.js"></script>\n</body>', 1)
open(a.dst, 'w', encoding='utf-8').write(s)
