# ccreward-cn 开发交接文档

> 本文档供接手开发的 Agent / 工程师阅读，用于快速了解项目现状、架构与后续工作。

## 一、项目背景与目标

### 1.1 起源
基于 GitHub 开源项目 `aashishvanand/ccreward-web`（面向印度/新加坡的信用卡权益优化应用）的思路，开发**面向国内市场**的信用卡权益与商家活动聚合平台。

### 1.2 核心需求
1. **选卡看权益**：用户选择持有的信用卡，查看该卡所有权益（含信用卡本身权益、积分兑换权益）
2. **商家活动聚合与比价**：实时聚合多平台（抖音/美团/支付宝/京东等）商家优惠活动，支持搜索与比价，找出最便宜的平台
3. **一键直达下单**：搜索结果提供"去下单"按钮，直接跳转对应平台购买页

### 1.3 产品形态规划
- Web 应用（当前已实现轻量版）
- 微信小程序（待开发）
- 数据获取：混合方案（官方API优先 → 网页爬取 → 众包兜底）

## 二、技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端框架 | FastAPI 0.115 | Python 异步 Web 框架 |
| 数据库 | SQLite + aiosqlite | 轻量级，原型阶段足够，后续可迁移 PostgreSQL |
| ORM | SQLAlchemy 2.0 | 异步模式 |
| 数据校验 | Pydantic 2.10 | API 契约 |
| 爬虫 | Playwright 1.49 | 浏览器自动化（骨架已搭，未启用真实爬取） |
| 定时任务 | APScheduler 3.11 | 爬虫调度 |
| 前端 | 原生 HTML + JS | 单页应用，无构建依赖，由 FastAPI 静态托管 |
| Python 版本 | **3.11**（重要） | 不能用 3.14，greenlet/pydantic-core 不兼容 |

## 三、项目结构

```
backend/
├── app/
│   ├── main.py                  # FastAPI 入口（生命周期、路由挂载、静态托管）
│   ├── config.py                # Pydantic Settings 配置
│   ├── database.py              # SQLAlchemy 异步引擎 + init_db
│   ├── seed.py                  # 种子数据导入（upsert 模式）
│   ├── models/                  # SQLAlchemy 数据模型
│   │   ├── card.py              #   信用卡 CreditCard
│   │   ├── benefit.py           #   卡权益 CardBenefit
│   │   ├── activity.py          #   商家活动 MerchantActivity
│   │   ├── redemption.py        #   积分兑换 RedemptionItem
│   │   └── user.py              #   用户卡片 UserCard
│   ├── schemas/                 # Pydantic API 契约
│   │   ├── card.py              #   CardOut / CardWithBenefits / BenefitOut
│   │   ├── activity.py          #   ActivityOut / PriceComparisonResult
│   │   └── redemption.py        #   RedemptionOut
│   ├── api/                     # API 路由
│   │   ├── cards.py             #   /api/cards/*
│   │   └── activities.py        #   /api/activities/*
│   ├── services/                # 业务逻辑层
│   │   ├── card_service.py      #   卡片查询、用户卡片、积分兑换
│   │   └── activity_service.py  #   活动搜索、多平台比价
│   ├── crawlers/                # 爬虫
│   │   ├── base.py              #   BaseCrawler 抽象基类
│   │   ├── douyin.py            #   抖音爬虫骨架（未启用真实爬取）
│   │   └── scheduler.py         #   APScheduler 定时调度
│   ├── seed_data/               # 种子数据（纯数据，便于维护）
│   │   ├── cards.py             #   27张卡 + 42条权益
│   │   ├── activities.py        #   20条商家活动（含下单链接）
│   │   └── redemptions.py       #   18条积分兑换商品
│   └── web/
│       └── index.html           # 轻量前端单页应用
├── data/                        # SQLite 数据库（自动生成，gitignore）
│   └── ccreward.db
├── requirements.txt
├── README.md
└── HANDOVER.md                  # 本文档
```

