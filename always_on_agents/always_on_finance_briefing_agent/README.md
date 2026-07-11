# 📈 Always-on 美股信披简报 Agent（FinanceScout）

FinanceScout 是一个基于 Google ADK 的常驻金融信息简报 Agent。它监控 SEC EDGAR 的最新信息披露，筛出真正的高信号事件——举牌（SC 13D）、重大事项临时报告（8-K）、机构季度持仓（13F-HR）、内部人交易（Form 4）、IPO 注册（S-1）——生成一份中文日报，并同时产出一篇可直接发布的公众号 markdown 文章。

一套管线，两个出口：**订阅简报**（邮件 / 企业微信 / 飞书 / Telegram webhook）负责收入，**公众号文章**负责获客。

架构复用自 [always_on_hn_briefing_agent](../always_on_hn_briefing_agent/)，仅替换了数据源、筛选逻辑和渲染层。

## 功能

- **EDGAR 监控**：抓取 SEC EDGAR 最新披露 atom feed，无需注册或 API key。
- **信号筛选**：按披露类型加权打分（举牌 > 8-K > 机构持仓 > 内部人交易），过滤常规噪音。
- **关注列表**：设置 `FINBRIEF_WATCHLIST` 后，相关公司的披露获得排序加权并在摘要中标注。
- **中文简报**：每条披露附"为何重要"的中文解释，面向没有 SEC 背景的读者。
- **内容流水线**：同一份数据自动渲染成公众号格式的 markdown 文章。
- **合规默认**：只做事实性摘要，每份简报和文章自动附带免责声明；Agent 指令中写死"不提供投资建议"。
- **定时投递**：FastAPI 调度接口 + Gmail / webhook 投递，默认 dry-run，不配置凭据不会发出任何内容。

## 工作原理

1. 抓取 EDGAR 最新披露 feed（或使用确定性示例数据做演示）。
2. 按披露类型权重、关注列表命中、新鲜度打分排序。
3. 渲染中文简报（text + HTML）和公众号文章（markdown）。
4. 通过 ADK Web 对话获取，或由 Cloud Scheduler 等定时触发 HTTP 接口。
5. 配置投递后，简报经 Gmail 发送或 POST 到 webhook（可接企业微信/飞书/Telegram 机器人）。

## 安装

```bash
cd always_on_agents/always_on_finance_briefing_agent
pip install -r requirements.txt
export GOOGLE_API_KEY="your_gemini_api_key"   # ADK Web 对话模式需要
```

SEC 要求请求方在 User-Agent 中标识身份，启用 live 模式前请设置：

```bash
export FINBRIEF_EDGAR_UA="YourProject your_email@example.com"
```

## 方式一：ADK Web 对话

```bash
adk web .
```

试试这些提示词：

```text
给我今天的美股信披简报。
```

```text
把今天的简报写成一篇公众号文章。
```

## 方式二：本地运行调度 API

```bash
uvicorn scheduler_api:app --host 0.0.0.0 --port 8000
```

预览一次运行（不投递）：

```bash
curl "http://127.0.0.1:8000/finance-brief/dry-run?top_n=5&live=false"
```

启用真实 EDGAR 数据：

```bash
export FINBRIEF_LIVE_EDGAR=true
curl -X POST "http://127.0.0.1:8000/finance-brief/trigger" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true, "top_n": 5, "live": true}'
```

设置关注列表（英文公司名子串，逗号分隔）：

```bash
export FINBRIEF_WATCHLIST="apple,nvidia,berkshire"
```

## 方式三：GitHub Actions 定时运行（零服务器，推荐起步用）

仓库自带 [`.github/workflows/finance-brief.yml`](../../.github/workflows/finance-brief.yml)，每个工作日北京时间 20:30（美东盘前）自动运行一次：抓取 EDGAR → 渲染简报 → 投递。管线只用 Python 标准库，CI 中无需安装依赖。

启用步骤：

1. 在你 fork 的仓库页面进入 **Actions** 标签，点击启用 workflows（fork 默认关闭定时任务）。
2. 在 **Settings → Secrets and variables → Actions** 配置：
   - Secret `FINBRIEF_WEBHOOK_URL`（推荐，接企业微信/飞书/Telegram 转发服务）**或**一组 Gmail 凭据（`FINBRIEF_EMAIL_TO/FROM`、`FINBRIEF_GMAIL_CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN`）。
   - Secret `FINBRIEF_EDGAR_UA`：形如 `"YourProject your_email@example.com"`（不设则回退为仓库地址标识）。
   - 可选 Variable：`FINBRIEF_WATCHLIST`、`FINBRIEF_TOP_N`、`FINBRIEF_DELIVERY`。
3. 手动触发一次验证：Actions → FinanceScout Daily Brief → **Run workflow**（可勾选 dry run 只渲染不投递）。

即使不配置任何投递，简报正文也会打印在运行日志里，公众号文章 markdown 会显示在 job summary 中。注意：GitHub 会在仓库 60 天无活动后自动暂停定时 workflow，收到提醒邮件后点一下 re-enable 即可。

本地/服务器上等价的单次运行命令（配 cron 使用）：

```bash
python3 run_daily.py
```

## 方式四：定时投递（自建服务）

投递是显式开启的：请求体包含 `"dry_run": false` 且配置了投递方式才会真正发送。

- `FINBRIEF_DELIVERY=gmail`：通过 Gmail API 发送（需 `FINBRIEF_EMAIL_TO/FROM`、`FINBRIEF_GMAIL_CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN`）。
- `FINBRIEF_DELIVERY=webhook`：POST 到 `FINBRIEF_WEBHOOK_URL`（可选 `FINBRIEF_WEBHOOK_TOKEN` 作为 Bearer token）。webhook 收到 `subject`、`text`、`html`、`filings`、`next_actions`、`article`（公众号 markdown）。

企业微信群机器人示例：把 `FINBRIEF_WEBHOOK_URL` 指向一个小型转发服务，将 `text` 字段转成企业微信机器人的 markdown 消息格式即可。

推荐的美股盘前定时（北京时间 20:30 前，对应美东盘前）：

```text
0 20 * * 1-5
```

部署方式与 HN 模板一致：调度 API 放到 Cloud Run（或任意服务器 + cron），由 Cloud Scheduler 调用 `/finance-brief/trigger` 或 `/finance-brief/pubsub`。

## 测试

```bash
cd always_on_agents
python3 -m pytest always_on_finance_briefing_agent/tests/unit/
```

## 合规红线

本项目定位为**公开信息披露的事实性聚合与摘要**：

- 不输出买入/卖出建议、目标价、收益预测（Agent 指令中已写死）。
- 每份简报和文章自动附带免责声明。
- 在中国大陆运营付费订阅时，请确保内容不构成《证券法》及证券投资咨询相关法规意义上的投资建议。

## 商业化路线

1. **第 1-2 周**：开 live 模式每天给自己发一份，人工复核摘要质量，调整 `FILING_TYPES` 权重。
2. **第 3-4 周**：公众号文章免费发，攒前 100 个读者。
3. **验证留存后**：开付费档（知识星球/小报童），付费版走 webhook 实时推送 + 关注列表定制。
4. **长期**：每天的结构化披露数据（`filings` JSON）落库，沉淀成可卖给机构的历史事件数据集。
