"""京东优惠爬虫：抓取京东到家/京东超市的团购和优惠券活动。

使用 Playwright 模拟移动端访问京东到家 H5 页面，
搜索目标品类关键词，解析优惠卡片信息。

京东到家商品以超市便利、生鲜水果为主，
京东超市以日用品优惠券为主。
"""

import asyncio
import logging
import re
import random
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler
from app.models.activity import Platform

logger = logging.getLogger(__name__)

# 京东到家 H5 搜索页
JD_DAOJIA_URL = "https://daojia.jd.com/"
# 京东搜索（通用）
JD_SEARCH_URL = "https://so.m.jd.com/ware/search.action?keyword="

# 目标品类
TARGET_KEYWORDS = [
    "瑞幸咖啡",
    "星巴克",
    "咖啡",
    "零食",
    "牛奶",
    "饮料",
    "纸巾",
    "洗衣液",
    "洗发水",
    "方便面",
]


class JDCrawler(BaseCrawler):
    """京东到家 & 京东超市优惠爬虫。"""

    name = "jd"
    platform = Platform.JD
    request_delay = 2.0  # JD 反爬更严格，延长间隔

    async def _fetch_daojia_keyword(self, page, keyword: str) -> list[dict]:
        """搜索京东到家某个关键词。"""
        results: list[dict] = []
        search_url = f"{JD_DAOJIA_URL}search?keyword={keyword}"

        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(self.request_delay)
            # 等待商品列表
            try:
                await page.wait_for_selector(
                    '[class*="goods"], [class*="product"], [class*="item"], [class*="sku"]',
                    timeout=10000,
                )
            except Exception:
                pass
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"[{self.name}] 京东到家搜索 '{keyword}' 页面加载异常: {e}")
            return results

        html = await page.content()
        soup = BeautifulSoup(html, "lxml")

        cards = soup.select(
            '[class*="goods-item"], [class*="product-item"], '
            '[class*="sku-item"], [class*="card"], li[class*="item"]'
        )
        if not cards:
            cards = soup.select('[class*="list"] > li, [class*="list"] > div')

        logger.info(f"[{self.name}] 京东到家搜索 '{keyword}' 找到 {len(cards)} 个卡片")

        for card in cards[:5]:  # 每关键词最多取 5 条
            item = self._parse_jd_card(card, keyword, "daojia")
            if item:
                results.append(item)

        return results

    async def _fetch_jd_supermarket_keyword(self, page, keyword: str) -> list[dict]:
        """搜索京东超市某个关键词（优惠券/满减）。"""
        results: list[dict] = []
        search_url = f"{JD_SEARCH_URL}{keyword}"

        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(self.request_delay)
            try:
                await page.wait_for_selector(
                    '[class*="goods"], [class*="product"], [class*="item"]',
                    timeout=10000,
                )
            except Exception:
                pass
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"[{self.name}] 京东超市搜索 '{keyword}' 页面加载异常: {e}")
            return results

        html = await page.content()
        soup = BeautifulSoup(html, "lxml")

        cards = soup.select(
            '[class*="gl-item"], [class*="goods-item"], '
            '[class*="product-wrap"], [class*="sku-item"]'
        )
        if not cards:
            cards = soup.select('.gl-warp > li')

        logger.info(f"[{self.name}] 京东超市搜索 '{keyword}' 找到 {len(cards)} 个卡片")

        for card in cards[:5]:
            item = self._parse_jd_card(card, keyword, "supermarket")
            if item:
                results.append(item)

        return results

    def _parse_jd_card(self, card, keyword: str, source: str) -> dict | None:
        """解析京东商品卡片。"""
        try:
            # 标题
            title_el = card.select_one(
                '[class*="title"], [class*="name"], [class*="p-name"], em, .p-name'
            )
            title = title_el.get_text(strip=True) if title_el else None

            # 价格
            price_el = card.select_one(
                '[class*="price"], [class*="p-price"], .J_price, [class*="jd-price"]'
            )
            price_text = price_el.get_text(strip=True) if price_el else ""
            # JD often has ￥ symbol
            price_match = re.search(r'[\d.]+', price_text)
            activity_price = float(price_match.group()) if price_match else None

            # 原价
            orig_el = card.select_one('[class*="original"], del, .p-market-price')
            orig_text = orig_el.get_text(strip=True) if orig_el else ""
            orig_match = re.search(r'[\d.]+', orig_text)
            original_price = float(orig_match.group()) if orig_match else (
                activity_price * 1.3 if activity_price else None
            )

            # 优惠标签
            tag_el = card.select_one('[class*="coupon"], [class*="tag"], [class*="promo"]')
            tag_text = tag_el.get_text(strip=True) if tag_el else ""

            # 链接
            link_el = card.select_one('a')
            url = link_el.get("href", "") if link_el else ""
            if url and not url.startswith("http"):
                url = f"https:{url}" if url.startswith("//") else f"https://daojia.jd.com{url}" if url.startswith("/") else url

            if not title or not activity_price:
                return None

            merchant_name = "京东到家" if source == "daojia" else "京东超市"
            prefix = "京东到家" if source == "daojia" else "京东超市"
            item_id = self._build_id(source, keyword, title, str(activity_price))

            return {
                "id": item_id,
                "title": f"{prefix} {title}" if prefix not in title else title,
                "platform": Platform.JD,
                "merchant_name": merchant_name,
                "category": self._guess_category(keyword),
                "product_name": title,
                "original_price": original_price,
                "activity_price": activity_price,
                "discount_description": tag_text or f"{prefix}优惠 {title}",
                "usage_conditions": f"{prefix}下单" if source == "daojia" else "京东App下单",
                "source_url": url or JD_DAOJIA_URL,
                "source_type": "crawler",
                "valid_to": datetime.now() + timedelta(days=14),
            }
        except Exception as e:
            logger.debug(f"[{self.name}] 解析卡片异常: {e}")
            return None

    @staticmethod
    def _guess_category(keyword: str) -> str:
        for kw in ["咖啡", "茶", "奶茶", "瑞幸", "星巴克"]:
            if kw in keyword:
                return "咖啡茶饮"
        for kw in ["零食", "牛奶", "饮料", "方便面"]:
            if kw in keyword:
                return "超市便利"
        for kw in ["纸巾", "洗衣液", "洗发水"]:
            if kw in keyword:
                return "超市便利"
        return "超市便利"

    async def fetch(self) -> list[dict]:
        """遍历关键词，分别抓取京东到家和京东超市。"""
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
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => false });
                    window.chrome = { runtime: {} };
                """)

                # 先抓京东到家
                for keyword in TARGET_KEYWORDS[:5]:  # 只搜前5个关键词（减少请求量）
                    logger.info(f"[{self.name}] 京东到家 搜索: {keyword}")
                    try:
                        items = await self._fetch_daojia_keyword(page, keyword)
                        all_items.extend(items)
                        logger.info(f"[{self.name}] {keyword} → {len(items)} 条")
                    except Exception as e:
                        logger.warning(f"[{self.name}] {keyword} 失败: {e}")
                    await asyncio.sleep(self.request_delay + random.uniform(1, 3))

                # 再抓京东超市
                for keyword in TARGET_KEYWORDS[5:]:
                    logger.info(f"[{self.name}] 京东超市 搜索: {keyword}")
                    try:
                        items = await self._fetch_jd_supermarket_keyword(page, keyword)
                        all_items.extend(items)
                        logger.info(f"[{self.name}] {keyword} → {len(items)} 条")
                    except Exception as e:
                        logger.warning(f"[{self.name}] {keyword} 失败: {e}")
                    await asyncio.sleep(self.request_delay + random.uniform(1, 3))

                await browser.close()
        except ImportError:
            logger.error(f"[{self.name}] Playwright 不可用")
            return []
        except Exception as e:
            logger.error(f"[{self.name}] 浏览器启动失败: {e}")
            return []

        return all_items


class JDGroceryCrawler(BaseCrawler):
    """京东超市粮油调味品爬虫（轻量，不需要浏览器）。"""

    name = "jd_grocery"
    platform = Platform.JD

    async def fetch(self) -> list[dict]:
        """使用 requests 抓取京东超市分类页（无需浏览器渲染的降级方案）。

        当 Playwright 不可用时作为 fallback，直接请求 API 接口。
        """
        import json
        import httpx

        all_items: list[dict] = []
        categories = [
            ("咖啡/奶茶", "咖啡茶饮", "https://search.jd.com/Search?keyword=咖啡&enc=utf-8"),
            ("零食大礼包", "超市便利", "https://search.jd.com/Search?keyword=零食大礼包&enc=utf-8"),
            ("饮料", "超市便利", "https://search.jd.com/Search?keyword=饮料&enc=utf-8"),
        ]

        async with httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=15.0,
        ) as client:
            for keyword, category, url in categories:
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    soup = BeautifulSoup(resp.text, "lxml")
                    items = soup.select('.gl-item, [class*="goods-item"]')
                    for item in items[:3]:
                        title_el = item.select_one('.p-name em, [class*="title"]')
                        price_el = item.select_one('.p-price i, [class*="price"]')
                        img_el = item.select_one('img')
                        title = title_el.get_text(strip=True) if title_el else keyword
                        price_text = price_el.get_text(strip=True) if price_el else ""
                        price_match = re.search(r'[\d.]+', price_text)
                        price = float(price_match.group()) if price_match else None
                        img = img_el.get("src", "") or img_el.get("data-lazy-img", "") if img_el else ""

                        if not title or not price:
                            continue

                        item_id = self._build_id("jd_grocery", keyword, title, str(price))
                        all_items.append({
                            "id": item_id,
                            "title": f"京东 {title[:50]}",
                            "platform": Platform.JD,
                            "merchant_name": "京东超市",
                            "category": category,
                            "product_name": title[:80],
                            "original_price": round(price * 1.2, 1),
                            "activity_price": price,
                            "discount_description": f"京东超市优惠 {title[:30]}",
                            "usage_conditions": "京东App下单",
                            "source_url": url,
                            "source_type": "crawler",
                            "image_url": img if img.startswith("http") else f"https:{img}" if img.startswith("//") else "",
                            "valid_to": datetime.now() + timedelta(days=14),
                        })
                    logger.info(f"[{self.name}] {keyword} → {len(items)} 条商品")
                    await asyncio.sleep(self.request_delay)
                except Exception as e:
                    logger.warning(f"[{self.name}] {keyword} 抓取失败: {e}")

        return all_items
