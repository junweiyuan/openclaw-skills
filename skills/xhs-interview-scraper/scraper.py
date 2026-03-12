"""
Xiaohongshu Interview Scraper - Core Scraping Module
小红书面试信息抓取核心模块

使用 Playwright 进行浏览器级别的搜索和数据抓取。
通过直接访问搜索页面并解析 DOM 获取笔记数据，避免 API 级别的反爬检测。
支持关键词搜索、内容解析、公司/岗位识别、反爬虫策略。
"""

import json
import logging
import os
import random
import re
import time
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional

from playwright.sync_api import sync_playwright, Page, BrowserContext

from config import (
    BATCH_REST_MAX,
    BATCH_REST_MIN,
    COMPANY_SHORT_NAMES,
    HISTORY_FILE,
    INTERVIEW_KEYWORDS,
    MAX_DAILY_REQUESTS,
    MAX_NOTE_AGE_DAYS,
    MAX_PAGES_PER_KEYWORD,
    MAX_REQUEST_INTERVAL,
    MIN_LIKES,
    MIN_REQUEST_INTERVAL,
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


def create_browser_context(cookie: str) -> tuple[BrowserContext, Page, "Browser", "Playwright"]:
    """
    创建 Playwright 浏览器上下文和页面，注入 cookie。

    :param cookie: 小红书网页版 cookie 字符串
    :return: (BrowserContext, Page, Browser, Playwright) 元组
    """
    playwright_ctx = sync_playwright().start()
    try:
        stealth_js_path = os.path.join(os.path.dirname(__file__), "stealth.min.js")

        if not os.path.exists(stealth_js_path):
            logger.warning("stealth.min.js not found. Downloading from CDN...")
            import urllib.request
            urllib.request.urlretrieve(
                "https://cdn.jsdelivr.net/gh/requireCool/stealth.min.js/stealth.min.js",
                stealth_js_path,
            )
            logger.info("stealth.min.js downloaded successfully.")

        browser = playwright_ctx.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            )
            context.add_init_script(path=stealth_js_path)

            cookie_pairs = [c.strip() for c in cookie.split(";") if "=" in c]
            browser_cookies = []
            for pair in cookie_pairs:
                name, _, value = pair.partition("=")
                browser_cookies.append({
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": ".xiaohongshu.com",
                    "path": "/",
                })
            if browser_cookies:
                context.add_cookies(browser_cookies)

            page = context.new_page()
            page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            logger.info("Playwright 浏览器上下文创建成功")
            return context, page, browser, playwright_ctx
        except Exception:
            browser.close()
            raise
    except Exception:
        playwright_ctx.stop()
        raise


def generate_search_queries() -> list[dict]:
    """生成搜索关键词组合列表。"""
    queries = []

    for company in COMPANY_SHORT_NAMES:
        for interview_kw in INTERVIEW_KEYWORDS:
            queries.append({
                "keyword": f"{company} {interview_kw}",
                "company": company,
                "interview_type": interview_kw,
                "tech_direction": "",
            })

    for tech in TECH_DIRECTIONS[:5]:
        for interview_kw in INTERVIEW_KEYWORDS[:3]:
            queries.append({
                "keyword": f"{tech} {interview_kw}",
                "company": "",
                "interview_type": interview_kw,
                "tech_direction": tech,
            })

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

    seen = set()
    unique_queries = []
    for q in queries:
        if q["keyword"] not in seen:
            seen.add(q["keyword"])
            unique_queries.append(q)

    logger.info(f"生成了 {len(unique_queries)} 个搜索关键词组合")
    return unique_queries


def identify_company(title: str, desc: str) -> str:
    """从标题和内容中识别公司名称。"""
    text = f"{title} {desc}".lower()
    company_mapping = {
        "openai": "OpenAI", "open ai": "OpenAI",
        "xai": "xAI", "x.ai": "xAI",
        "google": "Google", "谷歌": "Google",
        "amazon": "Amazon", "亚马逊": "Amazon", "aws": "Amazon",
        "apple": "Apple", "苹果": "Apple",
        "meta": "Meta", "facebook": "Meta",
        "anthropic": "Anthropic",
        "deepseek": "DeepSeek", "深度求索": "DeepSeek",
        "kimi": "Kimi", "月之暗面": "Kimi", "moonshot": "Kimi",
        "seed": "Seed",
        "字节跳动": "ByteDance/Seed", "bytedance": "ByteDance/Seed",
        "字节": "ByteDance/Seed", "tiktok": "ByteDance/Seed",
    }
    found = []
    for kw, name in company_mapping.items():
        if kw in text and name not in found:
            found.append(name)
    return ", ".join(found) if found else ""


