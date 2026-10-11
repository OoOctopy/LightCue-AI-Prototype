# LightCue AI Prototype

## 手机屏幕模拟灯（新增）

`phone_demo.py` 将六维模型建议接到浏览器页面。电脑打开控制页；小米 8 等手机打开 `/screen` 并点“开始”，跟随推荐改变页面颜色与明暗，约 3 秒缓慢过渡。

```powershell
python phone_demo.py --host 0.0.0.0 --port 8765
```

电脑控制页：`http://127.0.0.1:8765/`。手机模拟灯页：`http://电脑连接地址:8765/screen`。电脑和手机需有可达网络，可用同一 Wi-Fi 或手机 USB 网络共享；仅插上 USB 充电／传文件不会自动连通。当前不依赖 ADB，不要求 USB 调试。

可在 VS Code 终端启动。服务运行在本地网络，关闭运行进程即可停止。

也可双击 `start_phone_demo.cmd` 启动，并保持服务窗口打开。窗口显示本机控制页和手机地址格式。将 COMPUTER-IP 替换为电脑当前 Wi-Fi 或 USB 网络的 IPv4 地址。若手机持续加载，先确认电脑的控制页能打开；若电脑也打不开，查看启动窗口的错误信息。若电脑正常而手机打不开，需要继续检查手机到电脑的连接，不能把本机演示成功当作手机已连通。

控制页默认使用独立六维模拟历史，也可选择真实反馈历史。尚无真实记录时会暂缓。手动 S1–S4 按钮只用于检测页面控制；模型暂缓或连接断开时保留最近显示，重复同一策略不重复触发变化。控制页区分“页面连接”“等待过渡确认”“已确认完成过渡”。此确认只说明浏览器程序已执行显示逻辑，不能证明实际光学输出，需要肉眼或外部仪器观察。

手机应关闭自动亮度，保持固定系统亮度；可按浏览器全屏能力进入全屏。页面不会修改手机系统亮度、不会强制防休眠，也没有 Wake Lock 依赖，演示时需自行保持屏幕亮着。色温映射是手选屏幕颜色近似，明暗采用 CSS 不透明度模拟：不代表精确的 Kelvin、灯具百分比或照度。本功能不控制实体灯，不连接实时 HealthKit。

检查：`python -m unittest -v test_model test_health_import test_multidim test_phone_demo`。新旧共 26 项检查通过，含本机 HTTP 链路、模拟模型建议、暂缓保持、重复策略稳定、连接与过渡确认分离、过期确认和错误控制拒绝；用户已报告小米 8 连接，控制页已显示屏幕过渡确认；实际颜色与明暗仍需肉眼确认，不作为光学测量结果。

---

## v1.2：六维评价升级

已实现六维反馈存储、可调权重和逐维预测。尚未收集真实六维体验；已有 40 条旧版 Session 仍是单目标模拟评分，不转换为六维记录。旧版的 0.275 误差及两组评分属于 v1，不是新版六维验证结果。

| 维度 | 字段 | 1–5 分的方向（越高越好） | 原始依据与当前处理 |
|---|---|---|---|
| 任务效能 | task_effectiveness | 任务完成质量越满意，分数越高 | 可记录完成时间、正确率、产出量；不同任务量纲不同，由用户评分，暂不自动合成 |
| 认知投入 | cognitive_balance | 认知投入适度、主观负担可接受，分数越高 | 主观体验评分；HRV 前后值只作为参考记录，不直接推断心理压力 |
| 干预契机 | intervention_timing | 介入时机越合适，分数越高 | 体验后的用户反馈 |
| 视觉舒适 | visual_comfort | 越舒适、越少干扰，分数越高 | 用户评分；手动调节次数作为辅助记录，不等同于不舒适 |
| 稳定性 | stability | 用户认为调节越平稳、越少打断，分数越高 | 用户评分；记录调光次数、累计亮度变化百分点、累计色温变化 K；暂不跨量纲自动换算 |
| 接受度 | acceptance | 越愿意继续接受此类 AI 建议，分数越高 | 用户反馈 |

