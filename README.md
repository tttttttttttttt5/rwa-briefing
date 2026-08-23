# 📰 RWA 创业信息简报系统（AI驱动版）

> 每日自动整理RWA（现实世界资产）行业动态，按AI判断的"重要程度"分级推送
> 融资、项目上线、监管、大机构动向，一网打尽

---

## ✨ 核心功能

| 功能 | 说明 |
|------|------|
| 🔍 **多源数据采集** | RSS(Coindesk/The Block) + 公开API + 自定义项目追踪 |
| 🏷️ **叙事标签系统** | 自动匹配"定价/流动性/合规/基础设施/收益产品"等10种标签 |
| 🤖 **AI重要性评分** | 综合5个维度加权打分，自动分高/中/低三级 |
| 📋 **关注协议列表** | 自定义协议名单，命中即自动高优先级 |
| 💰 **融资阈值** | 超过 $1000万 自动标记"重大"，$5000万以上标记"极度重大" |
| 🏛️ **监管区域追踪** | 香港/新加坡/瑞士/美国/欧盟等地区政策优先推送 |
| 📈 **趋势统计** | 统计过去30天各标签出现频率与增长率，洞察叙事演变 |
| 📧 **分级推送** | 每日推送 / 仅重大事件推送 / 每周汇总 三档可选 |
| ⚙️ **YAML配置化** | 全部规则可通过 `config.yaml` 修改，无需动代码 |
| 🤖 **GitHub Actions** | 内置工作流，每日定时自动运行并邮件发送 |

---

## 🚀 快速开始

### 1. 本地安装与试运行

```bash
# 1. 克隆仓库后进入目录
cd rwa-briefing

# 2. 安装依赖（建议Python 3.10+）
pip install -r requirements.txt

# 3. 试运行（生成简报不发邮件，输出在 output/latest.md）
python main.py --dry-run

# 4. 查看生成的简报
cat output/latest.md
```

### 2. 在 GitHub 上自动化运行

#### 2.1 配置仓库 Secrets（用于发送邮件）

在 GitHub 仓库 → Settings → Secrets and variables → Actions 添加：

| Secret Name | 说明 | 示例 |
|-------------|------|------|
| `SMTP_USER` | 发件邮箱地址 | `rwa-alert@gmail.com` |
| `SMTP_PASSWORD` | 邮箱应用专用密码（不是登录密码！） | `abcd efgh ijkl mnop` |

> **Gmail 用户**：需要在 Google 账号开启「两步验证」→ 然后创建「应用专用密码」
>
> **QQ/163 邮箱**：在邮箱设置 → 开启 SMTP → 获取授权码

#### 2.2 修改 config.yaml 中的收件人

```yaml
push:
  email_recipients:
    - "your-email@example.com"   # ← 改成你的邮箱
```

#### 2.3 推送代码，Actions 会自动触发

- 每天 **北京时间 09:00** 自动运行
- 也可以在 Actions 页面手动触发运行（Run workflow）
- 运行完成后，可在 Actions 页面的 Summary 里直接预览简报内容

---

## ⚙️ 配置完全指南

