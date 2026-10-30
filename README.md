# endfield_modeling — 明日方舟：终末地伤害建模与模拟器

基于社区数据整理，仅供娱乐参考。

纯静态网页，全部计算在浏览器本地完成：组建干员队伍、配置武器与装备、选择敌人（训练假人预设），按动作时间轴结算伤害并拆解到每个技能。

- 发布：**v3.5**（打包 2026-10-13，`dist3-skylake`）。页面上报的计算口径是 **endfield-calc-3.2**：v3.3、v3.4、v3.5 没有改引擎和数值，只更新了共用主题（加载进度、`?v=` 缓存破坏、分享链接、方案/预设/伤害拆解）
- 数据版本：**终末地 1.5 版本下半**（上游 [rmxlinux/EndfieldData](https://github.com/rmxlinux/EndfieldData) commit `8c5305b`，生成于 2026-10-10T12:33:37Z）
- 34 名干员、370 个技能、80 把武器、258 件装备、24 个套装、137 个假人预设

## 一、怎么用

| 方式 | 文件 | 说明 |
|---|---|---|
| **网页** | [`dist/endfield/`](dist/endfield/) | 自包含静态包：`python3 -m http.server -d dist 8000`，打开 http://localhost:8000/endfield/ （需带末尾斜杠）。部署参考 [`dist/nginx.conf.example`](dist/nginx.conf.example) |

常用命令（需要 Python ≥ 3.9，无第三方依赖）：

    npm run build     # = python3 pipeline/build_pages.py --dist dist，重新生成 dist/endfield/
    npm run diff      # 对比 pipeline/out/endfield.json 与原版页面内嵌数据

## 二、目录

    dist/endfield/                 构建产物（index.html、assets/theme、assets/avatars、data/endfield.json、data/chunks.json）
    frontend/original/endfield.html 原版单文件模拟器页面（ZMD 引擎 bundle + 界面），内嵌的 DATA 字面量已置空，数据见 schema/
    frontend/theme/                主题样式、WebGL 背景、游戏切换、头像、加载进度与方案/预设/分享/拆解脚本
    frontend/apply-theme.py        主题注入脚本（构建时调用；主题 URL 加 ?v=内容哈希，并写入部署路径 __SIM_NAV）
    pipeline/build_pages.py        页面构建：切出内嵌数据、注入低置信标记、头像、分块加载、引擎事件与主题
    pipeline/shared/               sim_bridge.js、sim_chunks.js（构建时内联进页面；从 v3.5 发布包还原，上游源码不在本仓库）
    pipeline/endfield/             数据构建 build_endfield.py、技能解析、约定表、差异对比 diff_endfield.py（说明见其 README.md）
    pipeline/out/endfield.json     处理后的模拟数据（构建输入）及对比/自检报告
    schema/endfield_embedded_DATA.json  原版页面内嵌的数据（数据结构参照，也是技能解析复用的参考）
    assets-src/icons/endfield/     干员头像（33 张，128×128 webp）

## 三、重新生成数据（可选）

`pipeline/out/endfield.json` 已随仓库提供，直接 `npm run build` 即可。若要从游戏数据重新生成：

    git clone https://github.com/rmxlinux/EndfieldData zmd-EndfieldData-8c5305b   # 仓库根目录下，不提交
    git -C zmd-EndfieldData-8c5305b checkout 8c5305b
    python3 pipeline/endfield/build_endfield.py
    npm run diff
    npm run build

## 四、数据来源

- 游戏数据：[rmxlinux/EndfieldData](https://github.com/rmxlinux/EndfieldData)
- 角色头像：GitHub 仓库 Wanye-7300/baker-dx（commit 957bbd4），128×128 webp；版权归鹰角网络所有，来源声明素材仅供个人学习研究、不得商用。通用管理员 chr_9000_endmin 无头像，显示徽章

## 五、校验与已知限制

- 与原版模拟器逐项对比，各场景总伤害一致（默认场景 89,917）
- 技能自动解析的低置信度条目在界面上以琥珀色“低置信”标签标出，悬停可见原因
- 本地固定版本的数据与实现规则，未通过游戏内实测验证，不能解读为准确率或完整覆盖率
- 帧率假设 60 fps；部分技能次数/层数未确认的条目在界面上标出
- ZMD 引擎 bundle 原由 `scripts/zmd/build.mjs` 生成，该构建脚本与引擎源码不在本仓库中；引擎以原版页面内的 bundle 形式保留
- 发布包里的 `pipeline/shared/sim_bridge.js`、`sim_chunks.js` 以及页面上的 v3.2 事件注入，是从构建产物还原的；`frontend/ww/COMPONENTS.md` 里写的约定文档不在本仓库
- 页面构建会给每条技能补上 `skillIcon: null`、补上空的 `elementIcons`，并给头像 URL 加上 `?v=`。数据构建脚本本身不产出这两项；数值与 v3.1 相同
- 游戏切换链接指向 skylake 部署路径（`../endfiled_modeling/`，这个拼写是服务器目录）。本仓库只有终末地页面

## 许可证

- 代码：[MIT](LICENSE)，Copyright (c) 2026 lakeofsky347
- 游戏数据、干员头像等游戏素材的版权归鹰角网络（Hypergryph / Gryphline）所有，不在 MIT 许可范围内。本仓库收录它们仅用于非商业的同人研究，权利方提出要求即删除
- 模拟结果基于社区数据整理，仅供娱乐参考，不代表游戏内实际数值
