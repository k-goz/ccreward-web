"""场景推荐服务：根据用户场景关键词推荐最合适的信用卡

升级版：jieba 分词 + 同义词扩展 + 权重计分 + 标题语义匹配（Jaccard 相似度）
"""

import re
from collections import defaultdict

import jieba
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.card import CreditCard
from app.models.benefit import CardBenefit, BenefitCategory, BenefitType
from app.models.activity import MerchantActivity
from app.schemas.recommend import (
    RecommendResult,
    MatchedBenefit,
    RecommendResponse,
)

# ─── jieba 自定义词典 ────────────────────────────────────────────────
# 确保 SCENARIO_MAP 中的关键词和品牌词能被正确切分
_CUSTOM_WORDS = [
    # 品牌/专有名词（确保 jieba 能正确切分这些词）
    "星巴克", "瑞幸", "喜茶", "奈雪", "霸王茶姬", "蜜雪冰城", "茶百道", "库迪",
    "海底捞", "呷哺呷哺", "Costco", "costa", "manner",
    "沃尔玛", "大润发", "永辉", "家乐福", "盒马", "山姆",
    "京东", "淘宝", "拼多多", "天猫", "唯品会",
    "滴滴", "动车", "12306",
    "话费", "手机充值",
]
for _w in _CUSTOM_WORDS:
    jieba.add_word(_w)

# 抑制 jieba 初始化日志
jieba.setLogLevel(20)


# ─── 场景关键词 → BenefitCategory 映射 ──────────────────────────────
SCENARIO_MAP: dict[str, list[str]] = {
    # 餐饮 ─ 星巴克/咖啡/茶饮/奶茶/瑞幸/肯德基/麦当劳/汉堡王/火锅/外卖/吃饭/聚餐/美食/烘焙
    "星巴克": ["咖啡茶饮"],
    "瑞幸": ["咖啡茶饮"],
    "咖啡": ["咖啡茶饮"],
    "奶茶": ["咖啡茶饮"],
    "茶饮": ["咖啡茶饮"],
    "喜茶": ["咖啡茶饮"],
    "奈雪": ["咖啡茶饮"],
    "霸王茶姬": ["咖啡茶饮"],
    "肯德基": ["餐饮美食"],
    "麦当劳": ["餐饮美食"],
    "汉堡王": ["餐饮美食"],
    "火锅": ["餐饮美食"],
    "烤肉": ["餐饮美食"],
    "日料": ["餐饮美食"],
    "西餐": ["餐饮美食"],
    "烧烤": ["餐饮美食"],
    "美食": ["餐饮美食"],
    "烘焙": ["餐饮美食"],
    "外卖": ["餐饮美食", "线上消费"],
    "吃饭": ["餐饮美食"],
    "聚餐": ["餐饮美食"],
    "请客": ["餐饮美食"],
    "餐厅": ["餐饮美食"],
    "海底捞": ["餐饮美食"],

    # 出行 ─ 加油/洗车/打车/滴滴/高铁/机场/贵宾厅/机票/酒店/停车/自驾/租车
    "加油": ["加油"],
    "洗车": ["出行旅游"],
    "打车": ["出行旅游"],
    "滴滴": ["出行旅游"],
    "高铁": ["出行旅游"],
    "机场": ["出行旅游"],
    "贵宾厅": ["出行旅游"],
    "机票": ["出行旅游"],
    "酒店": ["出行旅游"],
    "停车": ["出行旅游"],
    "自驾": ["出行旅游"],
    "租车": ["出行旅游"],
    "旅游": ["出行旅游"],
    "出行": ["出行旅游"],
    "火车票": ["出行旅游"],

    # 购物 ─ 京东/淘宝/拼多多/超市/便利店/网购/商场/双11/618
    "京东": ["线上消费", "购物消费"],
    "淘宝": ["线上消费", "购物消费"],
    "拼多多": ["线上消费", "购物消费"],
    "天猫": ["线上消费", "购物消费"],
    "唯品会": ["线上消费", "购物消费"],
    "网购": ["线上消费"],
    "超市": ["超市便利"],
    "便利店": ["超市便利"],
    "商场": ["购物消费"],
    "购物": ["购物消费"],
    "双11": ["购物消费", "线上消费"],
    "618": ["购物消费", "线上消费"],
    "百货": ["购物消费"],
    "屈臣氏": ["购物消费"],
    "山姆": ["超市便利"],
    "盒马": ["超市便利"],
    "Costco": ["超市便利"],

    # 娱乐 ─ 电影/演出/KTV/演唱会/密室/剧本杀/脱口秀/游乐场/音乐节
    "电影": ["休闲娱乐"],
    "演出": ["休闲娱乐"],
    "KTV": ["休闲娱乐"],
    "演唱会": ["休闲娱乐"],
    "密室": ["休闲娱乐"],
    "剧本杀": ["休闲娱乐"],
    "脱口秀": ["休闲娱乐"],
    "游乐场": ["休闲娱乐"],
    "音乐节": ["休闲娱乐"],
    "话剧": ["休闲娱乐"],
    "娱乐": ["休闲娱乐"],

    # 生活 ─ 话费/水电/缴费/手机充值/宽带/燃气
    "话费": ["生活缴费"],
    "水电": ["生活缴费"],
    "缴费": ["生活缴费"],
    "燃气": ["生活缴费"],
    "宽带": ["生活缴费"],
    "通讯": ["生活缴费"],
    "手机充值": ["生活缴费"],
    "生活": ["生活缴费"],
}


