"""
电影数据爬虫模块
从豆瓣、猫眼等平台爬取电影评分和观众评价
"""
import requests
from bs4 import BeautifulSoup
import re
import time
import random
from datetime import datetime


class MovieCrawler:
    """电影数据爬虫类"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def _random_delay(self, min_sec=1, max_sec=3):
        """随机延迟，避免请求过快"""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def _safe_get(self, url, params=None, retries=3):
        """安全的GET请求，带重试机制"""
        for i in range(retries):
            try:
                response = self.session.get(url, params=params, timeout=10)
                response.raise_for_status()
                return response
            except Exception as e:
                if i < retries - 1:
                    self._random_delay(2, 4)
                else:
                    return None
        return None
    
    def search_movie_douban(self, movie_name):
        """搜索豆瓣电影"""
        try:
            url = f"https://movie.douban.com/subject_search"
            params = {"search_text": movie_name, "cat": 1002}
            response = self._safe_get(url, params)
            
            if not response:
                return None
            
            soup = BeautifulSoup(response.text, 'lxml')
            items = soup.select('.item')
            
            for item in items[:5]:
                title_elem = item.select_one('.title')
                if title_elem and movie_name[:2] in title_elem.text:
                    link = item.select_one('a')
                    if link:
                        return link.get('href')
            return None
        except Exception as e:
            print(f"豆瓣搜索出错: {e}")
            return None
    
    def get_douban_reviews(self, movie_url, limit=10):
        """获取豆瓣电影短评"""
        reviews = []
        try:
            if not movie_url:
                return reviews
            
            movie_id = re.search(r'/subject/(\d+)', movie_url)
            if not movie_id:
                return reviews
            
            mid = movie_id.group(1)
            comments_url = f"https://movie.douban.com/subject/{mid}/comments"
            params = {"limit": limit, "status": "P", "sort": "new_score"}
            
            response = self._safe_get(comments_url, params)
            if not response:
                return reviews
            
            soup = BeautifulSoup(response.text, 'lxml')
            comment_items = soup.select('.comment-item')
            
            for item in comment_items[:limit]:
                try:
                    content_elem = item.select_one('.comment-content')
                    rating_elem = item.select_one('.rating')
                    author_elem = item.select_one('.avatar')
                    
                    content = content_elem.text.strip() if content_elem else ""
                    rating_text = rating_elem.get('title', '') if rating_elem else ""
                    rating = 0
                    if "力荐" in rating_text:
                        rating = 5
                    elif "推荐" in rating_text:
                        rating = 4
                    elif "还行" in rating_text:
                        rating = 3
                    elif "较差" in rating_text:
                        rating = 2
                    elif "很差" in rating_text:
                        rating = 1
                    
                    author = author_elem.get('title', '匿名用户') if author_elem else "匿名用户"
                    
                    if content:
                        reviews.append({
                            "platform": "豆瓣",
                            "content": content[:500],
                            "rating": rating,
                            "author": author
                        })
                except Exception:
                    continue
            
            self._random_delay(1, 2)
        except Exception as e:
            print(f"获取豆瓣评论出错: {e}")
        return reviews
    
    def get_douban_rating(self, movie_name):
        """获取豆瓣评分"""
        try:
            url = f"https://movie.douban.com/subject_search"
            params = {"search_text": movie_name, "cat": 1002}
            response = self._safe_get(url, params)
            
            if not response:
                return None
            
            soup = BeautifulSoup(response.text, 'lxml')
            items = soup.select('.item')
            
            for item in items[:3]:
                title_elem = item.select_one('.title')
                if title_elem and (movie_name[:2] in title_elem.text or movie_name[:1] in title_elem.text):
                    rating_elem = item.select_one('.star')
                    if rating_elem:
                        rating_text = rating_elem.text
                        rating_match = re.search(r'(\d+\.\d)', rating_text)
                        if rating_match:
                            return float(rating_match.group(1))
            return None
        except Exception as e:
            print(f"获取豆瓣评分出错: {e}")
            return None
    
    def search_movie_maoyan(self, movie_name):
        """搜索猫眼电影"""
        try:
            url = "https://www.maoyan.com/search"
            params = {"key": movie_name}
            response = self._safe_get(url, params)
            
            if not response:
                return None
            
            soup = BeautifulSoup(response.text, 'lxml')
            movies = soup.select('.movie-card')
            
            for movie in movies[:3]:
                title_elem = movie.select_one('.movie-title')
                if title_elem and movie_name[:2] in title_elem.text:
                    link = movie.select_one('a')
                    if link:
                        return "https://www.maoyan.com" + link.get('href')
            return None
        except Exception as e:
            print(f"猫眼搜索出错: {e}")
            return None
    
    def get_maoyan_rating(self, movie_name):
        """获取猫眼评分"""
        try:
            search_url = "https://www.maoyan.com/search"
            params = {"key": movie_name}
            response = self._safe_get(search_url, params)
            
            if not response:
                return None
            
            soup = BeautifulSoup(response.text, 'lxml')
            cards = soup.select('.movie-card')
            
            for card in cards[:3]:
                title_elem = card.select_one('.movie-title')
                if title_elem and (movie_name[:2] in title_elem.text or movie_name[:1] in title_elem.text):
                    rating_elem = card.select_one('.rating')
                    if rating_elem:
                        rating_text = rating_elem.text.strip()
                        rating_match = re.search(r'(\d+\.\d)', rating_text)
                        if rating_match:
                            return float(rating_match.group(1))
            return None
        except Exception as e:
            print(f"获取猫眼评分出错: {e}")
            return None
    
    def get_imdb_rating(self, movie_name):
        """获取IMDB评分（通过搜索）"""
        try:
            url = "https://www.imdb.com/find"
            params = {"q": movie_name, "s": "tt"}
            response = self._safe_get(url, params)
            
            if not response:
                return None
            
            soup = BeautifulSoup(response.text, 'lxml')
            result = soup.select_one('.ipc-metadata-list-summary-item__t')
            
            if result:
                self._random_delay(1, 2)
                movie_url = "https://www.imdb.com" + result.get('href', '')
                movie_response = self._safe_get(movie_url)
                
                if movie_response:
                    movie_soup = BeautifulSoup(movie_response.text, 'lxml')
                    rating_elem = movie_soup.select_one('[data-testid="hero-rating-bar__aggregate-rating__score"] span')
                    if rating_elem:
                        rating_text = rating_elem.text.strip()
                        rating_match = re.search(r'(\d+\.\d)', rating_text)
                        if rating_match:
                            return float(rating_match.group(1))
            return None
        except Exception as e:
            print(f"获取IMDB评分出错: {e}")
            return None
    
    def analyze_reviews(self, reviews):
        """分析评论，提取满意点和槽点"""
        positive_keywords = [
            '精彩', '好看', '推荐', '感动', '震撼', '完美', '经典', '神作',
            '惊喜', '优秀', '演技', '配乐', '画面', '剧情', '感人', '热血',
            '温情', '幽默', '真实', '深刻', '良心', '值得', '必看', '爆哭'
        ]
        
        negative_keywords = [
            '失望', '难看', '无聊', '烂片', '尴尬', '拖沓', '尴尬', '强行',
            '智商', '狗血', '俗套', '空洞', '浮夸', '做作', '无聊', '催眠',
            '圈钱', '尴尬', '恶心', '垃圾', '浪费', '太差', '无脑', '硬伤'
        ]
        
        pros = []
        cons = []
        
        for review in reviews:
            content = review.get('content', '')
            rating = review.get('rating', 0)
            
            if rating >= 4:
                for keyword in positive_keywords:
                    if keyword in content and keyword not in pros:
                        pros.append(keyword)
            elif rating <= 2:
                for keyword in negative_keywords:
                    if keyword in content and keyword not in cons:
                        cons.append(keyword)
        
        return {
            "pros": pros[:8],
            "cons": cons[:8]
        }
    
    def get_full_movie_info(self, movie_name):
        """获取完整电影信息"""
        result = {
            "title": movie_name,
            "ratings": {},
            "reviews": [],
            "pros": [],
            "cons": []
        }
        
        self._random_delay(1, 2)
        douban_url = self.search_movie_douban(movie_name)
        douban_rating = self.get_douban_rating(movie_name)
        
        if douban_rating:
            result["ratings"]["douban"] = douban_rating
        
        if douban_url:
            reviews = self.get_douban_reviews(douban_url, limit=15)
            result["reviews"].extend(reviews)
        
        self._random_delay(1, 2)
        maoyan_rating = self.get_maoyan_rating(movie_name)
        if maoyan_rating:
            result["ratings"]["maoyan"] = maoyan_rating
        
        self._random_delay(1, 2)
        imdb_rating = self.get_imdb_rating(movie_name)
        if imdb_rating:
            result["ratings"]["imdb"] = imdb_rating
        
        if result["reviews"]:
            analysis = self.analyze_reviews(result["reviews"])
            result["pros"] = analysis["pros"]
            result["cons"] = analysis["cons"]
        
        return result


def search_movie_ratings(movie_name):
    """搜索电影评分的便捷函数"""
    crawler = MovieCrawler()
    return crawler.get_full_movie_info(movie_name)


if __name__ == "__main__":
    crawler = MovieCrawler()
    info = crawler.get_full_movie_info("流浪地球")
    print(info)
