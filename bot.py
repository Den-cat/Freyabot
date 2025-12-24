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
BOOSTY_URL = "https://boosty.to/freyasstory"

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

    # 1. API
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

    # 2. RSS
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
            log(f"Обновлено видео для {channel_id}")
    return state

def check_boosty(state):
    log(f"Проверка Boosty: {BOOSTY_URL}")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7'
        }
        r = requests.get(BOOSTY_URL, headers=headers, timeout=15)
        if r.status_code != 200:
            log(f"Boosty вернул код {r.status_code}")
            return state

        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Метод Meta-тегов (самый надежный для SSR)
        og_title = soup.find("meta", property="og:title")
        og_desc = soup.find("meta", property="og:description")
        
        # Если нашли данные в мете - используем их как "отпечаток" последнего поста
        content_fingerprint = ""
        if og_title: content_fingerprint += og_title.get("content", "")
        if og_desc: content_fingerprint += og_desc.get("content", "")
        
        if not content_fingerprint:
            # Запасной вариант: ищем в скриптах (Boosty хранит данные в начальном стейте)
            script_tags = soup.find_all("script")
            for s in script_tags:
                if "initialState" in s.text:
                    content_fingerprint = str(hash(s.text[:1000]))
                    break

        if not content_fingerprint:
            log("Не удалось определить контент Boosty. Возможно, страница пуста или скрыта.")
            return state

        last_id = state['boosty'].get('last_id')
        if last_id != content_fingerprint:
            log("Обнаружены изменения на странице Boosty!")
            # Постим только если это НЕ первая инициализация канала
            if state.get('initialized') and last_id is not None:
                msg = f"<b>Новый контент на Boosty!</b>\n\nПроверьте свежие обновления в блоге.\n\n<a href='{BOOSTY_URL}'>Перейти на Boosty</a>"
                send_telegram(msg)
            state['boosty']['last_id'] = content_fingerprint
        else:
            log("На Boosty без изменений.")

    except Exception as e:
        log(f"Ошибка парсинга Boosty: {e}")
    return state

def main():
    state = load_state()
    log(f"Статус инициализации: {state.get('initialized')}")
    
    if YT_CHANNEL_IDS_STR:
        for cid in YT_CHANNEL_IDS_STR.split(','):
            state = check_single_youtube_channel(state, cid, YT_API_KEY)
    
    state = check_boosty(state)
    
    if not state.get('initialized'):
        state['initialized'] = True
        log("Первый запуск: состояние сохранено, уведомления начнутся со следующего нового поста.")
    
    save_state(state)

if __name__ == "__main__":
    main()
