"""
豆瓣电影爬虫模块
爬取豆瓣电影数据并保存为 CSV，支持加载本地数据供大模型使用
"""
import random
import re
import time
import os
import csv
import requests
from lxml import etree
from urllib.parse import urljoin
from typing import List, Dict, Optional


def normalize_movie_name(name: str) -> str:
    """标准化电影名称，用于搜索匹配

    解决：电影名中的中文标点（，。）被搜索引擎拆分为多个词、
         用户输入含《》""等符号干扰匹配。

    策略：移除所有标点符号，只保留汉字/字母/数字，压缩空格。
    示例："你好，李焕英" → "你好李焕英"
    """
    if not name:
        return ''
    name = re.sub(r'[]》""''【】（）()[\{}《]', '', name)
    name = re.sub(r'[，。！？、；：…—～·.,!?:;-]', '', name)
    name = re.sub(r'\s+', '', name).strip()
    return name


# 请求头
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Referer': 'https://movie.douban.com/',
}

# CSV 文件路径
CSV_FILE = os.path.join(os.path.dirname(__file__), 'douban_movies.csv')


def extract_first(trees, default=""):
    """返回列表第一个元素，列表为空则返回默认值"""
    for x in trees:
        return x
    return default


class DoubanMovieCrawler:
    """豆瓣电影爬虫类"""
    
    def __init__(self, csv_file: str = None):
        self.csv_file = csv_file or CSV_FILE
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        
        # 内存中的电影数据
        self.movies_data: List[Dict] = []
        self._load_from_csv()
    
    def _random_delay(self, min_sec=2, max_sec=5):
        """随机延迟，避免请求过快被封"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)
    
    def _safe_get(self, url: str, retries: int = 3) -> Optional[str]:
        """安全的 GET 请求"""
        for i in range(retries):
            try:
                response = self.session.get(url, timeout=15)
                if response.status_code == 200:
                    response.encoding = 'utf-8'
                    return response.text
                elif response.status_code in [403, 429]:
                    # 被限制，等待更长时间
                    self._random_delay(5, 10)
                else:
                    if i < retries - 1:
                        self._random_delay(2, 4)
            except Exception as e:
                if i < retries - 1:
                    self._random_delay(2, 4)
        return None
    
    def crawl_douban_top250(self) -> List[Dict]:
        """爬取豆瓣电影 TOP250"""
        print("开始爬取豆瓣电影 TOP250...")
        
        movie_names, urls, scores, star_people_nums = [], [], [], []
        directors, actors, years, countrys, types = [], [], [], [], []
        one_evaluates = []
        
        def parse(page_url: str):
            """解析页面数据"""
            print(f"----------开始爬取：{page_url}-------------")
            page_source = self._safe_get(page_url)
            if not page_source:
                print(f"获取页面失败: {page_url}")
                return
            
            tree = etree.HTML(page_source)
            lis = tree.xpath("//ol[@class='grid_view']/li")
            
            for li in lis:
                url = extract_first(li.xpath(".//div[@class='hd']/a/@href")).strip()
                movie_name = "".join(li.xpath(".//div[@class='hd']/a//text()"))
                movie_name = re.sub(r"\s+", "", movie_name)
                score = extract_first(li.xpath(".//span[@class='rating_num']/text()")).strip()
                star_people_num = extract_first(li.xpath(".//div[@class='star']/span[4]/text()")).strip()
                star_people_num = re.search(r"\d+", star_people_num).group() if star_people_num else "0"
                one_evaluate = extract_first(li.xpath(".//p[@class='quote']/span/text()")).strip()
                
                info = "".join(li.xpath(".//div[@class='bd']/p/text()")).strip()
                infos = info.split("\n")
                
                director = ""
                actor = ""
                try:
                    director_part = infos[0].split("\xa0\xa0\xa0")[0]
                    director = director_part.replace("导演:", "").strip()
                    if len(infos[0].split("\xa0\xa0\xa0")) > 1:
                        actor = infos[0].split("\xa0\xa0\xa0")[1].strip()
                except:
                    pass
                
                info_sub = re.sub(r"\s+", "", infos[1]) if len(infos) > 1 else ""
                info_subs = info_sub.split("/")
                
                year, country, movie_type = "", "", ""
                if len(info_subs) >= 3:
                    year = info_subs[0]
                    country = info_subs[1]
                    movie_type = info_subs[2]
                elif len(info_subs) == 2:
                    year = info_subs[0]
                    country = info_subs[1]
                
                urls.append(url)
                movie_names.append(movie_name)
                scores.append(str(score))
                star_people_nums.append(str(star_people_num))
                one_evaluates.append(one_evaluate)
                directors.append(director)
                actors.append(actor)
                years.append(year)
                countrys.append(country)
                types.append(movie_type)
                
                print(f"{movie_name} | 评分: {score} | {year} | {country}")
                
                self._random_delay(2, 4)
            
            # 判断是否有下一页
            next_page = tree.xpath("//div[@class='paginator']/span[@class='next']")
            if next_page:
                a = next_page[0].xpath("./a")
                if a:
                    a_href = a[0].xpath("./@href")[0]
                    next_url = urljoin(page_url, a_href)
                    parse(next_url)
        
        # 开始爬取
        parse("https://movie.douban.com/top250")
        
        # 保存到 CSV
        self._save_to_csv(movie_names, urls, scores, star_people_nums, directors, actors, years, countrys, types, one_evaluates)
        
        # 更新内存数据
        self._load_from_csv()
        
        print(f"爬取完成，共 {len(movie_names)} 部电影")
        return self.movies_data
    
    def _save_to_csv(self, movie_names: List, urls: List, scores: List, star_people_nums: List,
                     directors: List, actors: List, years: List, countrys: List, 
                     types: List, one_evaluates: List):
        """保存数据到 CSV 文件"""
        df_data = {
            '电影名字': movie_names,
            '电影链接': urls,
            '评分': scores,
            '评价人数': star_people_nums,
            '导演': directors,
            '主演': actors,
            '年份': years,
            '国家': countrys,
            '类型': types,
            '一句话评价': one_evaluates
        }
        
        # 写入 BOM，让 Windows 记事本/Excel 正确识别 UTF-8 中文
        with open(self.csv_file, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=df_data.keys())
            writer.writeheader()
            for i in range(len(movie_names)):
                row = {k: v[i] if i < len(v) else '' for k, v in df_data.items()}
                writer.writerow(row)
        
        print(f"数据已保存到: {self.csv_file}")
    
    def _load_from_csv(self):
        """从 CSV 文件加载数据"""
        self.movies_data = []
        if not os.path.exists(self.csv_file):
            return
        
        try:
            with open(self.csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.movies_data.append({
                        'title': row.get('电影名字', ''),
                        'url': row.get('电影链接', ''),
                        'rating': float(row.get('评分', 0)) if row.get('评分') else 0,
                        'rating_count': row.get('评价人数', ''),
                        'director': row.get('导演', ''),
                        'actors': row.get('主演', ''),
                        'year': row.get('年份', ''),
                        'country': row.get('国家', ''),
                        'genre': row.get('类型', ''),
                        'quote': row.get('一句话评价', '')
                    })
            print(f"已从 {self.csv_file} 加载 {len(self.movies_data)} 部电影数据")
        except Exception as e:
            print(f"加载 CSV 数据失败: {e}")
    
    def search_by_name(self, movie_name: str) -> Optional[Dict]:
        """根据电影名称搜索（标准化模糊匹配）"""
        if not self.movies_data:
            self._load_from_csv()

        norm_name = normalize_movie_name(movie_name)
        if not norm_name:
            return None

        # 精确匹配（标准化后）
        for movie in self.movies_data:
            norm_title = normalize_movie_name(movie.get('title', ''))
            if norm_name == norm_title or norm_name in norm_title or norm_title in norm_name:
                return movie

        # 子串匹配：取标准化名称的前半段作为关键词（比固定取2字更精确）
        keywords = norm_name[:max(2, len(norm_name) // 2)]
        for movie in self.movies_data:
            norm_title = normalize_movie_name(movie.get('title', ''))
            if keywords in norm_title:
                return movie

        return None
    
    def search_by_genre(self, genre: str) -> List[Dict]:
        """根据类型搜索电影"""
        if not self.movies_data:
            self._load_from_csv()
        
        results = []
        genre_lower = genre.lower()
        for movie in self.movies_data:
            if genre_lower in movie.get('genre', '').lower():
                results.append(movie)
        return results
    
    def search_by_year(self, year: str) -> List[Dict]:
        """根据年份搜索电影"""
        if not self.movies_data:
            self._load_from_csv()
        
        results = []
        for movie in self.movies_data:
            if year in movie.get('year', ''):
                results.append(movie)
        return results
    
    def get_top_rated(self, limit: int = 10) -> List[Dict]:
        """获取评分最高的电影"""
        if not self.movies_data:
            self._load_from_csv()
        
        sorted_movies = sorted(self.movies_data, key=lambda x: x.get('rating', 0), reverse=True)
        return sorted_movies[:limit]
    
    def get_all_movies(self) -> List[Dict]:
        """获取所有电影数据"""
        if not self.movies_data:
            self._load_from_csv()
        return self.movies_data
    
    def format_for_ai(self, movie: Dict) -> str:
        """将电影数据格式化为 AI 可读的文本"""
        if not movie:
            return "未找到相关电影信息"
        
        parts = []
        parts.append(f"电影名称：{movie.get('title', '未知')}")
        parts.append(f"豆瓣评分：{movie.get('rating', '暂无')} 分（{movie.get('rating_count', '')} 人评价）")
        
        if movie.get('director'):
            parts.append(f"导演：{movie.get('director')}")
        if movie.get('actors'):
            parts.append(f"主演：{movie.get('actors')}")
        if movie.get('year'):
            parts.append(f"年份：{movie.get('year')}")
        if movie.get('country'):
            parts.append(f"国家：{movie.get('country')}")
        if movie.get('genre'):
            parts.append(f"类型：{movie.get('genre')}")
        if movie.get('quote'):
            parts.append(f"推荐理由：{movie.get('quote')}")
        
        return "\n".join(parts)


# 全局爬虫实例
_crawler_instance = None

def get_crawler() -> DoubanMovieCrawler:
    """获取爬虫单例"""
    global _crawler_instance
    if _crawler_instance is None:
        _crawler_instance = DoubanMovieCrawler()
    return _crawler_instance


def search_movie(movie_name: str) -> Optional[Dict]:
    """便捷函数：根据名称搜索电影"""
    return get_crawler().search_by_name(movie_name)


def search_by_genre(genre: str) -> List[Dict]:
    """便捷函数：根据类型搜索"""
    return get_crawler().search_by_genre(genre)


def search_by_year(year: str) -> List[Dict]:
    """便捷函数：根据年份搜索"""
    return get_crawler().search_by_year(year)


def get_top_movies(limit: int = 10) -> List[Dict]:
    """便捷函数：获取高分电影"""
    return get_crawler().get_top_rated(limit)


def crawl_and_save() -> List[Dict]:
    """便捷函数：爬取并保存数据"""
    crawler = DoubanMovieCrawler()
    return crawler.crawl_douban_top250()


if __name__ == "__main__":
    crawler = DoubanMovieCrawler()
    
    # 如果 CSV 不存在，先爬取
    if not os.path.exists(crawler.csv_file):
        print("CSV 文件不存在，开始爬取数据...")
        crawler.crawl_douban_top250()
    else:
        print("CSV 文件已存在，加载本地数据...")
        crawler._load_from_csv()
    
    # 测试搜索
    movie = crawler.search_by_name("流浪地球")
    if movie:
        print("\n找到电影:")
        print(crawler.format_for_ai(movie))
    else:
        print("未找到电影")
    
    # 显示高分电影
    print("\n豆瓣 TOP10 电影:")
    for i, m in enumerate(crawler.get_top_rated(10), 1):
        print(f"{i}. {m.get('title')} - {m.get('rating')}分")
