"""美团优惠爬虫：抓取餐饮/茶饮团购活动。

使用 Playwright 渲染页面 + BeautifulSoup 解析，
模拟移动端访问公开团购列表页。

当前实现：直接爬取美团公开搜索页面，解析商户卡片。
后续可扩展：登录态 + 个性化推荐页。
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler
from app.models.activity import Platform

logger = logging.getLogger(__name__)

MEITUAN_SEARCH_URL = "https://meituan.com/s/"
# 目标品类关键词
TARGET_KEYWORDS = ["瑞幸咖啡", "星巴克", "麦当劳", "肯德基", "喜茶", "奈雪的茶", "蜜雪冰城", "海底捞", "必胜客", "汉堡王"]


class MeituanCrawler(BaseCrawler):
    """美团团购活动爬虫。

    抓取美团公开搜索页面，按品类关键词逐个搜索，
    解析每个商户的团购套餐信息。
    """

    name = "meituan"
    platform = Platform.MEITUAN

    async def _fetch_keyword(self, page, keyword: str) -> list[dict]:
        """搜索单个关键词，返回该品类的活动列表。"""
        results: list[dict] = []
        search_url = f"{MEITUAN_SEARCH_URL}{keyword}"

        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(self.request_delay)
            # 等待搜索结果列表渲染
            await page.wait_for_selector("[class*='shop'], [class*='card'], [class*='list']", timeout=10000)
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"[{self.name}] 搜索 '{keyword}' 页面加载异常: {e}")
            return results

        html = await page.content()
        soup = BeautifulSoup(html, "lxml")

        # 美团搜索结果卡片选择器（常用 class 模式）
        cards = soup.select('[class*="shop-card"], [class*="deal-card"], [class*="poi-card"], li[class*="item"]')
        if not cards:
            cards = soup.select('[class*="list"] > li, [class*="list"] > div')

        logger.info(f"[{self.name}] 搜索 '{keyword}' 找到 {len(cards)} 个卡片")

        for card in cards:
            item = self._parse_card(card, keyword)
            if item:
                results.append(item)

        return results

    def _parse_card(self, card, keyword: str) -> dict | None:
        """从单个搜索结果卡片中提取活动信息。"""
        try:
            # 标题
            title_el = card.select_one('[class*="title"], [class*="name"], h3, h4')
            title = title_el.get_text(strip=True) if title_el else None

            # 价格
            price_el = card.select_one('[class*="price"], [class*="current"], .yen, [class*="amount"]')
            price_text = price_el.get_text(strip=True) if price_el else ""
            price_match = re.search(r'[\d.]+', price_text)
            activity_price = float(price_match.group()) if price_match else None

            # 原价
            orig_el = card.select_one('[class*="original"], [class*="old-price"], del, s')
            orig_text = orig_el.get_text(strip=True) if orig_el else ""
            orig_match = re.search(r'[\d.]+', orig_text)
            original_price = float(orig_match.group()) if orig_match else None

            # 描述
            desc_el = card.select_one('[class*="desc"], [class*="detail"], [class*="subtitle"], p')
            desc = desc_el.get_text(strip=True) if desc_el else title

            # 链接
            link_el = card.select_one('a')
            url = link_el.get("href", "") if link_el else ""
            if url and not url.startswith("http"):
                url = f"https://meituan.com{url}" if url.startswith("/") else f"https://meituan.com/{url}"

            if not title or not desc:
                return None

            item_id = self._build_id(keyword, title, str(activity_price))
            return {
                "id": item_id,
                "title": f"{keyword}{' ' + title if keyword not in title else ''}",
                "platform": Platform.MEITUAN,
                "merchant_name": keyword,
                "category": self._guess_category(keyword),
                "product_name": title,
                "original_price": original_price,
                "activity_price": activity_price,
                "discount_description": desc or f"美团 {title}",
                "source_url": url or MEITUAN_SEARCH_URL,
                "source_type": "crawler",
                "valid_to": datetime.now() + timedelta(days=14),
            }
        except Exception as e:
            logger.debug(f"[{self.name}] 解析卡片异常: {e}")
            return None

    @staticmethod
    def _guess_category(keyword: str) -> str:
        for kw in ["咖啡", "茶", "奶茶", "星巴克", "瑞幸", "喜茶", "奈雪", "蜜雪"]:
            if kw in keyword:
                return "咖啡茶饮"
        return "餐饮美食"

    async def fetch(self) -> list[dict]:
        """遍历所有品类关键词，抓取活动列表。"""
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
                page = await context.new_page()

                for keyword in TARGET_KEYWORDS:
                    logger.info(f"[{self.name}] 搜索: {keyword}")
                    try:
                        items = await self._fetch_keyword(page, keyword)
                        all_items.extend(items)
                        logger.info(f"[{self.name}] {keyword} → {len(items)} 条")
                    except Exception as e:
                        logger.warning(f"[{self.name}] {keyword} 抓取异常: {e}")
                    await asyncio.sleep(self.request_delay * 2)

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
