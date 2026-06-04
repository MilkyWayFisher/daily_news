# Daily Investment Intelligence Brief

每日投资情报简报系统。它面向长期股票和 ETF 投资者，自动整合商业新闻、地缘政治、市场行情、宏观数据和资产影响路径，生成中文晨报，并通过 Email 或 Telegram 推送。

系统只做信息整理、风险提示和投资研究辅助，不做自动交易，不接入券商账户，也不输出直接买卖指令。

## V1.0 功能

- 多新闻源：NewsAPI、GDELT、Alpha Vantage News Sentiment、RSS
- 市场数据：VOO、SPY、QQQ、NVDA、AAPL、MSFT、TSLA、TLT、GLD、XLE、USO、VIX、DXY、WTI、Gold 等
- 宏观数据：CPI、Core CPI、PCE、就业、Fed Funds、2Y/10Y 美债、GDP、Retail Sales 等，优先通过 FRED 获取
- 资产映射：通过 `config/asset_mapping.yaml` 将事件主题映射到资产、方向和影响路径
- 0-100 分事件评分：相关性、重要性、新颖性、市场影响、置信度
- 增强版中文晨报：总览、重点事件、宏观环境、地缘政治、公司行业、资产影响表、观察清单、系统判断
- 失败容错：缺少某个 API key 或某个接口失败时继续生成简报，并在简报中标注数据暂不可用
- 存储路径：
  - `data/raw/YYYY-MM-DD-news.json`
  - `data/processed/YYYY-MM-DD-events.json`
  - `data/processed/YYYY-MM-DD-market.json`
  - `data/processed/YYYY-MM-DD-macro.json`
  - `data/briefs/YYYY-MM-DD-brief.md`

旧路径 `data/YYYY-MM-DD/` 也会继续写入，便于兼容已有习惯。

## 快速开始

