# 声浪雷达 — 开发文档

> 面向开发者的技术文档，包含项目结构、技术架构、API 接口、配置详解等。

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **前端** | Vue 3.5 + Vite 6 + ECharts 6 + qrcode | SPA，构建产物由后端 serve |
| **后端** | Python 3.13 标准库（`http.server`） | 零框架依赖 |
| **Agent** | 纯 Python ReAct + OpenAI function calling | 不依赖 LangChain |
| **分词** | jieba 0.42+ | TF-IDF 关键词 + 词典法情感分析 |
| **情感词典** | Hownet + NTUSD + 清华李军 | 三库合并 ~24,000 词 |
| **AI** | OpenAI 兼容协议 | 默认 DeepSeek，可切换任意兼容模型 |
| **搜索** | B站 WBI 签名搜索接口 | 话题雷达全网搜索 |
| **存储** | 本地 JSON 文件 + 内存缓存 | 避免重复读盘 |
| **调度** | 内置线程调度器 | 30 秒巡检，并发上限 3 |

---

## 技术架构

```
┌──────────────────────────────────────────────────────┐
│                  前端 (Vue 3 + Vite 6)                  │
│  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌────────────┐ │
│  │ 视频分析 │ │ 话题雷达  │ │ 监测中心│ │ Agent 轨迹  │ │
│  │ ECharts  │ │ 聚合分析  │ │ 任务管理│ │ 行动建议    │ │
│  └─────────┘ └──────────┘ └────────┘ └────────────┘ │
└────────────────────┬─────────────────────────────────┘
                     │ HTTP /api/*
┌────────────────────▼─────────────────────────────────┐
│                后端 (Python 标准库)                     │
│  ┌──────────┐ ┌───────────┐ ┌────────────────────┐  │
│  │ 链接解析   │ │ 评论抓取    │ │ 分析引擎            │  │
│  │ BV/短链   │ │ 分页/登录   │ │ 情感/TF-IDF/聚类    │  │
│  └──────────┘ └───────────┘ └────────────────────┘  │
│  ┌──────────┐ ┌───────────┐ ┌────────────────────┐  │
│  │ Agent 核心│ │ LLM 报告   │ │ 预警系统            │  │
│  │ ReAct循环 │ │ 三级降级   │ │ LLM 二次判定       │  │
│  └──────────┘ └───────────┘ └────────────────────┘  │
│  ┌──────────┐ ┌───────────┐ ┌────────────────────┐  │
│  │ 调度器    │ │ 话题搜索    │ │ 数据持久化          │  │
│  │ 并发/周期 │ │ B站 WBI    │ │ data.json          │  │
│  └──────────┘ └───────────┘ └────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

---

## 项目结构

```
shenglang-radar-real/
├── server.py              # 后端核心（HTTP API + 评论抓取 + 分析 + 调度 + Agent）
├── start.bat / start.ps1  # Windows 一键启动脚本
├── Dockerfile             # 多阶段 Docker 构建（Node.js 前端 + Python 后端）
├── railway.json          # Railway 云部署配置
├── requirements.txt       # Python 依赖（jieba ≥ 0.42.1）
├── .env.example           # 环境变量配置模板（含多 LLM 提供商示例）
│
├── analysis/              # 舆情分析引擎
│   ├── __init__.py
│   ├── lexicon.py         # 词典法情感分析（三库合并 + 程度词 + 否定词）
│   ├── llm_report.py      # LLM AI 报告生成（三级降级链）
│   ├── llm_sentiment.py   # LLM 情感增强（中性评论二次分类）
│   ├── alert.py           # Agent 化预警（LLM 二次判定替代固定阈值）
│   └── agent_core.py      # ReAct Agent 核心（多轮推理 + 工具调用）
│
├── data/                  # 情感词典数据文件
│   └── lexicon/
│       ├── hownet/        # 知网情感词典（正面/负面/程度词）
│       ├── ntusd/         # NTUSD 情感词典（正面/负面）
│       ├── tsinghua/      # 清华李军情感词典（正面/负面）
│       ├── add_dict.txt   # 自定义补充词典
│       └── stop_words.txt # 停用词表
│
├── frontend/              # Vue 3 前端源码
│   ├── package.json       # Vue 3.5 + Vite 6 + ECharts 6 + qrcode
│   ├── vite.config.js
│   └── src/
│       ├── api/index.js           # API 封装
│       ├── App.vue                 # 根组件（路由 + 状态管理）
│       ├── assets/main.css         # 全局样式
│       ├── components/
│       │   ├── UnifiedInput.vue   # 视频分析/话题雷达模式切换
│       │   ├── AnalysisResult.vue # 分析结果展示（情感/风险/关键词/聚类/报告）
│       │   ├── TopicResult.vue    # 话题分析结果（聚合分析 + 跨视频对比）
│       │   ├── AgentTrace.vue     # Agent 推理轨迹可视化（时间线）
│       │   ├── ActionsPanel.vue   # AI 行动建议面板（回复/置顶/监控/告警）
│       │   ├── MonitorCard.vue    # 监测任务卡片
│       │   ├── MonitorForm.vue    # 监测任务创建/编辑表单
│       │   ├── TopicSearch.vue    # 话题搜索独立组件
│       │   ├── TopBar.vue        # 顶部导航栏（登录/设置/告警）
│       │   ├── HeroSection.vue   # 首页引导区
│       │   ├── LoginModal.vue     # B站扫码登录弹窗
│       │   ├── AlertModal.vue    # 告警配置弹窗
│       │   ├── SettingsModal.vue # LLM 配置弹窗
│       │   ├── AppToast.vue      # 全局提示消息
│       │   ├── BackgroundParticles.vue  # 背景粒子动效
│       │   ├── ui/
│       │   │   ├── EmptyState.vue  # 空状态占位
│       │   │   └── Skeleton.vue    # 骨架屏加载态
│       │   └── charts/
│       │       ├── SentimentRing.vue  # 情感分布环形图
│       │       └── TrendMini.vue      # 趋势迷你折线图
│       └── composables/
│           ├── useECharts.js    # ECharts 响应式封装
│           ├── useLogin.js       # B站登录状态管理
│           ├── useMonitors.js    # 监测任务 CRUD + 轮询
│           ├── useTheme.js       # 主题切换
│           └── useToast.js       # 全局提示
│
└── test_*.py              # 单元测试
    ├── test_lexicon.py    # 情感词典测试
    ├── test_llm_parse.py  # LLM 响应解析测试
    ├── test_alert.py      # 告警判定逻辑测试
    └── test_server_utils.py  # 服务端工具函数测试
