# LightCue AI Prototype v1

这是一个已运行验证的轻量个性化推荐原型。数据来自对话“解释是否需要AI”中确定的 40 条模拟 Session，编号、HRV 变化、任务、模式、策略和评分均保留。未定义的 baseline/current HRV、comfort 等字段没有补造。

## 在 VS Code 中运行

Microsoft Python 扩展已安装，项目已保存 Python 3.12.14 默认解释器配置，且已通过该解释器运行验证。使用的是本机 Codex 随附的 Python，路径见 `.vscode/settings.json`，不需要安装模型依赖。如果未来清理 Codex 的运行环境，需要重新选择 Python 解释器。系统的 `python` 命令目前仍指向 Windows 占位程序。

项目已由用户设为可信。已在 VS Code 状态栏确认选中的解释器为上述 Python 3.12.14，并实际运行 **LightCue: Check Python** 和 **LightCue: Recommendation Demo**；测试文本和推荐结果均在调试控制台正常输出。当前选中的运行配置为推荐演示，按 F5 即可再次运行。

Python Environments 扩展曾尝试安装 uv 并失败。本项目不需要 uv，已设置 `python.useEnvironmentsExtension: false`，使用已有解释器即可；该安装失败不影响已验证的调试运行。

打开“运行和调试”，选择 **LightCue: Check Python**，按 F5，调试控制台应显示：

```text
LightCue AI is running!
```

选择 **LightCue: Recommendation Demo**，按 F5，即可比较两种模式下的低幅度和高幅度变化。每种候选策略都会显示预测评分、历史记录编号、距离和归一化权重。

如使用 VS Code PowerShell 终端，可在项目文件夹运行以下命令。使用明确的解释器路径，避免 Windows 占位程序。

```powershell
& 'C:/Users/octopus ZHANG/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' test.py
& 'C:/Users/octopus ZHANG/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' lightcue_ai.py --hrv -10.3 --task Ideation --mode Creative
& 'C:/Users/octopus ZHANG/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' lightcue_ai.py --evaluate
& 'C:/Users/octopus ZHANG/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest -v test_model
```

## 推荐如何产生

1. 用户输入相对个人基线的 HRV 变化百分比、任务类型和模式。`10` 表示 `+10%`，不是 `0.10`。
2. Default 只比较 S1/S2；Creative 只比较 S3/S4。
3. 对每个候选策略，从同模式、同策略的历史中找到最相似的 3 条。
4. 相似度使用 HRV 变化的绝对幅度和任务是否相同：`距离 = sqrt(((历史幅度 - 当前幅度)/10)^2 + 0.25 × 任务不同)`。
5. 按 `1/(距离 + 0.05)` 加权平均历史 Goal Support，比较候选评分。

`k=3`、10 个百分点的缩放、任务差异权重和幅度特征都是公开的原型假设，没有使用“HRV 超过某阈值就选 Cue”的硬编码规则。符号保留在 CSV 中，但 v1 相似度只使用幅度；这来自模拟偏好设定，不能解释为生理事实。当前 Session 的评分不作为输入。

超出两个候选策略共有的历史幅度范围时，程序展示估分但暂缓推荐。评分相同时留给用户选择；缺少候选历史或输入无效时给出错误。评分差不是置信概率。

## 已验证结果

Creative / Ideation / +3.9%：S3 约 4.56，S4 约 3.10，推荐 S3。

Creative / Ideation / +10.0%：S3 约 3.56，S4 约 4.27，推荐 S4。

40 次逐条留出评分预测：每次先移除该条数据，再预测它已使用策略的评分。KNN 平均绝对误差约 0.275 分；同样留出后的模式/策略平均分基线误差约 0.687 分。此评估使用预先指定的参数，验证模拟评分重建能力，不是推荐准确率，也没有真实用户测试。

## 数据限制与实现边界

40 条数据中，Ideation/Writing 总是使用低干预策略，Visual Design/Research 总是使用 Cue 策略。任务与策略存在混杂，无法可靠分离任务偏好和策略效果；部分候选预测完全借用其他任务数据，输出会提示这一点。后续应在同一任务、模式和相近 HRV 情境下收集不同策略的反馈，保留用户选择，再做真实 Session 验证。

已实现：读取模拟 CSV、按候选策略估分、展示相似历史、模式内推荐、命令行输入、逐条留出评估。

尚未实现：真实用户反馈采集界面、直接 HealthKit API 访问、实时采样、手机应用和灯光硬件控制。这份原型不证明灯光的生理或临床效果。

## Apple 健康导出接入（离线）

已增加 `import_health.py`，从提供的健康导出 XML 中只提取 HRV SDNN Record。大型 XML 逐条处理，不复制完整健康档案，不提取其他测量或身份信息。原始文件仍在桌面的导出文件夹内。

在 VS Code 的“运行和调试”选择 **LightCue: Replay Apple Health Export**，按 F5。当前演示任务为用户选择的 **Ideation / Creative**；它不代表采样时的真实任务。该配置引用原始 XML 文件，移动原文件后需要更新 `.vscode/launch.json` 的路径。

生成的 `health_import/hrv_samples.csv` 保存 HRV 数值与采样时间，`health_import/latest_context.json` 保存最新历史情境。真实测量没有加入 `lightcue_sessions.csv`，也没有生成虚构的 Goal Support 评分。

基线使用最新样本时间之前 7 天的有效 HRV 中位数，至少需要 5 条历史样本。当前样本和同时间样本不进入自己的基线，跨越当前时间的记录也被排除；同时间有多个数值时取其中位数。7 天和 5 条是可调整的原型参数，不是医学标准。支持 ms 与 s 单位，忽略非正数、非有限值、无时区或倒置时间，删除时间和数值完全相同的重复记录。此版本未进行活动状态、设备来源或更高级的生理信号质量筛选。

首次导入得到 824 条有效唯一 HRV 记录，未发现非法或重复 HRV 记录。最新样本时间为北京时间 2026-10-05 22:36:25，HRV 约 35.48 ms；此前 7 天有 37 条基线样本，中位数约 47.45 ms，变化约 -25.23%。该幅度超过 Creative 模式候选策略共有的模拟历史范围 2.8%–13.0%，因此程序展示外推估分但暂缓推荐；估分不能作为已验证的偏好结果。

这实现的是 **真实导出 HRV → 滚动基线 → 相对变化 → 原型历史回放**，不构成持续 HealthKit 连接，也不表示当前生理状态。偏好模型仍使用 40 条模拟反馈。下一阶段需记录实际任务、使用策略和体验后的 Goal Support，再单独建立真实 Session 历史。

验证：原有 7 项模型检查与新增 4 项导入检查均通过，包含单位换算、仅 HRV 筛选、重复与非法值处理、基线排除当前和时间重叠样本、历史不足处理。
