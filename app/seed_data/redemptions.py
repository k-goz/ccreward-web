"""积分兑换商品种子数据（扩充版）。"""
from app.models.redemption import RedemptionItem

REDEMPTIONS = [
    # ============ 招行经典卡 ============
    {"id": "rdm_cmb_starbucks", "card_id": "cmb_classic_visa", "item_name": "星巴克大杯咖啡兑换券", "merchant_name": "星巴克", "category": "咖啡茶饮", "points_required": 799, "cash_value": 33.0, "description": "799积分兑换星巴克大杯咖啡"},
    {"id": "rdm_cmb_luckin", "card_id": "cmb_classic_visa", "item_name": "瑞幸咖啡标准杯兑换券", "merchant_name": "瑞幸咖啡", "category": "咖啡茶饮", "points_required": 499, "cash_value": 15.0, "description": "499积分兑换瑞幸标准杯"},
    {"id": "rdm_cmb_mcd", "card_id": "cmb_classic_visa", "item_name": "麦当劳巨无霸套餐兑换券", "merchant_name": "麦当劳", "category": "餐饮美食", "points_required": 1200, "cash_value": 39.0, "description": "1200积分兑换巨无霸套餐"},
    {"id": "rdm_cmb_kfc", "card_id": "cmb_classic_visa", "item_name": "肯德基全家桶兑换券", "merchant_name": "肯德基", "category": "餐饮美食", "points_required": 2000, "cash_value": 69.0, "description": "2000积分兑换全家桶"},
    {"id": "rdm_cmb_heytea", "card_id": "cmb_classic_visa", "item_name": "喜茶饮品兑换券", "merchant_name": "喜茶", "category": "咖啡茶饮", "points_required": 1500, "cash_value": 30.0, "description": "1500积分兑换喜茶饮品"},

    # ============ 招行YOUNG卡 ============
    {"id": "rdm_cmb_young_dianying", "card_id": "cmb_young", "item_name": "电影票兑换券", "merchant_name": "猫眼电影", "category": "休闲娱乐", "points_required": 400, "cash_value": 35.0, "description": "400积分兑换电影票"},
    {"id": "rdm_cmb_young_waimai", "card_id": "cmb_young", "item_name": "美团外卖红包", "merchant_name": "美团", "category": "餐饮美食", "points_required": 200, "cash_value": 10.0, "description": "200积分兑换10元外卖红包"},

    # ============ 招行白金卡 ============
    {"id": "rdm_cmb_platinum_flight", "card_id": "cmb_classic_platinum", "item_name": "国内机票兑换", "merchant_name": "携程", "category": "出行旅游", "points_required": 10000, "cash_value": 500.0, "description": "10000积分兑换500元机票抵扣"},

    # ============ 中信i白金 ============
    {"id": "rdm_citic_starbucks", "card_id": "citic_i_platinum", "item_name": "星巴克中杯兑换券", "merchant_name": "星巴克", "category": "咖啡茶饮", "points_required": 9, "cash_value": 30.0, "description": "9积分兑换星巴克中杯（9分享权益）"},
    {"id": "rdm_citic_luckin", "card_id": "citic_i_platinum", "item_name": "瑞幸咖啡兑换券", "merchant_name": "瑞幸咖啡", "category": "咖啡茶饮", "points_required": 9, "cash_value": 15.0, "description": "9积分兑换瑞幸咖啡（9分享权益）"},

    # ============ 中信华为卡 ============
    {"id": "rdm_citic_huawei", "card_id": "citic_huawei", "item_name": "华为云50元代金券", "merchant_name": "华为云", "category": "购物消费", "points_required": 5000, "cash_value": 50.0, "description": "5000积分兑换华为云代金券"},

    # ============ 平安由你卡 ============
    {"id": "rdm_pingan_jd", "card_id": "pingan_freedom", "item_name": "京东E卡100元", "merchant_name": "京东", "category": "购物消费", "points_required": 10000, "cash_value": 100.0, "description": "10000积分兑换100元京东E卡"},
    {"id": "rdm_pingan_phone", "card_id": "pingan_freedom", "item_name": "话费充值100元", "merchant_name": "中国移动", "category": "生活缴费", "points_required": 10000, "cash_value": 100.0, "description": "10000积分兑换100元话费"},

    # ============ 广发真情卡 ============
    {"id": "rdm_cgb_starbucks", "card_id": "cgb_zhenqing", "item_name": "星巴克大杯兑换券", "merchant_name": "星巴克", "category": "咖啡茶饮", "points_required": 20000, "cash_value": 33.0, "description": "20000广发积分兑换星巴克大杯"},

    # ============ 浦发AE白 ============
    {"id": "rdm_spdb_flight", "card_id": "spdb_ae_platinum", "item_name": "东航里程500点", "merchant_name": "东方航空", "category": "出行旅游", "points_required": 6000, "cash_value": 50.0, "description": "6000积分兑换500东航里程"},

    # ============ 华夏精英白金 ============
    {"id": "rdm_hxb_flight", "card_id": "hxb_elite_platinum", "item_name": "国航里程500点", "merchant_name": "中国国际航空", "category": "出行旅游", "points_required": 8000, "cash_value": 50.0, "description": "8000积分兑换500国航里程"},
    {"id": "rdm_hxb_train", "card_id": "hxb_elite_platinum", "item_name": "高铁贵宾候车券", "merchant_name": "12306", "category": "出行旅游", "points_required": 500, "cash_value": 30.0, "description": "500积分兑换高铁贵宾候车券"},

    # ============ 华夏星巴克卡 ============
    {"id": "rdm_hxb_starbucks", "card_id": "hxb_starbucks", "item_name": "星巴克大杯兑换券", "merchant_name": "星巴克", "category": "咖啡茶饮", "points_required": 3000, "cash_value": 33.0, "description": "3000积分兑换星巴克大杯"},

    # ============ 农行尊然白金 ============
    {"id": "rdm_abc_flight", "card_id": "abc_zunran_platinum", "item_name": "机票抵扣200元", "merchant_name": "携程", "category": "出行旅游", "points_required": 3000, "cash_value": 200.0, "description": "3000积分兑换200元机票抵扣"},

    # ============ 农行QQ卡 ============
    {"id": "rdm_abc_qq", "card_id": "abc_qq", "item_name": "QQ超级会员月卡", "merchant_name": "腾讯", "category": "购物消费", "points_required": 500, "cash_value": 20.0, "description": "500积分兑换QQ超级会员月卡"},

    # ============ 中银数字卡 ============
    {"id": "rdm_boc_jd", "card_id": "boc_digital", "item_name": "京东E卡50元", "merchant_name": "京东", "category": "购物消费", "points_required": 5000, "cash_value": 50.0, "description": "5000中行积分兑换50元京东E卡"},

    # ============ 工行祥龙卡 ============
    {"id": "rdm_icbc_xianglong", "card_id": "icbc_xianglong", "item_name": "高铁贵宾候车券", "merchant_name": "12306", "category": "出行旅游", "points_required": 10000, "cash_value": 30.0, "description": "10000积分兑换高铁贵宾候车券"},

    # ============ 建行MUSE卡 ============
    {"id": "rdm_ccb_muse", "card_id": "ccb_muse", "item_name": "大麦演出券100元", "merchant_name": "大麦", "category": "休闲娱乐", "points_required": 10000, "cash_value": 100.0, "description": "10000积分兑换100元演出券"},

    # ============ 民生精英白金 ============
    {"id": "rdm_cmbc_elite_jiu", "card_id": "cmbc_elite", "item_name": "酒后代驾券", "merchant_name": "滴滴", "category": "生活缴费", "points_required": 2000, "cash_value": 99.0, "description": "2000积分兑换酒后代驾券"},

    # ============ 交行白麒麟 ============
    {"id": "rdm_bocom_baijia", "card_id": "bocom_whitegold", "item_name": "酒后代驾券", "merchant_name": "滴滴", "category": "生活缴费", "points_required": 15000, "cash_value": 99.0, "description": "15000积分兑换酒后代驾券"},
    {"id": "rdm_bocom_flight", "card_id": "bocom_whitegold", "item_name": "航空里程1000点", "merchant_name": "三大航", "category": "出行旅游", "points_required": 18000, "cash_value": 100.0, "description": "18000积分兑换1000航空里程"},

    # ============ 区域银行兑换 ============
    {"id": "rdm_bjb_jd", "card_id": "bjb_bai", "item_name": "京东E卡50元", "merchant_name": "京东", "category": "购物消费", "points_required": 8000, "cash_value": 50.0, "description": "8000积分兑换50元京东E卡"},

    {"id": "rdm_shbank_waimai", "card_id": "shbank_unionpay", "item_name": "美团外卖红包20元", "merchant_name": "美团", "category": "餐饮美食", "points_required": 2000, "cash_value": 20.0, "description": "2000积分兑换20元外卖红包"},

    {"id": "rdm_gzcb_starbucks", "card_id": "gzcb_unionpay", "item_name": "星巴克中杯兑换券", "merchant_name": "星巴克", "category": "咖啡茶饮", "points_required": 15000, "cash_value": 30.0, "description": "15000积分兑换星巴克中杯"},

    {"id": "rdm_hzcb_alipay", "card_id": "hzcb_xihu", "item_name": "支付宝红包30元", "merchant_name": "支付宝", "category": "购物消费", "points_required": 3000, "cash_value": 30.0, "description": "3000积分兑换30元支付宝红包"},

    {"id": "rdm_njcb_suguo", "card_id": "njcb_unionpay", "item_name": "苏果超市券50元", "merchant_name": "苏果", "category": "购物消费", "points_required": 5000, "cash_value": 50.0, "description": "5000积分兑换50元苏果超市券"},

    {"id": "rdm_cdcb_huoguo", "card_id": "cdcb_shu", "item_name": "火锅代金券100元", "merchant_name": "小龙坎", "category": "餐饮美食", "points_required": 6000, "cash_value": 100.0, "description": "6000积分兑换100元火锅代金券"},

    {"id": "rdm_szpa_metro", "card_id": "szpa_unionpay", "item_name": "深圳通充值券50元", "merchant_name": "深圳通", "category": "出行旅游", "points_required": 5000, "cash_value": 50.0, "description": "5000积分兑换50元深圳通"},

    {"id": "rdm_suzbc_didi", "card_id": "suzbc_unionpay", "item_name": "滴滴快车券30元", "merchant_name": "滴滴", "category": "出行旅游", "points_required": 3000, "cash_value": 30.0, "description": "3000积分兑换30元滴滴快车券"},
]
