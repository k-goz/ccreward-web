"""什么值得买爬虫：抓取优惠信息。

使用 SMZDM 公开的 homepage/json_more API 获取优惠信息列表，
按品类过滤后标准化为 MerchantActivity 格式。
无需登录，纯 httpx 异步请求，零浏览器开销。
"""

import asyncio
import logging
import random
import re
from datetime import datetime, timedelta, timezone

import httpx

from app.crawlers.base import BaseCrawler
from app.models.activity import Platform

logger = logging.getLogger(__name__)

# SMZDM 公开 JSON 接口（无需认证）
SMZDM_API = "https://www.smzdm.com/homepage/json_more"

# 目标品类关键词
TARGET_CATEGORIES = [
    "餐饮美食", "咖啡奶茶", "外卖红包", "电影票",
    "商超便利", "加油", "话费充值",
    "数码家电", "日用百货", "生鲜水果", "图书文具",
]

# 品类过滤：SMZDM 返回的 top_category / category_names / title 与目标品类映射
CATEGORY_KEYWORDS = {
    # === 餐饮美食 ===
    "食品生鲜": "餐饮美食",
    "餐饮美食": "餐饮美食",
    "餐饮": "餐饮美食",
    "美食": "餐饮美食",
    "零食": "餐饮美食",
    "薯片": "餐饮美食",
    "饼干": "餐饮美食",
    "坚果": "餐饮美食",
    "巧克力": "餐饮美食",
    "糖果": "餐饮美食",
    "速食": "餐饮美食",
    "方便面": "餐饮美食",
    "螺蛳粉": "餐饮美食",
    "自热": "餐饮美食",
    "预制菜": "餐饮美食",
    "调料": "餐饮美食",
    "粮油": "餐饮美食",
    # === 咖啡奶茶 ===
    "咖啡": "咖啡奶茶",
    "奶茶": "咖啡奶茶",
    "茶饮": "咖啡奶茶",
    "瑞幸": "咖啡奶茶",
    "星巴克": "咖啡奶茶",
    "喜茶": "咖啡奶茶",
    "奈雪": "咖啡奶茶",
    "蜜雪": "咖啡奶茶",
    "霸王茶姬": "咖啡奶茶",
    "CoCo": "咖啡奶茶",
    "茶颜": "咖啡奶茶",
    "奶茶店": "咖啡奶茶",
    # === 外卖红包 ===
    "外卖": "外卖红包",
    "红包": "外卖红包",
    "配送": "外卖红包",
    "到家": "外卖红包",
    # === 电影票 ===
    "电影": "电影票",
    "影院": "电影票",
    "影票": "电影票",
    # === 商超便利 ===
    "商超": "商超便利",
    "超市": "商超便利",
    "便利店": "商超便利",
    # === 加油 ===
    "加油": "加油",
    "中石油": "加油",
    "中石化": "加油",
    # === 话费充值 ===
    "话费": "话费充值",
    "手机充值": "话费充值",
    "充值": "话费充值",
    "流量": "话费充值",
    # === 数码家电 ===
    "数码": "数码家电",
    "家电": "数码家电",
    "手机": "数码家电",
    "电脑": "数码家电",
    "笔记本": "数码家电",
    "平板": "数码家电",
    "耳机": "数码家电",
    "音箱": "数码家电",
    "电视": "数码家电",
    "冰箱": "数码家电",
    "洗衣机": "数码家电",
    "空调": "数码家电",
    "扫地机": "数码家电",
    "路由器": "数码家电",
    "充电器": "数码家电",
    "充电宝": "数码家电",
    "数据线": "数码家电",
    # === 日用百货 ===
    "日用": "日用百货",
    "洗护": "日用百货",
    "纸巾": "日用百货",
    "家清": "日用百货",
    "清洁": "日用百货",
    "洗衣": "日用百货",
    "拖把": "日用百货",
    "收纳": "日用百货",
    "牙膏": "日用百货",
    "牙刷": "日用百货",
    "洗发": "日用百货",
    "沐浴": "日用百货",
    "沐浴露": "日用百货",
    "湿巾": "日用百货",
    # === 生鲜水果 ===
    "生鲜": "生鲜水果",
    "水果": "生鲜水果",
    "蔬菜": "生鲜水果",
    "草莓": "生鲜水果",
    "芒果": "生鲜水果",
    "榴莲": "生鲜水果",
    "车厘子": "生鲜水果",
    "蓝莓": "生鲜水果",
    "苹果": "生鲜水果",
    "橙子": "生鲜水果",
    "海鲜": "生鲜水果",
    "肉类": "生鲜水果",
    "鸡蛋": "生鲜水果",
    "牛奶": "生鲜水果",
    # === 图书文具 ===
    "图书": "图书文具",
    "书籍": "图书文具",
    "文具": "图书文具",
    "笔": "图书文具",
    "书包": "图书文具",
    "绘本": "图书文具",
    "教材": "图书文具",
    "教辅": "图书文具",
}