## 四、如何运行

### 4.1 环境准备（重要）
```bash
cd /Users/king/IDEProjects/ccreward-web/backend

# 必须用 Python 3.11（不能用 3.14，native 扩展不兼容）
rm -rf .venv
/opt/homebrew/bin/python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4.2 启动
```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### 4.3 访问
- 前端界面：http://localhost:8000
- API 文档（Swagger）：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/health

### 4.4 数据库重置
```bash
rm -f data/ccreward.db
# 重启后端会自动建表 + 导入种子数据
```

种子数据采用 **upsert 模式**，重启后端会自动同步 `seed_data/` 中的最新数据到数据库，无需删库。

## 五、数据模型

### 5.1 CreditCard（信用卡）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | str(PK) | 如 `cmb_classic_visa` |
| bank | str | 银行名，如"招商银行" |
| name | str | 卡名 |
| network | Enum | 银联/Visa/Mastercard/美国运通/JCB |
| level | Enum | 经典版/金卡/白金卡/钻石卡/御尊卡/无限卡 |
| annual_fee | str | 年费政策文本 |
| description | str | 卡片描述 |

### 5.2 CardBenefit（卡权益）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | str(PK) | |
| card_id | FK | 关联 CreditCard |
| title | str | 权益标题 |
| benefit_type | Enum | 返现/积分累积/折扣/买一赠一/赠礼/贵宾厅/优先权益/保险/其他 |
| category | Enum | 餐饮美食/咖啡茶饮/购物消费/线上消费/出行旅游/加油/休闲娱乐/超市便利/生活缴费/通用 |
| description | str | 权益详情 |
| value_text | str | 如"买一赠一" |
| points_per_yuan | float | 积分累积比例 |
| discount_percent | float | 折扣百分比 |
| cashback_percent | float | 返现百分比 |
| usage_limit | str | 使用限制说明 |
| merchant_tags | str | 商户标签，逗号分隔 |

### 5.3 MerchantActivity（商家活动）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | str(PK) | |
| title | str | 活动标题 |
| platform | Enum | 抖音/美团/滴滴/淘宝/京东/拼多多/支付宝/微信/口碑/饿了么/唯品会/苏宁/其他 |
| merchant_name | str | 商家名，如"瑞幸咖啡" |
| category | str | 分类，如"咖啡茶饮" |
| product_name | str | 商品名 |
| original_price | float | 原价 |
| activity_price | float | 活动价 |
| discount_description | str | 优惠说明 |
| usage_conditions | str | 使用条件 |
| valid_from / valid_to | datetime | 有效期 |
| status | Enum | 进行中/已过期/未开始 |
| source_url | str | **下单直达链接** |
| source_type | str | manual / crawler |
| image_url | str | 活动图片 |

### 5.4 RedemptionItem（积分兑换商品）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | str(PK) | |
| card_id | FK(nullable) | 关联卡片，null 表示通用 |
| item_name | str | 商品名 |
| merchant_name | str | 商家 |
| category | str | 分类 |
| points_required | int | 所需积分 |
| cash_value | float | 约等于现金价值 |

### 5.5 UserCard（用户卡片）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | str(PK) | |
| user_id | str | 用户标识 |
| card_id | FK | 关联 CreditCard |
| nickname | str | 用户自定义昵称 |

## 六、API 列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/cards` | 查询所有卡片（含权益），可 `?bank=` 筛选 |
| GET | `/api/cards/{card_id}` | 单卡详情（含权益） |
| GET | `/api/cards/{card_id}/redemptions` | 该卡积分可兑换商品 |
| GET | `/api/cards/user/{user_id}` | 用户持有的卡片及权益 |
| GET | `/api/activities` | 搜索活动，参数 `keyword`/`platform`/`category`/`limit` |
| GET | `/api/activities/compare?keyword=` | **多平台比价**（核心），返回最低价、最便宜平台、各平台活动列表 |