```

---

## API 接口

### GET 接口

| 路径 | 说明 |
|------|------|
| `/api/analyze` | 视频分析（参数：`url`, `pages`） |
| `/api/monitors` | 获取所有监测任务 |
| `/api/monitor/history` | 获取监测任务历史记录（参数：`id`） |
| `/api/login/status` | 查询 B站登录状态 |
| `/api/config/llm` | 获取 LLM 配置 |
| `/api/config/alert` | 获取告警配置 |
| `/api/topic/search` | 话题搜索（参数：`keyword`, `top_n`） |
| `/api/topic/analyze` | 话题聚合分析（参数：`keyword`, `top_n`, `pages_per_video`） |
| `/api/agent/trace` | 获取 Agent 推理轨迹（参数：`trace_id`） |
| `/api/trend/up` | UP 主历史舆情趋势（参数：`mid`） |
| `/api/trend/topic` | 话题跨视频趋势（参数：`keyword`） |
| `/api/image` | 图片代理（防 SSRF，域名白名单） |

### POST 接口

| 路径 | 说明 |
|------|------|
| `/api/login/qrcode` | 生成 B站登录二维码 |
| `/api/login/poll` | 轮询二维码扫描状态 |
| `/api/login/logout` | 登出 B站 |
| `/api/config/llm` | 更新 LLM 配置 |
| `/api/config/alert` | 更新告警配置 |
| `/api/config/alert/test` | 测试告警推送 |
| `/api/monitor/add` | 添加监测任务 |
| `/api/monitor/update` | 更新监测任务 |
| `/api/monitor/delete` | 删除监测任务 |
| `/api/monitor/run` | 立即执行一次检测 |

---

## 环境变量

### LLM 配置

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `LLM_API_KEY` | LLM API Key | 空（降级为模板报告） |
| `LLM_BASE_URL` | OpenAI 兼容 API 地址 | `https://api.deepseek.com/v1` |
| `LLM_MODEL` | 模型名称 | `deepseek-chat` |
| `LLM_TIMEOUT` | 请求超时（秒） | `30` |

