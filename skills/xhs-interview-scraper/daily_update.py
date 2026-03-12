#!/usr/bin/env python3
"""
每日定时更新模块
Daily Update Module

可配合 cron 或 systemd timer 使用，实现每日自动更新面试信息。

使用方式：
    # 直接运行（需要 cookie.txt 文件）
    python daily_update.py

    # cron 配置示例（每天早上9点执行）
    # 0 9 * * * cd /path/to/xhs-interview-scraper && python daily_update.py

    # 也可以通过环境变量传入 cookie
    # XHS_COOKIE="your_cookie" python daily_update.py
"""

import logging
import os
import sys
from datetime import datetime

from config import DATA_DIR
from scraper import run_scraper, setup_logging
from excel_exporter import export_to_excel

logger = logging.getLogger(__name__)

COOKIE_FILE = "cookie.txt"


def get_cookie() -> str:
    """
    获取 Cookie，优先级：
    1. 环境变量 XHS_COOKIE
    2. cookie.txt 文件
    """
    # 从环境变量获取
    cookie = os.environ.get("XHS_COOKIE", "")
    if cookie:
        logger.info("从环境变量 XHS_COOKIE 获取 Cookie")
        return cookie

    # 从文件获取
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookie = f.read().strip()
        if cookie:
            logger.info("从 cookie.txt 获取 Cookie")
            return cookie

    logger.error(
        "未找到 Cookie！请设置环境变量 XHS_COOKIE 或创建 cookie.txt 文件"
    )
    sys.exit(1)


def daily_update():
    """执行每日更新"""
    setup_logging()
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info(f"每日定时更新开始: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    cookie = get_cookie()

    try:
        # 增量抓取，每次只搜索部分关键词以降低频率
        notes = run_scraper(
            cookie=cookie,
            incremental=True,
            max_keywords=None,  # 搜索所有关键词
        )
    except Exception as e:
        logger.error(f"抓取失败: {e}", exc_info=True)
        notes = []

    if notes:
        output_path = export_to_excel(
            notes=notes,
            append=True,
        )
        logger.info(f"新增 {len(notes)} 条笔记，保存到: {output_path}")
    else:
        logger.info("今日无新增笔记")

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    logger.info(f"更新完成，耗时: {duration:.0f} 秒")

    # 保存运行日志摘要
    summary_path = os.path.join(DATA_DIR, "daily_summary.log")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write(
            f"{start_time.strftime('%Y-%m-%d %H:%M:%S')} | "
            f"新增: {len(notes)} 条 | "
            f"耗时: {duration:.0f}秒\n"
        )


if __name__ == "__main__":
    daily_update()
