"""
Xiaohongshu Interview Scraper - Core Scraping Module
小红书面试信息抓取核心模块

使用 xhs 库（基于 Playwright）进行签名，通过 Web API 搜索和获取笔记。
支持关键词搜索、内容解析、公司/岗位识别、反爬虫策略。
"""

import json
import logging
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from xhs import XhsClient
from playwright.sync_api import sync_playwright

from config import (
    BATCH_REST_MAX,
    BATCH_REST_MIN,
    COMPANY_SHORT_NAMES,
    EXCEL_HEADERS,
    HISTORY_FILE,
    INTERVIEW_KEYWORDS,
    MAX_DAILY_REQUESTS,
    MAX_NOTE_AGE_DAYS,
    MAX_PAGES_PER_KEYWORD,
    MAX_REQUEST_INTERVAL,
    MIN_COLLECTS,
    MIN_LIKES,
    MIN_REQUEST_INTERVAL,
    TARGET_COMPANIES,
    TECH_DIRECTIONS,
    DATA_DIR,
    LOG_FILE,
)

logger = logging.getLogger(__name__)


def setup_logging():
    """设置日志系统"""
    os.makedirs(DATA_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def _random_sleep(min_sec: float, max_sec: float):
    """随机等待，模拟人类行为"""
    sleep_time = random.uniform(min_sec, max_sec)
    logger.debug(f"等待 {sleep_time:.1f} 秒...")
    time.sleep(sleep_time)


def create_xhs_client(cookie: str) -> XhsClient:
    """
    创建 XhsClient 实例，使用 Playwright 进行签名。

    :param cookie: 小红书网页版 cookie 字符串
    :return: XhsClient 实例
    """
    playwright_ctx = sync_playwright().start()
    stealth_js_path = os.path.join(os.path.dirname(__file__), "stealth.min.js")

    # 如果没有 stealth.min.js，提示下载
    if not os.path.exists(stealth_js_path):
        logger.warning(
            "stealth.min.js not found. Downloading from CDN..."
        )
        import urllib.request
        urllib.request.urlretrieve(
            "https://cdn.jsdelivr.net/gh/requireCool/stealth.min.js/stealth.min.js",
            stealth_js_path,
        )
        logger.info("stealth.min.js downloaded successfully.")

    browser = playwright_ctx.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
    )
    context.add_init_script(path=stealth_js_path)
    page = context.new_page()
    page.goto("https://www.xiaohongshu.com")
    # 注入 cookie
    browser_cookie = cookie
    page.evaluate("void(0)")  # ensure page is loaded

    def sign_func(uri, data=None, a1="", web_session=""):
        page.evaluate("void(0)")
        encrypt_params = page.evaluate(
            "([url, data]) => window._webmsxyw(url, data)",
            [uri, data],
        )
        return {
            "x-s": encrypt_params["X-s"],
            "x-t": str(encrypt_params["X-t"]),
        }

    xhs_client = XhsClient(cookie=cookie, sign=sign_func)
    logger.info("XhsClient 初始化成功")
    return xhs_client


def generate_search_queries() -> list[dict]:
    """
    生成搜索关键词组合列表。
    策略：公司名 + 面试关键词 + 技术方向（可选）

    :return: 搜索查询列表，每个元素包含 keyword, company, interview_type, tech_direction
    """
    queries = []

    # 策略1: 公司 + 面试关键词
    for company in COMPANY_SHORT_NAMES:
        for interview_kw in INTERVIEW_KEYWORDS:
            queries.append({
                "keyword": f"{company} {interview_kw}",
                "company": company,
                "interview_type": interview_kw,
                "tech_direction": "",
            })

    # 策略2: 技术方向 + 面试关键词（不限定公司）
    for tech in TECH_DIRECTIONS[:5]:  # 取前5个方向避免过多
        for interview_kw in INTERVIEW_KEYWORDS[:3]:  # 取前3个面试关键词
            queries.append({
                "keyword": f"{tech} {interview_kw}",
                "company": "",
                "interview_type": interview_kw,
                "tech_direction": tech,
            })

    # 策略3: 公司 + 技术方向（热门组合）
    hot_combos = [
        ("OpenAI", "LLM算法"), ("Google", "大模型算法"),
        ("Meta", "多模态算法"), ("DeepSeek", "LLM算法"),
        ("字节跳动", "大模型算法"), ("Anthropic", "RLHF"),
        ("Kimi", "算法工程师"), ("xAI", "算法研究"),
    ]
    for company, tech in hot_combos:
        queries.append({
            "keyword": f"{company} {tech} 面试",
            "company": company,
            "interview_type": "面试",
            "tech_direction": tech,
        })

    # 去重
    seen = set()
    unique_queries = []
    for q in queries:
        if q["keyword"] not in seen:
            seen.add(q["keyword"])
            unique_queries.append(q)

    logger.info(f"生成了 {len(unique_queries)} 个搜索关键词组合")
    return unique_queries