所有定制都在 [config.yaml](file:///workspace/config.yaml) 中修改，无需改代码。

### 📋 1. 关注的协议列表 (WATCHLIST_PROTOCOLS)

这些协议如果出现在新闻中，**自动获得优先级加分**。`priority_boost: true` 的协议额外再加分。

```yaml
WATCHLIST_PROTOCOLS:
  - name: "Morpho"              # 协议名称
    category: "借贷协议"         # 分类（简报中展示）
    priority_boost: true        # 是否再额外加分
  - name: "Ostium"
    category: "RWA交易平台"
    priority_boost: true
  # 继续添加...
```

### 💰 2. 融资规模阈值 (FUNDING_THRESHOLD)

单位：**万美元**。超过阈值的融资事件，重要程度得分越高。

```yaml
FUNDING_THRESHOLD:
  CRITICAL: 5000    # >5000万美元: 极度重大（满分）
  MAJOR: 1000       # >1000万美元: 重大（75%~100%分）
  MODERATE: 300     # >300万美元: 中等（40%~75%分）
```

### 🏛️ 3. 监管区域列表 (REGIONS_WATCHLIST)

这些司法管辖区出现政策新闻时，结合「合规」标签触发加分。

```yaml
REGIONS_WATCHLIST:
  - name: "香港"
    code: "HK"
    priority: "high"   # high/medium/low 影响得分倍数
  - name: "新加坡"
    code: "SG"
    priority: "high"
```

### 🏷️ 4. 叙事标签系统 (NARRATIVE_TAGS)

每个标签有一组关键词。新闻内容命中关键词即自动打上标签。可自己增删。

```yaml
NARRATIVE_TAGS:
  - tag: "定价"
    keywords: ["pricing", "oracle", "估值", "定价", "mark-to-market"]
    description: "资产定价、预言机相关"

  - tag: "代币化"
    keywords: ["tokenization", "代币化", "RWA", "国债", "T-Bill"]
    description: "实物资产代币化相关"
```

### 🤖 5. AI 重要程度规则 (IMPORTANCE_RULES)

调整各维度的权重，或修改评分阈值：

```yaml
IMPORTANCE_RULES:
  weights:
    watchlist_protocol: 40      # 命中关注协议 (满分权重)
    funding_threshold: 30       # 融资规模
    region_policy: 25           # 关注区域监管
    big_institution: 35         # 大机构动向
    narrative_trend: 15         # 是否属于当前热门叙事

  thresholds:
    HIGH: 70     # >=70分: 高优先级（上头条）
    MEDIUM: 35   # >=35分: 中优先级

  BIG_INSTITUTIONS:   # 大机构名单（提及即加分）
    - "BlackRock"
    - "贝莱德"
    - "a16z"
    # ...
```

### 📧 6. 推送频率

```yaml
push:
  # 可选: daily(每日) | major_only(仅重大事件) | weekly(每周汇总)
  frequency: "daily"

  # 每日推送时间
  daily_run_time: "01:00"  # UTC = 北京时间09:00

  # 每周推送日（frequency=weekly 时生效）
  weekly_run_day: 0   # 0=周一
```

---

## 📂 项目结构

```
/workspace
├── config.yaml                  # ✅ 唯一需要修改的配置文件
├── main.py                      # 🚀 主入口脚本
├── requirements.txt             # Python 依赖
├── .github/workflows/
│   └── daily_briefing.yml       # GitHub Actions 自动工作流
├── src/
│   ├── config_loader.py         # 配置加载与验证
│   ├── data_collector.py        # RSS/API 数据采集
│   ├── event_classifier.py      # 🤖 AI评分 + 标签匹配 + 趋势统计
│   ├── briefing_generator.py    # Markdown 简报生成
│   └── email_sender.py          # 邮件发送（SMTP）
├── output/                      # 📄 生成的简报（每日md文件+latest.md）
└── data/
    └── tag_trends.json          # 📈 30天标签趋势历史数据
```

---

## 🔄 数据接入扩展说明

当前数据采集模块 `src/data_collector.py` 中包含两部分：

### 已有实现
- **RSS订阅源**：CoinDesk / The Block / Cointelegraph / Decrypt 等公开RSS
- **模拟数据**：12条RWA新闻样本（用于演示/离线测试）

### 建议扩展（实际生产环境）

编辑 `src/data_collector.py` 的 `_collect_simulated_data` 方法，接入真实 API：

| 数据源 | 接入方式 | 说明 |
|--------|----------|------|
| **BlockBeats AI信息流** | 官方开放API | 搜索关键词 "RWA"、"代币化"、"融资" |
| **KuCoin Crypto Pulse** | KuCoin 开放API | 追踪 RWA 相关叙事和讨论热度 |
| **项目方 LinkedIn** | LinkedIn RSS / 官方博客 RSS | 对每个 WATCHLIST_PROTOCOLS 加对应的博客 URL |
| **Discord/Telegram** | 机器人 webhook | 关注核心项目社区公告 |

示例：接入 BlockBeats API
```python
def _collect_blockbeats(self, cutoff_time):
    url = "https://api.theblockbeats.news/v1/open-api/home-list?search=RWA"
    resp = requests.get(url, headers={"X-API-KEY": "<你的key>"})
    # ... 解析并返回 NewsEvent 列表
```

---

## 📝 输出简报示例结构

```
# 📰 RWA创业信息每日简报

## 📊 本期概览
| 指标 | 数值 |
|------|------|
| 📰 动态总数 | 12 条 |
| 🔴 高优先级 | 3 条 |
| 💰 融资总额 | 约 $17,650 万美元 |

## 🔴 头条关注
### 1. BlackRock扩大BUIDL基金规模，已突破30亿美元
> 机构动向

### 2. Morpho完成8000万美元B轮融资，a16z领投
> 融资 · 借贷协议

## 💰 融资速递
| 项目/协议 | 融资金额 | 投资方 |
|-----------|----------|--------|
| Morpho | 🔴 $8,000万 | a16z领投 |
| Maple Finance | 🟡 $1,500万 | - |

## 🏛️ 监管政策动态
### 🇭🇰 香港 (HK)
- 香港证监会发布代币化证券指引...

## 📈 叙事趋势洞察
### 🚀 上升趋势标签
- **代币化**: ████████ +120%
- **合规**: ██████ +75%

### 💡 AI洞察
📈 「代币化」叙事热度持续上升，建议重点关注相关项目动态。
💰 本期行业融资活跃，累计融资超过 $17,650万美元...
```

---

## 🤝 常见问题

**Q: 不想写代码，能不能用 Google Sheets + Zapier？**

A: 可以。备选方案：
1. 把 config.yaml 的各个配置项改成 Google Sheets 的 Tab（协议列表、区域列表、标签关键词）
2. Zapier 设一个 "每日定时触发"，读取 Sheets 内容
3. Zapier 调用 RSS by Zapier + Webhook，聚合后用 Filter 匹配关键词
4. 最后通过 Zapier 的 "Send Outbound Email" 发送
5. 本系统已经用纯代码实现了以上逻辑，且 AI 评分功能更灵活，推荐先试用本方案

**Q: 简报里的数据来源有限怎么办？**

A: 在 `config.yaml → data_sources → rss_feeds` 里添加更多 RSS 源，或修改 `src/data_collector.py` 接入付费 API（NewsAPI、CryptoPanic 等）。

**Q: 能否接入 LLM 让 AI 洞察更准确？**

A: 可以。编辑 `src/briefing_generator.py` 的 `_generate_ai_insight()` 方法，把基于规则的逻辑替换成 GPT/Claude API 调用即可。建议用环境变量存储 API Key。

---

## 📜 License

MIT