建议使用 Python 3.8 或更新版本。GitHub Actions 使用 Python 3.12，本地 Windows 环境如果没有 `py` 启动器，也可以直接使用 `python`。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m briefing --demo --dry-run
```

`--demo` 使用样例新闻，不依赖外部 API。`--dry-run` 不发送邮件或 Telegram。

## 真实运行

先编辑 `.env`，至少填好邮件配置：

```env
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=your_email@gmail.com
EMAIL_SMTP_PASSWORD=your_gmail_app_password
EMAIL_FROM=your_email@gmail.com
EMAIL_TO=receiver@example.com
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
```

Gmail 必须使用 App Password，不要使用普通登录密码。

检查邮件连接，不会发送邮件：

```powershell
python -m briefing --check-delivery
```

发送一封 demo 简报：

```powershell
python -m briefing --demo
```

运行真实简报：

```powershell
python -m briefing
```

## API Key

所有 key 都通过 `.env` 或 GitHub Secrets 管理，不要写死在代码里。

```env
NEWSAPI_KEY=
ALPHAVANTAGE_API_KEY=
ALPHAVANTAGE_KEY=
FRED_API_KEY=
FINNHUB_API_KEY=
OPENAI_API_KEY=
LLM_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
```

说明：

- `NEWSAPI_KEY`：商业新闻抓取
- `ALPHAVANTAGE_API_KEY` 或 `ALPHAVANTAGE_KEY`：股票相关新闻和市场价格
- `FRED_API_KEY`：宏观数据
- `OPENAI_API_KEY` 或 `LLM_API_KEY`：可选，用于增强中文分析；不填时使用规则分析器
- `FINNHUB_API_KEY`：预留扩展

缺少某个 key 时，相关模块会跳过或标注数据暂不可用，不会让整个程序崩溃。

## 配置

主要配置在 [config.yaml](config.yaml)，资产映射在 [config/asset_mapping.yaml](config/asset_mapping.yaml)。

常用字段：

- `watchlist.tickers`：关注资产
- `sources.*`：启用或关闭数据源
- `market.symbols`：市场指标列表
- `macro.indicators`：宏观指标列表
- `rules.min_score`：进入简报的最低分数，默认 50
- `rules.asset_mapping_path`：资产映射配置路径
- `delivery.channel`：`email` 或 `telegram`

## 质量控制规则

V1.0 现在使用事件质量门槛，而不是简单关键词模板：

- 新闻时效：每日重点事件默认只纳入过去 36 小时内新闻；36-72 小时最高 60 分，3-7 天最高 40 分，超过 7 天不得进入每日重点事件。
- 相关性：新闻必须直接涉及 watchlist、核心宏观变量、明确商品/能源冲击、重大政策/地缘风险或当天市场事件；弱相关社会新闻会被归为 `low_relevance`。
- 分类：分类使用 `macro`、`market`、`geopolitics`、`company`、`sector`、`earnings`、`policy`、`commodity`、`rates`、`low_relevance`。
- 资产映射：先生成 `risk_factor`，再映射 `primary_assets` 和 `secondary_assets`。例如俄罗斯原油优先映射到 `oil_supply`、WTI/USO/XLE；AI 芯片新闻映射到 `semiconductors`、NVDA/MRVL/AMD/SMH/SOXX。
- 评分：最终分数由 freshness、relevance、importance、asset impact、source quality、specificity、data quality 组成；泛化映射、无明确传导路径、旧新闻会被强制压分。
- 市场数据：Alpha Vantage 失败或限速时，会尝试 Stooq/FRED fallback。若核心市场数据缺失超过 40%，简报会降低市场判断置信度。
- 输出检查：输出前会剔除超过 7 天旧新闻，压低重复 transmission path、弱传导路径和低市场覆盖下的高置信度判断。

## V1.1 输出格式

简报输出已经改为更适合手机和 Telegram 阅读的中文 Markdown：

- 用户可见字段全部中文化，例如“风险因子”“主要影响资产”“传导路径”“综合评分”“观察指标”。
- 新闻发布时间按 `America/Chicago` 显示，简报顶部会展示本地数据窗口。
- 同一主题新闻会合并为事件簇，例如多条原油 / 中东风险新闻会合并到“原油与能源供应风险”。
- 每个事件簇会结合市场价格生成“价格确认”：已确认、部分确认、与价格相悖、数据不足或中性。
- 价格确认会影响事件置信度：价格相悖会降级，数据不足时置信度不会被抬高。
- 资产影响改为卡片式“资产影响速览”，避免 Telegram 中出现过宽表格。
- 宏观数据改为解释式摘要，只展示通胀、就业、利率、增长等关键结论。
- 主简报底部只保留简短系统状态；详细过滤记录、重复路径、事件簇调试信息会保存到 `data/debug/YYYY-MM-DD-debug.md`。

## GitHub Actions

`.github/workflows/daily-brief.yml` 支持每天美国中部时间 07:00 和 21:00 自动运行，也支持手动触发。GitHub Actions 的 cron 使用 UTC，因此 workflow 会在 UTC 候选时间启动，并用 `America/Chicago` 本地时间 gate 严格筛选 07:00 / 21:00，避免夏令时和冬令时偏移。

需要把 `.env` 中对应的 key 配到 GitHub Secrets 或 Variables。至少需要：

- Secrets：`EMAIL_SMTP_HOST`、`EMAIL_SMTP_PORT`、`EMAIL_SMTP_USERNAME`、`EMAIL_SMTP_PASSWORD`、`EMAIL_FROM`、`EMAIL_TO`
- 推荐 Secrets：`NEWSAPI_KEY`、`ALPHAVANTAGE_API_KEY`、`FRED_API_KEY`、`OPENAI_API_KEY`
- Variables：`EMAIL_USE_TLS=true`、`EMAIL_USE_SSL=false`、`OPENAI_MODEL=gpt-4.1-mini`

## 验证

```powershell
python -m unittest discover -s tests
python -m compileall briefing tests
python -m briefing --demo --dry-run --no-save
```

## 免责声明

本系统仅用于信息整理和投资研究辅助，不构成个性化投资建议，不保证收益，不替代专业投资顾问。
