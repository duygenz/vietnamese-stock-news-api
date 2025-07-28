from flask import Flask, jsonify, request
import feedparser
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import time
from urllib.parse import urljoin, urlparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import html

app = Flask(**name**)
logging.basicConfig(level=logging.INFO)

# Danh sách RSS feeds

RSS_FEEDS = [
“https://vietstock.vn/830/chung-khoan/co-phieu.rss”,
“https://cafef.vn/thi-truong-chung-khoan.rss”,
“https://vietstock.vn/145/chung-khoan/y-kien-chuyen-gia.rss”,
“https://vietstock.vn/737/doanh-nghiep/hoat-dong-kinh-doanh.rss”,
“https://vietstock.vn/1328/dong-duong/thi-truong-chung-khoan.rss”,
“https://vneconomy.vn/chung-khoan.rss”,
“https://vneconomy.vn/tin-moi.rss”,
“https://vneconomy.vn/tai-chinh.rss”,
“https://vneconomy.vn/nhip-cau-doanh-nghiep.rss”,
“https://vneconomy.vn/thi-truong.rss”
]

def clean_text(text):
“”“Làm sạch và chuẩn hóa text”””
if not text:
return “”

```
# Decode HTML entities
text = html.unescape(text)

# Remove HTML tags
text = re.sub(r'<[^>]+>', '', text)

# Clean up whitespace
text = re.sub(r'\s+', ' ', text)
text = text.strip()

return text
```

def extract_full_content(url, source_domain):
“”“Trích xuất toàn bộ nội dung bài viết từ URL”””
try:
headers = {
‘User-Agent’: ‘Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36’
}

```
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Xóa các thẻ không cần thiết
    for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'advertisement']):
        tag.decompose()
    
    content = ""
    
    # Các selector phù hợp với từng website
    if 'vietstock.vn' in source_domain:
        selectors = [
            '.detail-content',
            '.article-content',
            '.content-detail',
            '.post-content',
            '[class*="content"]'
        ]
    elif 'cafef.vn' in source_domain:
        selectors = [
            '.detail-content',
            '.sapo',
            '.content',
            '.article-body',
            '[class*="detail"]'
        ]
    elif 'vneconomy.vn' in source_domain:
        selectors = [
            '.detail-content',
            '.article-content',
            '.content-detail',
            '.entry-content',
            '[class*="content"]'
        ]
    else:
        selectors = [
            '.content',
            '.article-content',
            '.post-content',
            '.detail-content',
            '.entry-content'
        ]
    
    # Thử từng selector
    for selector in selectors:
        content_element = soup.select_one(selector)
        if content_element:
            content = content_element.get_text(separator=' ', strip=True)
            if len(content) > 100:  # Chỉ lấy nếu content đủ dài
                break
    
    # Nếu không tìm thấy content với selector, thử tìm trong body
    if not content or len(content) < 100:
        paragraphs = soup.find_all('p')
        content = ' '.join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20])
    
    return clean_text(content)
    
except Exception as e:
    logging.error(f"Error extracting content from {url}: {str(e)}")
    return ""
```

def parse_rss_feed(feed_url):
“”“Parse một RSS feed và trả về danh sách bài viết”””
try:
feed = feedparser.parse(feed_url)
articles = []

```
    source_domain = urlparse(feed_url).netloc
    
    for entry in feed.entries[:5]:  # Lấy 5 bài mới nhất từ mỗi feed
        try:
            # Lấy thông tin cơ bản
            title = clean_text(entry.get('title', ''))
            link = entry.get('link', '')
            summary = clean_text(entry.get('summary', ''))
            
            # Parse thời gian
            published = entry.get('published', '')
            try:
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_date = datetime(*entry.published_parsed[:6])
                else:
                    published_date = datetime.now()
            except:
                published_date = datetime.now()
            
            # Lấy toàn bộ nội dung bài viết
            full_content = extract_full_content(link, source_domain)
            
            # Nếu không lấy được full content, dùng summary
            if not full_content and summary:
                full_content = summary
            
            if title and link and full_content:
                articles.append({
                    'title': title,
                    'link': link,
                    'summary': summary,
                    'full_content': full_content,
                    'published': published_date.isoformat(),
                    'source': source_domain,
                    'feed_url': feed_url
                })
                
        except Exception as e:
            logging.error(f"Error parsing entry from {feed_url}: {str(e)}")
            continue
    
    return articles
    
except Exception as e:
    logging.error(f"Error parsing RSS feed {feed_url}: {str(e)}")
    return []
```

def create_chunks(articles, chunk_size=5):
“”“Chia danh sách bài viết thành các chunks”””
chunks = []
for i in range(0, len(articles), chunk_size):
chunk = articles[i:i + chunk_size]
chunks.append({
‘chunk_id’: len(chunks) + 1,
‘articles_count’: len(chunk),
‘articles’: chunk
})
return chunks

@app.route(’/api/news’, methods=[‘GET’])
def get_news():
“”“API endpoint để lấy tin tức”””
try:
# Lấy parameters
chunk_size = int(request.args.get(‘chunk_size’, 5))
max_articles = int(request.args.get(‘max_articles’, 50))
source = request.args.get(‘source’, ‘’).lower()

