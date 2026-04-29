"""
电影数据获取模块 v4（多源融合增强版 + 搜索过滤）

功能：
1. Bing 联网搜索（唯一联网方案）+ 电影相关性过滤
2. 豆瓣电影详情获取（评分、评论、真实评价）
3. 豆瓣近期热门/正在热映抓取
4. 本地数据推荐筛选
5. 影评专项搜索（评价查询时补充多来源观点）

关键改进：
- search_bing_for_movies: 自动过滤非电影类搜索结果
- fetch_douban_recent_hot: 抓取豆瓣近期热门电影
- 所有时效性搜索强制附加"电影"关键词
"""
import re
import logging
import urllib.parse
from datetime import datetime
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import requests

from crawler import normalize_movie_name

# 搜索超时（秒）
TIMEOUT = 8

# 电影相关性关键词（用于过滤搜索结果）
MOVIE_POSITIVE_KEYWORDS = [
    '电影', '影片', '院线', '上映', '热映', '排片', '票房',
    '导演', '主演', '演员', '评分', '豆瓣', 'IMDb', 'imdb',
    '影评', '观后感', '预告', '海报', '档期', '首映',
    'film', 'movie', 'cinema', 'box office',
]

MOVIE_NEGATIVE_KEYWORDS = [
    '游戏', '手游', '端游', '攻略', '下载', '安装',
    '小说', '书籍', '电子书', '动漫', '番剧',
    '股票', '基金', '理财', '培训', '课程',
    'Steam', 'App', '安卓', 'iOS',
]

logger = logging.getLogger(__name__)


