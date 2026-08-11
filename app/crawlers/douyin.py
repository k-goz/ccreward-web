"""抖音本地生活爬虫：抓取团购优惠券和商户活动。

使用 Playwright 模拟移动端访问抖音本地生活页面，
搜索目标品类关键词，解析团购卡片信息。

注意：抖音有较强反爬，生产环境需配合：
  - 代理IP池
  - 延时阈值随机化
  - 登录态 Cookie
  - 必要时的验证码识别
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler
from app.models.activity import Platform

logger = logging.getLogger(__name__)

# 抖音本地生活搜索基础 URL（移动端 H5）
DOUYIN_LIFE_URL = "https://www.douyin.com/search/"
# 搜索后缀
LIFE_SUFFIX = "?type=general&local_life"

TARGET_KEYWORDS = [
    "瑞幸咖啡团购",
    "星巴克团购",
    "麦当劳团购",
    "肯德基疯狂星期四",
    "喜茶团购",
    "奈雪的茶团购",
    "蜜雪冰城团购",
    "海底捞团购",
    "必胜客团购",
    "汉堡王团购",
]


class DouyinCrawler(BaseCrawler):
    """抖音本地生活团购爬虫。"""

    name = "douyin"
    platform = Platform.DOUYIN

    async def _search_keyword(self, page, keyword: str) -> list[dict]:
        """搜索单个关键词的团购列表。"""
        results: list[dict] = []
        search_url = f"{DOUYIN_LIFE_URL}{keyword}{LIFE_SUFFIX}"

        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(self.request_delay + 1)
            # 尝试多种可能的搜索结果容器
            selectors = [
                '[class*="search-result"] [class*="card"]',
                '[class*="list"] [class*="item"]',
                '[class*="video-card"]',
                '[class*="search"] [class*="card"]',
            ]
            found = False
            for sel in selectors:
                try:
                    await page.wait_for_selector(sel, timeout=8000)
                    found = True
                    break
                except Exception:
                    continue
            if not found:
                logger.info(f"[{self.name}] '{keyword}' 未找到搜索结果卡片")
                return results
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"[{self.name}] '{keyword}' 页面加载失败: {e}")
            return results

        # 滚动加载更多
        for _ in range(2):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(1)

        html = await page.content()
        soup = BeautifulSoup(html, "lxml")

        # 抖音搜索结果卡片
        cards = soup.select(
            '[class*="search-result-card"], [class*="video-card"], '
            '[class*="card-item"], [class*="list-item"], [data-e2e*="card"]'
        )
        if not cards:
            logger.info(f"[{self.name}] '{keyword}' 解析到 0 个卡片（页面可能需登录）")

        for card in cards:
            item = self._parse_douyin_card(card, keyword)
            if item:
                results.append(item)

        return results

    def _parse_douyin_card(self, card, keyword: str) -> dict | None:
        """解析抖音团购卡片。"""
        try:
            # 标题（商户名称 / 团购套餐名）
            title_el = (
                card.select_one('[class*="title"], [class*="name"], [class*="desc"], h3, h4')
                or card.select_one('span')
            )
            title = title_el.get_text(strip=True) if title_el else keyword

            # 价格
            price_el = card.select_one(
                '[class*="price"], [class*="current"], [class*="amount"], .yen, .money'
            )
            price_text = price_el.get_text(strip=True) if price_el else ""
            price_match = re.search(r'[\d.]+', price_text)
            activity_price = float(price_match.group()) if price_match else None

            # 原价
            orig_el = card.select_one('[class*="original"], [class*="old"], del, s, strike')
            orig_text = orig_el.get_text(strip=True) if orig_el else ""
            orig_match = re.search(r'[\d.]+', orig_text)
            original_price = float(orig_match.group()) if orig_match else None

            # 销量 / 标签
            tag_el = card.select_one('[class*="tag"], [class*="label"], [class*="sold"]')
            tag_text = tag_el.get_text(strip=True) if tag_el else ""

            # 描述
            desc_el = card.select_one('[class*="desc"], [class*="subtitle"], p')
            desc = desc_el.get_text(strip=True) if desc_el else f"抖音团购 {title}"

            # 构造 ID
            merchant = keyword.replace("团购", "").strip()
            item_id = self._build_id(merchant, title, str(activity_price))

            return {
                "id": item_id,
                "title": title,
                "platform": Platform.DOUYIN,
                "merchant_name": merchant or "抖音商家",
                "category": self._guess_category(keyword),
                "product_name": title,
                "original_price": original_price,
                "activity_price": activity_price,
                "discount_description": f"{title} ({tag_text})" if tag_text else desc or title,
                "usage_conditions": "抖音App下单，到店核销",
                "source_url": DOUYIN_LIFE_URL,
                "source_type": "crawler",
                "valid_to": datetime.now() + timedelta(days=7),
            }
        except Exception as e:
            logger.debug(f"[{self.name}] 解析异常: {e}")
            return None

    @staticmethod
    def _guess_category(keyword: str) -> str:
        for kw in ["咖啡", "茶", "奶茶", "喜茶", "奈雪", "蜜雪"]:
            if kw in keyword:
                return "咖啡茶饮"
        return "餐饮美食"

    async def fetch(self) -> list[dict]:
        """遍历品类关键词，抓取抖音团购活动。"""
        from playwright.async_api import async_playwright
        from app.config import settings

        all_items: list[dict] = []
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=settings.CRAWLER_USER_AGENT,
                    viewport={"width": 375, "height": 812},
                    locale="zh-CN",
                )
                # 注入反检测脚本
                page = await context.new_page()
                await page.add_init_script("""
                    // 覆盖 webdriver 检测
                    Object.defineProperty(navigator, 'webdriver', { get: () => false });
                    // 覆盖 chrome 对象
                    window.chrome = { runtime: {} };
                """)

                for keyword in TARGET_KEYWORDS:
                    logger.info(f"[{self.name}] 搜索: {keyword}")
                    try:
                        items = await self._search_keyword(page, keyword)
                        all_items.extend(items)
                        logger.info(f"[{self.name}] {keyword} → {len(items)} 条")
                    except Exception as e:
                        logger.warning(f"[{self.name}] {keyword} 失败: {e}")
                    # 随机延时防封
                    import random
                    await asyncio.sleep(self.request_delay + random.uniform(1, 3))

                await browser.close()
        except ImportError:
            logger.error(
                "[{self.name}] Playwright 不可用，请运行: playwright install chromium"
            )
            return []
        except Exception as e:
            logger.error(f"[{self.name}] 浏览器启动失败: {e}")
            return []

        return all_items
