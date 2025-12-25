import os
import json
import time
import requests
import feedparser
import re
from bs4 import BeautifulSoup

# --- НАСТРОЙКИ ---
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
YT_API_KEY = os.getenv('YOUTUBE_API_KEY')
YT_CHANNEL_IDS_STR = os.getenv('YOUTUBE_CHANNEL_ID', '') 
BOOSTY_BASE_URL = "https://boosty.to/freyasstory"

STATE_FILE = 'state.json'

def log(message):
    print(f"[LOG] {message}")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log(f"Ошибка чтения state.json: {e}")
    return {"initialized": False, "youtube": {}, "boosty": {}}

def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def send_telegram_notification(caption, photo_url=None):
    if not TOKEN or not CHAT_ID:
        log("ОШИБКА: Секреты не настроены!")
        return False
    
    # Пытаемся отправить фото, если есть URL
    if photo_url:
        url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        payload = {
            "chat_id": CHAT_ID,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "HTML"
        }
        try:
            r = requests.post(url, json=payload, timeout=15)
            if r.status_code == 200:
                return True
            log(f"Telegram API Photo Error: {r.text}")
        except Exception as e:
            log(f"Ошибка отправки фото в TG: {e}")

    # Если фото не отправилось или его нет - шлем текстом
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        log(f"Ошибка отправки текста в TG: {e}")
        return False

def check_single_youtube_channel(state, channel_id, api_key):
    channel_id = channel_id.strip()
    if not channel_id: return state
    log(f"Проверка YouTube: {channel_id}")
    
    video_id, video_title, video_url = None, None, None
    if api_key:
        try:
            api_url = f"https://www.googleapis.com/youtube/v3/search?key={api_key}&channelId={channel_id}&part=snippet,id&order=date&maxResults=1"
            res = requests.get(api_url, timeout=10).json()
            if 'items' in res and res['items']:
                item = res['items'][0]
                video_id = item['id'].get('videoId')
                video_title = item['snippet']['title']
                video_url = f"https://www.youtube.com/watch?v={video_id}"
        except: pass
    if not video_id:
        try:
            feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")
            if feed.entries:
                entry = feed.entries[0]
                video_id, video_title, video_url = entry.yt_videoid, entry.title, entry.link
        except: pass

    if video_id:
        chan_state = state['youtube'].get(channel_id, {})
        if chan_state.get('last_id') != video_id:
            if state.get('initialized') and chan_state.get('last_id'):
                header = "НОВОЕ ВИДЕО ТРЭШ ИСТОРИИ УЖЕ НА ЮТУБ"
                caption = f"{header}\n\n<a href='{video_url}'>{video_title}</a>"
                photo_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
                send_telegram_notification(caption, photo_url)
            state['youtube'][channel_id] = {"last_id": video_id, "title": video_title}
    return state

def check_boosty(state):
    urls_to_try = [BOOSTY_BASE_URL, f"{BOOSTY_BASE_URL}/posts"]
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
    }
    cookies = {'be_adult': '1', 'auth_checked': '1'}

    success = False
    for url in urls_to_try:
        log(f"Попытка доступа к Boosty: {url}")
        try:
            r = requests.get(url, headers=headers, cookies=cookies, timeout=15, allow_redirects=True)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                
                # Извлекаем данные из Meta-тегов
                og_title = soup.find("meta", property="og:title")
                og_image = soup.find("meta", property="og:image")
                og_url = soup.find("meta", property="og:url") # Прямая ссылка на пост
                
                title = og_title.get("content", "") if og_title else ""
                image = og_image.get("content", "") if og_image else None
                post_link = og_url.get("content", BOOSTY_BASE_URL) if og_url else BOOSTY_BASE_URL
                
                # Уникальный ID для отслеживания (заголовок + ссылка)
                content_fingerprint = f"{title}_{post_link}"

                if title:
                    last_id = state['boosty'].get('last_id')
                    if last_id != content_fingerprint:
                        log("Новый пост на Boosty!")
                        if state.get('initialized') and last_id is not None:
                            header = "НОВОЕ ВИДЕО ТРЭШ ИСТОРИИ УЖЕ НА БУСТИ"
                            caption = f"{header}\n\n<a href='{post_link}'>{title}</a>"
                            send_telegram_notification(caption, image)
                        state['boosty']['last_id'] = content_fingerprint
                    else:
                        log("На Boosty без изменений.")
                    success = True
                    break
        except Exception as e:
            log(f"Ошибка Boosty: {e}")
            
    if not success:
        log("Не удалось получить данные с Boosty.")
    return state

def main():
    state = load_state()
    if YT_CHANNEL_IDS_STR:
        for cid in YT_CHANNEL_IDS_STR.split(','):
            state = check_single_youtube_channel(state, cid, YT_API_KEY)
    
    state = check_boosty(state)
    
    if not state.get('initialized'):
        state['initialized'] = True
        log("Инициализация завершена.")
    
    save_state(state)

if __name__ == "__main__":
    main()