### 告警配置

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `ALERT_WEBHOOK_URL` | 飞书/钉钉/企业微信 Webhook 地址 | 空 |
| `ALERT_MIN_RISK` | 最低告警风险等级（`low` / `medium` / `high`） | `high` |
| `ALERT_COOLDOWN_SEC` | 同一任务告警冷却时间（秒） | `3600` |

### 鉴权

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `AUTH_TOKEN` | POST 接口访问令牌（远程访问时必填） | 空（仅允许本机） |

### 可选 LLM 提供商配置

| 提供商 | BASE_URL | MODEL | 说明 |
|--------|----------|-------|------|
| **DeepSeek**（默认） | `https://api.deepseek.com/v1` | `deepseek-chat` | 便宜、国内可直连 |
| **智谱 GLM** | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` | 国内可直连，有免费额度 |
| **通义千问** | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-turbo` | 阿里云 |
| **OpenAI** | `https://api.openai.com/v1` | `gpt-4o-mini` | 需代理 |
| **本地 Ollama** | `http://localhost:11434/v1` | `qwen2.5:7b` | 零 API 成本 |

---

## 部署

### Docker

```bash
# 构建镜像
docker build -t shenglang-radar .

# 运行（可通过环境变量注入 LLM 配置）
docker run -d -p 8088:8088 \
  -e LLM_API_KEY=sk-your-key \
  -e LLM_BASE_URL=https://api.deepseek.com/v1 \
  -e LLM_MODEL=deepseek-chat \
  shenglang-radar
```

Dockerfile 采用多阶段构建：
- 阶段 1：Node.js 22 Alpine 构建前端
- 阶段 2：Python 3.13 Slim 运行后端（内置 gcc/g++ 用于 jieba C 扩展编译）

### Railway

1. Fork 本仓库到 GitHub
2. 在 Railway 新建项目 → 连接 GitHub 仓库
3. Railway 自动检测 `Dockerfile` 并构建部署
4. 在 Railway 环境变量中配置 `LLM_API_KEY` 等敏感信息
5. 部署完成后自动获得公网访问地址

`railway.json` 已预置健康检查和重启策略配置。

---

## 测试

```bash
# 运行全部测试
.venv\Scripts\python -m pytest test_*.py -v

# 运行单个测试
.venv\Scripts\python -m pytest test_lexicon.py -v
```

| 测试文件 | 覆盖模块 |
|---------|---------|
| `test_lexicon.py` | 情感词典加载、分词、情感判定 |
| `test_llm_parse.py` | LLM 响应 JSON 解析、降级逻辑 |
| `test_alert.py` | 告警判定、冷却时间、Webhook 推送 |
| `test_server_utils.py` | 服务端工具函数（链接解析等） |

---

## 安全设计

| 措施 | 说明 |
|------|------|
| **本地分析** | 全部分析在本地完成，评论不经过第三方 |
| **二维码本地生成** | 前端 `qrcode` 库在浏览器本地生成，不泄露到第三方 |
| **图片代理防 SSRF** | `/api/image` 域名白名单 + 逐跳重定向校验 |
| **写接口鉴权** | POST 接口默认仅本机放行，远程需 `AUTH_TOKEN` |
| **敏感文件隔离** | `cookies.txt`、`data.json`、`.env` 已 `.gitignore` |
