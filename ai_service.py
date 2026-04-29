"""
AI 服务模块 v5（多数据源融合版）:

核心功能：
1. 判断用户问题是否需要外部数据
2. 基于多源融合数据生成最终回答:

原则：诚实回答，不编造信息；综合多源信息，自然融合输出
"""
import os
import json
import re
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)


# ==================== 系统提示词 ====================

SYSTEM_PROMPT = """你是一个专业的电影推荐助手，名叫"小影"。

【核心原则 - 实事求是】：
✅ 优先使用提供的搜索数据来回答问题
✅ 如果提供了数据，必须基于数据回答，禁止说"不知道"或"没有信息"
❌ 禁止编造评分、上映日期、演员等具体信息
❌ 禁止猜测或估计你不知道的数据

【你的能力】：
1. 多轮对话：像朋友一样自然聊天
2. 电影推荐：根据用户喜好推荐合适的电影
3. 信息查询：基于提供的数据回答问题
4. 评价分析：解读观众评价，分析优缺点

【回答风格】：
- 亲切友好
- 推荐时给出理由
- 当提供了搜索结果时，必须使用这些结果来回答"""

# LLM 意图分析提示词
ANALYZE_PROMPT = """分析用户关于电影的消息，提取关键信息。只返回一个JSON对象，不要任何其他文字。

{history_hint}用户消息: {message}

返回JSON示例:
{{
  "intent": "general | movie_info | recommend | realtime | similar",
  "movie_name": "电影名称或null",
  "genre": "类型如科幻/喜剧或null",
  "needs_data": true或false,
  "search_keywords": "搜索关键词，用于搜索引擎，必须包含电影类型词"
}}

规则:
- movie_info: 问某部电影的具体信息/评分/评价/剧情/演员
- recommend: 要求推荐电影
- realtime: 问最新/热门/新上映/近期/最近/今年/最火/票房
- similar: 找和某部电影类似的
- general: 闲聊/打招呼/电影知识讨论
- movie_name: 原样返回电影名，如"你好，李焕英"就返回"你好，李焕英"，不要去掉标点，没有则为null
- needs_data: 除纯闲聊外都需要数据
- search_keywords: 提取用于搜索引擎的关键词，**必须遵守以下规则**：
  1. **必须包含"电影"这个词**（避免搜索到游戏、小说等其他内容）
  2. 当用户问"最近/近期/最新/今年/当前"时，必须加上具体年份（如"2025-2026"）
  3. 当用户问"热门/最火/热映/排行/票房"时，必须加上"热映 票房"等词
  4. 用空格分隔关键词
  5. 示例："星际穿越 电影 评价"、"2025-2026 热映 票房 电影"、"2025-2026 喜剧 电影 推荐"
  6. 如无法提取则为null"""