class MovieDataFetcher:
    """电影数据统一获取器"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.bing.com/',
        }
    
    # ==================== 搜索结果过滤 ====================
    
    def _is_movie_related(self, title: str, snippet: str) -> bool:
        """判断搜索结果是否与电影相关
        
        规则：
        1. 标题或摘要含电影正面词 → 通过
        2. 标题或摘要含负面词且无正面词 → 过滤
        3. 无任何特征词 → 通过（宽松，避免误杀）
        """
        text = f"{title} {snippet}".lower()
        
        has_positive = any(kw.lower() in text for kw in MOVIE_POSITIVE_KEYWORDS)
        has_negative = any(kw.lower() in text for kw in MOVIE_NEGATIVE_KEYWORDS)
        
        # 有负面词但没有正面词 → 过滤
        if has_negative and not has_positive:
            logger.info(f"[过滤] 非电影内容: {title[:40]}...")
            return False
        
        return True
    
    # ==================== Bing 搜索 ====================
    
    def search_bing(self, query: str, max_results: int = 8) -> List[Dict[str, Any]]:
        """
        使用 Bing 搜索（原始方法，不过滤）
        
        Args:
            query: 搜索关键词
            max_results: 最大结果数
            
        Returns:
            搜索结果列表 [{title, url, snippet, source}]
        """
        results = []
        
        try:
            url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
            
            response = requests.get(
                url,
                headers=self.headers,
                timeout=TIMEOUT,
                allow_redirects=True
            )
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for item in soup.find_all('li', class_='b_algo', limit=max_results * 2):
                try:
                    title_elem = item.find('h2')
                    link_elem = item.find('a')
                    snippet_elem = item.find('p')
                    
                    if title_elem and link_elem:
                        title = title_elem.get_text(strip=True)
                        href = link_elem.get('href', '')
                        snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''
                        
                        if href and not href.startswith('#'):
                            results.append({
                                'title': title,
                                'url': href,
                                'snippet': snippet,
                                'source': 'bing'
                            })
                            
                            if len(results) >= max_results:
                                break
                except Exception:
                    continue
            
            logger.info(f"[bing] 查询: {query[:30]}... → {len(results)} 条结果")
            
        except requests.exceptions.Timeout:
            logger.warning(f"[bing] 超时: {query[:30]}...")
        except Exception as e:
            logger.warning(f"[bing] 出错: {e}")
        
        return results
    
    def search_bing_for_movies(self, query: str, max_results: int = 8) -> List[Dict[str, Any]]:
        """
        Bing 搜索 + 电影相关性过滤
        
        自动过滤掉游戏、小说、股票等非电影内容。
        如果过滤后结果不足，补充原始结果（宽松策略避免空结果）。
        """
        # 先多搜一些，过滤后保留需要的数量
        raw_results = self.search_bing(query, max_results=max_results * 2)
        
        # 过滤
        filtered = []
        rejected = []
        for r in raw_results:
            if self._is_movie_related(r.get('title', ''), r.get('snippet', '')):
                filtered.append(r)
            else:
                rejected.append(r)
        
        # 如果过滤后不足，从被拒绝的中补充（避免过度过滤导致无结果）
        if len(filtered) < max_results // 2 and rejected:
            supplement = rejected[:max_results - len(filtered)]
            filtered.extend(supplement)
            logger.info(f"[过滤] 过滤后不足，补充 {len(supplement)} 条")
        
        logger.info(f"[过滤] 原始 {len(raw_results)} 条 → 过滤后 {len(filtered)} 条 (移除 {len(rejected)} 条非电影内容)")
        
        return filtered[:max_results]
    
    # ==================== 豆瓣近期热门 ====================
    
    def fetch_douban_recent_hot(self, max_movies: int = 10) -> List[Dict[str, Any]]:
        """
        抓取豆瓣「正在热映」或「近期热门」电影列表
        
        数据来源：豆瓣电影 - 正在热映 / 即将上映
        返回格式：[{title, rating, url, year, genre}]
        """
        movies = []
        
        # 尝试抓取「正在热映」
        urls_to_try = [
            "https://movie.douban.com/cinema/nowplaying/",
            "https://movie.douban.com/chart",
        ]
        
        for page_url in urls_to_try:
            try:
                resp = requests.get(page_url, headers=self.headers, timeout=TIMEOUT)
                resp.encoding = 'utf-8'
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # 正在热映页面
                items = (soup.select('#nowplaying .list-item') or 
                        soup.select('.upcoming .list-item') or
                        soup.select('#content .grid_view .item') or
                        soup.select('.item'))
                
                for item in items[:max_movies]:
                    try:
                        # 标题
                        title_elem = (item.select_one('.stitle a') or 
                                     item.select_one('.movie-title') or
                                     item.select_one('a') or
                                     item.select_one('.title'))
                        title = title_elem.get_text(strip=True) if title_elem else ""
                        if not title:
                            continue
                        
                        # 评分
                        rating = None
                        rating_elem = item.select_one('.subject-rate') or item.select_one('[class*="rating"]')
                        if rating_elem:
                            try:
                                rating = float(rating_elem.get_text(strip=True))
                            except (ValueError, TypeError):
                                pass
                        
                        # 链接
                        movie_url = ""
                        link_elem = item.select_one('a')
                        if link_elem:
                            movie_url = link_elem.get('href', '')
                        
                        movies.append({
                            "title": title,
                            "rating": rating,
                            "url": movie_url,
                            "year": str(datetime.now().year),
                            "genre": "",
                            "source": "豆瓣正在热映",
                        })
                    except Exception:
                        continue
                
                if movies:
                    logger.info(f"[豆瓣热映] 从 {page_url} 获取 {len(movies)} 部")
                    return movies[:max_movies]
                    
            except Exception as e:
                logger.warning(f"[豆瓣热映] 抓取失败 {page_url}: {e}")
                continue
        
        logger.info(f"[豆瓣热映] 页面抓取失败，返回空列表")
        return movies
    
    # ==================== 豆瓣数据获取 ====================
    
    def fetch_douban_details(self, movie_name: str) -> Dict[str, Any]:
        """
        从豆瓣获取电影详情（评分、评论等）
        
        Args:
            movie_name: 电影名称
            
        Returns:
            {rating, rating_count, quote, reviews[], success}
        """
        result = {
            'movie_name': movie_name,
            'rating': None,
            'rating_count': None,
            'quote': None,
            'reviews': [],
            'success': False,
            'movie_url': None,  # 返回找到的电影URL，供其他方法复用
        }
        
        try:
            # 1. 在豆瓣搜索该电影（使用标准化名称，避免标点被拆分）
            norm_name = normalize_movie_name(movie_name)
            search_url = f"https://movie.douban.com/subject_search?search_text={urllib.parse.quote(norm_name)}&cat=1002"
            
            response = requests.get(search_url, headers=self.headers, timeout=TIMEOUT)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 找到电影链接
            movie_url = self._find_movie_url(soup, movie_name)
            
            if not movie_url:
                logger.info(f"[douban] 未找到: {movie_name}")
                return result
            
            result['movie_url'] = movie_url  # 保存URL供复用
            
            # 2. 访问电影详情页
            detail_resp = requests.get(movie_url, headers=self.headers, timeout=TIMEOUT)
            detail_resp.encoding = 'utf-8'
            detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
            
            # 提取评分
            rating = self._extract_rating(detail_soup)
            if rating:
                result['rating'] = rating
            
            # 提取评价人数
            count = self._extract_count(detail_soup)
            if count:
                result['rating_count'] = count
            
            # 提取推荐理由
            quote = self._extract_quote(detail_soup)
            if quote:
                result['quote'] = quote
            
            # 尝试获取热门评论
            reviews_url = movie_url.rstrip('/') + '/reviews'
            try:
                rev_resp = requests.get(reviews_url, headers=self.headers, timeout=5)
                rev_soup = BeautifulSoup(rev_resp.text, 'html.parser')
                
                review_items = rev_soup.select('.review-item .review-content') or \
                              rev_soup.select('[class*="review"]')
                
                for item in review_items[:3]:
                    text = item.get_text(strip=True)
                    if len(text) > 20:
                        result['reviews'].append({
                            'source': 'douban',
                            'text': text[:300]
                        })
            except Exception:
                pass
            
            result['success'] = bool(result['rating'])
            logger.info(f"[douban] 成功: {movie_name} → {result['rating']}分")
            
        except Exception as e:
            logger.warning(f"[douban] 获取失败: {e}")
        
        return result
    
    def _find_movie_url(self, soup, movie_name: str) -> Optional[str]:
        """从搜索页面找到匹配的电影URL（标准化匹配）"""
        norm_name = normalize_movie_name(movie_name)
        
        # 调试日志
        logger.info(f"[豆瓣搜索] 查找电影: '{movie_name}' → 标准化: '{norm_name}'")
        
        # 方法1：查找列表中的项目（豆瓣搜索结果页面）
        selectors = ['.subject-item', '.grid_view .item', '.subject-list .subject-item', '.item']
        
        for sel in selectors:
            items = soup.select(sel)
            if items:
                logger.info(f"[豆瓣搜索] 选择器 '{sel}' 找到 {len(items)} 个项目")
            for item in items[:5]:  # 增加检查数量到5个
                # 尝试多种方式获取标题
                title_elem = (item.select_one('.title a') or 
                             item.select_one('.title span') or 
                             item.select_one('.title') or
                             item.select_one('a.nbg'))
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    # 移除括号内容（如 年份、国家等）
                    title = re.sub(r'\([^)]*\)', '', title).strip()
                    norm_title = normalize_movie_name(title)
                    
                    logger.info(f"[豆瓣搜索] 检查标题: '{title}' → 标准化: '{norm_title}'")
                    
                    if norm_name and (norm_name in norm_title or norm_title in norm_name or 
                                      len(norm_name) >= 3 and norm_title in norm_name):
                        link = (item.select_one('a.nbg') or 
                               item.select_one('.title a') or 
                               item.select('a')[0] if item.select('a') else None)
                        if link and link.get('href'):
                            href = link.get('href', '')
                            if '/subject/' in href:
                                logger.info(f"[豆瓣搜索] 匹配成功! URL: {href}")
                                return href
        
        # 方法2：直接找包含 subject 的链接（更宽松的匹配）
        links = soup.find_all('a', href=re.compile(r'/subject/\d+'))
        for link in links[:8]:  # 增加检查数量
            link_text = link.get_text(strip=True)
            norm_link_text = normalize_movie_name(link_text)
            
            # 更宽松的匹配：只要包含关键词就算匹配
            if norm_name and len(norm_name) >= 2:
                if (norm_name in norm_link_text or norm_link_text in norm_name or
                    any(kw in norm_link_text for kw in [norm_name[:2], norm_name[:3]] if len(norm_name) >= 3)):
                    href = link.get('href', '')
                    logger.info(f"[豆瓣搜索] 方法2匹配: '{link_text}' → {href}")
                    return href
        
        logger.warning(f"[豆瓣搜索] 未找到匹配的电影: '{movie_name}'")
        return None
    
    def _extract_rating(self, soup) -> Optional[float]:
        """提取评分"""
        selectors = ['#interest_sectl .rating_num', '.ratingNum', 
                     'strong.rating_num', '[property="v:average"]']
        
        for sel in selectors:
            elem = soup.select_one(sel)
            if elem:
                try:
                    return float(elem.get_text(strip=True))
                except (ValueError, TypeError):
                    continue
        return None
    
    def _extract_count(self, soup) -> Optional[str]:
        """提取评价人数"""
        selectors = ['#interest_sectl .rating_people span', '[property="v:votes"]']
        
        for sel in selectors:
            elem = soup.select_one(sel)
            if elem:
                return elem.get_text(strip=True)
        return None
    
    def _extract_quote(self, soup) -> Optional[str]:
        """提取推荐理由"""
        selectors = ['#interest_sectl .inq', '.inq', '[property="v:summary"]']
        
        for sel in selectors:
            elem = soup.select_one(sel)
            if elem:
                return elem.get_text(strip=True)
        return None
    
    # ==================== 影评专项搜索（评价查询专用）====================
    
    def search_movie_reviews(self, movie_name: str, max_results: int = 8) -> List[Dict[str, Any]]:
        """
        专门用于搜索某部电影的评价/影评（多轮补充策略）

        策略：分两轮搜索——首轮用书名号获取标题语义，如果结果质量低
              （无评分/评价相关词），第二轮补充更精准的查询。

        Returns:
            [{source, title, content}]
        """
        all_reviews = []
        seen_snippets = set()

        title_wrapped = f'《{movie_name}》'

        # 第一轮：2个基础查询（必须包含"电影"关键词）
        first_round = [
            f'{title_wrapped} 电影 评价 影评 好不好看',
            f'{title_wrapped} 电影 观后感 口碑 豆瓣评分',
        ]

        for query in first_round:
            try:
                results = self.search_bing_for_movies(query, max_results=4)
                for r in results:
                    snippet = r.get("snippet", "")
                    if len(snippet) < 10:
                        continue
                    dedup_key = snippet[:30]
                    if dedup_key in seen_snippets:
                        continue
                    seen_snippets.add(dedup_key)
                    all_reviews.append({
                        "source": r.get("source", "网络"),
                        "title": r.get("title", ""),
                        "content": snippet,
                        "url": r.get("url", ""),
                    })
            except Exception as e:
                logger.warning(f"[影评搜索] 查询失败 '{query[:20]}...': {e}")

        # 第二轮补充：如果评价内容太少，用"豆瓣+评分"关键词精准定向
        # 解决《你好，李焕英》这类名字被搜索引擎错误拆分的问题
        if len(all_reviews) < 2:
            extra_queries = [
                f'{title_wrapped} 豆瓣 评分 口碑 电影 影评',
                f'{title_wrapped} 电影 评价 好看吗',
            ]
            for query in extra_queries:
                try:
                    results = self.search_bing_for_movies(query, max_results=4)
                    for r in results:
                        snippet = r.get("snippet", "")
                        if len(snippet) < 10:
                            continue
                        dedup_key = snippet[:30]
                        if dedup_key in seen_snippets:
                            continue
                        seen_snippets.add(dedup_key)
                        all_reviews.append({
                            "source": r.get("source", "网络"),
                            "title": r.get("title", ""),
                            "content": snippet,
                            "url": r.get("url", ""),
                        })
                except Exception as e:
                    logger.warning(f"[影评搜索-补充] 查询失败 '{query[:20]}...': {e}")

        logger.info(f"[影评搜索] '{movie_name}' → 获取 {len(all_reviews)} 条")
        return all_reviews[:max_results]

    def fetch_douban_short_reviews(self, movie_name: str, movie_url: str = None) -> List[Dict[str, Any]]:
        """
        尝试获取豆瓣短评（比长评更容易抓取到更多真实观众声音）
        
        Args:
            movie_name: 电影名称
            movie_url: 可选，已知的豆瓣电影页面URL（避免重复搜索）
        
        Returns:
            [{source, text, rating}]
        """
        reviews = []
        try:
            # 如果没有提供URL，需要先搜索找到
            if not movie_url:
                norm_name = normalize_movie_name(movie_name)
                search_url = f"https://movie.douban.com/subject_search?search_text={urllib.parse.quote(norm_name)}&cat=1002"
                response = requests.get(search_url, headers=self.headers, timeout=TIMEOUT)
                response.encoding = 'utf-8'
                soup = BeautifulSoup(response.text, 'html.parser')
                
                movie_url = self._find_movie_url(soup, movie_name)
                if not movie_url:
                    return reviews
            
            # 访问评论页
            comments_url = movie_url.rstrip('/') + '/comments'
            resp = requests.get(comments_url, headers=self.headers, timeout=TIMEOUT)
            resp.encoding = 'utf-8'
            comment_soup = BeautifulSoup(resp.text, 'html.parser')
            
            # 抓取短评
            comment_items = comment_soup.select('.comment-item') or \
                           comment_soup.select('[class*="comment"]')
            
            for item in comment_items[:10]:
                try:
                    # 评论内容
                    content_elem = item.select_one('.comment-content span.short') or \
                                   item.select_one('.short') or \
                                   item.select_one('.comment-text')
                    text = content_elem.get_text(strip=True) if content_elem else ""
                    
                    if not text or len(text) < 5:
                        continue
                    
                    # 评分（豆瓣用星星类名表示）
                    rating = None
                    rating_elem = item.select_one('[class*="rating"]')
                    if rating_elem:
                        class_str = rating_elem.get('class', [])
                        for cls in class_str:
                            match = re.search(r'allstar(\d+)0', cls)
                            if match:
                                rating = int(match.group(1))  # 10-50 → 对应1-5星
                                break
                    
                    reviews.append({
                        "source": "豆瓣短评",
                        "text": text[:300],
                        "rating": rating,
                    })
                except Exception:
                    continue
            
            if reviews:
                logger.info(f"[豆瓣短评] '{movie_name}' → {len(reviews)} 条")
                
        except Exception as e:
            logger.warning(f"[豆瓣短评] 获取失败: {e}")

        return reviews

    # ==================== 本地推荐 ====================
    
    def get_local_recommendations(self, genre: str = None, limit: int = 10) -> Dict[str, Any]:
        """
        从本地数据库推荐电影（由 app.py 调用时传入爬虫数据）
        注意：此方法需要配合 crawler 使用，这里返回格式化的推荐结构
        
        Returns:
            {source, movies[], summary}
        """
        from crawler import DoubanMovieCrawler
        crawler = DoubanMovieCrawler()
        
        all_movies = crawler.get_all_movies()
        if not all_movies:
            return {"source": "none", "movies": [], "summary": ""}
        
        # 按类型筛选
        filtered = all_movies
        if genre:
            filtered = [m for m in all_movies if genre in m.get('genre', '')]
        
        # 按评分排序，取前N个
        filtered.sort(key=lambda x: x.get('rating', 0), reverse=True)
        top = filtered[:limit]
        
        movies_list = []
        for i, m in enumerate(top, 1):
            entry = {
                "title": m.get("title", ""),
                "rating": m.get("rating"),
                "genre": m.get("genre", ""),
                "year": m.get("year", ""),
                "quote": m.get("quote", ""),
            }
            movies_list.append(entry)
        
        summary_parts = []
        for i, m in enumerate(movies_list, 1):
            line = f"{i}. 《{m['title']}》- {m['rating']}分 | {m['genre']} | {m['year']}年"
            summary_parts.append(line)
            if m.get('quote'):
                summary_parts.append(f"   \"{m['quote']}\"")
        
        genre_hint = f"{genre}类型 " if genre else ""
        summary = f"【豆瓣TOP250 {genre_hint}高分电影】\n\n" + "\n".join(summary_parts)
        
        similar = [{"title": m["title"], "snippet": f"{m['rating']}分 | {m['genre']}"} for m in movies_list[:8]]
        
        return {
            "source": "local",
            "movies": movies_list,
            "summary": summary,
            "similar": similar,
            "rating": {"douban": top[0].get("rating")} if top else {},
        }


# 测试
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    fetcher = MovieDataFetcher()
    
    print("\n" + "=" * 50)
    print("测试 Bing 搜索")
    print("=" * 50)
    results = fetcher.search_bing("2026 喜剧电影推荐")
    for r in results[:3]:
        print(f"- {r['title']}")
    
    print("\n" + "=" * 50)
    print("测试 豆瓣详情")
    print("=" * 50)
    douban_data = fetcher.fetch_douban_details("你好，李焕英")
    print(f"评分: {douban_data.get('rating')}")
    print(f"评价: {douban_data.get('quote')}")
    print(f"评论数: {len(douban_data.get('reviews', []))}")
    
    print("\n" + "=" * 50)
    print("测试 本地推荐")
    print("=" * 50)
    recs = fetcher.get_local_recommendations(genre="喜剧", limit=5)
    print(f"来源: {recs['source']}")
    print(recs['summary'][:200])
