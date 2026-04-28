# 智能电影推荐 Agent

基于通义千问大模型的多轮对话式电影推荐系统

## 功能特性

- 🎯 **智能推荐**: 根据用户偏好推荐电影
- ⭐ **全网评分**: 搜索豆瓣、猫眼、IMDB等平台评分
- 📝 **真实评价**: 爬取观众真实评价
- ✅❌ **优缺点分析**: 自动分析满意点和槽点
- 💬 **多轮对话**: 支持上下文理解的对话交互

## 技术栈

- **后端**: Python + Flask
- **AI**: 通义千问 qwen-plus
- **爬虫**: requests + BeautifulSoup
- **搜索**: DuckDuckGo
- **前端**: HTML + Tailwind CSS

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python app.py
```

### 3. 访问应用

打开浏览器访问: http://localhost:5000

## 项目结构

```
├── app.py              # Flask 主应用
├── ai_service.py       # AI 服务模块
├── crawler.py          # 电影数据爬虫
├── search.py           # 联网搜索模块
├── requirements.txt    # 依赖列表
├── templates/
│   └── index.html      # 前端页面
└── SPEC.md             # 项目规范
```

## 使用示例

- "我想看科幻片，有什么推荐吗？"
- "《流浪地球2》评分怎么样？"
- "帮我找评分高的喜剧片"
- "最近有什么热门电影？"
