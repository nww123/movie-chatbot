"""
智能电影推荐 Agent - Flask 后端
"""
import os
import re
import json
import threading
from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
from datetime import datetime

# 导入自定义模块
from ai_service import AIService
from crawler import MovieCrawler
from search import MovieSearcher

app = Flask(__name__)
CORS(app)

# 配置
API_KEY  = os.getenv("DASHSCOPE_API_KEY")
if not API_KEY:
    raise RuntimeError("请先配置环境变量 DASHSCOPE_API_KEY")

# 初始化服务
ai_service = AIService(API_KEY)
movie_crawler = MovieCrawler()
movie_searcher = MovieSearcher()

# 会话存储 (生产环境应使用 Redis)
sessions = {}


def get_user_session(session_id):
    """获取或创建用户会话"""
    if session_id not in sessions:
        sessions[session_id] = {
            "history": [],
            "preferences": [],
            "last_movie": None
        }
    return sessions[session_id]


def extract_movie_from_text(text):
    """从文本中提取电影名称"""
    patterns = [
        r'《([^》]+)》',
        r'"([^"]+)"',
        r'《([^》]+)》',
    ]
    
    movies = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        movies.extend(matches)
    
    return list(set(movies))


def should_fetch_movie_data(text):
    """判断是否需要获取电影数据"""
    keywords = [
        '评分', '评价', '影评', '评论', '怎么样', '好看吗',
        '观众', '口碑', '优缺点', '推荐', '想看'
    ]
    text_lower = text.lower()
    return any(k in text_lower for k in keywords)


@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    """处理用户对话请求"""
    data = request.json
    message = data.get('message', '').strip()
    session_id = data.get('session_id', 'default')
    
    if not message:
        return jsonify({"error": "消息不能为空"})
    
    session = get_user_session(session_id)
    history = session.get('history', [])
    
    # 提取提及的电影
    mentioned_movies = extract_movie_from_text(message)
    
    # 检查是否需要获取电影数据
    movie_data_response = None
    if mentioned_movies and should_fetch_movie_data(message):
        try:
            movie_name = mentioned_movies[0]
            session['last_movie'] = movie_name
            
            # 并行获取数据
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                crawler_future = executor.submit(movie_crawler.get_full_movie_info, movie_name)
                search_future = executor.submit(movie_searcher.get_comprehensive_movie_info, movie_name)
                
                crawler_result = crawler_future.result()
                search_result = search_future.result()
            
            # 合并数据
            movie_data_response = {
                "movie_name": movie_name,
                "ratings": crawler_result.get('ratings', {}) or search_result.get('ratings', {}),
                "reviews": crawler_result.get('reviews', []) or search_result.get('reviews', []),
                "pros": crawler_result.get('pros', []),
                "cons": crawler_result.get('cons', []),
                "summary": search_result.get('summary', ''),
                "similar": search_result.get('similar', [])
            }
            
            # 添加上下文信息
            if movie_data_response['ratings']:
                rating_str = []
                if 'douban' in movie_data_response['ratings']:
                    rating_str.append(f"豆瓣{movie_data_response['ratings']['douban']}")
                if 'maoyan' in movie_data_response['ratings']:
                    rating_str.append(f"猫眼{movie_data_response['ratings']['maoyan']}")
                if 'imdb' in movie_data_response['ratings']:
                    rating_str.append(f"IMDB{movie_data_response['ratings']['imdb']}")
                
                context_info = f"\n\n补充信息：{movie_name} 的评分数据——{' / '.join(rating_str)}"
                if movie_data_response['pros']:
                    context_info += f"\n好评关键词：{', '.join(movie_data_response['pros'][:5])}"
                if movie_data_response['cons']:
                    context_info += f"\n差评关键词：{', '.join(movie_data_response['cons'][:5])}"
                message += context_info
            
        except Exception as e:
            print(f"获取电影数据出错: {e}")
    
    # 调用 AI
    try:
        response = ai_service.chat(message, history)
        
        # 更新历史
        history.append({"role": "user", "content": data.get('message', '')})
        history.append({"role": "assistant", "content": response})
        session['history'] = history[-20:]  # 保留最近20条
        
        result = {
            "response": response,
            "movie_data": movie_data_response,
            "timestamp": datetime.now().isoformat()
        }
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/movie/search', methods=['GET'])
def search_movie():
    """搜索电影"""
    query = request.args.get('query', '').strip()
    
    if not query:
        return jsonify({"error": "搜索词不能为空"})
    
    try:
        result = movie_searcher.get_comprehensive_movie_info(query)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/movie/detail', methods=['GET'])
def movie_detail():
    """获取电影详情"""
    title = request.args.get('title', '').strip()
    
    if not title:
        return jsonify({"error": "电影名称不能为空"})
    
    try:
        # 并行获取数据
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            crawler_future = executor.submit(movie_crawler.get_full_movie_info, title)
            search_future = executor.submit(movie_searcher.get_comprehensive_movie_info, title)
            
            crawler_result = crawler_future.result()
            search_result = search_future.result()
        
        # 合并结果
        result = {
            "title": title,
            "ratings": crawler_result.get('ratings', {}) or search_result.get('ratings', {}),
            "reviews": crawler_result.get('reviews', []) or [],
            "pros": crawler_result.get('pros', []),
            "cons": crawler_result.get('cons', []),
            "summary": search_result.get('summary', ''),
            "similar": search_result.get('similar', [])
        }
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/recommend', methods=['POST'])
def recommend():
    """电影推荐"""
    data = request.json
    preferences = data.get('preferences', [])
    session_id = data.get('session_id', 'default')
    
    session = get_user_session(session_id)
    
    try:
        # 根据偏好生成推荐请求
        pref_text = "、".join(preferences) if preferences else ""
        prompt = f"请根据我的偏好推荐电影。偏好：{pref_text}。请给出3-5部电影推荐，包括电影名称和简短推荐理由。"
        
        response = ai_service.chat(prompt, session.get('history', []))
        
        return jsonify({
            "recommendations": response,
            "preferences": preferences
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/hot', methods=['GET'])
def hot_movies():
    """获取热门电影"""
    category = request.args.get('category', '最新')
    
    try:
        movies = movie_searcher.search_hot_movies(category)
        return jsonify({"movies": movies})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/session/clear', methods=['POST'])
def clear_session():
    """清除会话"""
    data = request.json
    session_id = data.get('session_id', 'default')
    
    if session_id in sessions:
        sessions[session_id] = {
            "history": [],
            "preferences": [],
            "last_movie": None
        }
    
    return jsonify({"success": True})


@app.route('/api/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


if __name__ == '__main__':
    # 读取 Railway 分配的端口，本地开发默认用 5000
    port = int(os.getenv("PORT", 5000))
    # 关闭 debug，禁用重载器，绑定 0.0.0.0
    app.run(
        debug=False,
        host='0.0.0.0',
        port=port,
        use_reloader=False
    )
