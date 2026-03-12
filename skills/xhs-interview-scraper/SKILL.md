# 小红书面试信息抓取工具 - 技能文件

## 概述

本工具用于从小红书（Xiaohongshu/RedNote）平台抓取 LLM/AI 相关岗位的面试经历、面试题、面筋等内容，
将图文内容结构化转换为 Excel 表格存储，支持按公司、岗位方向、时间等维度检索。

## 目标公司

OpenAI, xAI, Google, Amazon, Apple, Meta, Anthropic, DeepSeek, Kimi, Seed (字节跳动)

## 技术方向

LLM算法, AIInfra, 多模态算法, 强化学习算法, NLP算法, 推理优化, 算法工程师, 算法研究

## 搜索关键词策略

采用三层组合策略生成搜索关键词：

1. **公司 + 面试关键词**: `"OpenAI 面试经历"`, `"Google 面筋"`, `"DeepSeek 面试题"` ...
2. **技术方向 + 面试关键词**: `"LLM算法 面试经历"`, `"多模态算法 面筋"` ...
3. **公司 + 技术方向 + 面试**: `"OpenAI LLM算法 面试"`, `"Meta 多模态算法 面试"` ...

面试关键词包括: 面试经历, 面试题, 面筋, 面经, 笔试题, OA

## 数据结构 (Excel表头)

| 字段 | 说明 |
|------|------|
| 笔记ID | 小红书笔记唯一标识 |
| 标题 | 笔记标题 |
| 内容摘要 | 笔记正文前500字 |
| 发布时间 | 笔记发布时间 |
| 公司 | 自动识别的目标公司名 |
| 岗位方向 | 自动识别的技术方向 |
| 面试类型 | 面试经历/面试题/面筋等 |
| 作者昵称 | 发布者昵称 |
| 作者ID | 发布者用户ID |
| 作者主页 | 发布者主页链接 |
| 笔记链接 | 笔记完整URL |
| 点赞数 | 笔记点赞数 |
| 收藏数 | 笔记收藏数 |
| 评论数 | 笔记评论数 |
| 分享数 | 笔记分享数 |
| 笔记类型 | 图文/视频 |
| 标签 | 笔记标签列表 |
| 抓取时间 | 数据抓取时间 |
| 搜索关键词 | 命中的搜索关键词 |

## 反爬虫策略

1. **随机延迟**: 每次请求间隔 3-8 秒随机等待
2. **批次休息**: 每搜索 10 个关键词后休息 30-60 秒
3. **每日限额**: 最大 200 次请求/天
4. **低频抓取**: 默认每个关键词最多翻 5 页（小红书限制最多约 11 页）
5. **User-Agent 伪装**: 使用常见浏览器 UA
6. **Playwright 签名**: 使用 stealth.min.js 绕过基础检测

## 环境准备

```bash
# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium

# 下载 stealth.min.js（首次运行会自动下载）
curl -O https://cdn.jsdelivr.net/gh/requireCool/stealth.min.js/stealth.min.js
```

## 使用流程

### 1. 获取 Cookie

1. 用浏览器打开 https://www.xiaohongshu.com
2. 登录你的小红书账号
3. 按 F12 打开开发者工具
4. 进入 Application → Cookies → www.xiaohongshu.com
5. 复制所有 cookie 键值对，拼接为字符串格式: `"a1=xxx; web_session=xxx; ..."`
6. 或者在 Network 标签中随意点击一个请求，从 Request Headers 中复制完整 Cookie
7. 保存到 `cookie.txt` 文件中

> **重要**: Cookie 有效期有限（通常数天到数周），过期后需要重新获取。
> 建议定期检查 Cookie 有效性。

### 2. 首次抓取

```bash
# 方式一: 命令行传入 cookie
python main.py --cookie "a1=xxx; web_session=xxx; ..."

# 方式二: 从文件读取 cookie
python main.py --cookie-file cookie.txt

# 测试模式（只搜索3个关键词）
python main.py --cookie-file cookie.txt --max-keywords 3
```

### 3. 增量更新

```bash
# 只获取新笔记（默认行为）
python main.py --cookie-file cookie.txt --incremental

# 全量重新抓取
python main.py --cookie-file cookie.txt --full
```

### 4. 每日定时任务

```bash
# 手动运行
python daily_update.py

# 使用 cron 定时（每天早上9点）
crontab -e
# 添加: 0 9 * * * cd /path/to/xhs-interview-scraper && /usr/bin/python3 daily_update.py

# 使用环境变量传入 cookie
XHS_COOKIE="a1=xxx; ..." python daily_update.py
```

### 5. 查看结果

Excel 文件保存在 `data/interview_notes.xlsx`，包含以下 Sheet：
- **统计摘要**: 按公司、技术方向的统计概览
- **全部笔记**: 所有笔记数据（可筛选、排序）
- **各公司分Sheet**: 按公司分类的笔记（如 OpenAI、Google 等）

## 输出文件说明

```
data/
├── interview_notes.xlsx    # 主数据文件（Excel）
├── interview_notes.json    # JSON 格式数据（可选，--export-json）
├── fetched_note_ids.json   # 已抓取笔记ID记录（用于增量更新）
├── scraper.log             # 运行日志
└── daily_summary.log       # 每日更新摘要
```

## 配置说明

所有配置项在 `config.py` 中，可根据需求调整：

- `TARGET_COMPANIES`: 目标公司列表
- `INTERVIEW_KEYWORDS`: 面试类型关键词
- `TECH_DIRECTIONS`: 技术方向关键词
- `MIN_REQUEST_INTERVAL` / `MAX_REQUEST_INTERVAL`: 请求间隔
- `MAX_PAGES_PER_KEYWORD`: 每个关键词翻页数
- `MAX_DAILY_REQUESTS`: 每日最大请求数
- `MIN_LIKES`: 最低点赞数过滤
- `MAX_NOTE_AGE_DAYS`: 笔记最大时间范围（天）

## 注意事项

1. **合规使用**: 请遵守小红书平台的使用条款，仅用于个人学习研究
2. **低频抓取**: 请勿高频请求，避免对平台造成压力
3. **Cookie 安全**: 不要将 cookie 提交到版本控制或分享给他人
4. **数据隐私**: 抓取的数据仅供个人使用，注意保护作者隐私
5. **反爬风险**: 如果触发验证码（461/471状态码），请暂停抓取并稍后重试
6. **IP 封禁**: 如遇 IP 封禁，可配置代理使用

## 项目结构

```
xhs-interview-scraper/
├── main.py              # 主入口，命令行工具
├── scraper.py           # 核心抓取模块
├── excel_exporter.py    # Excel 导出模块
├── daily_update.py      # 每日定时更新模块
├── config.py            # 配置文件
├── requirements.txt     # Python 依赖
├── SKILL.md             # 技能文件（本文件）
├── .gitignore           # Git 忽略规则
└── data/                # 数据输出目录
    ├── interview_notes.xlsx
    ├── fetched_note_ids.json
    └── scraper.log
```