# ─── 同义词表（双向映射） ────────────────────────────────────────────
# 每个核心词映射到同义词列表，构建时自动生成反向映射
SYNONYM_DICT: dict[str, list[str]] = {
    # 餐饮类
    "吃饭": ["用餐", "餐饮", "美食", "吃", "聚餐", "请客", "下馆子", "觅食"],
    "咖啡": ["拿铁", "美式", "星巴克", "咖啡店", "瑞幸", "costa", "manner"],
    "奶茶": ["茶饮", "喜茶", "奈雪", "蜜雪冰城", "霸王茶姬", "饮品", "茶百道", "库迪"],
    "火锅": ["海底捞", "呷哺呷哺", "巴奴", "锅", "涮肉"],
    "烧烤": ["烤肉", "串", "撸串", "夜宵"],
    "外卖": ["美团", "饿了么", "配送", "外卖"],
    "日料": ["寿司", "刺身", "日本料理", "居酒屋"],
    "西餐": ["牛排", "意大利", "法餐", "西餐厅"],

    # 出行类
    "加油": ["中石化", "中石油", "加油站", "92号", "95号", "98号"],
    "打车": ["滴滴", "出租车", "网约车", "出行", "专车"],
    "高铁": ["火车", "动车", "火车票", "12306", "铁路"],
    "机票": ["飞机", "航空", "航班", "登机", "航空公司"],
    "酒店": ["住宿", "旅馆", "民宿", "希尔顿", "万豪", "洲际"],
    "旅游": ["旅行", "出游", "度假", "景点", "游玩"],

    # 购物类
    "网购": ["淘宝", "京东", "拼多多", "天猫", "网购", "电商", "网购"],
    "超市": ["沃尔玛", "大润发", "永辉", "家乐福", "盒马", "山姆", "costco"],
    "购物": ["买东西", "消费", "逛街", "商场", "百货", "剁手"],

    # 娱乐类
    "电影": ["影院", "看电影", "票", "IMAX", "观影"],
    "演出": ["话剧", "音乐剧", "戏剧", "表演", "票务"],
    "娱乐": ["玩", "休闲", "放松", "消遣"],

    # 生活类
    "话费": ["手机充值", "充值", "通讯", "移动", "联通", "电信"],
    "缴费": ["水电费", "燃气费", "电费", "水费", "物业费"],
}

