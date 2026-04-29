"""
智能电影推荐 - Flask 后端

核心流程：
用户输入 → 大模型判断 → 多数据源并行获取 → 大模型整合输出

关键改进：
- 不再"三选一"，多数据源可组合使用
- 评价查询时自动抓取真实观众评论
- LLM 基于全部可用数据综合回答
"""
import os
import logging
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 导入自定义模块
from ai_service import AIService
from crawler import DoubanMovieCrawler, normalize_movie_name
from search import MovieDataFetcher

app = Flask(__name__)
CORS(app)

# 配置
API_KEY = os.getenv("ARK_API_KEY")

# 初始化服务
ai_service = AIService(API_KEY)
movie_crawler = DoubanMovieCrawler()
data_fetcher = MovieDataFetcher()

# 会话存储
sessions = {}


def get_user_session(session_id):
    """获取或创建用户会话"""
    if session_id not in sessions:
        sessions[session_id] = {
            "history": [],
            "last_movie": None,
            "last_response": None,
        }
    return sessions[session_id]






@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    """处理用户对话请求 - 核心入口（v5 LLM 意图理解版）"""
    data = request.json
    message = data.get('message', '').strip()
    session_id = data.get('session_id', 'default')

    logger.info(f"\n{'='*60}")
    logger.info(f"【收到请求】: {message}")

    if not message:
        return jsonify({"error": "消息不能为空"})

    session = get_user_session(session_id)
    history = session.get('history', [])

    # LLM 一步完成意图识别 + 电影名提取（自然语言理解，不受标点/分词干扰）
    intent_info = ai_service.analyze_user_message(message, history)

    # 标准化电影名（用于本地匹配/豆瓣搜索）
    movie_name = intent_info.get("movie_name")
    norm_movie_name = normalize_movie_name(movie_name) if movie_name else None
    intent_info["movie_name"] = norm_movie_name

    logger.info(f"【最终意图】: intent={intent_info['intent']}, movie={norm_movie_name or movie_name}, data_type={intent_info.get('data_type')}")

    response = None
    combined_data = None

    if intent_info['intent'] == 'general' and not intent_info['needs_data']:
        # 纯闲聊，大模型直接回答
        logger.info("【流程】纯闲聊 → 大模型直接回答")
        response = ai_service.generate_response(message, history)
    else:
        # 需要数据 → 多数据源融合获取
        logger.info(f"【流程】数据融合模式: intent={intent_info['intent']}")
        combined_data = fetch_combined_data(intent_info, message)
        response = ai_service.generate_with_data(message, history, combined_data)

    # 更新会话历史
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": response})
    session['history'] = history[-20:]

    if intent_info["movie_name"]:
        session['last_movie'] = intent_info["movie_name"]

    session['last_response'] = response

    logger.info(f"【响应】完成, 数据来源: {combined_data.get('sources') if combined_data else '无'}")

    return jsonify({
        "response": response,
        "movie_data": combined_data,
        "query_understanding": intent_info,
        "timestamp": datetime.now().isoformat(),
    })


def _build_time_sensitive_query(search_keywords: str, user_message: str, genre: str = None) -> str:
    """构建时效性搜索关键词
    
    策略：
    1. 以 LLM 提取的 search_keywords 为基础
    2. 强制补充时效性词汇（2025-2026, 近期上映）
    3. 强制包含"电影"（避免搜到游戏等）
    4. 去重
    """
    current_year = datetime.now().year
    
    # 基础关键词
    parts = []
    
    if search_keywords:
        # 用 LLM 提取的关键词
        parts = search_keywords.split()
    
    # 强制补充时效性词汇
    time_words = ['最近', '近期', '最新', '今年', '新', '当前', '当下', '最近']
    has_time_word = any(w in user_message.lower() for w in time_words)
    has_year = any(str(y) in ' '.join(parts) for y in [current_year, current_year - 1])
    
    if has_time_word and not has_year:
        # 强制加年份
        parts.append(f"{current_year-1}-{current_year}")
    
    # 强制包含"近期上映"或"热映"
    hot_words = ['热门', '最火', '火', '热映', '排行', '票房', '流行']
    has_hot_word = any(w in user_message.lower() for w in hot_words)
    if has_hot_word:
        if '热映' not in ' '.join(parts):
            parts.append('热映')
        if '票房' not in ' '.join(parts) and '排行' not in ' '.join(parts):
            parts.append('票房')
    
    # 强制包含"电影"
    if '电影' not in ' '.join(parts):
        parts.append('电影')
    
    # 类型词
    if genre and genre not in ' '.join(parts):
        parts.append(genre)
    
    # 补充推荐词
    if '推荐' not in ' '.join(parts):
        parts.append('推荐')
    
    # 去重并组合
    seen = set()
    deduped = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            deduped.append(p)
    
    return ' '.join(deduped)