# 商城名称 → Platform 映射
MALL_PLATFORM_MAP = {
    "京东": Platform.JD,
    "天猫精选": Platform.TAOBAO,
    "天猫超市": Platform.TAOBAO,
    "天猫": Platform.TAOBAO,
    "淘宝": Platform.TAOBAO,
    "拼多多": Platform.PINDUODUO,
    "美团": Platform.MEITUAN,
    "饿了么": Platform.ELEME,
    "口碑": Platform.KOUWEI,
    "苏宁": Platform.SUNING,
    "唯品会": Platform.VIPSHOP,
    "支付宝": Platform.ALIPAY,
}

MAX_PAGES = 25
MAX_ITEM_AGE_DAYS = 30  # 超过 30 天未更新的旧条目自动过滤


def _clean_product_name(title: str) -> str:
    """从 title 中智能提取 product_name。

    去掉:
      - 【】 包裹的标记（如【必看】【小编推荐】）
      - 平台名前缀（如「京东」「天猫精选」）
      - 前后空白和多余空格

    返回纯净的商品名称，最多 200 字符。
    """
    if not title:
        return ""
    # 去除【...】标记
    name = re.sub(r'【[^】]*】', '', title)
    # 去除「...」标记
    name = re.sub(r'「[^」]*」', '', name)
    # 去除常见平台前缀
    name = re.sub(r'^(?:京东|天猫精选|天猫超市|天猫|淘宝|拼多多|美团|饿了么)\s*[:：]?\s*', '', name)
    # 去除前后空白和多余空格
    name = re.sub(r'\s+', ' ', name).strip()
    # 限制长度
    return name[:200] if name else title[:200]


