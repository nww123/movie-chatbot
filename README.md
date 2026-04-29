# 🎬 智能电影推荐Bot

基于大模型的多轮对话式电影推荐系统，融合多数据源（Bing 联网搜索 + 豆瓣电影 + 本地数据库），提供智能推荐与真实评价分析。

## 功能特性

- 🎯 **智能推荐** — 根据类型、偏好推荐电影
- 🔥 **时效搜索** — 联网搜索近期热映、票房排行
- ⭐ **多源评分** — 豆瓣 / IMDb 等多平台评分融合
- 📝 **真实评价** — 抓取豆瓣观众短评与影评
- 💬 **多轮对话** — 上下文理解，自然交互

## 技术栈

- **后端**: Python 3.12 + Flask
- **AI**: 火山引擎 Doubao（OpenAI 兼容接口）
- **搜索**: Bing 联网搜索 + 电影相关性过滤
- **数据**: 豆瓣 TOP250 本地 + 实时网页抓取
- **前端**: HTML + Tailwind CSS

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入 ARK_API_KEY
```

### 3. 启动服务

```bash
# 开发模式
python app.py

# 生产模式
gunicorn app:app --host 0.0.0.0 --port 5000
```

### 4. 访问应用

浏览器打开 http://localhost:5000

## 项目结构

```
├── app.py              # Flask 主应用 & 数据融合逻辑
├── ai_service.py       # AI 服务（意图分析 + 生成回答）
├── crawler.py          # 豆瓣电影爬虫 & 本地数据
├── search.py           # Bing 搜索 + 豆瓣网页抓取
├── templates/
│   └── index.html      # 前端页面
├── requirements.txt    # Python 依赖
├── Procfile            # Railway 部署入口
├── runtime.txt         # Python 版本锁定
└── .env.example        # 环境变量模板
```


## 环境变量

| 变量名 | 说明 | 必需 |
|--------|------|------|
| `ARK_API_KEY` | 火山引擎 ARK API Key | ✅ |
| `PORT` | 服务端口（Railway 自动注入） | ❌ |
