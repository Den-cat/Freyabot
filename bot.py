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

def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        log("ОШИБКА: Секреты не настроены!")
        return False
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        log(f"Ошибка отправки в TG: {e}")
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
                send_telegram(f"<b>Новое видео!</b>\n\n{video_title}\n\n<a href='{video_url}'>Смотреть</a>")
            state['youtube'][channel_id] = {"last_id": video_id, "title": video_title}
    return state

def check_boosty(state):
    # Пробуем несколько вариантов URL
    urls_to_try = [BOOSTY_BASE_URL, f"{BOOSTY_BASE_URL}/posts"]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://www.google.com/',
        'Cache-Control': 'no-cache'
    }
    
    # Куки для имитации подтверждения возраста и базовой сессии
    cookies = {
        'be_adult': '1',
        'auth_checked': '1'
    }

    success = False
    for url in urls_to_try:
        log(f"Попытка доступа к Boosty: {url}")
        try:
            r = requests.get(url, headers=headers, cookies=cookies, timeout=15, allow_redirects=True)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                
                # Ищем заголовок поста или описание в Meta-тегах
                og_title = soup.find("meta", property="og:title")
                og_desc = soup.find("meta", property="og:description")
                
                content_fingerprint = ""
                if og_title: content_fingerprint += og_title.get("content", "")
                if og_desc: content_fingerprint += og_desc.get("content", "")
                
                # Если мета-теги пустые, ищем в скриптах состояния
                if not content_fingerprint:
                    scripts = soup.find_all("script")
                    for s in scripts:
                        if "initialState" in s.text:
                            # Берем часть строки состояния как ID
                            content_fingerprint = str(hash(s.text[:2000]))
                            break

                if content_fingerprint:
                    last_id = state['boosty'].get('last_id')
                    if last_id != content_fingerprint:
                        log("Изменения на Boosty найдены!")
                        if state.get('initialized') and last_id is not None:
                            send_telegram(f"<b>Новый контент на Boosty!</b>\n\nСвежее обновление уже в блоге.\n\n<a href='{BOOSTY_BASE_URL}'>Перейти на Boosty</a>")
                        state['boosty']['last_id'] = content_fingerprint
                    else:
                        log("На Boosty всё по-прежнему.")
                    success = True
                    break
            else:
                log(f"URL {url} вернул код {r.status_code}")
        except Exception as e:
            log(f"Ошибка при запросе {url}: {e}")
            
    if not success:
        log("КРИТИЧЕСКАЯ ОШИБКА: Не удалось получить данные с Boosty ни по одной из ссылок.")
        
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
