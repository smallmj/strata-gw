# STRATA — Strata 网关

**中文 | [English](README_en.md)**

**一块本地 GPU · 若干本地模型 · 一个把加载换装、显存腾让、监控和特训都收进一页的本地推理网关。**

![控制台整页实景（中文界面）](docs/preview-full-zh.png)

Strata-gw 是个人「模型加载台」的网关 + Web 控制台层：在**一块 GPU** 上管理 N 个
模型后端，同一时刻只允许一个驻留。加载 / 卸载 / 换模都是显式、经确证的动作，
并有事件时间线可查——没有任何暗箱自动换装。在路由之上，页面还自带：叠层特工
档案卡（参数 · 标签 · 档案，统一 schema、直接从网关自身读取；标签与档案还能让
在位模型自己写）、每模型一页翻卡特训抽屉（采样默认、启动配置、立绘、标签/档案
编辑）、一个收纳 token · 语言 · 背景视频 · 桌宠的 ⚙ 弹窗、实时 monitor（tokens/s、
显存、内存、专家缓存、GPU 温度）、事件动态，以及整页 EN/中文 双语界面。

它需要**你自己的 Strata 引擎安装**（提供 `serve/server.py` 的那个引擎）。
网关本身只用 Python 标准库——零 pip 依赖。

## 工作原理

- 每个后端都是 OpenAI 兼容服务器；网关对外只有一个聚合的 OpenAI 兼容端点，
  外加一套 `router/*` 控制 API。
- **懒加载：** 后端的引擎进程只在需要时拉起。
- **互斥驻留：** 换模 = 卸载在位 → 确证显存已让出 → 加载下一个。
  状态永远来自引擎本身，不做乐观猜测。
- **闲置回收：** 驻留模型闲置到 `idle_unload_s` 会自动卸载腾卡。
- **外部显存让卡（可选）：** 若另一个 GPU 占用者暴露 `/free` 与 `/system_stats`
  （例如出图服务），网关可以在加载前请它让卡——在 gateway.json 配置
  `gpu_free.urls`。
- 网关代理、但你的引擎未必实现的端点（`/settings`、`/config`、`/metrics` 等），
  在面板里显示为*不可用*——永远不会把页面拖崩。

## 三分钟跑起来

```bash
git clone <本仓库> strata-gw
cd strata-gw
cp config-examples/gateway.example.json gateway.json        # 可选旋钮
cp config-examples/strata-backend.example.json strata-mymodel.json
#   编辑 strata-mymodel.json：model_name / model_dir（port 0 = 自动分配）
```

把网关指向你的引擎根目录（里面有 `serve/server.py` 和 `.venv`）：设 `STRATA_HOME`
环境变量、或在 `gateway.json` 里填 `"strata_home"`、或直接把网关检出到引擎根目录
里面。要指定某个 python 解释器就设 `STRATA_PYTHON`。

启动（Windows：编辑好 `launcher/strata-gateway.cmd` 里的 `GW_HOME` 行后双击；
Linux/macOS）：

```bash
bash launcher/strata-gateway.sh        # 或：python3 strata-router.py
```

打开 `http://127.0.0.1:18075/gateway`。网关默认端口 `18075`
（用 `STRATA_ROUTER_PORT` 覆盖；18080 留给引擎自己），后端端口从 `18101` 起自动分配。
终端验证：

```bash
curl -s http://127.0.0.1:18075/router/version
```

把任意 OpenAI 兼容客户端指到 `http://127.0.0.1:18075`，在页面上点「开工」加载模型
（或 `POST router/load {"model":"mymodel"}`）。

## 卡片、特训与立绘

每张档案卡正面底部是一条等高操作行：左边「特训」「开工/下班」两颗同规格按钮，
右边是不可点击的状态框与加载计时圈。所有卡片等高，操作行永远钉在卡面最下方。
点「特训」卡片翻面——采样默认、启动配置、立绘上传、标签与档案编辑都在抽屉里；
特训页右下角「保存」写入、「回岗」返回。风险动作「销卡」会先弹窗写清后果
（档案永久删除、写回 cards.json、重启不回潮），确认才执行。

`cards/cards.json` 存每个模型的展示信息：昵称、立绘、标签与特工档案。在位模型
可以一键**自动生成**自己的标签与档案。每个已安装后端自动获得一张卡（cards.json
只做装饰）；未安装的出厂卡显示为*未安装*、可一键销卡。立绘经页面上传
（存于 `gw-assets/uploads/`，git-ignored）。

## gateway.json 键位

| 键 | 含义 |
|---|---|
| `strata_home` | 引擎根目录（覆盖仓库根；环境变量 `STRATA_HOME` 优先） |
| `github_url` | 顶栏 GitHub 按钮指向 |
| `gpu_free.urls` | 支持 `/free` 的让卡端点列表 |
| `gpu_free.target_mib` | 要求腾出的显存底线；`0` = 按驻留后端自动水位 |
| `gpu_free.gentle_wait_s` / `wait_s` / `timeout_s` | 让卡节奏 |

## 桌宠

一个可拖拽的桌宠（`⚙` → 桌宠）常驻页面；点它弹出紧凑的原生聊天窗——气泡经
`/v1/chat/completions` 流式往返，绑定当前驻留模型。桌宠不承载其他功能，
加载永远在卡片上。它的立绘以虚拟模型 `_pet` 经同一路由供图。拖动=移动（持久化），
右键菜单=尺寸 / 隐藏。遵循 `prefers-reduced-motion`。

## 测试

```bash
python3 tests/test_gateway_switch.py strata-router.py   # 大基线套件
for f in tests/test_*.py; do python3 "$f"; done         # 全部套件，含卫生 lint
```

全绿=可以放心改。基线套件会在 1809x–1810x 端口起桩后端，别和实况 demo 同时跑。

## 由谁写成

strata-gw 的代码、测试、文档与页面设计，全部由一台 RTX 3090 + 64GB DDR4
家用机上、经 Strata 本地推理网关跑起的 **qwen3.8-flash-next-iq3_s** 写成——
就是这张加载台所服务的模型；示例立绘与背景视频同样出自这台机器。每段 git
历史都带 `Written-by: qwen3.8-flash-next-iq3_s via strata-gw (RTX 3090, 64GB DDR4)`
trailer，欢迎点查；后续维护仍由它继续。

All of strata-gw's code, tests, docs and page design were written by
**qwen3.8-flash-next-iq3_s**, running on a home machine (RTX 3090, 64GB DDR4)
behind the very Strata gateway this console drives. The example portraits and
the background video were generated on the same machine. Every commit carries a
`Written-by: qwen3.8-flash-next-iq3_s via strata-gw (RTX 3090, 64GB DDR4)`
trailer; future maintenance continues the same way.

## License

MIT — 见 [LICENSE](LICENSE)。