def identify_company(title: str, desc: str) -> str:
    """
    从标题和内容中识别公司名称。

    :param title: 笔记标题
    :param desc: 笔记内容
    :return: 识别到的公司名称，未识别到返回空字符串
    """
    text = f"{title} {desc}".lower()
    company_mapping = {
        "openai": "OpenAI",
        "open ai": "OpenAI",
        "xai": "xAI",
        "x.ai": "xAI",
        "google": "Google",
        "谷歌": "Google",
        "amazon": "Amazon",
        "亚马逊": "Amazon",
        "aws": "Amazon",
        "apple": "Apple",
        "苹果": "Apple",
        "meta": "Meta",
        "facebook": "Meta",
        "anthropic": "Anthropic",
        "deepseek": "DeepSeek",
        "深度求索": "DeepSeek",
        "kimi": "Kimi",
        "月之暗面": "Kimi",
        "moonshot": "Kimi",
        "seed": "Seed",
        "字节跳动": "ByteDance/Seed",
        "bytedance": "ByteDance/Seed",
        "字节": "ByteDance/Seed",
        "tiktok": "ByteDance/Seed",
    }
    found_companies = []
    for keyword, company_name in company_mapping.items():
        if keyword in text:
            if company_name not in found_companies:
                found_companies.append(company_name)
    return ", ".join(found_companies) if found_companies else ""


def identify_tech_direction(title: str, desc: str) -> str:
    """
    从标题和内容中识别技术方向/岗位。

    :param title: 笔记标题
    :param desc: 笔记内容
    :return: 识别到的技术方向
    """
    text = f"{title} {desc}"
    direction_patterns = {
        "LLM算法": [r"LLM", r"大语言模型", r"大模型算法", r"大模型"],
        "AIInfra": [r"AI\s*Infra", r"AI基础设施", r"训练框架", r"推理部署"],
        "多模态算法": [r"多模态", r"multimodal", r"视觉语言"],
        "强化学习算法": [r"强化学习", r"RLHF", r"RL", r"reinforcement"],
        "NLP算法": [r"NLP", r"自然语言处理"],
        "推理优化": [r"推理优化", r"inference", r"量化", r"蒸馏"],
        "算法工程师": [r"算法工程师", r"算法岗"],
        "算法研究": [r"算法研究", r"research", r"研究员"],
        "预训练": [r"预训练", r"pre-?train"],
        "对齐": [r"对齐", r"alignment"],
    }
    found_directions = []
    for direction, patterns in direction_patterns.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                if direction not in found_directions:
                    found_directions.append(direction)
                break
    return ", ".join(found_directions) if found_directions else ""


def identify_interview_type(title: str, desc: str) -> str:
    """
    识别面试类型（面试经历/面试题/面筋等）

    :param title: 笔记标题
    :param desc: 笔记内容
    :return: 面试类型
    """
    text = f"{title} {desc}"
    type_patterns = {
        "面试经历": [r"面试经历", r"面试经验", r"面试分享", r"offer"],
        "面试题": [r"面试题", r"面试问题", r"考题", r"笔试题"],
        "面筋/面经": [r"面筋", r"面经"],
        "OA": [r"OA", r"在线测评", r"笔试"],
        "简历": [r"简历", r"投递", r"内推"],
        "薪资": [r"薪资", r"薪酬", r"待遇", r"package", r"offer"],
    }
    found_types = []
    for itype, patterns in type_patterns.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                if itype not in found_types:
                    found_types.append(itype)
                break
    return ", ".join(found_types) if found_types else "面试相关"


def parse_note_time(timestamp_ms: int) -> str:
    """
    将时间戳（毫秒）转换为可读的时间字符串。

    :param timestamp_ms: 毫秒级时间戳
    :return: 格式化时间字符串
    """
    if not timestamp_ms:
        return ""
    try:
        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone(timedelta(hours=8)))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError):
        return ""


