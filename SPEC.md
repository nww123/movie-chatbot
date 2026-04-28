# 智能电影推荐 Agent - 项目规范

## 1. 项目概述

**项目名称**: Smart Movie Recommender (智能电影推荐 Agent)  
**项目类型**: 全栈 AI 应用（Python 后端 + HTML 前端）  
**核心功能**: 基于通义千问大模型的多轮对话式电影推荐系统，支持联网搜索电影评分、爬取真实观众评价、分析满意点/槽点、智能推荐电影  
**目标用户**: 电影爱好者，需要选片参考的用户

## 2. 技术架构

### 后端 (Python)
- **框架**: Flask
- **AI 模型**: 通义千问 qwen-plus (API)
- **爬虫**: requests + BeautifulSoup (豆瓣、猫眼)
- **搜索**: DuckDuckGo 搜索电影评分

### 前端 (HTML)
- **UI 框架**: Tailwind CSS
- **交互**: 原生 JavaScript
- **实时通信**: Server-Sent Events (SSE)

## 3. 功能模块

### 3.1 多轮对话系统
- 支持自然语言多轮对话
- 记忆上下文，理解用户意图
- 智能追问获取偏好信息

### 3.2 电影数据获取
- **评分获取**: 联网搜索获取豆瓣、猫眼、IMDB 评分
- **观众评价爬取**: 
  - 豆瓣电影短评
  - 猫眼电影评论
- **数据清洗**: 提取评价关键词、情感分析

### 3.3 智能分析
- 满意点分析 (提取正面评价关键词)
- 槽点分析 (提取负面评价关键词)
- 综合评分解读

### 3.4 电影推荐
- 基于用户兴趣标签推荐
- 相似电影推荐
- 热门/高分电影推荐

## 4. API 设计

### 4.1 对话接口
```
POST /api/chat
Request: { "message": "string", "history": [] }
Response: SSE stream
```

### 4.2 电影搜索接口
```
GET /api/movie/search?query=电影名
Response: { movies: [], ratings: {} }
```

### 4.3 电影详情接口
```
GET /api/movie/detail?title=电影名
Response: { title, ratings, reviews: [], pros: [], cons: [] }
```

### 4.4 推荐接口
```
POST /api/recommend
Request: { "preferences": [] }
Response: { movies: [] }
```

## 5. 界面设计

### 5.1 整体风格
- 暗色主题 (电影院氛围)
- 卡片式布局展示电影信息
- 流畅的对话式交互

### 5.2 主要页面
1. **主聊天界面**: 对话区 + 电影展示区
2. **电影卡片**: 海报、评分、评价摘要
3. **评价详情**: 真实观众评价列表

### 5.3 颜色方案
- 主色: #E50914 (Netflix 红)
- 背景: #141414 (深灰黑)
- 卡片: #1F1F1F
- 文字: #FFFFFF / #B3B3B3
- 强调: #FFD700 (评分金色)

## 6. 数据结构

### 6.1 电影信息
```python
{
    "title": str,
    "poster": str,
    "year": int,
    "director": str,
    "actors": list,
    "genre": list,
    "ratings": {
        "douban": float,
        "maoyan": float,
        "imdb": float
    },
    "reviews": [
        {"platform": str, "content": str, "rating": int, "author": str}
    ],
    "pros": ["看点1", "看点2"],
    "cons": ["槽点1", "槽点2"]
}
```

### 6.2 对话历史
```python
[
    {"role": "user", "content": str},
    {"role": "assistant", "content": str}
]
```

## 7. 错误处理
- API 调用失败: 返回友好提示 + 降级策略
- 爬虫失败: 使用缓存数据或搜索结果
- 网络超时: 重试机制 (3次)

## 8. 部署说明
- 后端运行: `python app.py`
- 前端访问: `http://localhost:5000`
- 依赖安装: `pip install -r requirements.txt`