def fetch_combined_data(intent_info, user_message):
    """多数据源融合获取 - 核心改进：不再是三选一，而是按需组合

    融合策略：
    ┌─────────────────────────────────────────────────────────┐
    │ 意图类型          │ 使用的数据源                          │
    ├─────────────────────────────────────────────────────────┤
    │ 电影评分/评价     │ 本地DB + 豆瓣网页 + Bing影评(三源)    │
    │ 时效性+类型       │ Bing搜索 + 本地TOP250补充(双源)      │
    │ 纯时效性          │ Bing搜索(主) + 本地热门(辅)           │
    │ 类型推荐          │ 本地TOP250(主) + LLM知识              │
    │ 相似电影          │ 本地同类 + 联网搜索(双源)             │
    │ 通用/兜底         │ 本地TOP250热门                       │
    └─────────────────────────────────────────────────────────┘
    """
    data_type = intent_info.get("data_type")
    movie_name = intent_info.get("movie_name")
    intent = intent_info.get("intent")

    # 融合结果容器
    combined = {
        "sources": [],           # 使用了哪些数据源
        "movie_name": movie_name or "未知",
        "intent": intent,
        "rating": {},            # 多平台评分 {douban: x, maoyan: y}
        "summary": "",           # 本地电影摘要/列表
        "reviews": [],           # 真实观众评价（重点）
        "web_reviews": [],       # 网络搜索到的评论/资讯
        "similar": [],           # 相似电影
        "recommendations": [],   # 推荐列表
        "quote": "",             # 一句话评价
    }

    try:
        # ════════════════════════════════════════
        # 场景1: 电影评分/评价查询 → 三源融合
        # ════════════════════════════════════════
        if data_type == "douban_info" and movie_name:
            logger.info(f"【数据融合】评分/评价查询: '{movie_name}' → 三源融合")

            # 源1: 本地数据库
            local_data = movie_crawler.search_by_name(movie_name)
            if local_data:
                combined["sources"].append("local_db")
                combined["rating"]["douban"] = local_data.get("rating")
                combined["summary"] = movie_crawler.format_for_ai(local_data)
                combined["quote"] = local_data.get("quote", "")

            # 源2: 豆瓣网页（评分+真实评论）- 同时获取movie_url供后续复用
            douban_web = data_fetcher.fetch_douban_details(movie_name)
            douban_url = douban_web.get("movie_url")  # 复用此URL，避免重复搜索
            if douban_web.get("success"):
                combined["sources"].append("douban_web")
                if not combined["rating"].get("douban"):
                    combined["rating"]["douban"] = douban_web.get("rating")
                if douban_web.get("rating_count"):
                    combined["rating"]["douban_count"] = douban_web.get("rating_count")
                if douban_web.get("quote"):
                    combined["quote"] = douban_web["quote"]
                # 豆瓣真实评论（核心！）
                for rev in douban_web.get("reviews", []):
                    combined["reviews"].append({
                        "source": "豆瓣",
                        "text": rev.get("text", ""),
                        "rating": None,
                    })

            # 源3: Bing专项影评搜索（带电影过滤，避免搜到游戏等）
            bing_review_results = data_fetcher.search_movie_reviews(movie_name, max_results=6)
            for br in bing_review_results[:5]:
                # 额外过滤：标题和内容中不应包含明显的非电影关键词
                br_text = f"{br.get('title', '')} {br.get('content', '')}".lower()
                if any(kw in br_text for kw in ['游戏', '手游', '攻略', '小说', 'Steam']):
                    logger.info(f"[过滤] 影评中非电影内容: {br.get('title', '')[:30]}")
                    continue
                combined["web_reviews"].append({
                    "source": br.get("source", "网络"),
                    "title": br.get("title", ""),
                    "content": br.get("content", ""),
                })
            if bing_review_results:
                combined["sources"].append("bing_search")

            # 源4: 豆瓣短评（复用上面已找到的URL，避免重复搜索豆瓣）
            short_reviews = data_fetcher.fetch_douban_short_reviews(movie_name, movie_url=douban_url)
            for sr in short_reviews[:5]:
                combined["reviews"].append({
                    "source": sr.get("source", "豆瓣"),
                    "text": sr.get("text", ""),
                    "rating": sr.get("rating"),
                })

        # ════════════════════════════════════════
        # 场景2: 时效性+类型查询 → Bing为主 + 豆瓣热映 + 本地辅助
        # ════════════════════════════════════════
        elif data_type and data_type.endswith("_realtime"):
            genre = data_type.replace("_realtime", "")
            logger.info(f"【数据融合】时效性{genre or ''}查询 → Bing+豆瓣热映+本地辅助")

            search_keywords = intent_info.get("search_keywords")
            search_query = _build_time_sensitive_query(search_keywords, user_message, genre)
            
            logger.info(f"【搜索关键词】: {search_query}")
            
            # 源1: Bing联网搜索（主，带电影过滤）
            bing_results = data_fetcher.search_bing_for_movies(search_query, max_results=8)
            for r in bing_results[:8]:
                combined["web_reviews"].append({
                    "source": r.get("source", "Bing"),
                    "title": r.get("title"),
                    "content": r.get("snippet", ""),
                })
            if bing_results:
                combined["sources"].append("bing_search")

            # 源2: 豆瓣正在热映（增强近期数据权威性）
            recent_hot = data_fetcher.fetch_douban_recent_hot(max_movies=8)
            if recent_hot:
                combined["sources"].append("douban_hot")
                for m in recent_hot:
                    combined["recommendations"].append({
                        "title": m.get("title", ""),
                        "rating": m.get("rating"),
                        "genre": m.get("genre", ""),
                        "year": m.get("year", ""),
                    })
                hot_summary = "、".join([f"《{m['title']}》" for m in recent_hot[:8]])
                combined["summary"] += f"\n【豆瓣正在热映】{hot_summary}"

            # 源3: 本地同类型高分片（仅作为辅助补充，明确标注非近期）
            if genre and (not bing_results or len(bing_results) < 3):
                local_recs = data_fetcher.get_local_recommendations(genre=genre, limit=5)
                if local_recs.get("movies"):
                    combined["sources"].append("local_db_supplement")
                    combined["recommendations"].extend(local_recs["movies"])
                    combined["summary"] += f"\n\n【⚠️ 同类型经典参考 - 非近期影片】\n{local_recs['summary'][:300]}"

        # ════════════════════════════════════════
        # 场景3: 纯时效性/新片 → Bing为主 + 豆瓣热映 + 本地辅助
        # ════════════════════════════════════════
        elif data_type == "web_search":
            logger.info(f"【数据融合】纯时效性查询 → Bing+豆瓣热映+本地辅助")

            search_keywords = intent_info.get("search_keywords")
            search_query = _build_time_sensitive_query(search_keywords, user_message)
            
            logger.info(f"【搜索关键词】: {search_query}")
            
            # 源1: Bing联网搜索（主，带电影过滤）
            bing_results = data_fetcher.search_bing_for_movies(search_query, max_results=8)
            for r in bing_results[:8]:
                combined["web_reviews"].append({
                    "source": r.get("source", "Bing"),
                    "title": r.get("title"),
                    "content": r.get("snippet", ""),
                })
            if bing_results:
                combined["sources"].append("bing_search")

            # 源2: 豆瓣正在热映（近期权威数据）
            recent_hot = data_fetcher.fetch_douban_recent_hot(max_movies=8)
            if recent_hot:
                combined["sources"].append("douban_hot")
                for m in recent_hot:
                    combined["recommendations"].append({
                        "title": m.get("title", ""),
                        "rating": m.get("rating"),
                        "genre": m.get("genre", ""),
                        "year": m.get("year", ""),
                    })
                hot_summary = "、".join([f"《{m['title']}》" for m in recent_hot[:8]])
                combined["summary"] += f"\n【豆瓣正在热映】{hot_summary}"

            # 源3: 本地热门（仅当 Bing 无有效结果时才补充，明确标注非近期）
            if not bing_results or len(bing_results) < 2:
                top_movies = movie_crawler.get_top_rated(5)
                if top_movies:
                    combined["sources"].append("local_db_supplement")
                    combined["recommendations"].extend([
                        {"title": m.get("title"), "rating": m.get("rating"), "genre": m.get("genre"), "year": m.get("year", "")}
                        for m in top_movies
                    ])
                    combined["summary"] += "\n\n【⚠️ 经典高分参考 - 非近期影片】\n" + "\n".join(
                        [f"{i}. 《{m.get('title')}》- {m.get('rating')}分 ({m.get('year', '')}年)" for i, m in enumerate(top_movies, 1)]
                    )

        # ════════════════════════════════════════
        # 场景4: 类型推荐 → 本地主 + 可选联网补充
        # ════════════════════════════════════════
        elif data_type and "_recommend" in data_type:
            genre = data_type.replace("_recommend", "") if data_type != "local_recommend" else None
            logger.info(f"【数据融合】{' '+genre+'类型' if genre else ''}推荐 → 本地TOP250")

            # 源1: 本地筛选
            local_recs = data_fetcher.get_local_recommendations(genre=genre, limit=12)
            combined["sources"].append("local_db")
            combined["recommendations"] = local_recs.get("movies", [])
            combined["summary"] = local_recs.get("summary", "")
            combined["similar"] = local_recs.get("similar", [])
            if local_recs.get("rating", {}).get("douban"):
                combined["rating"]["douban"] = local_recs["rating"]["douban"]

            # 源2: 如果是具体类型推荐，也搜一下最新动态作为补充
            if genre:
                current_year = datetime.now().year
                extra_query = f"{current_year-1}-{current_year} {genre}电影 新片 评价 推荐"
                extra_results = data_fetcher.search_bing_for_movies(extra_query, max_results=3)
                for r in extra_results[:3]:
                    if r.get("snippet"):
                        combined["web_reviews"].append({
                            "source": r.get("source", "网络"),
                            "title": r.get("title"),
                            "content": r.get("snippet", ""),
                        })
                if extra_results:
                    combined["sources"].append("bing_search")

        # ════════════════════════════════════════
        # 场景5: 相似电影 → 双源
        # ════════════════════════════════════════
        elif data_type == "similar_movies" and movie_name:
            logger.info(f"【数据融合】相似电影: '{movie_name}' → 本地+联网")

            # 源1: 本地同类
            local_data = movie_crawler.search_by_name(movie_name)
            if local_data:
                combined["sources"].append("local_db")
                genre = local_data.get("genre", "")
                similar_local = movie_crawler.search_by_genre(genre)[:8]
                combined["similar"] = [
                    {"title": m.get("title"), "snippet": f"评分 {m.get('rating')} | {m.get('genre')}"}
                    for m in similar_local if m.get("title") != movie_name
                ]

            # 源2: 联网搜索（《》强制标题语义，防止电影名被拆分）
            search_query = f'类似 《{movie_name}》 的电影推荐'
            bing_results = data_fetcher.search_bing_for_movies(search_query, max_results=5)
            for r in bing_results[:5]:
                if r.get("snippet"):
                    combined["web_reviews"].append({
                        "source": r.get("source", "网络"),
                        "title": r.get("title"),
                        "content": r.get("snippet", ""),
                    })
            if bing_results:
                combined["sources"].append("bing_search")

        # ════════════════════════════════════════
        # 兜底: 返回本地热门
        # ════════════════════════════════════════
        if not combined["sources"]:
            top_movies = movie_crawler.get_top_rated(10)
            if top_movies:
                combined["sources"].append("local_db")
                movies_list = []
                for i, m in enumerate(top_movies, 1):
                    movies_list.append(f"{i}. 《{m.get('title')}》- {m.get('rating')}分 | {m.get('genre')} | {m.get('year')}")
                combined["summary"] = "【豆瓣高分电影推荐】\n" + "\n".join(movies_list)
                combined["similar"] = [{"title": m.get("title"), "snippet": f"{m.get('rating')}分"} for m in top_movies[:8]]
                combined["recommendations"] = [{"title": m.get("title"), "rating": m.get("rating")} for m in top_movies[:10]]

    except Exception as e:
        logger.error(f"【数据获取失败】: {e}")

    # 标记是否包含真实评价（供前端判断是否展示评价面板）
    combined["has_reviews"] = len(combined.get("reviews", [])) > 0 or len(combined.get("web_reviews", [])) > 0

    logger.info(f"【融合结果】数据源: {combined['sources']}, 评价数: {len(combined['reviews'])}, 网络信息数: {len(combined['web_reviews'])}")

    return combined


