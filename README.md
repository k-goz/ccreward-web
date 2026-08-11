# ccreward-cn 后端服务

国内信用卡权益与商家活动聚合 API，基于 FastAPI + SQLite + Playwright 爬虫。

## 快速开始

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

启动后访问：
- 前端界面：http://localhost:8000
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/health

## 核心功能

| 功能 | API | 说明 |
|------|-----|------|
| 查询卡片列表 | `GET /api/cards` | 获取所有信用卡及权益 |
| 查询卡片详情 | `GET /api/cards/{id}` | 单卡权益详情 |
| 积分兑换商品 | `GET /api/cards/{id}/redemptions` | 该卡积分可兑换的商品 |
| 用户卡片 | `GET /api/cards/user/{user_id}` | 用户持有的卡片及权益 |
| 搜索活动 | `GET /api/activities?keyword=瑞幸咖啡` | 搜索商家活动 |
| 多平台比价 | `GET /api/activities/compare?keyword=瑞幸咖啡` | 同一商品多平台比价 |

## 项目结构

```
backend/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置
│   ├── database.py          # 数据库
│   ├── seed.py              # 种子数据
│   ├── models/              # 数据模型（卡片、权益、活动、兑换）
│   ├── schemas/             # Pydantic 契约
│   ├── api/                 # API 路由
│   ├── services/            # 业务逻辑
│   ├── crawlers/            # 爬虫（骨架 + 调度器）
│   └── web/                 # 轻量前端
└── data/                    # SQLite 数据库（自动生成）
```

## 爬虫说明

爬虫目前为骨架实现（`app/crawlers/douyin.py`），演示接入方式但未执行真实爬取。
生产环境需：
1. `playwright install chromium` 安装浏览器
2. 配置代理池和登录态
3. 实现具体页面的解析逻辑
4. 注意遵守目标网站 robots.txt 和法律法规