# 构建反向同义词映射：同义词 → 核心词
_REVERSE_SYNONYMS: dict[str, str] = {}
for _core, _syns in SYNONYM_DICT.items():
    for _syn in _syns:
        _REVERSE_SYNONYMS[_syn.lower()] = _core
        _REVERSE_SYNONYMS[_syn] = _core

# 品牌词集合（权重略低于核心品类词）
_BRAND_WORDS: set[str] = set()
for _syns in SYNONYM_DICT.values():
    for _s in _syns:
        # 品牌词通常是同义词列表中长度 >= 2 的非通用词
        if len(_s) >= 2 and _s not in ("吃", "锅", "串", "玩", "票", "消费"):
            _BRAND_WORDS.add(_s.lower())
            _BRAND_WORDS.add(_s)


# ─── 停用词 ──────────────────────────────────────────────────────────
_STOPWORDS: set[str] = {
    "的", "了", "我", "想", "去", "在", "个", "是", "有", "和", "就",
    "不", "也", "都", "而", "及", "与", "或", "这", "那", "里", "哪",
    "要", "会", "能", "可以", "吗", "呢", "吧", "啊", "哦", "嗯",
    "一下", "一些", "什么", "怎么", "为什么", "哪里", "哪个",
    "比较", "最", "非常", "特别", "已经", "还是", "或者", "但",
    "但是", "因为", "所以", "如果", "虽然", "不过", "然后", "现在",
    "今天", "明天", "昨天", "附近", "旁边", "附近", "这边", "那边",
    "帮", "帮我", "请问", "请", "麻烦", "给", "给个",
    "喝", "吃", "买", "看", "玩",  # 动词泛用词保留在分词中但不作为匹配主词
}


def _tokenize(scenario: str) -> list[str]:
    """jieba 分词 + 去停用词 + 去标点 + 复合词拆分"""
    raw_tokens = jieba.lcut(scenario.strip())
    tokens = []
    for t in raw_tokens:
        t = t.strip()
        # 去标点和空白
        if not t or re.match(r'^[\s\W_]+$', t):
            continue
        # 去停用词（但保留可能在 SCENARIO_MAP 中的词）
        if t in _STOPWORDS and t not in SCENARIO_MAP:
            continue
        # 复合词拆分：如果 token 包含 SCENARIO_MAP 中的关键词作为子串，拆出来
        # 例如 jieba 可能输出 "喝咖啡"，拆成 "喝" + "咖啡"
        sub_tokens = _split_compound_token(t)
        tokens.extend(sub_tokens)
    return tokens


def _split_compound_token(token: str) -> list[str]:
    """尝试从复合 token 中提取 SCENARIO_MAP 关键词。"""
    # 如果 token 本身就在 SCENARIO_MAP 中，直接返回
    if token in SCENARIO_MAP:
        return [token]
    # 尝试在 token 中查找 SCENARIO_MAP 的关键词
    found = []
    remaining = token
    for kw in sorted(SCENARIO_MAP.keys(), key=len, reverse=True):
        if kw in remaining:
            found.append(kw)
            remaining = remaining.replace(kw, "", 1)
    if found:
        # 把剩余部分也作为 token（如果是停用词会被后续过滤）
        result = []
        for f in found:
            result.append(f)
        # remaining 可能是动词前缀如 "喝"
        remaining = remaining.strip()
        if remaining and remaining not in _STOPWORDS:
            result.append(remaining)
        return result
    return [token]


def _lookup_synonym(token: str) -> str | None:
    """查同义词表，返回 token 对应的核心词"""
    # 直接查
    if token in _REVERSE_SYNONYMS:
        return _REVERSE_SYNONYMS[token]
    # 小写查
    if token.lower() in _REVERSE_SYNONYMS:
        return _REVERSE_SYNONYMS[token.lower()]
    return None