# ==================== API 接口 ====================

@app.route('/api/movie/search', methods=['GET'])
def search_movie():
    """搜索本地电影数据库"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"error": "查询不能为空"})
    
    try:
        result = movie_crawler.search_by_name(query)
        if result:
            return jsonify({"movie": result})
        else:
            return jsonify({"movie": None, "message": "未找到该电影"})
    except Exception as e:
        logger.error(f"电影搜索出错: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/movie/top', methods=['GET'])
def get_top_movies():
    """获取豆瓣TOP250"""
    limit = request.args.get('limit', 20, type=int)
    try:
        top_movies = movie_crawler.get_top_rated(limit)
        return jsonify({"movies": top_movies})
    except Exception as e:
        logger.error(f"获取TOP电影出错: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/session/history', methods=['GET'])
def get_session_history():
    """获取会话历史"""
    session_id = request.args.get('session_id', 'default')
    session = get_user_session(session_id)
    return jsonify({
        "history": session.get('history', []),
        "last_movie": session.get('last_movie')
    })


@app.route('/api/session/clear', methods=['POST'])
def clear_session():
    """清除会话"""
    data = request.json or {}
    session_id = data.get('session_id', 'default')
    sessions[session_id] = {"history": [], "last_movie": None, "last_response": None}
    return jsonify({"success": True})


if __name__ == '__main__':
    print("=" * 60)
    print("智能电影推荐系统 启动中...")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)
