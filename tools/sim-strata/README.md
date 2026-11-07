# protocol snapshot: Strata v0.2.11 / engine 0.1.57 (pinned 2026-11-07)

# sim-strata - the demo kit / 演示环境包

**中文**：这是一套**全假**的 Strata 演示环境：假安装工具（setup.py）、假引擎
（serve/server.py）、假出图服务（holder.py）。它不产生任何真实推理、不下载
任何真实文件、不碰任何真实显卡——它的存在只为让 strata-gw 的「招募特工」
全流程在一台没装 Strata 的机器上完整跑通，让人看清向导、直播、翻卡、磁盘
地图每一步。所有端口（网关 18175、假引擎 18201 起、出图服务 18288）都住在
演示专用段，永远不会碰到生产网关。

**English**: a fully **pretend** Strata environment: fake installer
(`setup.py`), fake engine (`serve/server.py`), fake image service
(`holder.py`). It performs no real inference, downloads nothing, touches no
real GPU. It exists so strata-gw's recruit wizard can be walked end-to-end
on a machine with no Strata at all - wizard, live log, card flip, disk map,
every step in view. All ports (gateway 18175, engines 18201+, image service
18288) live in the demo band and never collide with production.

## 用法 / Usage (Windows)

1. Clone the `dev` branch to `D:\strata-gw-test`, keep the kit folder as is.
2. Double-click `tools\sim-strata\make-env.cmd` — it lays out
   `D:\Strata-test` (fake Strata) plus `start-test.cmd` / `stop-test.cmd` /
   `update-test.cmd` inside the gw dir.
3. Double-click `start-test.cmd` in the gw dir. Its banner prints
   `TEST BUILD: <hash> (sim environment)` — the hash you see is the build
   you are accepting.
4. Open `http://127.0.0.1:18175` in a browser. Pick family **SimCore**,
   tier **Q4SIM**, watch it enroll; try **FAILSIM** to see the failure badge
   and the one-click retry. Refresh the page: everything still stands.
5. `update-test.cmd <bundle>` pulls a new build without touching the
   pretend model data; `stop-test.cmd` takes the whole sim tree down.

## 假到什么程度 / How fake is it

- 假安装：分 5 步打印 `sim: fetching ...`，用空洞文件冒充 pack（默认每 GB
  档案占 100 MiB 磁盘，`SIM_STRATA_PACK_MB_PER_GB` 可调，`SIM_STRATA_TOTAL_S`
  控制假下载总时长，默认 45 秒）。
- 假引擎：只会说 canned 台词（自我介绍/翻译/代笔三种分支），`/metrics`
  是一条正弦缓漂的假曲线——监视盘有形状，但没有任何计算。
- 假出图服务：`/free` 后假装让出显卡 30 秒，60 秒后回占——显存读数会动。
- `FAILSIM` 档在约 60% 处故意摔线（exit 3），专门用来演示「重新入册」。
- `simcore` 与 `simvista` 故意共享一个 `shared-ngram` pack——磁盘地图里
  「共享 ×2」的活教材。

Nothing in this folder is ever imported by the product; the product tree
never references it. 产品代码永远不 import 本目录。
