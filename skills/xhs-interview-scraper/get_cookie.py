#!/usr/bin/env python3
"""
通过 Playwright 获取小红书完整 Cookie（包含 HttpOnly 的 web_session）。

两种模式：
1. 交互模式（默认）：打开浏览器窗口，用户扫码登录后自动保存 cookie
2. 无头模式（--headless）：截图二维码供用户扫描，轮询等待登录成功

用法：
    # 交互模式（推荐，会弹出浏览器窗口）
    python get_cookie.py

    # 无头模式（适合远程服务器）
    python get_cookie.py --headless

    # 作为模块调用
    from get_cookie import login_and_save_cookie
    cookie_str = login_and_save_cookie()
"""

import argparse
import json
import logging
import os
import time

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(_DIR, "cookie.txt")
QR_SCREENSHOT = os.path.join(_DIR, "data", "qr_code.png")


def _has_web_session(cookies: list[dict]) -> bool:
    """检查 cookie 中是否包含 web_session（表示已登录）。"""
    return any(c["name"] == "web_session" for c in cookies)


def _save_cookies(context, cookie_file: str = COOKIE_FILE) -> tuple[str, list[dict]]:
    """从浏览器上下文提取 cookie 并保存到文件。"""
    cookies = context.cookies(["https://www.xiaohongshu.com"])
    cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

    with open(cookie_file, "w", encoding="utf-8") as f:
        f.write(cookie_str)

    # 同时保存详细 JSON 格式
    json_file = cookie_file.replace(".txt", "_detail.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2, ensure_ascii=False)

    return cookie_str, cookies


def login_and_save_cookie(
    headless: bool = False,
    cookie_file: str = COOKIE_FILE,
    timeout: int = 120,
) -> str:
    """启动浏览器登录小红书并保存 cookie。

    :param headless: 是否使用无头模式
    :param cookie_file: cookie 保存路径
    :param timeout: 等待登录的超时时间（秒）
    :return: cookie 字符串
    """
    stealth_js_path = os.path.join(_DIR, "stealth.min.js")
    os.makedirs(os.path.dirname(QR_SCREENSHOT), exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        if os.path.exists(stealth_js_path):
            context.add_init_script(path=stealth_js_path)

        page = context.new_page()

        try:
            logger.info("正在打开小红书...")
            page.goto(
                "https://www.xiaohongshu.com",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            time.sleep(2)

            # 检查是否已经登录
            cookies = context.cookies(["https://www.xiaohongshu.com"])
            if _has_web_session(cookies):
                logger.info("已经处于登录状态！")
                cookie_str, cookies = _save_cookies(context, cookie_file)
                logger.info(f"Cookie 已保存到 {cookie_file}")
                return cookie_str

            # 需要登录 - 等待二维码出现
            logger.info("需要扫码登录...")

            if headless:
                # 无头模式：截图二维码
                page.screenshot(path=QR_SCREENSHOT)
                logger.info(f"请扫描二维码登录（截图保存在: {QR_SCREENSHOT}）")
                print(f"\n{'='*50}")
                print("请用小红书APP扫描二维码登录")
                print(f"二维码截图: {QR_SCREENSHOT}")
                print(f"等待登录中... (超时: {timeout}秒)")
                print(f"{'='*50}\n")
            else:
                print(f"\n{'='*50}")
                print("请在弹出的浏览器窗口中扫码登录小红书")
                print(f"等待登录中... (超时: {timeout}秒)")
                print(f"{'='*50}\n")

            # 轮询等待登录成功
            start_time = time.time()
            while time.time() - start_time < timeout:
                cookies = context.cookies(["https://www.xiaohongshu.com"])
                if _has_web_session(cookies):
                    logger.info("登录成功！")
                    cookie_str, cookies = _save_cookies(context, cookie_file)
                    logger.info(f"Cookie 已保存到 {cookie_file}")

                    print(f"\n{'='*50}")
                    print(f"登录成功！Cookie 已保存到 {cookie_file}")
                    print(f"共 {len(cookies)} 个 cookie")
                    print(f"{'='*50}\n")
                    return cookie_str

                elapsed = int(time.time() - start_time)
                if elapsed > 0 and elapsed % 10 == 0:
                    logger.info(f"等待扫码中... ({elapsed}/{timeout}秒)")
                    # 无头模式下刷新二维码截图（二维码可能过期）
                    if headless and elapsed % 30 == 0:
                        page.screenshot(path=QR_SCREENSHOT)
                        logger.info("二维码截图已刷新")

                time.sleep(2)

            logger.error(f"登录超时（{timeout}秒），请重试")
            raise TimeoutError(f"登录等待超时 ({timeout}秒)")

        finally:
            context.close()
            browser.close()


def main():
    parser = argparse.ArgumentParser(description="获取小红书 Cookie")
    parser.add_argument(
        "--headless", action="store_true", help="使用无头模式（截图二维码）"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="等待登录超时时间（秒，默认120）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=COOKIE_FILE,
        help=f"Cookie 保存路径（默认: {COOKIE_FILE}）",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        cookie_str = login_and_save_cookie(
            headless=args.headless,
            cookie_file=args.output,
            timeout=args.timeout,
        )
        print(f"\nCookie 字符串 ({len(cookie_str)} 字符):")
        print(cookie_str[:100] + "..." if len(cookie_str) > 100 else cookie_str)
    except TimeoutError:
        print("\n登录超时，请重试。")
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\n用户取消。")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
