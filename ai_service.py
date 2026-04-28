"""
通义千问 AI 服务模块
支持多轮对话、意图识别、电影推荐
"""
import dashscope
from dashscope import Generation
from typing import List, Dict, Any, Optional
import json
import re


class AIService:
    """通义千问 AI 服务类"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        dashscope.api_key = api_key
        self.model = "qwen-plus"
        
        # 电影推荐系统提示词
        self.system_prompt = """你是一个专业的电影推荐助手，名叫"小影"。你的职责是：

1. **多轮对话**: 与用户进行自然、友好的多轮对话，了解他们的电影偏好
2. **电影推荐**: 根据用户的兴趣、口味、观看历史推荐合适的电影
3. **信息查询**: 帮助用户了解电影的基本信息（导演、演员、类型等）
4. **评价分析**: 解读电影的口碑、观众评价，分析优缺点

**对话风格要求**:
- 亲切友好，像朋友聊天一样
- 主动询问用户的观影偏好
- 推荐时给出简短的理由
- 如果用户提到具体电影，可以深入讨论

**推荐策略**:
- 先了解用户的喜好（类型、演员、导演等）
- 根据用户描述的偏好进行个性化推荐
- 推荐时说明推荐理由
- 可以推荐类似风格的电影

记住：你是一个热情专业的电影顾问，帮助用户找到他们会喜欢的电影！"""
    
    def chat(self, message: str, history: List[Dict[str, str]] = None) -> str:
        """
        多轮对话
        Args:
            message: 用户当前消息
            history: 对话历史 [(role, content), ...]
        Returns:
            AI 回复文本
        """
        messages = [{"role": "system", "content": self.system_prompt}]
        
        if history:
            for item in history:
                messages.append({
                    "role": item.get("role", "user"),
                    "content": item.get("content", "")
                })
        
        messages.append({"role": "user", "content": message})
        
        try:
            response = Generation.call(
                model=self.model,
                messages=messages,
                temperature=0.7,
                top_p=0.8,
                max_tokens=2000,
                result_format='message'
            )
            
            if response.status_code == 200:
                return response.output.choices[0].message.content
            else:
                return f"抱歉，服务出现了一点问题，请稍后再试。(错误码: {response.code})"
                
        except Exception as e:
            return f"抱歉，发生了错误：{str(e)}"
    
    def extract_movie_names(self, text: str) -> List[str]:
        """从文本中提取电影名称"""
        # 常见电影名称模式
        patterns = [
            r'《([^》]+)》',  # 《电影名》
            r'"([^"]+)"',      # "电影名"
            r'《([^》]+)》',
        ]
        
        movies = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            movies.extend(matches)
        
        return list(set(movies))
    
    def is_movie_query(self, text: str) -> bool:
        """判断是否为电影相关查询"""
        movie_keywords = [
            '电影', '看什么', '推荐', '评分', '好看', '评价',
            '导演', '演员', '上映', '票房', '影评', '观后感',
            '科幻', '喜剧', '动作', '爱情', '悬疑', '恐怖',
            '剧情', '动画', '纪录片'
        ]
        
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in movie_keywords)
    
    def generate_recommendation_reason(self, movie_name: str, preferences: List[str]) -> str:
        """生成推荐理由"""
        messages = [
            {"role": "system", "content": "你是一个专业的电影推荐助手，根据用户偏好为电影生成简短推荐理由（50字以内）。"},
            {"role": "user", "content": f"用户偏好: {', '.join(preferences)}\n电影: {movie_name}\n请生成一句简短的推荐理由:"}
        ]
        
        try:
            response = Generation.call(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=100,
                result_format='message'
            )
            
            if response.status_code == 200:
                return response.output.choices[0].message.content.strip()
            else:
                return "这部电影值得一看！"
        except:
            return "这部电影值得一看！"
    
    def analyze_review_sentiment(self, reviews: List[Dict]) -> Dict[str, Any]:
        """分析评论情感"""
        positive = 0
        negative = 0
        neutral = 0
        
        for review in reviews:
            rating = review.get('rating', 0)
            if rating >= 4:
                positive += 1
            elif rating <= 2:
                negative += 1
            else:
                neutral += 1
        
        total = len(reviews) if reviews else 1
        return {
            "positive_rate": round(positive / total * 100, 1),
            "negative_rate": round(negative / total * 100, 1),
            "neutral_rate": round(neutral / total * 100, 1),
            "summary": self._generate_sentiment_summary(positive, negative, neutral)
        }
    
    def _generate_sentiment_summary(self, positive: int, negative: int, neutral: int) -> str:
        """生成情感总结"""
        if positive > negative * 2:
            return "观众口碑极佳，绝大多数观众给予好评"
        elif positive > negative:
            return "观众口碑较好，好评略多于差评"
        elif negative > positive:
            return "口碑两极分化，负面评价较多"
        elif neutral > positive + negative:
            return "口碑中规中矩，观众反应平淡"
        else:
            return "口碑一般，正负评价相当"
    
    def format_movie_info_for_display(self, movie_info: Dict) -> str:
        """格式化电影信息为可读文本"""
        lines = []
        
        lines.append(f"📽️ **{movie_info.get('title', '未知电影')}**")
        lines.append("")
        
        if movie_info.get('ratings'):
            ratings = movie_info['ratings']
            rating_strs = []
            if 'douban' in ratings:
                rating_strs.append(f"豆瓣 {ratings['douban']}")
            if 'maoyan' in ratings:
                rating_strs.append(f"猫眼 {ratings['maoyan']}")
            if 'imdb' in ratings:
                rating_strs.append(f"IMDB {ratings['imdb']}")
            if rating_strs:
                lines.append(f"⭐ 评分: {', '.join(rating_strs)}")
        
        if movie_info.get('pros'):
            lines.append(f"✅ 好评关键词: {', '.join(movie_info['pros'][:5])}")
        
        if movie_info.get('cons'):
            lines.append(f"❌ 差评关键词: {', '.join(movie_info['cons'][:5])}")
        
        if movie_info.get('reviews') and len(movie_info['reviews']) > 0:
            lines.append("")
            lines.append("📝 部分观众评价:")
            for i, review in enumerate(movie_info['reviews'][:3], 1):
                content = review.get('content', '')[:100]
                rating = review.get('rating', 0)
                rating_star = '⭐' * rating if rating > 0 else ''
                lines.append(f"  {i}. {content}... {rating_star}")
        
        return '\n'.join(lines)


# 示例用法
if __name__ == "__main__":
    api_key = "sk-68d30fbc67204755b10941e5760db31d"
    ai = AIService(api_key)
    
    # 测试对话
    response = ai.chat("我想看一部科幻电影，有什么推荐吗？")
    print(response)
