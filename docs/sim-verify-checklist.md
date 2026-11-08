# strata-gw v0.2 首次部署验收清单 / First-Deploy Acceptance Checklist

**BUILD: ______** ← 双击 `start-test.cmd` 后横幅第一行 `TEST BUILD: <hash> (sim
environment)` 的哈希，抄在这里。本清单每修一轮 bug 会重发增量包，你只需复验对应编号项；签满即冻结此哈希。
Copy the hash from the `TEST BUILD:` banner of `start-test.cmd` here. After each
bugfix round only the listed items need re-checking; when all ten are signed the
hash is frozen as the merge object.

环境 / the box: `D:\strata-gw-test`（dev 分支）+ `D:\Strata-test`（模拟 Strata）。
打开浏览器 `http://127.0.0.1:18175`（外网访问需先经主人批准加防火墙规则，本机浏览器不需要）。
Page under test: `http://127.0.0.1:18175` — local browser needs no firewall rule.

| # | 操作 / do | 预期 / expect | ✓ |
|---|---|---|---|
| 1 | 全新环境双击 `start-test.cmd` / double-click `start-test.cmd` | 窗口打出 TEST BUILD 横幅与三行端口说明；网关活着（零配置不退出）；页面整页入职清单：引擎 ✓ `0.0.0-sim` / 体检一句话 / 0 位特工。Banner + zero-config gateway alive + full onboarding page (engine ✓ 0.0.0-sim, one-line check, 0 operatives). | ☐ |
| 2 | 点「+ 招募特工」/ hit "+ recruit operative" | 左右分栏出现家族列表：SimCore/SimForge/SimVista（+尝鲜灰标 SimBeta + SimMulti 自带 V1/V2 档位）；FAILSIM 档说明写"演示失败"用途。Wizard split columns: 3 families + preview badge + multi-file family with own tiers; FAILSIM says it fails on purpose. | ☐ |
| 3 | 选 SimCore One + Q4SIM → 参数页五项都看一眼 → 确认 → 警告弹窗 → 直播 ~45s / pick SimCore Q4SIM, glance at the five params, confirm, warning dlg, live log | 警告说明「勿关窗、可重新入册」；终端风日志滚动（`sim: fetching …`）；顶栏出现「特工入册中…」chip；**中途**点 × 关掉向导、回主页、再点 chip → 直播继续且进度不丢；done 后新卡**面朝下 2 秒自动翻正**；顶栏 chip 消失。 | ☐ |
| 4 | 新卡点「开工」→ 打开监视盘 → 聊天 / clock the new card, open monitor, chat | 假引擎 ~2s 驻留转「在岗」；监视盘假曲线缓漂有形状；聊天得到 canned 台词（「测试特工在岗…」）。/ fake engine loads in ~2s, canned monitor curve drifts, chat answers canned. | ☐ |
| 5 | 卡片翻到特训页：手改昵称保存；点「自动生成标签与档案」/ rename the card, then auto-generate the dossier | 昵称即时生效；自动生成走 canned 自述（中英双语），确认弹窗后直写卡片。/ rename persists; dossier generation returns canned self-report (zh+en) behind a confirm dlg. | ☐ |
| 6 | 再招募：选 SimCore + **FAILSIM** → 等 ~60% 处失败 → 点「回上一步重跑」→ 改成 Q8SIM → 成功 / recruit FAILSIM | 直播 ~60% 处 `sim: link flapped` 红胶囊；重跑按钮参数全保留；改档后成功翻卡登场；「+ 招募特工」按钮上的红徽标在失败后出现、成功后消失。/ fails at ~60%, retry keeps params, success flips a new card; the retry badge appears on failure and clears on success. | ☐ |
| 7 | 中断恢复：招募 MAXSIM 途中**直接关掉 start-test 窗口** → 重开 `start-test.cmd` / kill the window mid-download, relaunch | 重开后红徽标仍在（历史从 `router-setup.json` 回读）；点开直接预填进步骤2，「重新入册」一键成功翻卡。/ badge survives restart (history read back); one-click re-enroll succeeds. | ☐ |
| 8 | 零删除语义：资源管理器把 `D:\Strata-test\strata-simcore-one-q4sim.json` 改名 → 看主页 → 再放回 / rename a config, watch, rename back | ≤5 秒卡片变「未入册」灰态并出现指路文案；网关没有任何删除按钮；文件放回后 ≤5s 后端自动复活（档案还在的卡直接回来）。/ card greys to "unregistered" with guidance within 5s, gateway never deletes, restoring the file brings it back. | ☐ |
| 9 | 齿轮 ⚙ → 磁盘占用区 / gear → disk map | 每个特工一行 GB 数（10⁹ 口径）；SimVista/SimCore 的 shared-ngram 标「共享 ×2」；假 pack 数字与实际空洞文件大小一致（4GB 档约 400MB 磁盘占用，`download_gb×100MiB`）。/ per-model sizes in 10⁹ GB, shared pack flagged "shared ×2". | ☐ |
| 10 | 主题/双语/窄屏 / theme · language · width | 「中/EN」切全站无漏中文；向导步骤条与主钮跟随主题色；把窗口拖到 ~800px 宽，向导两栏自动堆叠不破版；演示模式黄角标常驻（引擎是模拟件，title 有说明）。/ full EN coverage, wizard follows the accent, columns stack at 800px, demo-mode chip stays on. | ☐ |

**让卡链路（附加项）/ VRAM handover (bonus):** 主页「外部显存让卡」→ 假出图服务
读数下降 → 水位满足让位 → 事件留痕；`/free` 后 60 秒内读数自行回占。
/ give-card button frees the pretend VRAM, the holder re-takes it within 60s.

签满十项后回复「签满」，我按此哈希走 T18 合并审查单。
When all ten are signed, tell me and I'll open the merge review at this hash.