**默认六项等权重**，因为设计图没有指定比例。修改 `preference_weights.json` 的六个数值即可，程序会自动归一化；值必须非负且总和大于零。0 表示不参与本次综合评分。权重是可配置的设计选择，不是模型学出的权重，也不同于案例相似度权重。

计算流程：找每个策略的相似历史 → 分别预测各项反馈 → 按维度权重加权 → 比较策略综合评分。所有启用维度必须都有反馈才可作为邻居；每个候选默认至少需 3 条完整记录。缺失项保留 null，不借用旧版 goal_support 或 HRV 补造。真实与模拟历史不能混用，超出共同历史范围或同分仍暂缓。

```powershell
# 六维演示：16 条另行构造的模拟记录，不写入真实历史
python lightcue_ai.py --multidim --demo

# 使用真实六维反馈历史；尚无记录时明确暂缓
python lightcue_ai.py --multidim --hrv 10 --task Ideation --mode Creative

# 实际体验后填写模板副本，再保存反馈
python lightcue_ai.py --multidim --record completed_feedback.json

# 新旧功能检查
python -m unittest -v test_model test_health_import test_multidim
```

`feedback_template_v2.json` 是空白模板，不能直接作为已完成体验保存。填写唯一编号、HRV 情境、实际任务／模式／使用策略与实际反馈；完成体验后将 `experience_completed` 改为 true。缺失评分保持 null；至少有一项实际评分才可保存。真实记录存入本机 `data/feedback_v2.jsonl`，默认不提交到仓库。

通过命令行运行六维模拟演示。本次已增加手机浏览器屏幕模拟灯，仍无手机反馈采集界面、直接 HealthKit 接入或实体灯控制；新版真实偏好预测效果尚未验证。

---

**当前新增 v1.2 六维计算与本地反馈存储；v1.0 单目标原型仍保留。** v1.1 为此前的文档完善。v1.2 已通过功能检查，真实六维偏好尚未验证。

这是一个已运行验证的轻量个性化推荐原型。数据来自对话“解释是否需要AI”中确定的 40 条模拟 Session，编号、HRV 变化、任务、模式、策略和评分均保留。未定义的 baseline/current HRV、comfort 等字段没有补造。

## 项目目标与实现范围

验证问题：系统能否从带有偏好规律的历史 Session 中，识别情境与策略评分的关系，并给出可解释的策略建议？

| 内容 | 当前状态 | 可以说明的成果 |
|---|---|---|
| Python 与推荐程序 | 已验证 | 可在 VS Code 中运行测试与推荐示例 |
| 偏好历史 | 模拟数据 | 40 条明确标记 simulated 的反馈 |
| 相似度推荐 | 已实现 | 模式内策略比较、预计评分、案例及权重 |
| Apple 健康 XML 导入 | 已实现 | 支持离线提取 HRV SDNN 样本；真实导出留在本机 |
| HRV 个人基线 | 已实现 | 历史窗口中位数及相对变化计算 |
| 真实用户偏好 | 待验证 | 需收集实际灯光体验与评分 |
| HealthKit 自动读取、手机 App | 未来集成 | 尚未实现 |
| 实体灯控制 | 未来集成 | 当前只输出建议，不执行灯光变化 |

## 竞品与设计参照

桌面研究日期：2026-10-11。以下只比较官方页面明确说明的功能，未进行产品实测，不据此断言竞品没有其他 AI 或健康相关功能。

| 产品／方案 | 官方资料中说明的功能 | 调整依据 | 对 LightCue 的启发 |
|---|---|---|---|
| Philips Hue App | 场景库、自定义颜色／亮度、定时及日出日落自动化；官方 App Store 页面还介绍 AI 场景建议与自动化 | 场景选择、时间／日出日落、自然语言请求 | 降低设置成本；LightCue 进一步探索情境与历史体验评分之间的关系 |
| Nanoleaf Essentials Circadian Lighting | 兼容灯泡／灯带随一天变化调整色温，支持日出日落及手动时间设置 | 所在地日出日落、时间或用户设置 | 平缓调节与低干扰；与基于历史体验评分的策略比较区分 |
| LightCue 当前原型 | 模式内比较策略，展示预计评分、相似记录和权重；离线处理 HRV | HRV 变化幅度、任务、模式、模拟反馈 | 可解释的策略级推荐验证；尚不具备商用产品的灯具控制能力 |