### 比价返回结构示例
```json
{
  "keyword": "瑞幸咖啡",
  "total_platforms": 4,
  "cheapest_platform": "抖音",
  "cheapest_price": 9.9,
  "items": [
    {
      "platform": "抖音",
      "platform_label": "抖音",
      "activity_id": "act_dy_luckin_5",
      "title": "瑞幸咖啡抖音券 9.9元任选2杯",
      "activity_price": 9.9,
      "original_price": 60.0,
      "discount_description": "9.9元任选2杯，相当于4.95元/杯",
      "usage_conditions": "抖音App下单，到店自取",
      "source_url": "https://www.douyin.com/life/",
      "is_cheapest": true
    }
  ]
}
```

## 七、当前数据规模

| 数据 | 数量 | 说明 |
|------|------|------|
| 信用卡 | 27 张 | 覆盖 15 家主流银行 |
| 卡权益 | 42 条 | 每卡 1-4 条 |
| 商家活动 | 20 条 | 覆盖瑞幸/星巴克/麦当劳/肯德基/喜茶/奈雪/海底捞/必胜客/蜜雪冰城/汉堡王 |
| 积分兑换 | 18 条 | 多张卡的积分商城商品 |

银行覆盖：招商(3) / 工商(2) / 建设(2) / 中信(2) / 平安(2) / 广发(2) / 浦发(2) / 兴业(2) / 光大(2) / 农行(2) / 中行(2) / 民生(1) / 华夏(1) / 邮储(1) / 交行(1)

## 八、前端功能

单页应用 `app/web/index.html`，两个 Tab：

1. **我的卡片**：按银行分组展示 27 张卡，点击任一张查看权益 + 积分兑换商品
2. **搜索比价**：输入关键词（或点快捷标签）→ 多平台比价 → 每条活动有"去下单"按钮直达平台，最低价区有大号绿色下单按钮

前端为原生 HTML+JS，无构建步骤，由 FastAPI 在 `/` 路径托管，`/assets` 挂载静态目录。

## 九、爬虫骨架说明

`app/crawlers/` 已搭好骨架但**未启用真实爬取**：

- `base.py`：`BaseCrawler` 抽象基类，定义 `fetch()` → `save()` → `run()` 流程，upsert 入库
- `douyin.py`：`DemoDouyinCrawler`，`fetch()` 返回空列表，`fetch_with_playwright()` 是真实爬取示例代码（未启用）
- `scheduler.py`：APScheduler 定时调度，默认每 6 小时执行一次，`CRAWLER_ENABLED=True` 时启动

启用真实爬取需要：
1. `playwright install chromium` 安装浏览器
2. 实现 `fetch()` 的页面解析逻辑
3. 配置代理池、登录态、反爬处理
4. **注意合规**：遵守目标网站 robots.txt 和法律法规

## 十、后续开发路线图

### P1 - 数据扩充（优先）
- [ ] 补充更多银行卡（区域性银行：北京/上海/广州/成都等城商行）
- [ ] 补充更多商家活动（滴滴/淘宝/拼多多/饿了么/口碑等平台）
- [ ] 补充更多积分兑换商品（各行积分商城真实数据）
- [ ] 卡片图片 URL（当前 image_url 为空）

### P2 - 真实爬虫接入
- [ ] 实现 Playwright 真实爬取：抖音本地生活、美团团购页
- [ ] 反爬处理：代理池、UA 轮换、验证码识别、登录态管理
- [ ] 活动详情页 URL 精确抓取（当前 source_url 为平台首页，需抓取真实活动页）
- [ ] 增量更新策略：只更新有变化的活动，避免重复爬取
- [ ] 合规审查：robots.txt、爬取频率、数据使用范围

### P3 - 用户系统
- [ ] 接入微信扫码登录（或 Firebase Auth）
- [ ] 用户卡片管理 CRUD（UserCard 模型已建，API 待补全 POST/PATCH/DELETE）
- [ ] 用户收藏活动、搜索历史
- [ ] 个性化推送（基于用户卡片权益 + 常搜商品）

