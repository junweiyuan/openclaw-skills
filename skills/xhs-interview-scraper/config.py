"""
Configuration for Xiaohongshu Interview Scraper
小红书面试信息抓取工具配置文件
"""

# ============================================================
# 目标公司列表 (Target Companies)
# ============================================================
TARGET_COMPANIES = [
    "openai", "OpenAI",
    "xai", "xAI",
    "google", "Google", "谷歌",
    "amazon", "Amazon", "亚马逊",
    "apple", "Apple", "苹果",
    "meta", "Meta", "Facebook",
    "anthropic", "Anthropic",
    "deepseek", "DeepSeek", "深度求索",
    "kimi", "Kimi", "月之暗面", "Moonshot",
    "seed", "Seed", "字节跳动", "ByteDance",
]

# ============================================================
# 搜索关键词模板 (Search Keyword Templates)
# ============================================================
# 面试类型关键词
INTERVIEW_KEYWORDS = ["面试经历", "面试题", "面筋", "面经", "笔试题", "OA"]

# 技术方向关键词
TECH_DIRECTIONS = [
    "LLM算法",
    "大模型算法",
    "AIInfra",
    "AI Infra",
    "多模态算法",
    "强化学习算法",
    "RLHF",
    "算法工程师",
    "算法研究",
    "NLP算法",
    "推理优化",
]

# 组合搜索关键词: 公司名 + 面试类型 + 技术方向
# 例如: "OpenAI 面试经历 LLM算法", "Google 面筋 大模型"
COMPANY_SHORT_NAMES = [
    "OpenAI", "xAI", "Google", "Amazon", "Apple",
    "Meta", "Anthropic", "DeepSeek", "Kimi", "Seed",
    "字节跳动", "谷歌",
]

# ============================================================
# 反爬虫策略配置 (Anti-Crawling Settings)
# ============================================================
# 每次请求之间的最小等待时间（秒）
MIN_REQUEST_INTERVAL = 3
# 每次请求之间的最大等待时间（秒）
MAX_REQUEST_INTERVAL = 8
# 每批次搜索后的休息时间（秒）
BATCH_REST_MIN = 30
BATCH_REST_MAX = 60
# 每个搜索关键词最大抓取页数 (小红书限制最多约11页)
MAX_PAGES_PER_KEYWORD = 5
# 每日最大请求次数
MAX_DAILY_REQUESTS = 200

# ============================================================
# 数据过滤配置 (Data Filtering Settings)
# ============================================================
# 只抓取最近N天内的笔记
MAX_NOTE_AGE_DAYS = 365
# 最低点赞数过滤（过滤低质量内容）
MIN_LIKES = 5
# 最低收藏数
MIN_COLLECTS = 0

# ============================================================
# 输出配置 (Output Settings)
# ============================================================
# Excel输出文件名
OUTPUT_EXCEL = "interview_notes.xlsx"
# 数据存储目录
DATA_DIR = "data"
# 历史记录文件（用于增量更新）
HISTORY_FILE = "data/fetched_note_ids.json"
# 日志文件
LOG_FILE = "data/scraper.log"

# ============================================================
# Excel表头定义 (Excel Headers)
# ============================================================
EXCEL_HEADERS = [
    "笔记ID",
    "标题",
    "内容摘要",
    "发布时间",
    "公司",
    "岗位方向",
    "面试类型",
    "作者昵称",
    "作者ID",
    "作者主页",
    "笔记链接",
    "点赞数",
    "收藏数",
    "评论数",
    "分享数",
    "笔记类型",
    "标签",
    "抓取时间",
    "搜索关键词",
]