def _parse_scenario(scenario: str) -> list[tuple[str, float]]:
    """解析场景关键词，返回 (category_label, weight) 元组列表。

    权重规则：
    - SCENARIO_MAP 直接匹配 = 1.0
    - 同义词扩展匹配 = 0.7
    - 品牌词匹配 = 0.6

    返回去重后的列表，同一类别取最高权重。
    """
    tokens = _tokenize(scenario)
    # 同时保留原始字符串用于直接子串匹配
    lower_scenario = scenario.lower()

    cat_weights: dict[str, float] = {}

    # 1. 逐 token 查 SCENARIO_MAP
    for token in tokens:
        # 精确匹配 SCENARIO_MAP
        if token in SCENARIO_MAP:
            for cat in SCENARIO_MAP[token]:
                if cat_weights.get(cat, 0.0) < 1.0:
                    cat_weights[cat] = 1.0
            continue

        # 同义词扩展
        core_word = _lookup_synonym(token)
        if core_word and core_word in SCENARIO_MAP:
            for cat in SCENARIO_MAP[core_word]:
                if cat_weights.get(cat, 0.0) < 0.7:
                    cat_weights[cat] = 0.7
            continue

        # 品牌词：检查 token 是否是某个品牌词
        if token.lower() in _BRAND_WORDS or token in _BRAND_WORDS:
            # 找到该品牌词对应的核心词
            core = _lookup_synonym(token)
            if core and core in SCENARIO_MAP:
                for cat in SCENARIO_MAP[core]:
                    if cat_weights.get(cat, 0.0) < 0.6:
                        cat_weights[cat] = 0.6

    # 2. 原始子串匹配（兼容旧行为，但权重 0.5）
    for keyword, categories in SCENARIO_MAP.items():
        if keyword in lower_scenario or keyword in scenario:
            for cat in categories:
                if cat_weights.get(cat, 0.0) < 0.5:
                    cat_weights[cat] = 0.5

    # 兜底
    if not cat_weights:
        cat_weights["通用"] = 0.3

    # 返回按权重降序排列
    return sorted(cat_weights.items(), key=lambda x: x[1], reverse=True)


def _match_category(category_label: str) -> BenefitCategory | None:
    """将中文类别标签转为 BenefitCategory 枚举。"""
    label_map = {
        "餐饮美食": BenefitCategory.DINING,
        "咖啡茶饮": BenefitCategory.COFFEE,
        "购物消费": BenefitCategory.SHOPPING,
        "线上消费": BenefitCategory.ONLINE,
        "出行旅游": BenefitCategory.TRAVEL,
        "加油": BenefitCategory.PETROL,
        "休闲娱乐": BenefitCategory.ENTERTAINMENT,
        "超市便利": BenefitCategory.GROCERY,
        "生活缴费": BenefitCategory.BILL,
        "通用": BenefitCategory.GENERAL,
    }
    return label_map.get(category_label)


def _calc_benefit_score(benefit: CardBenefit) -> float:
    """单条权益计分：折扣 + 返现 + 积分 + 品类匹配。"""
    score = 0.0
    if benefit.discount_percent:
        score += min(benefit.discount_percent / 5.0, 5.0)  # 最高5分
    if benefit.cashback_percent:
        score += min(benefit.cashback_percent * 2.0, 10.0)  # 最高10分
    if benefit.points_per_yuan:
        score += min(benefit.points_per_yuan * 2.0, 6.0)   # 最高6分
    # 买一赠一 / 贵宾厅 / 优先权益 额外加分
    if benefit.benefit_type in (BenefitType.BUY_ONE_GET_ONE,):
        score += 2.0
    if benefit.benefit_type in (BenefitType.LOUNGE, BenefitType.PRIORITY):
        score += 1.5
    return score


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """计算两个词集合的重叠率（Overlap Coefficient）。

    使用 overlap = |A ∩ B| / min(|A|, |B|) 而非标准 Jaccard，
    因为用户 query 通常只有 1-3 个词，而标题可能有 5+ 个词，
    标准 Jaccard 会严重稀释相似度。
    """
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    min_size = min(len(set_a), len(set_b))
    return len(intersection) / min_size if min_size > 0 else 0.0