class AIService:
    """AI 服务类"""
    
    def __init__(self, api_key: str, model: str = "ep-20260428182033-gwk8z"):
        self.api_key = api_key
        self.model = model
        
        if api_key:
            self.client = OpenAI(
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key=api_key,
            )
        else:
            self.client = None
    
    # ==================== LLM 意图分析 ====================

    def analyze_user_message(self, message: str, history: List[Dict] = None) -> Dict:
        """用 LLM 一步完成意图识别 + 电影名提取 + 是否需要数据判断

        优势：自然语言理解，不受标点/分词/错别字干扰。
        原流程需要正则提取 + 额外 LLM 判断（2步），现在合并为 1 次 LLM 调用。
        """
        if not self.client:
            return {"intent": "general", "movie_name": None, "needs_data": False,
                    "genre": None, "data_type": None, "search_keywords": None}

        history_hint = ""
        if history and len(history) >= 2:
            last_q = history[-2].get("content", "")[-80:]
            last_a = history[-1].get("content", "")[-80:]
            history_hint = f"上轮对话:\n用户: {last_q}\n助手: {last_a}\n\n"

        prompt = ANALYZE_PROMPT.format(message=message, history_hint=history_hint)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=150
            )
            content = response.choices[0].message.content.strip()
            # 清理可能的 markdown 代码块
            content = re.sub(r'^```json?\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
            content = content.strip()

            result = json.loads(content)

            intent = result.get("intent", "general")
            movie_name = result.get("movie_name")
            genre = result.get("genre")
            needs_data = result.get("needs_data", False)

            # 映射 intent → data_type（与原 extract_intent_and_entities 兼容）
            data_type = None
            if intent == "movie_info" and movie_name:
                data_type = "douban_info"
            elif intent == "recommend" and genre:
                data_type = f"{genre}_recommend"
            elif intent == "recommend":
                data_type = "local_recommend"
            elif intent == "realtime" and genre:
                data_type = f"{genre}_realtime"
            elif intent == "realtime":
                data_type = "web_search"
            elif intent == "similar" and movie_name:
                data_type = "similar_movies"

            search_keywords = result.get("search_keywords")
            logger.info(f"[LLM分析] intent={intent}, movie={movie_name}, genre={genre}, needs_data={needs_data}, search_keywords={search_keywords}")

            return {
                "intent": intent,
                "movie_name": movie_name,
                "genre": genre,
                "needs_data": needs_data,
                "data_type": data_type,
                "search_keywords": search_keywords,  # 关键：保留搜索关键词
            }

        except json.JSONDecodeError as e:
            logger.warning(f"[LLM分析] JSON解析失败: {e}, 原文: {content[:100]}")
        except Exception as e:
            logger.warning(f"[LLM分析] 调用失败: {e}")

        return {"intent": "general", "movie_name": None, "needs_data": False,
                "genre": None, "data_type": None, "search_keywords": None}
    
    # ==================== 直接回答 ====================
    
    def generate_response(self, message: str, history: List[Dict] = None) -> str:
        """
        直接生成回答（不需要额外数据）
        
        Args:
            message: 用户消息
            history: 对话历史
            
        Returns:
            生成的回答文本
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        # 添加历史
        if history:
            for item in history[-6:]:  # 最近3轮
                messages.append({
                    "role": item.get("role", "user"),
                    "content": item.get("content", "")[:500]
                })
        
        messages.append({"role": "user", "content": message})
        
        return self._call_api(messages, temperature=0.7)
    
    # ==================== 基于多源融合数据回答 ====================

    def generate_with_data(self, message: str, history: List[Dict] = None,
                          movie_data: Dict = None) -> str:
        """
        基于融合的多数据源生成回答（v5 - 多源融合版）

        关键改进：不再基于单一数据源，而是综合所有可用数据源，
                 让 LLM 像人类一样整合多方信息给出完整答案。
        """
        sources = movie_data.get('sources', [])
        source_labels = {
            'local_db': '本地豆瓣TOP250数据库',
            'douban_web': '豆瓣电影网页',
            'bing_search': 'Bing联网搜索',
            'fallback': '本地热门',
        }
        source_names = [source_labels.get(s, s) for s in sources]

        data_system = f"""{SYSTEM_PROMPT}

【重要 - 多源数据融合】你当前拥有来自多个数据源的**真实数据**，请像一位专业影评人一样，
将以下信息自然地融合在你的回答中：

━━━ 数据来源 ({len(sources)}个) ━━━
{' → '.join(source_names)}
━━━━━━━━━━━━━━━━━━━━━━━
"""

        # === 1. 评分信息（多平台）===
        ratings = movie_data.get('rating', {})
        if ratings:
            data_system += "\n【评分信息】:\n"
            for platform, value in ratings.items():
                if platform == 'douban_count':
                    data_system += f"  - 豆瓣评价人数: {value}人\n"
                else:
                    label = {'douban': '豆瓣', 'maoyan': '猫眼', 'imdb': 'IMDb'}.get(platform, platform)
                    data_system += f"  - {label}: {value}分\n"

        # === 2. 一句话评价/推荐语 ===
        quote = movie_data.get("quote")
        if quote:
            data_system += f"\n【推荐语】: \"{quote}\"\n"

        # === 3. 真实观众评价（核心重点！）===
        reviews = movie_data.get("reviews", [])
        if reviews:
            data_system += f"\n【真实观众评价 - 来自豆瓣等平台】({len(reviews)}条):\n"
            for i, rev in enumerate(reviews[:6], 1):
                text = rev.get("text", "")
                src = rev.get("source", "观众")
                rating_str = ""
                if rev.get("rating"):
                    rating_str = f" ⭐{rev['rating']}"
                data_system += f"  {i}. [{src}]{rating_str}: {text[:250]}\n"
            data_system += "  > 以上是真实观众的原始评价，请在回答中引用和解读这些观点\n"

        # === 4. 网络/搜索资讯 ===
        web_reviews = movie_data.get("web_reviews", [])
        if web_reviews:
            data_system += f"\n【网络资讯/更多评价 - 来自搜索结果】({len(web_reviews)}条):\n"
            for i, item in enumerate(web_reviews[:5], 1):
                content = item.get("content", "")
                title = item.get("title", "")
                src = item.get("source", "网络")
                data_system += f"  {i}. [{src}] {title}: {content[:200]}\n"

        # === 5. 电影列表 / 推荐摘要 ===
        summary = movie_data.get("summary", "")
        if summary:
            # 如果包含"非近期"标注，特别提醒LLM
            is_supplement = "非近期" in summary or "经典参考" in summary
            label = "【⚠️ 辅助参考 - 非近期影片，请勿当作近期热映推荐】" if is_supplement else "【参考电影列表】"
            data_system += f"\n{label}:\n{summary[:600]}\n"

        # === 6. 推荐电影详情 ===
        recommendations = movie_data.get("recommendations", [])
        if recommendations:
            data_system += "\n【推荐电影详情】:\n"
            for i, m in enumerate(recommendations[:8], 1):
                title = m.get("title", "未知")
                rating = m.get("rating", "?")
                genre = m.get("genre", "")
                year = m.get("year", "")
                detail = f"{rating}分"
                if genre:
                    detail += f" | {genre}"
                if year:
                    detail += f" | {year}年"
                data_system += f"  {i}. 《{title}》- {detail}\n"

        # === 7. 相似电影 ===
        similar = movie_data.get("similar", [])
        if similar:
            data_system += "\n【相关/相似电影】:\n"
            for i, m in enumerate(similar[:6], 1):
                title = m.get("title", "")
                snippet = m.get("snippet", "")
                data_system += f"  {i}. 《{title}》{f' - {snippet}' if snippet else ''}\n"

        # 最终指令：根据实际可用数据给出不同策略的输出要求
        has_real_reviews = len(reviews) > 0
        has_web_reviews = len(web_reviews) > 0

        if has_real_reviews:
            output_req = (
                "以上【真实观众评价】是观众原始观点，请在回答中引用并分析共识观点，"
                "总结观众喜爱和不喜爱的方面，给出平衡客观的评价。"
            )
        elif has_web_reviews:
            output_req = (
                "你必须基于【网络资讯/搜索结果】来回答，禁止说'没有信息'或'不知道'。"
                "这些搜索结果包含了有价值的信息，请提取其中的片名、评分、口碑等关键信息，"
                "整理成有条理的回答。如果搜索结果不够完整，也要尽力给出最有价值的部分。"
            )
        else:
            output_req = (
                "当前缺乏有效的评价数据，请结合你对该电影的了解（如导演、演员、题材、往期作品）"
                "给出客观分析，诚实说明数据有限的部分，侧重于常识性评价。"
            )

        data_system += f"""

【输出要求】：
1. 自然融合以上所有数据源的信息，不要生硬堆砌
2. {output_req}
3. 保持友好专业的语气，像一个懂电影的朋友在聊天
"""

        # 构建消息
        messages = [{"role": "system", "content": data_system}]

        if history:
            for item in history[-6:]:
                messages.append({
                    "role": item.get("role", "user"),
                    "content": item.get("content", "")[:500]
                })

        messages.append({"role": "user", "content": message})

        return self._call_api(messages, temperature=0.75)
    
    # ==================== API 调用 ====================
    
    def _call_api(self, messages: List[Dict], temperature: float = 0.7) -> str:
        """
        调用火山引擎 API
        """
        if not self.client:
            return "抱歉，AI服务未配置，请检查 API Key 设置"
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                top_p=0.8,
                max_tokens=2000
            )

            if response.choices:
                return response.choices[0].message.content
            else:
                return "抱歉，服务暂时不可用，请稍后再试。"

        except Exception as e:
            logging.getLogger(__name__).error(f"[API] 调用失败: {e}")
            return f"抱歉，发生了错误：{str(e)}"


# 测试
if __name__ == "__main__":
    api_key = os.getenv('ARK_API_KEY')
    ai = AIService(api_key)
    
    # 测试判断能力
    test_questions = [
        ("你好", True),
        ("流浪地球评分多少", False),
        ("推荐喜剧片", False),
        ("什么是科幻电影", True),
    ]
    
    print("=" * 60)
    print("测试：能否直接回答")
    print("=" * 60)
    
    for question, expected in test_questions:
        result = ai.can_answer_directly(question)
        status = "✓" if result == expected else "✗"
        print(f"{status} \"{question}\" → needs_data={not result} (预期: {not expected})")