官方来源：

- [Philips Hue：场景与自动化](https://www.philips-hue.com/en-us/explore-hue/apps/bridge)
- [Philips Hue 官方 App Store：AI 场景建议及自动化](https://apps.apple.com/us/app/philips-hue/id1055281310?ls=1)
- [Nanoleaf 官方：Using Circadian Lighting](https://support.nanoleaf.me/hc/en-us/articles/36324247124756-In-the-App-Feature-Using-Circadian-Lighting)

设计结论：本项目探索“情境＋重复体验反馈”的策略推荐。现阶段已验证流程，尚未证明优于商用产品，也未验证真实用户效果。

## AI 功能清单

| 阶段 | 输入／处理 | 输出 | 状态 |
|---|---|---|---|
| 情境输入 | HRV 变化、任务、用户模式 | 当前推荐情境 | 已实现 |
| 候选筛选 | Default 仅 S1/S2；Creative 仅 S3/S4 | 两个候选策略 | 已实现 |
| 相似检索 | 每个候选从同模式、同策略的历史中寻找默认 3 条邻居 | 历史编号、距离、权重 | 已实现 |
| 评分预测 | 按相似程度加权汇总历史 Goal Support | 预计目标支持评分，1–5 分 | 已实现 |
| 推荐／暂缓 | 比较评分；超出共同历史幅度范围暂缓；相同评分留给用户选择 | 策略建议或说明 | 已实现 |
| 体验后反馈 | 实际使用策略与体验后的六维评分 | 独立的本地真实反馈文件 | v1.2 保存接口已实现，尚未收集真实反馈 |
| 灯光执行 | 转换策略为设备指令 | 实体灯变化 | 未来集成 |

模型类型为**逐策略的加权 KNN 评分预测**。当前 Session 尚未产生的评分不会作为推荐输入。

## 数据字段与灯光策略

| 字段 | 示例 | 用途 |
|---|---|---|
| session_id | 001 | 历史编号 |
| hrv_change_pct | -13.4 | 相对基线变化百分比；相似度使用其绝对幅度 |
| task_type | Ideation | 构思、视觉设计、写作、研究 |
| mode | Creative | 用户意图与候选筛选 |
| strategy | S3 | 当次使用策略 |
| goal_support | 4.5 | 灯光对目标的支持评分，1–5 分 |
| data_source | simulated | 明确来源 |

下表是**设计映射，尚未用于实体灯控制**：

| 策略 | 模式 | 色温 | 亮度 | 过渡 | 干预设计 |
|---|---|---:|---:|---|---|
| S1 Stable | Default | 4000K | 25% | 缓慢 | 稳定、低干扰 |
| S2 Focus Cue | Default | 5000K | 40% | 缓慢 | 轻度专注提示 |
| S3 Creative Drift | Creative | 3800K | 25% | 缓慢 | 低干预创作状态 |
| S4 Creative Cue | Creative | 4300K | 35% | 缓慢 | 创作模式中的轻度提示 |

## 环境与依赖

| 要求 | 说明 |
|---|---|
| Python | 已在 3.12.14 验证，建议 Python 3.12 |
| 第三方 Python 包 | 无；模型、XML 导入与测试只使用标准库 |
| 编辑器 | VS Code 可选；普通终端也可运行 |
| VS Code 扩展 | 编辑器内调试建议 Microsoft Python / Python Debugger |
| Apple 健康 XML | 仅离线导入需要；模拟推荐不需要 |

[requirements.txt](requirements.txt) 说明运行依赖；[REQUIREMENTS.md](REQUIREMENTS.md) 说明功能要求及验收条件。标准库中的 argparse、csv、dataclasses、datetime、json、math、pathlib、statistics、xml.etree.ElementTree、unittest、tempfile 等随 Python 提供，不需要逐个安装。

在已选好解释器的项目终端中运行：

```powershell
python test.py
python lightcue_ai.py --demo
python lightcue_ai.py --evaluate
python -m unittest -v test_model test_health_import
python import_health.py 'C:/path/to/export.xml' --task Ideation --mode Creative
```

导入时替换为自己实际的主健康 XML 文件路径，不使用 `export_cda.xml`。演示任务不代表采样时的真实任务。下面的固定解释器路径为本机说明，不是其他电脑的安装要求。

## 在 VS Code 中运行

安装官方 Python 3.12 与 Microsoft Python 扩展，用 VS Code 打开本项目，再通过 **Python: Select Interpreter** 选择已安装的 Python。编辑器配置因电脑而异，不随公开版本打包。

在项目终端先运行 `python test.py`，应显示 `LightCue AI is running!`。随后运行 `python lightcue_ai.py --multidim --demo`；手机演示运行 `python phone_demo.py --host 0.0.0.0 --port 8765`。Windows 用户也可双击 `start_phone_demo.cmd`。

## 推荐如何产生

1. 用户输入相对个人基线的 HRV 变化百分比、任务类型和模式。`10` 表示 `+10%`，不是 `0.10`。
2. Default 只比较 S1/S2；Creative 只比较 S3/S4。
3. 对每个候选策略，从同模式、同策略的历史中找到最相似的 3 条。
4. 相似度使用 HRV 变化的绝对幅度和任务是否相同：`距离 = sqrt(((历史幅度 - 当前幅度)/10)^2 + 0.25 × 任务不同)`。
5. 按 `1/(距离 + 0.05)` 加权平均历史 Goal Support，比较候选评分。

`k=3`、10 个百分点的缩放、任务差异权重和幅度特征都是公开的原型假设，没有使用“HRV 超过某阈值就选 Cue”的硬编码规则。符号保留在 CSV 中，但 v1 相似度只使用幅度；这来自模拟偏好设定，不能解释为生理事实。当前 Session 的评分不作为输入。

超出两个候选策略共有的历史幅度范围时，程序展示估分但暂缓推荐。评分相同时留给用户选择；缺少候选历史或输入无效时给出错误。评分差不是置信概率。

## 已验证结果

| 情境 | S3 预计评分 | S4 预计评分 | 输出 |
|---|---:|---:|---|
| Creative / Ideation / +3.9% | 4.56 | 3.10 | S3 |
| Creative / Ideation / +10.0% | 3.56 | 4.27 | S4 |

| 逐条留出评分预测方法 | 平均绝对误差（评分点数） |
|---|---:|
| 加权 KNN | 0.275 |
| 同模式／策略平均评分基准 | 0.687 |

Creative / Ideation / +3.9%：S3 约 4.56，S4 约 3.10，推荐 S3。

Creative / Ideation / +10.0%：S3 约 3.56，S4 约 4.27，推荐 S4。

40 次逐条留出评分预测：每次先移除该条数据，再预测它已使用策略的评分。KNN 平均绝对误差约 0.275 分；同样留出后的模式/策略平均分基线误差约 0.687 分。此评估使用预先指定的参数，验证模拟评分重建能力，不是推荐准确率，也没有真实用户测试。

## 数据限制与实现边界

40 条数据中，Ideation/Writing 总是使用低干预策略，Visual Design/Research 总是使用 Cue 策略。任务与策略存在混杂，无法可靠分离任务偏好和策略效果；部分候选预测完全借用其他任务数据，输出会提示这一点。后续应在同一任务、模式和相近 HRV 情境下收集不同策略的反馈，保留用户选择，再做真实 Session 验证。

已实现：读取模拟 CSV、按候选策略估分、展示相似历史、模式内推荐、命令行输入、逐条留出评估。

尚未实现：真实用户反馈采集界面、直接 HealthKit API 访问、实时采样、手机应用和灯光硬件控制。这份原型不证明灯光的生理或临床效果。

## Apple 健康导出接入（离线）

已增加 `import_health.py`，从提供的健康导出 XML 中只提取 HRV SDNN Record。大型 XML 逐条处理，不复制完整健康档案，不提取其他测量或身份信息。原始健康档案与生成的真实 HRV 文件仅在本机保留，公开项目和发布包不包含这些文件。

使用前面的 `python import_health.py` 命令导入自己的 XML。演示中选择的任务／模式不代表采样时的真实任务。

生成的 `health_import/hrv_samples.csv` 保存 HRV 数值与采样时间，`health_import/latest_context.json` 保存最新历史情境。真实测量没有加入 `lightcue_sessions.csv`，也没有生成虚构的 Goal Support 评分。

基线使用最新样本时间之前 7 天的有效 HRV 中位数，至少需要 5 条历史样本。当前样本和同时间样本不进入自己的基线，跨越当前时间的记录也被排除；同时间有多个数值时取其中位数。7 天和 5 条是可调整的原型参数，不是医学标准。支持 ms 与 s 单位，忽略非正数、非有限值、无时区或倒置时间，删除时间和数值完全相同的重复记录。此版本未进行活动状态、设备来源或更高级的生理信号质量筛选。

离线回放流程为 **导出 HRV → 历史基线 → 相对变化 → 推荐或暂缓**。超出候选历史共同范围时暂缓推荐。真实 HRV 不构成真实偏好标签，仍需收集实际使用策略后的反馈。此流程不连接实时 HealthKit，也不代表当前生理状态。

验证：原有 7 项模型检查与新增 4 项导入检查均通过，包含单位换算、仅 HRV 筛选、重复与非法值处理、基线排除当前和时间重叠样本、历史不足处理。

## 版本与迭代计划

| 版本 | 状态 | 内容 | 完成／验收依据 |
|---|---|---|---|
| v1.0 功能原型 | 已实现、已验证 | 模拟数据、加权 KNN、解释输出、离线 HRV 导入 | 演示结果与已有 11 项检查 |
| v1.1 文档完善 | 2026-10-11 已完成 | 竞品表、AI 清单、依赖说明、功能要求、策略映射和实现边界 | README、requirements.txt、REQUIREMENTS.md；未修改模型行为 |
| v1.2 六维反馈迭代 | 六维计算与本地保存已实现；真实验证待完成 | 六维权重、逐维预测、缺失项处理、来源隔离；后续补充真实体验覆盖与效果评估 | 新旧共 22 项检查通过；无真实六维用户效果结果 |
| v1.3 手机屏幕演示 | 已实现 | 浏览器控制页、S1–S4 手动测试、六维推荐驱动颜色与明暗、连接及过渡确认 | 26 项检查通过；屏幕模拟，不是实体灯控制 |
| 后续产品集成 | 规划 | 手机授权读取 HealthKit、反馈界面、实体灯控制 | 在真实设备上单独验证各接口后才能标为已完成 |

## 文件说明

| 文件 | 用途 |
|---|---|
| README.md | 概述、竞品、运行方法与迭代计划 |
| REQUIREMENTS.md | 功能要求与验收条件 |
| requirements.txt | 第三方运行依赖说明，当前无额外依赖 |
| test.py | Python 环境检查 |
| lightcue_sessions.csv | 40 条模拟反馈 |
| lightcue_ai.py | 策略预测、解释、推荐与评估 |
| lightcue_multidim.py | 六维评分、可调权重、来源隔离和实际体验反馈保存 |
| preference_weights.json | 六项评价权重，默认等权 |
| feedback_template_v2.json | 空白六维体验反馈模板 |
| test_multidim.py | 六维计算与反馈保存检查 |
| multidim_demo_results.txt | 独立六维模拟演示结果 |
| import_health.py | 离线 HRV 提取、基线与回放 |
| test_model.py / test_health_import.py | 模型与导入检查 |
| demo_results.txt | 已验证的模拟运行结果 |
| health_import/ | 本机导入后的 HRV、情境与运行结果；不随公开版本提供 |
| phone_demo.py / phone_web/ | 手机屏幕模拟灯服务、电脑控制页与手机显示页 |
| start_phone_demo.cmd | Windows 双击启动手机演示 |
| test_phone_demo.py | 模型到屏幕的 HTTP 链路与状态检查 |
| CHANGELOG.md | 本次升级内容与验证记录 |

作品集建议表述：**实现了可解释的灯光策略推荐功能原型，通过模拟 Session 验证推荐流程，并以真实 HRV 导出验证离线处理。**