def _tokenize_for_jaccard(text: str) -> set[str]:
    """对文本做 jieba 分词，返回词集合（去停用词去标点 + 复合词拆分）。"""
    if not text:
        return set()
    raw = jieba.lcut(text.strip())
    result = set()
    for t in raw:
        t = t.strip()
        if not t or re.match(r'^[\s\W_]+$', t):
            continue
        if t in _STOPWORDS and t not in SCENARIO_MAP:
            continue
        # 复合词拆分
        sub_tokens = _split_compound_token(t)
        for st in sub_tokens:
            if st and st not in _STOPWORDS:
                result.add(st.lower())
    return result


async def recommend_cards(
    scenario: str,
    db: AsyncSession,
    user_id: str | None = None,
) -> RecommendResponse:
    """根据场景关键词推荐最合适的信用卡。

    升级版流程：
    1. jieba 分词 + 同义词扩展解析场景
    2. 按权重查询匹配的权益
    3. 对 benefit/activity 标题做 Jaccard 语义匹配
    4. 综合得分 = 品类得分 × 权重 + 标题匹配得分
    5. 返回 Top 5 推荐
    """
    # 1. 解析场景（带权重）
    cat_weight_pairs = _parse_scenario(scenario)
    category_labels = [label for label, _ in cat_weight_pairs]

    # 构建类别→权重映射
    cat_weight_map: dict[str, float] = {label: w for label, w in cat_weight_pairs}

    # 转为 BenefitCategory 枚举
    benefit_categories: list[tuple[BenefitCategory, float]] = []
    seen_cats: set[BenefitCategory] = set()
    for label, weight in cat_weight_pairs:
        cat_enum = _match_category(label)
        if cat_enum and cat_enum not in seen_cats:
            benefit_categories.append((cat_enum, weight))
            seen_cats.add(cat_enum)

    # 用户 query 的 token 集合（用于 Jaccard）
    query_tokens = _tokenize_for_jaccard(scenario)

    # 2. 查询匹配的权益
    conditions = []
    for cat_enum, _weight in benefit_categories:
        conditions.append(CardBenefit.category == cat_enum)

    # 同时用 merchant_tags / title 模糊匹配关键词
    keyword_conditions = []
    lower_scenario = scenario.lower()
    for kw in SCENARIO_MAP:
        if kw in lower_scenario or kw in scenario:
            keyword_conditions.append(CardBenefit.merchant_tags.ilike(f"%{kw}%"))
            keyword_conditions.append(CardBenefit.title.ilike(f"%{kw}%"))

    where_clause = or_(*conditions) if conditions else or_(False)
    if keyword_conditions:
        where_clause = or_(where_clause, *keyword_conditions)

    # 也查询 merchant_activities
    activity_conditions = []
    for cat_enum, _ in benefit_categories:
        activity_conditions.append(MerchantActivity.category.ilike(f"%{cat_enum.value}%"))
    for kw in SCENARIO_MAP:
        if kw in lower_scenario or kw in scenario:
            activity_conditions.append(MerchantActivity.merchant_name.ilike(f"%{kw}%"))
            activity_conditions.append(MerchantActivity.title.ilike(f"%{kw}%"))

    stmt_benefits = (
        select(CardBenefit)
        .options(joinedload(CardBenefit.card))
        .where(CardBenefit.is_active == True, where_clause)
    )
    result_benefits = await db.execute(stmt_benefits)
    benefits = result_benefits.unique().scalars().all()

    # 按 card_id 聚合
    card_scores: dict[str, float] = {}
    card_matched_benefits: dict[str, list[tuple[CardBenefit, float]]] = {}

    for ben in benefits:
        if ben.card is None:
            continue

        # 基础权益得分
        base_score = _calc_benefit_score(ben)

        # 品类匹配加权：找到该 benefit 的 category 对应的权重
        cat_weight = 1.0  # 默认权重
        for cat_enum, weight in benefit_categories:
            if ben.category == cat_enum:
                cat_weight = weight
                break

        # 标题 Jaccard 相似度
        ben_title_tokens = _tokenize_for_jaccard(ben.title or "")
        jaccard = _jaccard_similarity(query_tokens, ben_title_tokens)

        # 综合得分 = 基础得分 × 品类权重 + 标题匹配得分
        # 标题匹配得分 = jaccard × 10（缩放到与基础得分可比）
        # 只有 Jaccard > 0.3 才计入标题匹配分
        title_score = jaccard * 10.0 if jaccard > 0.3 else 0.0

        total_score = base_score * cat_weight + title_score

        card_scores[ben.card_id] = card_scores.get(ben.card_id, 0.0) + total_score
        card_matched_benefits.setdefault(ben.card_id, []).append((ben, total_score))

    # 3. 也考虑 merchant_activities（附加值加权）
    if activity_conditions:
        act_stmt = (
            select(MerchantActivity)
            .where(MerchantActivity.is_active == True, or_(*activity_conditions))
            .limit(50)
        )
        act_result = await db.execute(act_stmt)
        activities = act_result.scalars().all()

        for act in activities:
            # 活动标题 Jaccard 匹配
            act_title_tokens = _tokenize_for_jaccard(act.title or "")
            act_jaccard = _jaccard_similarity(query_tokens, act_title_tokens)
            act_score = act_jaccard * 5.0 if act_jaccard > 0.3 else 0.5

            # 给已经有权益匹配的卡适当加权
            for card_id in card_scores:
                card_scores[card_id] += act_score

    # 4. 排序，取 Top 5
    sorted_cards = sorted(card_scores.items(), key=lambda x: x[1], reverse=True)[:5]

    # 5. 查询卡片详情
    top_card_ids = [cid for cid, _ in sorted_cards]
    if top_card_ids:
        card_stmt = (
            select(CreditCard)
            .where(CreditCard.id.in_(top_card_ids))
        )
        card_result = await db.execute(card_stmt)
        cards_map = {c.id: c for c in card_result.scalars().all()}
    else:
        cards_map = {}

    # 6. 构建响应
    recommendations: list[RecommendResult] = []
    for card_id, total_score in sorted_cards:
        card = cards_map.get(card_id)
        if card is None:
            continue

        matched_bens = card_matched_benefits.get(card_id, [])
        # 按贡献度排序
        matched_bens.sort(key=lambda x: x[1], reverse=True)
        matched_list = [
            MatchedBenefit(
                id=ben.id,
                title=ben.title,
                benefit_type=ben.benefit_type.value if ben.benefit_type else "",
                category=ben.category.value if ben.category else "",
                description=ben.description,
                discount_percent=ben.discount_percent,
                cashback_percent=ben.cashback_percent,
                points_per_yuan=ben.points_per_yuan,
                score_contribution=round(s, 2),
            )
            for ben, s in matched_bens
        ]

        # 生成推荐理由
        top_ben = matched_bens[0][0] if matched_bens else None
        if top_ben and top_ben.cashback_percent and top_ben.cashback_percent > 0:
            reason = f"{card.bank}{card.name} 在该场景享 {top_ben.cashback_percent:.0f}% 返现，共匹配 {len(matched_bens)} 项权益"
        elif top_ben and top_ben.discount_percent and top_ben.discount_percent > 0:
            reason = f"{card.bank}{card.name} 享 {top_ben.discount_percent:.0f}% 折扣，共匹配 {len(matched_bens)} 项权益"
        elif matched_bens:
            reason = f"{card.bank}{card.name} 在该场景匹配 {len(matched_bens)} 项权益，综合性价比最高"
        else:
            reason = f"{card.bank}{card.name} 推荐"

        from app.schemas.card import CardOut

        recommendations.append(RecommendResult(
            card=CardOut.model_validate(card),
            total_score=round(total_score, 2),
            matched_benefits=matched_list,
            reason=reason,
        ))

    return RecommendResponse(
        scenario=scenario,
        matched_categories=category_labels,
        recommendations=recommendations,
    )
