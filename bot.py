import os
import json
import time
import requests
import feedparser
from bs4 import BeautifulSoup

# --- НАСТРОЙКИ ИЗ СЕКРЕТОВ GITHUB ---
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
YT_API_KEY = os.getenv('YOUTUBE_API_KEY')

# Получаем список ID через запятую. Если пусто, используем пустую строку.
# Пример в секретах: UC_ID1, UC_ID2, UC_ID3
YT_CHANNEL_IDS_STR = os.getenv('YOUTUBE_CHANNEL_ID', '') 
BOOSTY_URL = "https://boosty.to/freyasstory"

STATE_FILE = 'state.json'

def log(message):
    print(f"[LOG] {message}")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"initialized": False, "youtube": {}, "boosty": {}}

def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        log("ОШИБКА: Токен или Chat ID не настроены!")
        return False
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        r = requests.post(url, json=payload)
        if r.status_code == 200:
            log("Сообщение успешно отправлено в Telegram!")
            return True
        else:
            log(f"ОШИБКА TG: {r.text}")
            return False
    except Exception as e:
        log(f"Ошибка при отправке: {e}")
        return False

def check_single_youtube_channel(state, channel_id, api_key):
    channel_id = channel_id.strip()
    if not channel_id:
        return state

    log(f"Проверяю канал: {channel_id}")
    video_id = None
    video_title = None
    video_url = None

    # ПРИОРЕТЕТ 1: YouTube API
    if api_key:
        api_url = f"https://www.googleapis.com/youtube/v3/search?key={api_key}&channelId={channel_id}&part=snippet,id&order=date&maxResults=1"
        try:
            res = requests.get(api_url).json()
            if 'items' in res and len(res['items']) > 0:
                item = res['items'][0]
                if 'videoId' in item['id']:
                    video_id = item['id']['videoId']
                    video_title = item['snippet']['title']
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
        except Exception as e:
            log(f"Ошибка API для {channel_id}: {e}")

    # ПРИОРЕТЕТ 2: RSS (если API не сработало)
    if not video_id:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        try:
            feed = feedparser.parse(rss_url)
            if feed.entries:
                entry = feed.entries[0]
                video_id = entry.yt_videoid
                video_title = entry.title
                video_url = entry.link
        except Exception as e:
            log(f"Ошибка RSS для {channel_id}: {e}")

    if not video_id:
        log(f"Данные для канала {channel_id} не найдены.")
        return state

    # Проверка на новизну для конкретного канала
    # Теперь структура в state: state['youtube'][channel_id] = { "last_id": "..." }
    channel_state = state['youtube'].get(channel_id, {})
    last_id = channel_state.get('last_id')

    if last_id != video_id:
        log(f"НОВОЕ ВИДЕО на {channel_id}: {video_title}")
        
        # Отправляем только если это не самый первый запуск для этого канала
        # ИЛИ если система в целом уже инициализирована
        if state.get('initialized') and last_id is not None:
            msg = f"<b>Новое видео на YouTube!</b>\n\n{video_title}\n\n<a href='{video_url}'>Смотреть на YouTube</a>"
            send_telegram(msg)
        
        # Обновляем состояние именно для этого канала
        state['youtube'][channel_id] = {
            "last_id": video_id,
            "last_title": video_title,
            "updated_at": int(time.time())
        }
    else:
        log(f"На канале {channel_id} изменений нет.")
    
    return state

def check_boosty(state):
    log("Проверяю Boosty...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        r = requests.get(BOOSTY_URL, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, 'lxml')
        
        # Пытаемся найти посты
        posts = soup.find_all('div', class_=lambda x: x and 'Post_root' in x)
        if not posts:
            log("Посты на Boosty не найдены (возможно, закрытый профиль или смена дизайна).")
            return state

        latest_post = posts[0]
        # Генерируем уникальный ключ поста
        post_id = str(hash(latest_post.text[:200])) 

        last_id = state['boosty'].get('last_id')
        if last_id != post_id:
            log("НОВЫЙ ПОСТ НА BOOSTY!")
            if state.get('initialized') and last_id is not None:
                msg = f"<b>Новый пост на Boosty!</b>\n\nЭксклюзивный контент уже доступен.\n\n<a href='{BOOSTY_URL}'>Открыть Boosty</a>"
                send_telegram(msg)
            state['boosty']['last_id'] = post_id
        else:
            log("На Boosty новых постов нет.")
    except Exception as e:
        log(f"Ошибка Boosty: {e}")
    
    return state

def main():
    log("=== Запуск цикла проверки ===")
    state = load_state()
    
    # Обработка YouTube каналов
    if YT_CHANNEL_IDS_STR:
        ids = YT_CHANNEL_IDS_STR.split(',')
        for cid in ids:
            state = check_single_youtube_channel(state, cid, YT_API_KEY)
    else:
        log("ВНИМАНИЕ: Список YouTube каналов пуст (YOUTUBE_CHANNEL_ID).")

    # Обработка Boosty
    state = check_boosty(state)
    
    # Флаг первой общей инициализации
    if not state.get('initialized'):
        log("Первичная настройка завершена. База данных обновлена.")
        state['initialized'] = True
    
    save_state(state)
    log("=== Проверка завершена успешно ===")

if __name__ == "__main__":
    main()
