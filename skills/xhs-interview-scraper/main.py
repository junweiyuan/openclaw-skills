#!/usr/bin/env python3
"""
小红书面试信息抓取工具 - 主入口
XHS Interview Scraper - Main Entry Point

用途：从小红书抓取 LLM/AI 相关面试经历、面试题、面筋等内容，
     结构化存储到 Excel 表格，支持增量更新。

用法：
    # 首次运行（抓取所有关键词）
    python main.py --cookie "your_cookie_here"

    # 增量更新（只获取新笔记）
    python main.py --cookie "your_cookie_here" --incremental

    # 限制搜索关键词数量（用于测试）
    python main.py --cookie "your_cookie_here" --max-keywords 5

    # 指定输出文件
    python main.py --cookie "your_cookie_here" --output my_notes.xlsx

    # 每日定时任务模式
    python main.py --cookie "your_cookie_here" --daily

获取Cookie说明：
    1. 用浏览器打开 https://www.xiaohongshu.com
    2. 登录账号
    3. 按 F12 打开开发者工具 → Application → Cookies
    4. 复制整个 cookie 字符串
"""

import argparse
import logging
import os
import sys
import json
from datetime import datetime

from config import DATA_DIR, OUTPUT_EXCEL
from scraper import run_scraper, setup_logging
from excel_exporter import export_to_excel

logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="小红书面试信息抓取工具 - 抓取 LLM/AI 相关面试内容",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本使用（首次抓取）
  python main.py --cookie "a1=xxx; web_session=xxx; ..."

  # 增量更新
  python main.py --cookie "a1=xxx; ..." --incremental

  # 测试模式（只搜索少量关键词）
  python main.py --cookie "a1=xxx; ..." --max-keywords 3

  # 从文件读取cookie
  python main.py --cookie-file cookie.txt

目标公司: OpenAI, xAI, Google, Amazon, Apple, Meta, Anthropic, DeepSeek, Kimi, Seed
技术方向: LLM算法, AIInfra, 多模态算法, 强化学习算法, NLP, 推理优化
        """,
    )
    cookie_group = parser.add_mutually_exclusive_group(required=True)
    cookie_group.add_argument(
        "--cookie",
        type=str,
        help="小红书网页版 Cookie 字符串",
    )
    cookie_group.add_argument(
        "--cookie-file",
        type=str,
        help="包含 Cookie 的文本文件路径",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        default=True,
        help="增量模式：跳过已抓取的笔记（默认开启）",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="全量模式：忽略历史记录，重新抓取所有内容",
    )
    parser.add_argument(
        "--max-keywords",
        type=int,
        default=None,
        help="最大搜索关键词数量（用于测试，默认不限制）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help=f"输出 Excel 文件路径（默认: {os.path.join(DATA_DIR, OUTPUT_EXCEL)}）",
    )
    parser.add_argument(
        "--daily",
        action="store_true",
        help="每日定时任务模式：增量抓取并追加到现有文件",
    )
    parser.add_argument(
        "--export-json",
        action="store_true",
        help="同时导出 JSON 格式数据",
    )
    return parser.parse_args()


def load_cookie_from_file(filepath: str) -> str:
    """从文件加载 Cookie"""
    if not os.path.exists(filepath):
        logger.error(f"Cookie 文件不存在: {filepath}")
        sys.exit(1)
    with open(filepath, "r", encoding="utf-8") as f:
        cookie = f.read().strip()
    if not cookie:
        logger.error("Cookie 文件为空")
        sys.exit(1)
    return cookie


def export_json(notes: list[dict], output_dir: str):
    """导出 JSON 格式数据"""
    json_path = os.path.join(output_dir, "interview_notes.json")
    data = {
        "metadata": {
            "exported_at": datetime.now().isoformat(),
            "total_count": len(notes),
            "source": "xiaohongshu",
        },
        "notes": notes,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"JSON 文件已保存: {json_path}")


def main():
    args = parse_args()
    setup_logging()

    logger.info("=" * 60)
    logger.info("小红书面试信息抓取工具 v1.0")
    logger.info("=" * 60)

    # 获取 Cookie
    if args.cookie_file:
        cookie = load_cookie_from_file(args.cookie_file)
    else:
        cookie = args.cookie

    # 确定是否增量模式
    incremental = not args.full

    if args.daily:
        logger.info("运行模式: 每日定时更新")
        incremental = True

    logger.info(f"增量模式: {'开启' if incremental else '关闭'}")
    if args.max_keywords:
        logger.info(f"关键词限制: {args.max_keywords}")

    # 运行抓取
    try:
        notes = run_scraper(
            cookie=cookie,
            incremental=incremental,
            max_keywords=args.max_keywords,
        )
    except KeyboardInterrupt:
        logger.warning("用户中断抓取")
        notes = []
    except Exception as e:
        logger.error(f"抓取过程出错: {e}", exc_info=True)
        notes = []

    if not notes:
        logger.warning("未抓取到任何新笔记")
        return

    # 导出 Excel
    output_path = export_to_excel(
        notes=notes,
        output_path=args.output,
        append=incremental,
    )
    logger.info(f"Excel 输出: {output_path}")

    # 可选: 导出 JSON
    if args.export_json:
        export_json(notes, DATA_DIR)

    logger.info("=" * 60)
    logger.info("任务完成!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