def is_note_recent(timestamp_ms: int, max_age_days: int = MAX_NOTE_AGE_DAYS) -> bool:
    """
    检查笔记是否在指定天数内。

    :param timestamp_ms: 毫秒级时间戳
    :param max_age_days: 最大天数
    :return: 是否在范围内
    """
    if not timestamp_ms:
        return True  # 如果没有时间信息，默认保留
    try:
        note_time = datetime.fromtimestamp(
            timestamp_ms / 1000, tz=timezone(timedelta(hours=8))
        )
        cutoff = datetime.now(tz=timezone(timedelta(hours=8))) - timedelta(days=max_age_days)
        return note_time >= cutoff
    except (ValueError, OSError):
        return True


def load_history() -> set:
    """加载已抓取笔记ID的历史记录"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("note_ids", []))
    return set()


def save_history(note_ids: set):
    """保存已抓取笔记ID"""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    data = {
        "note_ids": list(note_ids),
        "last_updated": datetime.now().isoformat(),
        "count": len(note_ids),
    }
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def search_notes(
    xhs_client: XhsClient,
    query: dict,
    max_pages: int = MAX_PAGES_PER_KEYWORD,
    existing_ids: Optional[set] = None,
) -> list[dict]:
    """
    搜索小红书笔记并解析结果。

    :param xhs_client: XhsClient 实例
    :param query: 搜索查询信息（包含 keyword, company, interview_type, tech_direction）
    :param max_pages: 最大搜索页数
    :param existing_ids: 已存在的笔记ID集合（用于去重）
    :return: 解析后的笔记列表
    """
    keyword = query["keyword"]
    results = []
    if existing_ids is None:
        existing_ids = set()

    logger.info(f"开始搜索: '{keyword}'")

    for page in range(1, max_pages + 1):
        try:
            _random_sleep(MIN_REQUEST_INTERVAL, MAX_REQUEST_INTERVAL)
            search_result = xhs_client.get_note_by_keyword(
                keyword=keyword,
                page=page,
                sort="time_descending",  # 按时间排序获取最新内容
            )

            if not search_result or not search_result.get("items"):
                logger.info(f"  关键词 '{keyword}' 第 {page} 页无结果，停止翻页")
                break

            items = search_result.get("items", [])
            has_more = search_result.get("has_more", False)

            for item in items:
                note_card = item.get("note_card", {})
                if not note_card:
                    continue

                note_id = item.get("id", "")
                if note_id in existing_ids:
                    continue

                # 获取基本信息
                title = note_card.get("display_title", "")
                desc = note_card.get("desc", "")
                user_info = note_card.get("user", {})
                interact_info = note_card.get("interact_info", {})

                # 时间戳
                note_time = note_card.get("time", 0)
                last_update = note_card.get("last_update_time", 0)

                # 过滤: 时间范围
                if not is_note_recent(note_time):
                    continue

                # 过滤: 最低互动量
                liked_count = _parse_count(interact_info.get("liked_count", "0"))
                collected_count = _parse_count(interact_info.get("collected_count", "0"))
                if liked_count < MIN_LIKES and collected_count < MIN_COLLECTS:
                    continue

                # 识别公司和技术方向
                detected_company = identify_company(title, desc)
                if not detected_company and query.get("company"):
                    detected_company = query["company"]

                detected_tech = identify_tech_direction(title, desc)
                if not detected_tech and query.get("tech_direction"):
                    detected_tech = query["tech_direction"]

                detected_interview_type = identify_interview_type(title, desc)

                # 提取标签
                tag_list = note_card.get("tag_list", [])
                tags = ", ".join([t.get("name", "") for t in tag_list if t.get("name")])

                # 笔记类型
                note_type = note_card.get("type", "normal")

                # 作者信息
                author_name = user_info.get("nickname", "")
                author_id = user_info.get("user_id", "")
                author_home = f"https://www.xiaohongshu.com/user/profile/{author_id}" if author_id else ""

                # 笔记链接
                note_link = f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else ""

                # 内容摘要（截取前500字）
                content_summary = desc[:500] if desc else title

                parsed_note = {
                    "笔记ID": note_id,
                    "标题": title,
                    "内容摘要": content_summary,
                    "发布时间": parse_note_time(note_time),
                    "公司": detected_company,
                    "岗位方向": detected_tech,
                    "面试类型": detected_interview_type,
                    "作者昵称": author_name,
                    "作者ID": author_id,
                    "作者主页": author_home,
                    "笔记链接": note_link,
                    "点赞数": liked_count,
                    "收藏数": collected_count,
                    "评论数": _parse_count(interact_info.get("comment_count", "0")),
                    "分享数": _parse_count(interact_info.get("share_count", "0")),
                    "笔记类型": "视频" if note_type == "video" else "图文",
                    "标签": tags,
                    "抓取时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "搜索关键词": keyword,
                }
                results.append(parsed_note)
                existing_ids.add(note_id)

            logger.info(f"  第 {page} 页获取 {len(items)} 条，累计有效 {len(results)} 条")

            if not has_more:
                break

        except Exception as e:
            logger.error(f"  搜索 '{keyword}' 第 {page} 页出错: {e}")
            _random_sleep(10, 20)  # 出错后等待更久
            break

    return results


def _parse_count(count_str) -> int:
    """解析数量字符串（如 '1.2万'）为整数"""
    if isinstance(count_str, int):
        return count_str
    if not count_str:
        return 0
    count_str = str(count_str).strip()
    if "万" in count_str:
        try:
            return int(float(count_str.replace("万", "")) * 10000)
        except ValueError:
            return 0
    try:
        return int(count_str)
    except ValueError:
        return 0


def fetch_note_detail(
    xhs_client: XhsClient,
    note_id: str,
    xsec_token: str = "",
) -> Optional[dict]:
    """
    获取单个笔记的详细内容。

    :param xhs_client: XhsClient 实例
    :param note_id: 笔记ID
    :param xsec_token: xsec_token（从搜索结果中获取）
    :return: 笔记详情字典
    """
    try:
        _random_sleep(MIN_REQUEST_INTERVAL, MAX_REQUEST_INTERVAL)
        note_detail = xhs_client.get_note_by_id(
            note_id=note_id,
            xsec_token=xsec_token,
        )
        return note_detail
    except Exception as e:
        logger.error(f"获取笔记详情失败 {note_id}: {e}")
        return None


def run_scraper(
    cookie: str,
    incremental: bool = True,
    max_keywords: Optional[int] = None,
) -> list[dict]:
    """
    运行抓取器主流程。

    :param cookie: 小红书网页版 cookie
    :param incremental: 是否增量抓取（跳过已抓取过的笔记）
    :param max_keywords: 最大搜索关键词数量（用于测试）
    :return: 所有抓取到的笔记列表
    """
    setup_logging()
    logger.info("=" * 60)
    logger.info("小红书面试信息抓取开始")
    logger.info("=" * 60)

    # 加载历史记录
    existing_ids = load_history() if incremental else set()
    logger.info(f"已有历史记录: {len(existing_ids)} 条")

    # 创建客户端
    xhs_client = create_xhs_client(cookie)

    # 生成搜索关键词
    queries = generate_search_queries()
    if max_keywords:
        queries = queries[:max_keywords]

    all_notes = []
    total_requests = 0
    batch_count = 0

    for i, query in enumerate(queries):
        if total_requests >= MAX_DAILY_REQUESTS:
            logger.warning(f"已达到每日最大请求次数 ({MAX_DAILY_REQUESTS})，停止抓取")
            break

        logger.info(f"\n[{i + 1}/{len(queries)}] 搜索: {query['keyword']}")

        notes = search_notes(
            xhs_client=xhs_client,
            query=query,
            existing_ids=existing_ids,
        )
        all_notes.extend(notes)
        total_requests += MAX_PAGES_PER_KEYWORD

        # 每10个关键词休息一段时间
        batch_count += 1
        if batch_count >= 10:
            logger.info(f"已完成一批搜索，休息中...")
            _random_sleep(BATCH_REST_MIN, BATCH_REST_MAX)
            batch_count = 0

    # 保存历史记录
    for note in all_notes:
        existing_ids.add(note["笔记ID"])
    save_history(existing_ids)

    logger.info("=" * 60)
    logger.info(f"抓取完成！共获取 {len(all_notes)} 条新笔记")
    logger.info(f"历史总计: {len(existing_ids)} 条")
    logger.info("=" * 60)

    return all_notes
