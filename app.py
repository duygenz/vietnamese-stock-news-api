from flask import Flask, jsonify, request
import feedparser
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
from dateutil import parser as date_parser
import time
from urllib.parse import urljoin, urlparse
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Danh sách RSS feeds
RSS_FEEDS = [
    "https://vietstock.vn/830/chung-khoan/co-phieu.rss",
    "https://cafef.vn/thi-truong-chung-khoan.rss",
    "https://vietstock.vn/145/chung-khoan/y-kien-chuyen-gia.rss",
    "https://vietstock.vn/737/doanh-nghiep/hoat-dong-kinh-doanh.rss",
    "https://vietstock.vn/1328/dong-duong/thi-truong-chung-khoan.rss",
    "https://vneconomy.vn/chung-khoan.rss",
    "https://vneconomy.vn/tin-moi.rss",
    "https://vneconomy.vn/tai-chinh.rss",
    "https://vneconomy.vn/nhip-cau-doanh-nghiep.rss",
    "https://vneconomy.vn/thi-truong.rss"
]

def clean_text(text):
    """Làm sạch text, loại bỏ HTML tags và ký tự không mong muốn"""
    if not text:
        return ""
    
    # Loại bỏ HTML tags
    soup = BeautifulSoup(text, 'html.parser')
    text = soup.get_text()
    
    # Loại bỏ ký tự xuống dòng thừa và khoảng trắng
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    return text

def get_full_article_content(url):
    """Lấy nội dung đầy đủ của bài viết từ URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Xác định domain để áp dụng selector phù hợp
        domain = urlparse(url).netloc
        
        content = ""
        
        if 'vietstock.vn' in domain:
            # Selector cho VietStock
            article_body = soup.find('div', class_='article-content') or \
                          soup.find('div', class_='content-news') or \
                          soup.find('div', class_='news-content')
            
        elif 'cafef.vn' in domain:
            # Selector cho CafeF
            article_body = soup.find('div', class_='detail-content') or \
                          soup.find('div', class_='content') or \
                          soup.find('div', class_='article-content')
            
        elif 'vneconomy.vn' in domain:
            # Selector cho VnEconomy
            article_body = soup.find('div', class_='detail-content') or \
                          soup.find('div', class_='article-content') or \
                          soup.find('div', class_='content-news')
        else:
            # Fallback selectors
            article_body = soup.find('div', class_='content') or \
                          soup.find('div', class_='article-content') or \
                          soup.find('article')
        
        if article_body:
            # Loại bỏ các thẻ không mong muốn
            for tag in article_body.find_all(['script', 'style', 'iframe', 'ins', 'aside']):
                tag.decompose()
            
            content = clean_text(article_body.get_text())
        
        return content if content else "Không thể lấy nội dung đầy đủ"
        
    except Exception as e:
        logging.error(f"Error getting full content from {url}: {str(e)}")
        return "Không thể lấy nội dung đầy đủ"

def create_chunks(text, chunk_size=1000):
    """Chia text thành các chunks nhỏ hơn"""
    if not text:
        return []
    
    # Chia theo câu trước
    sentences = re.split(r'[.!?]+', text)
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        # Nếu thêm câu này vào chunk hiện tại mà không vượt quá giới hạn
        if len(current_chunk + sentence) <= chunk_size:
            current_chunk += sentence + ". "
        else:
            # Lưu chunk hiện tại và bắt đầu chunk mới
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence + ". "
    
    # Thêm chunk cuối cùng
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

def parse_rss_feed(feed_url):
    """Parse RSS feed và trả về danh sách bài viết"""
    try:
        feed = feedparser.parse(feed_url)
        articles = []
        
        for entry in feed.entries[:5]:  # Lấy 5 bài mới nhất từ mỗi feed
            try:
                # Lấy thông tin cơ bản
                title = clean_text(entry.title) if hasattr(entry, 'title') else "Không có tiêu đề"
                link = entry.link if hasattr(entry, 'link') else ""
                description = clean_text(entry.description) if hasattr(entry, 'description') else ""
                
                # Parse thời gian
                published = ""
                if hasattr(entry, 'published'):
                    try:
                        pub_date = date_parser.parse(entry.published)
                        published = pub_date.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        published = entry.published
                
                # Lấy nội dung đầy đủ từ link
                full_content = get_full_article_content(link) if link else description
                
                # Tạo chunks từ nội dung đầy đủ
                chunks = create_chunks(full_content, chunk_size=800)
                
                article = {
                    "title": title,
                    "link": link,
                    "description": description,
                    "published": published,
                    "source": urlparse(feed_url).netloc,
                    "full_content": full_content,
                    "chunks": chunks,
                    "total_chunks": len(chunks)
                }
                
                articles.append(article)
                
            except Exception as e:
                logging.error(f"Error processing entry from {feed_url}: {str(e)}")
                continue
        
        return articles
        
    except Exception as e:
        logging.error(f"Error parsing RSS feed {feed_url}: {str(e)}")
        return []

@app.route('/')
def home():
    """Trang chủ API"""
    return jsonify({
        "message": "Vietnam Stock News API",
        "endpoints": {
            "/api/news": "Lấy tất cả tin tức mới nhất",
            "/api/news?source=domain": "Lấy tin từ source cụ thể",
            "/api/news?limit=10": "Giới hạn số lượng bài viết",
            "/api/news?chunk_size=500": "Tùy chỉnh kích thước chunk"
        },
        "sources": [urlparse(feed).netloc for feed in RSS_FEEDS]
    })

@app.route('/api/news')
def get_news():
    """API endpoint để lấy tin tức"""
    try:
        # Lấy parameters
        source_filter = request.args.get('source', '').lower()
        limit = int(request.args.get('limit', 20))
        chunk_size = int(request.args.get('chunk_size', 800))
        
        all_articles = []
        
        # Lấy tin từ tất cả RSS feeds
        for feed_url in RSS_FEEDS:
            # Nếu có filter source, chỉ lấy từ source đó
            if source_filter and source_filter not in urlparse(feed_url).netloc.lower():
                continue
                
            articles = parse_rss_feed(feed_url)
            
            # Tạo lại chunks với kích thước tùy chỉnh nếu cần
            if chunk_size != 800:
                for article in articles:
                    article['chunks'] = create_chunks(article['full_content'], chunk_size)
                    article['total_chunks'] = len(article['chunks'])
            
            all_articles.extend(articles)
        
        # Sắp xếp theo thời gian (mới nhất trước)
        all_articles.sort(key=lambda x: x['published'], reverse=True)
        
        # Giới hạn số lượng
        all_articles = all_articles[:limit]
        
        return jsonify({
            "status": "success",
            "total_articles": len(all_articles),
            "articles": all_articles,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logging.error(f"Error in get_news: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/api/article/<path:article_url>')
def get_single_article(article_url):
    """Lấy nội dung đầy đủ của một bài viết cụ thể"""
    try:
        chunk_size = int(request.args.get('chunk_size', 800))
        
        full_content = get_full_article_content(article_url)
        chunks = create_chunks(full_content, chunk_size)
        
        return jsonify({
            "status": "success",
            "url": article_url,
            "full_content": full_content,
            "chunks": chunks,
            "total_chunks": len(chunks),
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/api/sources')
def get_sources():
    """Lấy danh sách các nguồn tin"""
    sources = []
    for feed_url in RSS_FEEDS:
        domain = urlparse(feed_url).netloc
        sources.append({
            "domain": domain,
            "rss_url": feed_url
        })
    
    return jsonify({
        "status": "success",
        "total_sources": len(sources),
        "sources": sources
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)