```
    # Filter RSS feeds nếu có source được chỉ định
    feeds_to_parse = RSS_FEEDS
    if source:
        feeds_to_parse = [feed for feed in RSS_FEEDS if source in feed.lower()]
        if not feeds_to_parse:
            return jsonify({
                'error': f'No feeds found for source: {source}',
                'available_sources': ['vietstock', 'cafef', 'vneconomy']
            }), 400
    
    all_articles = []
    
    # Sử dụng ThreadPoolExecutor để parse RSS feeds song song
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_feed = {executor.submit(parse_rss_feed, feed): feed for feed in feeds_to_parse}
        
        for future in as_completed(future_to_feed):
            feed = future_to_feed[future]
            try:
                articles = future.result()
                all_articles.extend(articles)
            except Exception as e:
                logging.error(f"Error getting articles from {feed}: {str(e)}")
    
    # Sắp xếp theo thời gian mới nhất
    all_articles.sort(key=lambda x: x['published'], reverse=True)
    
    # Giới hạn số lượng bài viết
    all_articles = all_articles[:max_articles]
    
    # Tạo chunks
    chunks = create_chunks(all_articles, chunk_size)
    
    return jsonify({
        'success': True,
        'total_articles': len(all_articles),
        'total_chunks': len(chunks),
        'chunk_size': chunk_size,
        'timestamp': datetime.now().isoformat(),
        'sources_parsed': len(feeds_to_parse),
        'chunks': chunks
    })
    
except Exception as e:
    logging.error(f"Error in get_news: {str(e)}")
    return jsonify({
        'success': False,
        'error': str(e),
        'timestamp': datetime.now().isoformat()
    }), 500
```

@app.route(’/api/news/chunk/<int:chunk_id>’, methods=[‘GET’])
def get_chunk(chunk_id):
“”“Lấy một chunk cụ thể”””
try:
chunk_size = int(request.args.get(‘chunk_size’, 5))

```
    all_articles = []
    
    # Parse tất cả RSS feeds
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_feed = {executor.submit(parse_rss_feed, feed): feed for feed in RSS_FEEDS}
        
        for future in as_completed(future_to_feed):
            try:
                articles = future.result()
                all_articles.extend(articles)
            except Exception as e:
                logging.error(f"Error getting articles: {str(e)}")
    
    # Sắp xếp theo thời gian
    all_articles.sort(key=lambda x: x['published'], reverse=True)
    
    # Tạo chunks
    chunks = create_chunks(all_articles, chunk_size)
    
    # Tìm chunk theo ID
    target_chunk = None
    for chunk in chunks:
        if chunk['chunk_id'] == chunk_id:
            target_chunk = chunk
            break
    
    if not target_chunk:
        return jsonify({
            'success': False,
            'error': f'Chunk {chunk_id} not found',
            'available_chunks': len(chunks)
        }), 404
    
    return jsonify({
        'success': True,
        'chunk': target_chunk,
        'timestamp': datetime.now().isoformat()
    })
    
except Exception as e:
    return jsonify({
        'success': False,
        'error': str(e)
    }), 500
```

@app.route(’/api/sources’, methods=[‘GET’])
def get_sources():
“”“Lấy danh sách các nguồn RSS”””
sources = {}
for feed in RSS_FEEDS:
domain = urlparse(feed).netloc
if domain not in sources:
sources[domain] = []
sources[domain].append(feed)

```
return jsonify({
    'success': True,
    'sources': sources,
    'total_feeds': len(RSS_FEEDS)
})
```

@app.route(’/health’, methods=[‘GET’])
def health_check():
“”“Health check endpoint”””
return jsonify({
‘status’: ‘healthy’,
‘timestamp’: datetime.now().isoformat(),
‘version’: ‘1.0.0’
})

@app.route(’/’, methods=[‘GET’])
def home():
“”“Trang chủ với hướng dẫn sử dụng API”””
return jsonify({
‘message’: ‘Vietnamese Stock News API’,
‘version’: ‘1.0.0’,
‘endpoints’: {
‘GET /api/news’: ‘Lấy tin tức dưới dạng chunks’,
‘GET /api/news/chunk/<id>’: ‘Lấy một chunk cụ thể’,
‘GET /api/sources’: ‘Lấy danh sách nguồn RSS’,
‘GET /health’: ‘Health check’
},
‘parameters’: {
‘chunk_size’: ‘Số bài viết trong mỗi chunk (default: 5)’,
‘max_articles’: ‘Số bài viết tối đa (default: 50)’,
‘source’: ‘Filter theo nguồn (vietstock, cafef, vneconomy)’
},
‘example_usage’: [
‘/api/news?chunk_size=3&max_articles=30’,
‘/api/news?source=vietstock’,
‘/api/news/chunk/1’
]
})

if **name** == ‘**main**’:
port = int(os.environ.get(‘PORT’, 5000))
app.run(host=‘0.0.0.0’, port=port, debug=False)
