"""
联网搜索模块
使用 DuckDuckGo 搜索电影评分和评价
"""
import requests
from duckduckgo_search import DDGS
from bs4 import BeautifulSoup
import re
import time


class MovieSearcher:
    """电影联网搜索类"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    
    def search_movie_ratings(self, movie_name: str) -> dict:
        """
        搜索电影评分
        Returns:
            {
                "title": str,
                "ratings": {"douban": float, "maoyan": float, "imdb": float},
                "summary": str
            }
        """
        result = {
            "title": movie_name,
            "ratings": {},
            "summary": ""
        }
        
        try:
            # 搜索豆瓣评分
            with DDGS() as ddgs:
                search_query = f"{movie_name} 豆瓣评分"
                results = list(ddgs.text(search_query, max_results=3))
                
                for r in results:
                    text = r.get('body', '')
                    if '豆瓣' in text:
                        douban_match = re.search(r'豆瓣[:：]?\s*(\d+\.\d)', text)
                        if douban_match:
                            result["ratings"]["douban"] = float(douban_match.group(1))
                            break
                
                # 搜索猫眼评分
                search_query = f"{movie_name} 猫眼评分"
                results = list(ddgs.text(search_query, max_results=3))
                
                for r in results:
                    text = r.get('body', '')
                    if '猫眼' in text or 'Maoyan' in text:
                        maoyan_match = re.search(r'(\d+\.\d)', text)
                        if maoyan_match:
                            result["ratings"]["maoyan"] = float(maoyan_match.group(1))
                            break
                
                # 搜索IMDB评分
                search_query = f"{movie_name} IMDB rating"
                results = list(ddgs.text(search_query, max_results=5))
                
                for r in results:
                    text = r.get('body', '')
                    if 'IMDb' in text or 'IMDB' in text:
                        imdb_match = re.search(r'(\d+\.\d)', text)
                        if imdb_match:
                            rating = float(imdb_match.group(1))
                            if 1 <= rating <= 10:
                                result["ratings"]["imdb"] = rating
                                break
                
                # 获取电影简介
                search_query = f"{movie_name} 电影简介"
                results = list(ddgs.text(search_query, max_results=1))
                
                if results:
                    result["summary"] = results[0].get('body', '')[:300]
        
        except Exception as e:
            print(f"搜索出错: {e}")
        
        return result
    
    def search_movie_reviews(self, movie_name: str) -> list:
        """
        搜索电影评价
        Returns:
            [{"source": str, "content": str, "author": str}]
        """
        reviews = []
        
        try:
            with DDGS() as ddgs:
                search_query = f"{movie_name} 影评 观众评价"
                results = list(ddgs.text(search_query, max_results=10))
                
                for r in results:
                    reviews.append({
                        "source": r.get('hostname', '网络'),
                        "content": r.get('body', '')[:500],
                        "url": r.get('href', '')
                    })
        
        except Exception as e:
            print(f"搜索影评出错: {e}")
        
        return reviews
    
    def search_similar_movies(self, movie_name: str) -> list:
        """
        搜索相似电影推荐
        """
        similar = []
        
        try:
            with DDGS() as ddgs:
                search_query = f"类似 {movie_name} 的电影 推荐"
                results = list(ddgs.text(search_query, max_results=8))
                
                for r in results:
                    title = r.get('title', '')
                    if '类似' in title or '推荐' in title:
                        similar.append({
                            "title": title.split('-')[0].replace('类似', '').strip(),
                            "snippet": r.get('body', '')[:200]
                        })
        
        except Exception as e:
            print(f"搜索相似电影出错: {e}")
        
        return similar
    
    def search_hot_movies(self, category: str = "最新") -> list:
        """
        搜索热门电影
        category: 最新 / 2024 / 2025 / 科幻 / 喜剧 等
        """
        movies = []
        
        try:
            with DDGS() as ddgs:
                search_query = f"{category}热门电影 2025 推荐"
                results = list(ddgs.text(search_query, max_results=10))
                
                for r in results:
                    title = r.get('title', '')
                    if '电影' in title:
                        movies.append({
                            "title": title.split('电影')[0].strip(),
                            "snippet": r.get('body', '')[:200],
                            "url": r.get('href', '')
                        })
        
        except Exception as e:
            print(f"搜索热门电影出错: {e}")
        
        return movies
    
    def get_comprehensive_movie_info(self, movie_name: str) -> dict:
        """
        获取完整的电影信息（搜索+影评）
        """
        info = self.search_movie_ratings(movie_name)
        info["reviews"] = self.search_movie_reviews(movie_name)
        info["similar"] = self.search_similar_movies(movie_name)
        return info


def test():
    searcher = MovieSearcher()
    result = searcher.search_movie_ratings("流浪地球2")
    print(result)


if __name__ == "__main__":
    test()