def _parse_timesort(item: dict) -> datetime | None:
    """从 SMZDM 条目的 timesort 字段解析发布时间。

    timesort 通常为 Unix 时间戳（秒）。
    """
    timesort = item.get("timesort")
    if timesort and isinstance(timesort, (int, float)) and timesort > 0:
        try:
            return datetime.fromtimestamp(timesort, tz=timezone.utc)
        except (ValueError, OSError):
            pass
    # 也尝试毫秒级时间戳
    if timesort and isinstance(timesort, (int, float)) and timesort > 1_000_000_000_000:
        try:
            return datetime.fromtimestamp(timesort / 1000, tz=timezone.utc)
        except (ValueError, OSError):
            pass
    # 尝试 article_date 或 article_format_date 字符串
    date_str = item.get("article_date") or item.get("article_format_date")
    if date_str:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(str(date_str), fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def _is_too_old(item: dict, max_age_days: int = MAX_ITEM_AGE_DAYS) -> bool:
    """判断 item 是否超过 max_age_days 天未更新。"""
    pub_time = _parse_timesort(item)
    if pub_time is None:
        return False  # 无法解析时间，保留（不过滤）
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    return pub_time < cutoff


class SMZDMCrawler(BaseCrawler):
    """什么值得买优惠信息爬虫。

    通过 homepage/json_more 公开接口获取优惠信息，
    无需登录、无需浏览器，纯 httpx 异步请求。
    自动按品类关键词过滤，覆盖餐饮美食、咖啡奶茶、外卖红包、
    电影票、商超便利、加油、话费充值、数码家电、日用百货、
    生鲜水果、图书文具等品类。
    """

    name = "smzdm"
    display_name = "什么值得买"
    request_delay = 2.0  # SMZDM 有反爬策略，延长间隔
    max_retries = 3

    def _map_category(self, item: dict) -> str:
        """根据 SMZDM 返回的品类信息，映射到目标品类。

        优先匹配 top_category 和 category_names，
        其次匹配 title 中的关键词。
        """
        top_cat = item.get("top_category", "")
        cat_names: list[str] = item.get("category_names", [])
        title = item.get("article_title", "")

        # 品类字段权重更高
        field_text = f"{top_cat} {' '.join(cat_names)}"
        title_text = title

        # 先在品类字段中匹配
        for kw, target in CATEGORY_KEYWORDS.items():
            if kw in field_text:
                return target

        # 再在标题中匹配
        for kw, target in CATEGORY_KEYWORDS.items():
            if kw in title_text:
                return target

        return "餐饮美食"  # 默认归类

    def _map_platform(self, mall: str) -> Platform:
        """商城名称映射到 Platform 枚举。"""
        return MALL_PLATFORM_MAP.get(mall, Platform.OTHER)

    @staticmethod
    def _parse_price(price_text: str) -> float | None:
        """从 SMZDM 价格字符串中提取数字价格。

        支持格式:
          - "12.71元（需买7件，需用券）" → 12.71
          - "满199减100" → 199（取满减值）
          - "3件7折" → 不直接提取（折扣依赖原价）
          - "到手价 29.9元" → 29.9
          - "29.9元包邮" → 29.9
          - "实付低至19.9元" → 19.9（在 content 解析中处理）
        """
        if not price_text:
            return None

        # 优先提取纯数字价格: 形如 "12.71元" 或 "29.9元包邮"
        match = re.search(r'(\d+\.?\d*)\s*元', price_text)
        if match:
            return float(match.group(1))

        # 满减格式: "满199减100" → 取满减值（表示满足条件后能享受的折扣）
        match = re.search(r'满(\d+\.?\d*)\s*减', price_text)
        if match:
            # 满减中，"满"的值是门槛而非实际价格，
            # 但在价格展示上下文中，这通常是关键金额
            threshold = float(match.group(1))
            # 如果也有 "减" 后的值，尝试取实际到手价
            sub_match = re.search(r'满\d+\.?\d*\s*减\s*(\d+\.?\d*)', price_text)
            if sub_match:
                # 满减场景：取满减值作为参考价格
                return threshold

        # 纯数字（不带"元"字）
        match = re.search(r'(\d+\.?\d{1,2})\s*$', price_text)
        if match:
            return float(match.group(1))

        return None

    @staticmethod
    def _parse_original_price(content: str) -> float | None:
        """从活动描述中提取原价。

        示例: "目前活动售价23.2元" → 23.2
        """
        if not content:
            return None
        match = re.search(r'(?:售价|原价|现价|活动售价|日常售价|日常价)\s*(\d+\.?\d*)\s*元', content)
        if match:
            return float(match.group(1))
        return None

    def _parse_item(self, item: dict) -> dict | None:
        """将 SMZDM 单条数据标准化为 MerchantActivity 格式。"""
        try:
            title = item.get("article_title", "")
            mall = item.get("article_mall", "")
            price_text = item.get("article_price", "")
            content = item.get("article_content", "")
            article_id = str(item.get("article_id", ""))
            article_url = item.get("article_url", "")
            pic_url = item.get("article_pic", "")
            is_sold_out = item.get("article_is_sold_out", 0)
            is_timeout = item.get("article_is_timeout", 0)

            # 跳过已售罄或已过期
            if is_sold_out or is_timeout:
                return None

            # 必须有商城名称和标题
            if not mall or not title:
                return None

            # 时效性过滤：跳过超过 30 天的旧条目
            if _is_too_old(item, MAX_ITEM_AGE_DAYS):
                return None

            category = self._map_category(item)
            platform = self._map_platform(mall)

            activity_price = self._parse_price(price_text)
            original_price = self._parse_original_price(content)

            # 如果活动价格为 None，尝试从 content 中提取
            if activity_price is None:
                # content 中可能有 "实付低至19.9元" "到手价29.9元" 等表述
                for pat in (
                    r'(?:实付[^\d]*|到手[^\d]*|低至[^\d]*|好价[^\d]*|折后[^\d]*)\s*(\d+\.?\d*)\s*元',
                    r'(?:到手|好价|实付|折后)[：:]\s*(\d+\.?\d*)\s*元',
                    r'(\d+\.?\d*)\s*元\s*(?:包邮|到手|拿下|好价)',
                ):
                    match = re.search(pat, content)
                    if match:
                        activity_price = float(match.group(1))
                        break

            # 智能提取 product_name（去掉标记、平台名）
            product_name = _clean_product_name(title)

            # 生成唯一 ID
            item_id = self._build_id("smzdm", article_id)

            return {
                "id": item_id,
                "title": title[:250],
                "platform": platform,
                "merchant_name": mall,
                "category": category,
                "product_name": product_name,
                "original_price": original_price,
                "activity_price": activity_price,
                "discount_description": price_text or content[:500],
                "usage_conditions": f"{mall}下单",
                "source_url": article_url or f"https://www.smzdm.com/p/{article_id}/",
                "source_type": "smzdm",
                "image_url": pic_url if pic_url and pic_url.startswith("http") else None,
                "valid_from": datetime.now(),
                "valid_to": datetime.now() + timedelta(days=7),
            }
        except Exception as e:
            logger.debug(f"[{self.name}] 解析条目异常: {e}")
            return None

    async def fetch(self) -> list[dict]:
        """抓取 SMZDM 优惠列表，遍历多页按品类过滤后返回。"""
        all_items: list[dict] = []
        seen_ids: set[str] = set()
        stats = {"total_raw": 0, "skipped_sold_out": 0, "skipped_no_mall": 0, "skipped_too_old": 0}

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.smzdm.com/",
        }

        async with httpx.AsyncClient(
            headers=headers,
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            for page in range(1, MAX_PAGES + 1):
                try:
                    logger.info(f"[{self.name}] 请求第 {page}/{MAX_PAGES} 页")
                    resp = await client.get(SMZDM_API, params={"p": page})

                    if resp.status_code != 200:
                        logger.warning(
                            f"[{self.name}] 第 {page} 页返回 HTTP {resp.status_code}，停止翻页"
                        )
                        break

                    data = resp.json()
                    if data.get("error_code") != 0:
                        logger.warning(
                            f"[{self.name}] API 错误 code={data.get('error_code')}: "
                            f"{data.get('error_msg', '')}"
                        )
                        break

                    articles: list[dict] = data.get("data", [])
                    if not articles:
                        logger.info(f"[{self.name}] 第 {page} 页无数据，翻页结束")
                        break

                    stats["total_raw"] += len(articles)

                    page_items = []
                    for article in articles:
                        # 统计跳过原因（采样前几条做详细日志）
                        sold_out = article.get("article_is_sold_out", 0)
                        timeout = article.get("article_is_timeout", 0)
                        mall = article.get("article_mall", "")

                        if sold_out or timeout:
                            stats["skipped_sold_out"] += 1
                            continue
                        if not mall:
                            stats["skipped_no_mall"] += 1
                            continue
                        if _is_too_old(article, MAX_ITEM_AGE_DAYS):
                            stats["skipped_too_old"] += 1
                            continue

                        item = self._parse_item(article)
                        if item and item["id"] not in seen_ids:
                            seen_ids.add(item["id"])
                            page_items.append(item)

                    all_items.extend(page_items)
                    logger.info(
                        f"[{self.name}] 第 {page} 页: {len(articles)} 条原始, "
                        f"{len(page_items)} 条匹配 (累计 {len(all_items)})"
                    )

                except httpx.TimeoutException:
                    logger.warning(f"[{self.name}] 第 {page} 页请求超时，跳过")
                    continue
                except Exception as e:
                    logger.warning(f"[{self.name}] 第 {page} 页异常: {e}", exc_info=True)
                    continue

                # 请求间隔（含随机抖动避免被识别为爬虫）
                delay = self.request_delay + random.uniform(0.5, 2.0)
                await asyncio.sleep(delay)

        logger.info(
            f"[{self.name}] 抓取完成: 共 {len(all_items)} 条优惠 "
            f"(遍历 {MAX_PAGES} 页, 原始 {stats['total_raw']} 条, "
            f"过滤: 售罄/过期 {stats['skipped_sold_out']}, "
            f"无商城 {stats['skipped_no_mall']}, "
            f"过旧 {stats['skipped_too_old']})"
        )
        return all_items