def identify_tech_direction(title: str, desc: str) -> str:
    """从标题和内容中识别技术方向/岗位。"""
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
    found = []
    for direction, patterns in direction_patterns.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                if direction not in found:
                    found.append(direction)
                break
    return ", ".join(found) if found else ""


def identify_interview_type(title: str, desc: str) -> str:
    """识别面试类型"""
    text = f"{title} {desc}"
    type_patterns = {
        "面试经历": [r"面试经历", r"面试经验", r"面试分享", r"offer"],
        "面试题": [r"面试题", r"面试问题", r"考题", r"笔试题"],
        "面筋/面经": [r"面筋", r"面经"],
        "OA": [r"OA", r"在线测评", r"笔试"],
        "简历": [r"简历", r"投递", r"内推"],
        "薪资": [r"薪资", r"薪酬", r"待遇", r"package", r"offer"],
    }
    found = []
    for itype, patterns in type_patterns.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                if itype not in found:
                    found.append(itype)
                break
    return ", ".join(found) if found else "面试相关"


def parse_note_time(time_str: str) -> str:
    """解析笔记时间字符串。"""
    if not time_str:
        return ""
    time_str = time_str.strip()
    time_str = re.sub(r"^编辑于\s*", "", time_str)

    if re.match(r"\d{4}-\d{2}-\d{2}", time_str):
        return time_str[:10]
    if re.match(r"\d{2}-\d{2}$", time_str):
        candidate = f"{datetime.now().year}-{time_str}"
        try:
            candidate_date = datetime.strptime(candidate, "%Y-%m-%d")
            if candidate_date > datetime.now():
                candidate = f"{datetime.now().year - 1}-{time_str}"
        except ValueError:
            pass
        return candidate
    match = re.match(r"(\d+)\s*天前", time_str)
    if match:
        return (datetime.now() - timedelta(days=int(match.group(1)))).strftime(
            "%Y-%m-%d"
        )
    match = re.match(r"(\d+)\s*小时前", time_str)
    if match:
        return datetime.now().strftime("%Y-%m-%d")
    if "昨天" in time_str:
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    return time_str


def is_note_recent(date_str: str, max_age_days: int = MAX_NOTE_AGE_DAYS) -> bool:
    """检查笔记是否在指定天数内。"""
    if not date_str:
        return True
    try:
        note_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return note_date >= datetime.now() - timedelta(days=max_age_days)
    except (ValueError, IndexError):
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


def _parse_count(count_str) -> int:
    """解析数量字符串（如 '1.2万'）为整数"""
    if isinstance(count_str, int):
        return count_str
    if not count_str:
        return 0
    count_str = str(count_str).strip().replace("+", "")
    if "万" in count_str:
        try:
            return int(float(count_str.replace("万", "")) * 10000)
        except ValueError:
            return 0
    try:
        return int(count_str)
    except ValueError:
        return 0


# JavaScript for extracting note cards from the search results page
_JS_EXTRACT_NOTES = r"""
() => {
    const notes = [];
    const sections = document.querySelectorAll('section.note-item');
    for (const section of sections) {
        try {
            const linkEl = section.querySelector('a');
            const href = linkEl ? linkEl.getAttribute('href') : '';
            const noteIdMatch = href
                ? href.match(/\/(?:explore|search_result)\/([a-f0-9]+)/)
                : null;
            const noteId = noteIdMatch ? noteIdMatch[1] : '';

            const titleEl = section.querySelector('.title span');
            const title = titleEl ? titleEl.textContent.trim() : '';

            const authorEl = section.querySelector('.author .name');
            const authorName = authorEl ? authorEl.textContent.trim() : '';
            const authorLink = section.querySelector('.author');
            const authorHref = authorLink ? authorLink.getAttribute('href') : '';
            const authorIdMatch = authorHref
                ? authorHref.match(/\/user\/profile\/([a-f0-9]+)/)
                : null;
            const authorId = authorIdMatch ? authorIdMatch[1] : '';

            const likeEl = section.querySelector('.like-wrapper .count');
            const likeCount = likeEl ? likeEl.textContent.trim() : '0';

            const isVideo = !!section.querySelector('.play-icon');

            if (noteId) {
                notes.push({
                    noteId, title, authorName, authorId,
                    likeCount, isVideo,
                    href: 'https://www.xiaohongshu.com' + href,
                });
            }
        } catch(e) {}
    }
    return notes;
}
"""

