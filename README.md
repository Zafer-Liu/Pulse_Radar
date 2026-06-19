<p align="center">
  <h1 align="center">🔊 声浪雷达</h1>
  <p align="center"><strong>B站舆情分析 · Agent 智能预警 · 话题全网搜索</strong></p>
</p>

<div align="center">

![Python](https://img.shields.io/badge/Python-3.13%2B-blue?logo=python&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D?logo=vuedotjs&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-支持-2496ED?logo=docker&logoColor=white)
![TRAE](https://img.shields.io/badge/TRAE%20AI-创造力大赛-6366F1)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

</div>

<blockquote>
<p>粘贴 B站视频链接一键分析，或输入话题关键词全网搜索聚合分析。<b>ReAct Agent 多轮推理</b>自主查证评论、<b>LLM 智能预警</b>替代固定阈值、<b>结构化行动建议</b>可直接执行。全部分析在本地完成，数据不出本机。</p>
<p>🏆 本项目为 <b>2026 TRAE AI 创造力大赛</b> 参赛作品。</p>
</blockquote>

<p align="center">
  <a href="#quickstart">⚡ 快速体验</a> ·
  <a href="#features">✨ 核心能力</a> ·
  <a href="#agent">🤖 Agent 系统</a> ·
  <a href="#usage">📖 使用指南</a> ·
  <a href="#config">🔧 配置</a> ·
  <a href="#deploy">🚀 部署</a> ·
  <a href="#faq">❓ FAQ</a>
</p>

---

<a id="quickstart"></a>
## ⚡ 30 秒快速体验

```bash
# 1. 克隆项目
git clone https://github.com/YOUR_USERNAME/shenglang-radar-real.git
cd shenglang-radar-real

# 2. 创建虚拟环境 + 安装依赖
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# 3. 构建前端
cd frontend
npm install && npm run build
cd ..

# 4. 启动服务
.venv\Scripts\python server.py

# 5. 浏览器打开 http://127.0.0.1:8088
```

> 💡 Windows 用户也可以直接双击 `start.bat`，脚本会自动检测 `.venv` 并完成前端构建。

---

<a id="features"></a>
## ✨ 核心能力

### 视频分析

| 分类 | 能力 | 说明 |
|------|------|------|
| **数据采集** | B站视频信息解析 | 支持 `b23.tv` 短链自动展开 + `BV` 长链直接解析 |
| | 公开评论抓取 | 可配置抓取页数（3/5/10/20 页），登录后获取全量评论 |
| | 扫码登录 | 前端本地生成二维码，不经过第三方服务 |
| **舆情分析** | 情感分析 | 词典法三库合并（Hownet / NTUSD / 清华李军 ~2.4 万词），含程度词加权 + 否定词翻转 |
| | LLM 情感增强 | 对中性评论进行 LLM 二次分类，提升准确度 |
| | 风险识别 | 自动标记高风险评论（辱骂、引战、敏感话题等） |
| | 关键词提取 | jieba TF-IDF 提取高频关键词 |
| | 观点聚类 | 基于关键词的评论聚类 |
| | AI 报告生成 | LLM / Agent 生成结构化舆情报告，无 API key 时自动降级为模板报告 |
| **监测调度** | 多视频管理 | 同时添加多个视频监测任务 |
| | 定时检测 | 每 N 小时 / 每 N 天自动检测，并发调度（上限 3 个） |
| | 历史记录 | 每个任务保留最近 30 次检测结果 |
| **可视化** | 仪表盘 | 情感饼图、风险分布、关键词云 |
| | 数据来源 | 展示原始评论数、有效评论数、水军识别、分析引擎标签 |

### 话题雷达

| 能力 | 说明 |
|------|------|
| 全网搜索 | 输入话题关键词，调用 B站搜索接口检索相关视频 |
| 聚合分析 | 取 Top N 热门视频，分别抓取评论后聚合分析整体舆情 |
| 跨视频对比 | 各视频独立分析 + 整体情绪分布、关键词、观点聚类 |
| 话题报告 | 自动生成话题舆情文本报告 |

---

<a id="agent"></a>
## 🤖 Agent 系统

### 四阶段智能架构

```
阶段一：Agent 化预警          阶段二：归因分析 Agent
┌─────────────────────┐    ┌──────────────────────────┐
│ 固定阈值 → LLM 判定  │    │ ReAct 循环多轮推理        │
│ 历史基线对比          │    │ 工具调用：搜索/修正/趋势   │
│ 误报率大幅下降        │    │ 推理轨迹可视化             │
└─────────────────────┘    └──────────────────────────┘

阶段三：策略生成 Agent       阶段四：多视频协同分析
┌─────────────────────┐    ┌──────────────────────────┐
│ 结构化行动建议        │    │ 跨视频情绪趋势对比        │
│ 回复草稿 / 置顶推荐   │    │ UP 主历史舆情追踪         │
│ 加密监控 / 团队通知   │    │ 话题发酵差异分析          │
│ 一键执行              │    │ 历史快照库               │
└─────────────────────┘    └──────────────────────────┘
```

### 阶段一：智能预警

传统方案用固定阈值报警（风险等级 ≥ high 就触发），但不同 UP 主的评论基线差异很大。声浪雷达采集本次快照与历史均值，交给 LLM 判断是否为真正的舆情异常，大幅降低误报率。LLM 不可用时自动降级回固定阈值。

### 阶段二：归因分析

单次 LLM 调用容易误判（如把反讽评论误判为负面）。Agent 采用 ReAct 循环，自主决定是否需要查看更多评论细节来验证判断，最多 5 轮推理。分析报告下方可展开查看完整的推理轨迹。

### 阶段三：策略生成

Agent 不仅输出分析报告，还生成可直接执行的结构化行动建议：

| 动作类型 | 说明 | 交互 |
|---------|------|------|
| **回复草稿** | 针对负面评论生成回复建议 | 一键复制 |
| **置顶推荐** | 标注正面高赞评论建议置顶 | 一键执行 |
| **加密监控** | 发现潜在风险话题建议持续跟踪 | 一键创建任务 |
| **团队通知** | 检测到严重舆情建议通知团队 | 一键推送 |

### 阶段四：多视频协同

历史记录升级为"快照库"，每次分析保存完整情绪分布。支持跨视频情绪趋势对比、UP 主历史舆情追踪、话题发酵差异分析。

### 三级降级保障

```
Agent 多轮推理 → 单次 LLM → 模板报告
     ↓ 失败         ↓ 失败      ↓ 兜底
```

无论是否有 API Key、网络是否正常，系统始终能输出分析结果。

---

<a id="usage"></a>
## 📖 使用指南

### 视频即时分析

1. 在输入框粘贴 B站视频链接（`https://www.bilibili.com/video/BV...`）
2. 选择抓取评论页数（3 / 5 / 10 / 20 页）
3. 点击 **立即分析**
4. 查看舆情分析报告：情感分布、风险识别、关键词、观点聚类、AI 报告

### 话题全网搜索

1. 点击顶部 **话题雷达** 切换到话题模式
2. 输入话题关键词（如"AI大模型"、"新能源"）
3. 选择分析视频数量（Top 3 / 5 / 8 / 10）和每视频评论页数
4. 点击 **话题分析**
5. 系统自动搜索 → 抓取评论 → 聚合分析 → 生成话题报告

### 多视频自动监测

1. 输入 B站视频链接 + 选择评论页数
2. 设置检测周期：每 N 小时 / 每 N 天
3. 点击 **加入监测**
4. 调度器自动按周期执行，支持"立即检测"和"查看历史结果"

### 扫码登录

B站对未登录请求限流严重，不登录只能拿到 3 条精选评论。点击右上角"登录 B站"扫码登录即可获取全量评论。二维码在浏览器本地生成，不经过任何第三方服务。

---

<a id="config"></a>
## 🔧 配置

### AI 报告（可选）

配置 LLM API Key 后可启用 AI 报告生成和 Agent 智能分析。不配置也能正常使用，系统会自动降级为模板报告。

```bash
cp .env.example .env
# 编辑 .env，填入你的 LLM_API_KEY
```

**支持的 LLM 提供商**：

| 提供商 | 说明 |
|--------|------|
| **DeepSeek**（默认） | 便宜、国内可直连 |
| **智谱 GLM** | 国内可直连，有免费额度 |
| **通义千问** | 阿里云 |
| **OpenAI** | 需代理 |
| **本地 Ollama** | 零 API 成本 |

### 告警通知（可选）

支持飞书、钉钉、企业微信 Webhook 告警。配置 LLM 后告警系统会使用智能判定替代固定阈值，大幅降低误报率。

### 部署方式

| 方式 | 说明 |
|------|------|
| **本地运行** | `python server.py`，浏览器打开 `http://127.0.0.1:8088` |
| **Docker** | `docker build -t shenglang-radar . && docker run -p 8088:8088 shenglang-radar` |
| **Railway** | Fork 到 GitHub → 连接 Railway → 自动构建部署 |

---

<a id="security"></a>
## 🔒 安全与隐私

- **全部分析在本地完成**，评论数据不经过任何第三方服务器
- **二维码本地生成**，登录凭证不泄露
- **敏感文件自动隔离**，`.env`、cookies 等不会被提交到代码仓库

---

<a id="faq"></a>
## ❓ 常见问题

<details>
<summary><b>为什么只能抓到 3 条评论？</b></summary>

B站对未登录请求限流。点击右上角"登录 B站"扫码登录即可获取全量评论。
</details>

<details>
<summary><b>不配置 API Key 能用吗？</b></summary>

可以。系统会自动降级为模板报告，情感分析、关键词提取、观点聚类等功能不受影响。配置 API Key 后可解锁 AI 报告、Agent 多轮推理、智能预警等高级功能。
</details>

<details>
<summary><b>Agent 推理轨迹不显示？</b></summary>

Agent 轨迹仅在 LLM 可用且分析成功时生成。请检查是否配置了 `LLM_API_KEY`。
</details>

<details>
<summary><b>告警一直不触发 / 误报太多？</b></summary>

配置 `LLM_API_KEY` 后，告警系统会使用智能判定，对比历史基线后决定是否告警，大幅降低误报率。
</details>

<details>
<summary><b>话题搜索没有结果？</b></summary>

尝试换个关键词或减少筛选条件。
</details>

<details>
<summary><b>b23.tv 短链解析失败？</b></summary>

请改用浏览器地址栏里的 BV 长链。
</details>

<details>
<summary><b>如何零成本使用 AI 功能？</b></summary>

安装 [Ollama](https://ollama.ai)，拉取 `qwen2.5:7b` 模型，在 `.env` 中配置本地地址即可。详见 `.env.example`。
</details>

---

<a id="license"></a>
## 📄 许可证

本项目基于 MIT License 开源。

---

<p align="center">
  <sub>Built with ❤️ for 2026 TRAE AI 创造力大赛</sub>
</p>