### P4 - 小程序端
- [ ] 用 Taro 或 uni-app 开发微信小程序，复用后端 API
- [ ] 小程序内下单（通过小程序跳转能力，比 H5 链接体验更好）
- [ ] 订阅消息推送（活动更新提醒）

### P5 - 众包后台
- [ ] 管理员后台：录入/审核/编辑卡片权益、商家活动
- [ ] 用户上报：权益过期、活动失效、价格错误
- [ ] 数据版本管理 + 审核流程

### P6 - 智能推荐
- [ ] 基于用户卡片权益，推荐最优支付路径（如"瑞幸咖啡用招行卡走抖音最便宜"）
- [ ] 消费场景匹配：输入消费场景（如"周三下午喝咖啡"），推荐卡片 + 平台组合
- [ ] 积分最优兑换路径计算

### P7 - 工程优化
- [ ] 数据库迁移至 PostgreSQL（用户量上来后）
- [ ] Redis 缓存热点查询
- [ ] 前端升级：从原生 HTML 迁移到 React/Vue + 组件库，或复用原 ccreward-web 的 Next.js 框架
- [ ] 部署：Docker + 国内云（阿里云/腾讯云）
- [ ] 监控：爬虫成功率、API 延迟、数据新鲜度

## 十一、已知问题与注意事项

1. **Python 版本**：必须用 3.11，不能用 3.14（greenlet/pydantic-core 的 C 扩展不兼容 3.14，编译失败）
2. **SQL 日志刷屏**：`config.py` 中 `DEBUG=True` 会打印所有 SQL，生产环境设为 False
3. **source_url 为平台首页**：当前种子数据的下单链接是各平台首页/搜索页，非真实活动详情页。真实链接需爬虫抓取
4. **活动有效期**：种子数据用 `datetime.now() + timedelta(days=N)` 生成，每次 upsert 会刷新，不会过期
5. **无用户鉴权**：当前 UserCard 的 user_id 由前端传入，无鉴权，生产环境需加登录态校验
6. **CORS 全开**：`CORS_ORIGINS=["*"]`，生产环境需限制
7. **原 ccreward-web 前端未复用**：根目录的 Next.js 项目（src/）是原印度/新加坡版本，当前国内版后端独立在 backend/，前端是轻量单页。后续可考虑复用 Next.js 框架重构前端

## 十二、关键文件速查

| 用途 | 路径 |
|------|------|
| 后端入口 | `backend/app/main.py` |
| 配置 | `backend/app/config.py` |
| 数据模型 | `backend/app/models/*.py` |
| API 路由 | `backend/app/api/*.py` |
| 业务逻辑 | `backend/app/services/*.py` |
| 种子数据 | `backend/app/seed_data/*.py` |
| 种子导入逻辑 | `backend/app/seed.py` |
| 爬虫骨架 | `backend/app/crawlers/*.py` |
| 前端 | `backend/app/web/index.html` |
| 依赖 | `backend/requirements.txt` |
| 数据库 | `backend/data/ccreward.db`（自动生成） |
| 原项目(印度/SG版) | `src/`（Next.js，未改造） |

## 十三、开发约定

1. **种子数据维护**：新增卡片/活动直接编辑 `app/seed_data/*.py`，重启后端自动 upsert
2. **新增模型字段**：改 `models/` 后需 `rm -f data/ccreward.db` 重建（原型阶段无 migration）
3. **新增 API**：在 `api/` 加路由 → `services/` 加业务逻辑 → `schemas/` 加契约 → `main.py` include_router
4. **新增爬虫**：继承 `BaseCrawler`，实现 `fetch()`，在 `scheduler.py` 注册
5. **代码风格**：函数名用语义化命名（如 `list_cards`、`compare_prices`），数据脚本用 Python