# JavaScript for extracting note detail from a detail page
_JS_EXTRACT_DETAIL = r"""
() => {
    const result = {};
    const titleEl = document.querySelector('#detail-title');
    result.title = titleEl ? titleEl.textContent.trim() : '';

    const descEl = document.querySelector('#detail-desc');
    result.desc = descEl ? descEl.textContent.trim() : '';

    const timeEl = document.querySelector('.date');
    result.dateStr = timeEl ? timeEl.textContent.trim() : '';

    const likeEl = document.querySelector('.like-wrapper .count');
    result.likeCount = likeEl ? likeEl.textContent.trim() : null;

    const collectEl = document.querySelector('.collect-wrapper .count');
    result.collectCount = collectEl ? collectEl.textContent.trim() : null;

    const commentEl = document.querySelector('.chat-wrapper .count');
    result.commentCount = commentEl ? commentEl.textContent.trim() : null;

    const tagEls = document.querySelectorAll('#detail-desc a.tag');
    result.tags = Array.from(tagEls)
        .map(t => t.textContent.trim())
        .filter(Boolean);

    return result;
}
"""


def _extract_notes_from_page(page: Page) -> list[dict]:
    """从当前搜索结果页面中提取笔记卡片数据。"""
    return page.evaluate(_JS_EXTRACT_NOTES)


def _fetch_note_detail_from_page(page: Page, note_url: str) -> dict:
    """通过浏览器访问笔记详情页获取更多信息。"""
    try:
        page.goto(note_url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        return page.evaluate(_JS_EXTRACT_DETAIL)
    except Exception as e:
        logger.debug(f"获取笔记详情失败: {e}")
        return {}


def search_notes_via_browser(
    page: Page,
    query: dict,
    max_pages: int = MAX_PAGES_PER_KEYWORD,
    existing_ids: Optional[set] = None,
) -> list[dict]:
    """通过浏览器搜索小红书笔记并解析结果。"""
    keyword = query["keyword"]
    results = []
    if existing_ids is None:
        existing_ids = set()

    logger.info(f"开始搜索: '{keyword}'")

    encoded_keyword = urllib.parse.quote(keyword)
    search_url = (
        f"https://www.xiaohongshu.com/search_result?"
        f"keyword={encoded_keyword}&source=web_explore_feed"
    )

    try:
        page.goto(search_url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # 关闭可能弹出的登录框
        try:
            close_btn = page.query_selector(".close-button, .login-modal .close")
            if close_btn:
                close_btn.click()
                time.sleep(0.5)
        except Exception:
            pass

        all_note_ids_on_page = set()

        for scroll_round in range(max_pages):
            raw_notes = _extract_notes_from_page(page)

            new_notes_this_round = 0
            for raw in raw_notes:
                note_id = raw.get("noteId", "")
                if (
                    not note_id
                    or note_id in existing_ids
                    or note_id in all_note_ids_on_page
                ):
                    continue

                all_note_ids_on_page.add(note_id)
                title = raw.get("title", "")
                author_name = raw.get("authorName", "")
                author_id = raw.get("authorId", "")
                like_count = _parse_count(raw.get("likeCount", "0"))
                if like_count < MIN_LIKES:
                    continue
                is_video = raw.get("isVideo", False)
                note_link = raw.get("href", "")
                if not note_link and note_id:
                    note_link = (
                        f"https://www.xiaohongshu.com/explore/{note_id}"
                    )

                detected_company = identify_company(title, "")
                if not detected_company and query.get("company"):
                    detected_company = query["company"]

                detected_tech = identify_tech_direction(title, "")
                if not detected_tech and query.get("tech_direction"):
                    detected_tech = query["tech_direction"]

                detected_interview_type = identify_interview_type(title, "")

                author_home = (
                    f"https://www.xiaohongshu.com/user/profile/{author_id}"
                    if author_id
                    else ""
                )

                parsed_note = {
                    "笔记ID": note_id,
                    "标题": title,
                    "内容摘要": "",
                    "发布时间": "",
                    "公司": detected_company,
                    "岗位方向": detected_tech,
                    "面试类型": detected_interview_type,
                    "作者昵称": author_name,
                    "作者ID": author_id,
                    "作者主页": author_home,
                    "笔记链接": note_link,
                    "点赞数": like_count,
                    "收藏数": 0,
                    "评论数": 0,
                    "分享数": 0,
                    "笔记类型": "视频" if is_video else "图文",
                    "标签": "",
                    "抓取时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "搜索关键词": keyword,
                }
                results.append(parsed_note)
                existing_ids.add(note_id)
                new_notes_this_round += 1

            logger.info(
                f"  第 {scroll_round + 1} 轮滚动: "
                f"本轮新增 {new_notes_this_round} 条，"
                f"累计有效 {len(results)} 条"
            )

            if new_notes_this_round == 0 and scroll_round > 0:
                logger.info("  无新增笔记，停止滚动")
                break

            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            _random_sleep(2, 4)

    except Exception as e:
        logger.error(f"  搜索 '{keyword}' 出错: {e}")
        _random_sleep(10, 20)

    return results


def enrich_notes_with_details(
    page: Page,
    notes: list[dict],
    max_detail_fetches: int = 10,
) -> list[dict]:
    """对搜索结果中的笔记逐个打开详情页补充内容。"""
    count = 0
    for note in notes:
        if count >= max_detail_fetches:
            break
        note_link = note.get("笔记链接", "")
        if not note_link:
            continue

        _random_sleep(MIN_REQUEST_INTERVAL, MAX_REQUEST_INTERVAL)
        detail = _fetch_note_detail_from_page(page, note_link)

        if detail:
            if detail.get("desc"):
                note["内容摘要"] = detail["desc"][:500]
            if detail.get("dateStr"):
                note["发布时间"] = parse_note_time(detail["dateStr"])
            if detail.get("collectCount"):
                note["收藏数"] = _parse_count(detail["collectCount"])
            if detail.get("commentCount"):
                note["评论数"] = _parse_count(detail["commentCount"])
            if detail.get("likeCount"):
                note["点赞数"] = _parse_count(detail["likeCount"])
            if detail.get("tags"):
                note["标签"] = ", ".join(detail["tags"])

            if detail.get("desc"):
                title = note.get("标题", "")
                desc = detail["desc"]
                new_company = identify_company(title, desc)
                if new_company:
                    note["公司"] = new_company
                new_tech = identify_tech_direction(title, desc)
                if new_tech:
                    note["岗位方向"] = new_tech
                new_type = identify_interview_type(title, desc)
                if new_type:
                    note["面试类型"] = new_type
        count += 1

    logger.info(f"  已补充 {count} 条笔记的详情信息")
    return notes


def run_scraper(
    cookie: str,
    incremental: bool = True,
    max_keywords: Optional[int] = None,
) -> list[dict]:
    """运行抓取器主流程。"""
    setup_logging()
    logger.info("=" * 60)
    logger.info("小红书面试信息抓取开始")
    logger.info("=" * 60)

    existing_ids = load_history() if incremental else set()
    logger.info(f"已有历史记录: {len(existing_ids)} 条")

    context, page, browser, playwright_instance = create_browser_context(cookie)

    all_notes = []
    try:
        queries = generate_search_queries()
        if max_keywords:
            queries = queries[:max_keywords]

        total_searches = 0
        batch_count = 0

        for i, query in enumerate(queries):
            if total_searches >= MAX_DAILY_REQUESTS:
                logger.warning(
                    f"已达到每日最大请求次数 ({MAX_DAILY_REQUESTS})，停止抓取"
                )
                break

            logger.info(f"\n[{i + 1}/{len(queries)}] 搜索: {query['keyword']}")

            notes = search_notes_via_browser(
                page=page,
                query=query,
                existing_ids=existing_ids,
            )

            if notes:
                notes = enrich_notes_with_details(page, notes, max_detail_fetches=5)
                notes = [
                    n for n in notes
                    if is_note_recent(n.get("发布时间", ""))
                ]

            all_notes.extend(notes)
            total_searches += 1

            _random_sleep(MIN_REQUEST_INTERVAL, MAX_REQUEST_INTERVAL)

            batch_count += 1
            if batch_count >= 10:
                logger.info("已完成一批搜索，休息中...")
                _random_sleep(BATCH_REST_MIN, BATCH_REST_MAX)
                batch_count = 0
    finally:
        for note in all_notes:
            existing_ids.add(note["笔记ID"])
        save_history(existing_ids)

        try:
            context.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass
        try:
            playwright_instance.stop()
        except Exception:
            pass

    logger.info("=" * 60)
    logger.info(f"抓取完成！共获取 {len(all_notes)} 条新笔记")
    logger.info(f"历史总计: {len(existing_ids)} 条")
    logger.info("=" * 60)

    return all_notes
