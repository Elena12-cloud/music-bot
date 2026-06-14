import logging
import os
import sqlite3
import uuid
import urllib.parse
from datetime import datetime
from typing import Optional

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import (
    Update, ReplyKeyboardRemove,
    InlineKeyboardButton, InlineKeyboardMarkup,
    InlineQueryResultArticle, InputTextMessageContent,
)
from telegram.ext import (
    Application, CommandHandler, ConversationHandler,
    MessageHandler, CallbackQueryHandler, InlineQueryHandler,
    ContextTypes, filters,
)
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
DB_PATH = os.path.join(os.path.dirname(__file__), "playlists.db")

MUSIC_FACTS = [
    "🎵 Битлз записали более 200 песен за свою карьеру, но ни один из них не умел читать ноты.",
    "🎸 Гитара «Stratocaster» от Fender была создана в 1954 году и до сих пор остаётся одной из самых популярных.",
    "🎹 Людвиг ван Бетховен написал свою 9-ю симфонию, будучи полностью глухим.",
    "🎤 Фредди Меркьюри обладал диапазоном голоса почти в 4 октавы.",
    "🎧 Первый альбом, проданный миллионным тиражом на CD — это Dire Straits «Brothers in Arms» (1985).",
    "🎺 Джаз зародился в Новом Орлеане в конце XIX века как смесь блюза, рэгтайма и европейской гармонии.",
    "🥁 Карлос Сантана продал более 100 миллионов альбомов — больше, чем многие рок-легенды.",
    "🎻 Скрипка Страдивари звучит лучше современных инструментов — учёные до сих пор не могут объяснить почему.",
    "🎵 Самая продаваемая песня всех времён — «White Christmas» Бинга Кросби (50+ млн копий).",
    "🎸 Джими Хендрикс никогда не брал уроков музыки — он был самоучкой.",
    "🎤 Мадонна — самая коммерчески успешная певица всех времён по версии Книги рекордов Гиннеса.",
    "🎹 Моцарт написал свою первую симфонию в возрасте 8 лет.",
    "🎧 Стриминговые сервисы воспроизводят более 100 миллиардов треков в месяц по всему миру.",
    "🎺 Луи Армстронг был арестован в 11 лет — именно тогда он начал учиться играть на трубе в исправительном заведении.",
    "🥁 Ударные — один из древнейших инструментов: первые барабаны найдены в Китае и датируются 5500 годом до н.э.",
]

QUESTIONS = [
    "🎵 *Вопрос 1 из 8*\n\nКакая песня возвращает вас к *особым событиям* в жизни?\n\n_Напишите название и исполнителя_",
    "🎵 *Вопрос 2 из 8*\n\nКакая песня возвращает вас в *воспоминания юности* (18–30 лет)?\n\n_Напишите название и исполнителя_",
    "🎵 *Вопрос 3 из 8*\n\nКакая песня характеризует вас как *профессионала своего дела*?\n\n_Напишите название и исполнителя_",
    "🎵 *Вопрос 4 из 8*\n\nПод какую песню вам *всегда захочется танцевать*?\n\n_Напишите название и исполнителя_",
    "🎵 *Вопрос 5 из 8*\n\nКакую песню вам *всегда хочется петь*?\n\n_Напишите название и исполнителя_",
    "🎵 *Вопрос 6 из 8*\n\nКакую музыку вы слушаете когда хотите *успокоиться и расслабиться*?\n\n_Напишите название или жанр_",
    "🎵 *Вопрос 7 из 8*\n\nКакая музыка помогает вам *сосредоточиться на работе*?\n\n_Напишите название или жанр_",
    "🎵 *Вопрос 8 из 8*\n\nЕсли бы ваша жизнь была фильмом — какая песня звучала бы в *финальных титрах*?\n\n_Напишите название и исполнителя_",
]

LABELS = [
    "🎭 Особые события", "🌟 Воспоминания юности", "💼 Профессионал",
    "💃 Танцевальная", "🎤 Любимая для пения", "🧘 Расслабление",
    "🎯 Концентрация", "🎬 Финальные титры жизни",
]

MOODS = {
    "грустно": "sad melancholic ballad",
    "грусть": "sad melancholic ballad",
    "весело": "happy upbeat pop",
    "радость": "happy upbeat pop",
    "энергия": "energetic workout",
    "спорт": "energetic workout",
    "романтика": "romantic love song",
    "любовь": "romantic love song",
    "спокойно": "calm relaxing ambient",
    "релакс": "calm relaxing ambient",
    "работа": "focus concentration instrumental",
    "концентрация": "focus concentration instrumental",
    "вечеринка": "party dance hits",
    "танцы": "party dance hits",
}

Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8 = range(8)

# ─── База данных ──────────────────────────────────────────────────────────────

def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TEXT,
            referred_by INTEGER,
            is_premium INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            created_at TEXT NOT NULL,
            tracks TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS votes (
            user_id INTEGER NOT NULL,
            track_key TEXT NOT NULL,
            vote INTEGER NOT NULL,
            artist TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, track_key)
        );
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            track_name TEXT NOT NULL,
            artist TEXT NOT NULL,
            yt_link TEXT,
            preview_url TEXT,
            cover_url TEXT,
            added_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS weekly_subscribers (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            taste_profile TEXT
        );
        CREATE TABLE IF NOT EXISTS group_sessions (
            group_id TEXT PRIMARY KEY,
            creator_id INTEGER NOT NULL,
            members TEXT NOT NULL,
            answers TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def register_user(user_id: int, username: str, first_name: str, referred_by: int = None) -> bool:
    """Register new user. Returns True if new user."""
    conn = sqlite3.connect(DB_PATH)
    existing = conn.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO users (user_id, username, first_name, joined_at, referred_by) VALUES (?, ?, ?, ?, ?)",
            (user_id, username or "", first_name or "", datetime.now().strftime("%d.%m.%Y %H:%M"), referred_by)
        )
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False


def get_user(user_id: int) -> Optional[tuple]:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row


def is_premium(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT is_premium FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return bool(row and row[0])


def get_referral_count(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (user_id,)).fetchone()[0]
    conn.close()
    return count


def upgrade_to_premium(user_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET is_premium=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def save_playlist(user_id: int, username: str, tracks: list) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO playlists (user_id, username, created_at, tracks) VALUES (?, ?, ?, ?)",
        (user_id, username or "", datetime.now().strftime("%d.%m.%Y %H:%M"), "\n".join(tracks))
    )
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def get_user_playlists(user_id: int) -> list:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, created_at, tracks FROM playlists WHERE user_id=? ORDER BY id DESC LIMIT 5", (user_id,)
    ).fetchall()
    conn.close()
    return rows


def get_playlist_by_id(pid: int) -> Optional[tuple]:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id, username, created_at, tracks FROM playlists WHERE id=?", (pid,)).fetchone()
    conn.close()
    return row


def save_vote(user_id: int, track_key: str, vote: int, artist: str = "") -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO votes (user_id, track_key, vote, artist, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, track_key, vote, artist, datetime.now().strftime("%d.%m.%Y %H:%M"))
    )
    conn.commit()
    conn.close()


def get_top_tracks(limit: int = 10) -> list:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT track_key, SUM(vote) as score, COUNT(*) as votes FROM votes GROUP BY track_key ORDER BY score DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return rows


def get_user_profile(user_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    liked = conn.execute(
        "SELECT track_key, artist FROM votes WHERE user_id=? AND vote=1 ORDER BY created_at DESC LIMIT 10",
        (user_id,)
    ).fetchall()
    disliked = conn.execute(
        "SELECT COUNT(*) FROM votes WHERE user_id=? AND vote=-1", (user_id,)
    ).fetchone()[0]
    total_votes = conn.execute("SELECT COUNT(*) FROM votes WHERE user_id=?", (user_id,)).fetchone()[0]
    playlist_count = conn.execute("SELECT COUNT(*) FROM playlists WHERE user_id=?", (user_id,)).fetchone()[0]
    conn.close()
    artists = list(set([r[1] for r in liked if r[1]]))[:5]
    return {"liked": liked, "disliked": disliked, "total_votes": total_votes,
            "playlist_count": playlist_count, "artists": artists}


def add_favorite(user_id: int, track_name: str, artist: str, yt_link: str, preview_url: str, cover_url: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO favorites (user_id, track_name, artist, yt_link, preview_url, cover_url, added_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, track_name, artist, yt_link, preview_url, cover_url, datetime.now().strftime("%d.%m.%Y %H:%M"))
    )
    conn.commit()
    conn.close()


def get_favorites(user_id: int) -> list:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, track_name, artist, yt_link FROM favorites WHERE user_id=? ORDER BY id DESC LIMIT 10", (user_id,)
    ).fetchall()
    conn.close()
    return rows


def remove_favorite(fav_id: int, user_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM favorites WHERE id=? AND user_id=?", (fav_id, user_id))
    conn.commit()
    conn.close()


def get_stats() -> dict:
    conn = sqlite3.connect(DB_PATH)
    users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    playlists = conn.execute("SELECT COUNT(*) FROM playlists").fetchone()[0]
    votes = conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
    favorites = conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0]
    conn.close()
    return {"users": users, "playlists": playlists, "votes": votes, "favorites": favorites}


def subscribe_weekly(user_id: int, username: str, taste: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO weekly_subscribers (user_id, username, taste_profile) VALUES (?, ?, ?)",
        (user_id, username or "", taste)
    )
    conn.commit()
    conn.close()


def unsubscribe_weekly(user_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM weekly_subscribers WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def get_all_weekly_subscribers() -> list:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT user_id, taste_profile FROM weekly_subscribers").fetchall()
    conn.close()
    return rows


def get_all_users() -> list:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    return [r[0] for r in rows]


# ─── API ──────────────────────────────────────────────────────────────────────

def youtube_link(query: str) -> str:
    return f"https://music.youtube.com/search?q={urllib.parse.quote(query)}"


async def search_deezer(query: str, limit: int = 1) -> Optional[dict]:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://api.deezer.com/search", params={"q": query, "limit": limit}, timeout=10)
            data = resp.json()
        tracks = data.get("data", [])
        return tracks[0] if tracks else None
    except Exception as e:
        logger.warning(f"Deezer error: {e}")
        return None


async def search_deezer_many(query: str, limit: int = 5) -> list:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://api.deezer.com/search", params={"q": query, "limit": limit}, timeout=10)
            data = resp.json()
        return data.get("data", [])
    except Exception as e:
        logger.warning(f"Deezer error: {e}")
        return []


async def find_cover_version(track_name: str, original_artist: str) -> Optional[dict]:
    """Find a cover version: same song, different artist."""
    try:
        async with httpx.AsyncClient() as client:
            # Сначала ищем по названию песни
            for query in [track_name, f"{track_name} cover"]:
                resp = await client.get("https://api.deezer.com/search", params={"q": query, "limit": 20}, timeout=10)
                tracks = resp.json().get("data", [])
                for track in tracks:
                    artist = track.get("artist", {}).get("name", "")
                    if artist.lower() != original_artist.lower():
                        return track
        return None
    except Exception as e:
        logger.warning(f"Cover search error: {e}")
        return None


async def get_similar(artist: str, track: str) -> Optional[dict]:
    """Get similar track via Last.fm, fallback to Deezer search by artist."""
    # Пробуем Last.fm
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://ws.audioscrobbler.com/2.0/",
                params={"method": "track.getSimilar", "artist": artist, "track": track,
                        "api_key": LASTFM_API_KEY, "format": "json", "limit": 5},
                timeout=10
            )
            data = resp.json()
        similar = data.get("similartracks", {}).get("track", [])
        if similar:
            return similar[0]
    except Exception as e:
        logger.warning(f"LastFM error: {e}")

    # Фолбэк: ищем другие треки того же исполнителя на Deezer
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://api.deezer.com/search",
                                    params={"q": f"artist:\"{artist}\"", "limit": 10}, timeout=10)
            tracks = resp.json().get("data", [])
        track_lower = track.lower()
        for t in tracks:
            if t.get("title", "").lower() != track_lower:
                # Возвращаем как псевдо-объект Last.fm
                return {
                    "name": t.get("title", ""),
                    "artist": {"name": t.get("artist", {}).get("name", artist)},
                    "_deezer": t,  # уже готовый объект Deezer
                }
    except Exception as e:
        logger.warning(f"Deezer fallback error: {e}")

    return None


async def search_by_lyrics(lyrics: str) -> Optional[str]:
    """Search song by lyrics fragment using lyrics.ovh."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"https://api.lyrics.ovh/suggest/{urllib.parse.quote(lyrics)}", timeout=10)
            data = resp.json()
        tracks = data.get("data", [])
        if tracks:
            t = tracks[0]
            return f"{t.get('artist', {}).get('name', '')} — {t.get('title', '')}"
        return None
    except Exception as e:
        logger.warning(f"Lyrics search error: {e}")
        return None


# ─── Карточка трека ───────────────────────────────────────────────────────────

async def send_track_card(update: Update, label: str, track: dict,
                           is_recommendation: bool = False,
                           recommendation_label: Optional[str] = None) -> str:
    name = track.get("title", "")
    artist = track.get("artist", {}).get("name", "")
    cover = track.get("album", {}).get("cover_big") or track.get("album", {}).get("cover_medium", "")
    preview_url = track.get("preview", "")
    yt = youtube_link(f"{artist} {name}")
    track_key = f"{artist}::{name}"

    if recommendation_label:
        prefix = recommendation_label
    elif is_recommendation:
        prefix = "✨ *Похожий трек:*"
    else:
        prefix = f"*{label}*"

    caption = f"{prefix}\n🎵 *{name}*\n👤 {artist}\n\n[Слушать на YouTube Music]({yt})"

    vote_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("👍", callback_data=f"vote_up::{track_key}::{artist}"),
        InlineKeyboardButton("👎", callback_data=f"vote_down::{track_key}::{artist}"),
        InlineKeyboardButton("⭐ В избранное", callback_data=f"fav::{name}::{artist}::{yt}::{preview_url}::{cover}"),
    ]])

    try:
        if cover:
            await update.message.reply_photo(photo=cover, caption=caption, parse_mode="Markdown")
        else:
            await update.message.reply_text(caption, parse_mode="Markdown", disable_web_page_preview=True)
        if preview_url:
            await update.message.reply_audio(
                audio=preview_url, title=name, performer=artist,
                caption="🎧 Превью 30 сек", reply_markup=vote_markup,
            )
        else:
            await update.message.reply_text("Оцените:", reply_markup=vote_markup)
    except Exception as e:
        logger.warning(f"Error sending track card: {e}")
        await update.message.reply_text(caption, parse_mode="Markdown",
                                        disable_web_page_preview=True, reply_markup=vote_markup)

    tag = "✨ Рек." if is_recommendation else label
    return f"{tag}: {name} — {artist} | {yt}"


# ─── Сборка плейлиста ─────────────────────────────────────────────────────────

async def build_playlist(update: Update, context: ContextTypes.DEFAULT_TYPE,
                          answers: list, save: bool = True, premium: bool = False) -> list:
    user = update.effective_user
    track_lines = []
    limit = len(LABELS) if not premium else len(LABELS)  # для премиум — больше рекомендаций

    await update.message.reply_text("🎵 *Ваш персональный плейлист*", parse_mode="Markdown")

    for answer, label in zip(answers[:limit], LABELS[:limit]):
        track = await search_deezer(answer)
        if track:
            line = await send_track_card(update, label, track, is_recommendation=False)
            track_lines.append(line)

            artist = track.get("artist", {}).get("name", "")
            name = track.get("title", "")

            # Кавер-версия
            cover_track = await find_cover_version(name, artist)
            if cover_track:
                cover_artist = cover_track.get("artist", {}).get("name", "")
                line_cover = await send_track_card(
                    update, label, cover_track, is_recommendation=True,
                    recommendation_label=f"🎸 *Другое исполнение:* {name} — {cover_artist}",
                )
                track_lines.append(line_cover)

            # Похожий трек
            similar_lastfm = await get_similar(artist, name)
            if similar_lastfm:
                # Если фолбэк уже вернул готовый Deezer-объект
                if "_deezer" in similar_lastfm:
                    similar_deezer = similar_lastfm["_deezer"]
                else:
                    s_name = similar_lastfm.get("name", "")
                    s_artist = (similar_lastfm.get("artist", {}).get("name", "")
                                if isinstance(similar_lastfm.get("artist"), dict)
                                else similar_lastfm.get("artist", ""))
                    similar_deezer = await search_deezer(f"{s_artist} {s_name}")
                if similar_deezer:
                    line2 = await send_track_card(update, label, similar_deezer, is_recommendation=True)
                    track_lines.append(line2)

            # Для премиум — ещё 2 дополнительных рекомендации
            if premium:
                extra_tracks = await search_deezer_many(f"{artist} similar", limit=5)
                for et in extra_tracks[:2]:
                    if et.get("artist", {}).get("name", "").lower() != artist.lower():
                        line_extra = await send_track_card(update, label, et, is_recommendation=True,
                                                           recommendation_label="💎 *Премиум рекомендация:*")
                        track_lines.append(line_extra)
                        break
        else:
            yt = youtube_link(answer)
            await update.message.reply_text(f"*{label}*\n🎵 [{answer}]({yt})",
                                            parse_mode="Markdown", disable_web_page_preview=True)
            track_lines.append(f"{label}: {answer} | {yt}")

    if save and track_lines:
        playlist_id = save_playlist(user.id, user.username or user.first_name, track_lines)
        taste = ", ".join(answers[:3])
        subscribe_weekly(user.id, user.username or user.first_name, taste)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Поделиться плейлистом", switch_inline_query=f"playlist_{playlist_id}")],
            [InlineKeyboardButton("📋 Мои плейлисты", callback_data="my_playlists")],
            [InlineKeyboardButton("🔔 Еженедельный плейлист: ВКЛ", callback_data="weekly_on")],
        ])
        await update.message.reply_text(
            "🎧 Приятного прослушивания!\n\n_Плейлист сохранён в вашей истории_",
            parse_mode="Markdown", reply_markup=keyboard,
        )

    return track_lines


# ─── Команды ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    args = context.args

    # Реферальная система
    referred_by = None
    if args and args[0].startswith("ref_"):
        try:
            referred_by = int(args[0].split("_")[1])
        except (IndexError, ValueError):
            pass

    # Групповой режим
    if args and args[0].startswith("group_"):
        group_id = args[0].split("_", 1)[1]
        context.user_data["group_id"] = group_id
        context.user_data["answers"] = []
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}! Вас пригласили в *групповой плейлист*.\n\n"
            "Ответьте на вопросы — и я добавлю вашу музыку в общий список! 🎵",
            parse_mode="Markdown",
        )
        await update.message.reply_text(QUESTIONS[0], parse_mode="Markdown")
        return Q1

    is_new = register_user(user.id, user.username, user.first_name, referred_by)

    # Если новый пользователь — онбординг
    if is_new:
        if referred_by:
            ref_count = get_referral_count(referred_by)
            if ref_count >= 3:
                upgrade_to_premium(referred_by)
                try:
                    await context.bot.send_message(
                        chat_id=referred_by,
                        text="🎉 Поздравляем! Вы пригласили 3 друзей и получили *Премиум* навсегда!\n"
                             "Теперь ваши плейлисты будут расширенными 🎧",
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

        await update.message.reply_text(
            f"👋 Добро пожаловать, {user.first_name}!\n\n"
            "🎵 *Я — ваш персональный музыкальный бот*\n\n"
            "Вот что я умею:\n"
            "• Создаю *персональный плейлист* по 8 вопросам\n"
            "• Нахожу *кавер-версии* ваших любимых песен\n"
            "• Предлагаю *похожие треки*\n"
            "• Присылаю *30-секундные превью* прямо в Telegram\n"
            "• Делаю *плейлист для компании*\n"
            "• Шлю новый плейлист *каждую неделю*\n\n"
            "Поехали! 🚀",
            parse_mode="Markdown",
        )
    else:
        premium_badge = " 💎" if is_premium(user.id) else ""
        await update.message.reply_text(
            f"🎵 Привет, {user.first_name}{premium_badge}! Выберите режим:",
            parse_mode="Markdown",
        )

    context.user_data["answers"] = []

    # Проверяем статус подписки
    conn = sqlite3.connect(DB_PATH)
    is_subscribed = conn.execute("SELECT 1 FROM weekly_subscribers WHERE user_id=?", (user.id,)).fetchone()
    conn.close()
    sub_btn = ("🔕 Отписаться от рассылки", "weekly_off") if is_subscribed else ("🔔 Подписаться на плейлист недели", "weekly_on_start")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎵 Мой плейлист", callback_data="solo_start")],
        [InlineKeyboardButton("👥 Плейлист для компании", callback_data="group_start")],
        [InlineKeyboardButton("💎 Премиум плейлист", callback_data="premium_start")],
        [InlineKeyboardButton(sub_btn[0], callback_data=sub_btn[1])],
    ])
    await update.message.reply_text("Выберите тип плейлиста:", reply_markup=keyboard)
    return Q1


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answer = update.message.text.strip()
    context.user_data["answers"].append(answer)
    step = len(context.user_data["answers"])

    if step < len(QUESTIONS):
        await update.message.reply_text(QUESTIONS[step], parse_mode="Markdown")
        return step
    else:
        await update.message.reply_text("✨ Отлично! Составляю ваш персональный плейлист...")
        premium = is_premium(update.effective_user.id)
        await build_playlist(update, context, context.user_data["answers"], premium=premium)
        return ConversationHandler.END


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    playlists = get_user_playlists(user_id)
    if not playlists:
        await update.message.reply_text("У вас пока нет плейлистов. Напишите /start чтобы создать!")
        return
    buttons = [[InlineKeyboardButton(f"🎵 {created_at}", callback_data=f"show_{pl_id}")]
               for pl_id, created_at, _ in playlists]
    await update.message.reply_text("📋 *Ваши плейлисты:*", parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup(buttons))


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    profile = get_user_profile(user_id)
    ref_count = get_referral_count(user_id)
    premium = is_premium(user_id)

    text = f"👤 *Ваш музыкальный профиль*\n\n"
    text += f"{'💎 Премиум пользователь' if premium else '🆓 Бесплатный аккаунт'}\n\n"
    text += f"🎵 Плейлистов создано: *{profile['playlist_count']}*\n"
    text += f"👍 Понравилось треков: *{len(profile['liked'])}*\n"
    text += f"👎 Не понравилось: *{profile['disliked']}*\n"
    text += f"👥 Приглашено друзей: *{ref_count}*\n\n"

    if profile["artists"]:
        text += f"🎸 *Любимые исполнители:*\n"
        for a in profile["artists"]:
            text += f"  • {a}\n"

    if not premium:
        text += f"\n💡 Пригласите *3 друга* и получите Премиум бесплатно!"

    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Пригласить друга", url=ref_link)],
            [InlineKeyboardButton("⭐ Моё избранное", callback_data="show_favorites")],
        ])
    )


async def cmd_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    favs = get_favorites(user_id)
    if not favs:
        await update.message.reply_text("У вас пока нет избранных треков.\n\nНажмите ⭐ под любым треком чтобы добавить!")
        return
    text = "⭐ *Ваше избранное:*\n\n"
    buttons = []
    for fav_id, track_name, artist, yt_link in favs:
        text += f"🎵 [{track_name} — {artist}]({yt_link})\n"
        buttons.append([InlineKeyboardButton(f"🗑 {track_name[:30]}", callback_data=f"del_fav::{fav_id}")])
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True,
                                    reply_markup=InlineKeyboardMarkup(buttons))


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    top = get_top_tracks(10)
    if not top:
        await update.message.reply_text("Пока нет данных. Оценивайте треки 👍👎 и рейтинг появится!")
        return
    text = "🏆 *Топ треков среди пользователей:*\n\n"
    for i, (track_key, score, votes) in enumerate(top, 1):
        parts = track_key.split("::")
        name = parts[1] if len(parts) > 1 else track_key
        artist = parts[0] if len(parts) > 1 else ""
        yt = youtube_link(f"{artist} {name}")
        text += f"{i}. [{name} — {artist}]({yt}) ⭐{score} ({votes} оценок)\n"
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


async def cmd_mood(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        moods_list = " · ".join(MOODS.keys())
        await update.message.reply_text(
            f"🎭 *Музыка по настроению*\n\nНапишите: `/mood [настроение]`\n\n"
            f"Доступные настроения:\n_{moods_list}_",
            parse_mode="Markdown",
        )
        return

    mood_input = " ".join(context.args).lower().strip()
    query = MOODS.get(mood_input)

    if not query:
        await update.message.reply_text(
            f"Не знаю такого настроения 😕\n\nПопробуйте: грустно, весело, энергия, романтика, спокойно, работа, вечеринка"
        )
        return

    await update.message.reply_text(f"🎭 Подбираю музыку для настроения *{mood_input}*...", parse_mode="Markdown")

    tracks = await search_deezer_many(query, limit=5)
    if not tracks:
        await update.message.reply_text("Не удалось найти треки. Попробуйте позже.")
        return

    for track in tracks[:3]:
        await send_track_card(update, f"🎭 {mood_input.capitalize()}", track)


async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("🔍 Напишите строчку из песни:\n`/find текст песни`", parse_mode="Markdown")
        return

    lyrics = " ".join(context.args)
    await update.message.reply_text(f"🔍 Ищу песню по тексту: _{lyrics}_...", parse_mode="Markdown")

    result = await search_by_lyrics(lyrics)
    if result:
        track = await search_deezer(result)
        if track:
            await update.message.reply_text(f"✅ Нашёл: *{result}*", parse_mode="Markdown")
            await send_track_card(update, "🔍 Найденный трек", track)
        else:
            yt = youtube_link(result)
            await update.message.reply_text(f"✅ Возможно это: *{result}*\n[Поиск на YouTube]({yt})",
                                            parse_mode="Markdown")
    else:
        # Ищем напрямую по тексту
        track = await search_deezer(lyrics)
        if track:
            await send_track_card(update, "🔍 Найденный трек", track)
        else:
            await update.message.reply_text("😕 Не смог найти. Попробуйте написать точнее.")


async def cmd_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🔔 *Еженедельный плейлист*\n\n"
        "Каждый понедельник в 09:00 я буду присылать вам новый плейлист на основе ваших вкусов!\n\n"
        "Создайте хотя бы один плейлист через /start — и подписка активируется автоматически.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔕 Отписаться", callback_data="weekly_off")]])
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    stats = get_stats()
    await update.message.reply_text(
        f"📊 *Статистика бота*\n\n"
        f"👥 Пользователей: *{stats['users']}*\n"
        f"🎵 Плейлистов создано: *{stats['playlists']}*\n"
        f"👍 Оценок треков: *{stats['votes']}*\n"
        f"⭐ В избранном: *{stats['favorites']}*",
        parse_mode="Markdown",
    )


async def cmd_fact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import random
    fact = random.choice(MUSIC_FACTS)
    await update.message.reply_text(f"🎵 *Факт дня о музыке*\n\n{fact}", parse_mode="Markdown")


async def cmd_subscribers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ADMIN_ID = 601054792
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Только для администратора.")
        return
    conn = sqlite3.connect(DB_PATH)
    subs = conn.execute("SELECT user_id, username, taste_profile FROM weekly_subscribers").fetchall()
    all_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    if not subs:
        await update.message.reply_text("Подписчиков пока нет.")
        return
    text = f"📋 *Подписчики на еженедельный плейлист:* {len(subs)} из {all_users} пользователей\n\n"
    for user_id, username, taste in subs:
        name = f"@{username}" if username else f"id{user_id}"
        taste_short = (taste[:40] + "…") if taste and len(taste) > 40 else (taste or "—")
        text += f"• {name} — _{taste_short}_\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Опрос отменён. Напишите /start чтобы начать заново.",
                                    reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ─── Callback-кнопки ──────────────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user

    # Голосование
    if data.startswith("vote_up::") or data.startswith("vote_down::"):
        parts = data.split("::")
        vote = 1 if data.startswith("vote_up") else -1
        track_key = parts[1] if len(parts) > 1 else ""
        artist = parts[2] if len(parts) > 2 else ""
        save_vote(user.id, track_key, vote, artist)
        emoji = "👍 Отлично, запомнил!" if vote == 1 else "👎 Запомнил, учту!"
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(emoji)
        return

    # Избранное — добавить
    if data.startswith("fav::"):
        parts = data.split("::")
        if len(parts) >= 4:
            track_name = parts[1]
            artist = parts[2]
            yt_link = parts[3]
            preview_url = parts[4] if len(parts) > 4 else ""
            cover_url = parts[5] if len(parts) > 5 else ""
            add_favorite(user.id, track_name, artist, yt_link, preview_url, cover_url)
            await query.message.reply_text(f"⭐ *{track_name}* добавлен в избранное!", parse_mode="Markdown")
        return

    # Избранное — удалить
    if data.startswith("del_fav::"):
        fav_id = int(data.split("::")[1])
        remove_favorite(fav_id, user.id)
        await query.message.reply_text("🗑 Трек удалён из избранного.")
        return

    # Показать избранное
    if data == "show_favorites":
        favs = get_favorites(user.id)
        if not favs:
            await query.message.reply_text("У вас пока нет избранных треков.")
            return
        text = "⭐ *Ваше избранное:*\n\n"
        for fav_id, track_name, artist, yt_link in favs:
            text += f"🎵 [{track_name} — {artist}]({yt_link})\n"
        await query.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)
        return

    # Старт соло
    if data == "solo_start":
        context.user_data["answers"] = []
        context.user_data["premium_mode"] = False
        await query.message.reply_text(QUESTIONS[0], parse_mode="Markdown")
        return

    # Старт премиум
    if data == "premium_start":
        if not is_premium(user.id):
            ref_count = get_referral_count(user.id)
            bot_username = (await context.bot.get_me()).username
            ref_link = f"https://t.me/{bot_username}?start=ref_{user.id}"
            await query.message.reply_text(
                f"💎 *Премиум плейлист*\n\n"
                f"Получите расширенный плейлист с 20+ треками!\n\n"
                f"🎁 *Получить бесплатно:* пригласите 3 друзей\n"
                f"✅ Приглашено: {ref_count}/3\n\n"
                f"Ваша реферальная ссылка:\n{ref_link}",
                parse_mode="Markdown",
            )
            return
        context.user_data["answers"] = []
        context.user_data["premium_mode"] = True
        await query.message.reply_text("💎 *Премиум режим активирован!* Вы получите расширенный плейлист.\n",
                                       parse_mode="Markdown")
        await query.message.reply_text(QUESTIONS[0], parse_mode="Markdown")
        return

    # Старт группы
    if data == "group_start":
        group_id = str(uuid.uuid4())[:8]
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO group_sessions (group_id, creator_id, members, answers, created_at) VALUES (?, ?, ?, ?, ?)",
            (group_id, user.id, str(user.id), "", datetime.now().strftime("%d.%m.%Y %H:%M"))
        )
        conn.commit()
        conn.close()
        bot_username = (await context.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start=group_{group_id}"
        await query.message.reply_text(
            f"👥 *Плейлист для компании*\n\n"
            f"Отправьте ссылку друзьям — каждый ответит на вопросы, бот составит *общий плейлист*!\n\n"
            f"🔗 {link}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎵 Составить общий плейлист", callback_data=f"group_build_{group_id}")]
            ])
        )
        return

    # Построить групповой плейлист
    if data.startswith("group_build_"):
        group_id = data.split("_", 2)[2]
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT answers FROM group_sessions WHERE group_id=?", (group_id,)).fetchone()
        conn.close()
        if not row or not row[0]:
            await query.message.reply_text("Пока никто не ответил. Поделитесь ссылкой с друзьями!")
            return
        all_answers = row[0].split("|||")
        combined = []
        for i in range(len(LABELS)):
            for ans_block in all_answers:
                parts = ans_block.split("\n")
                if i < len(parts):
                    combined.append(parts[i])
        await query.message.reply_text("🎉 Составляю общий плейлист для всей компании!")
        await build_playlist(update, context, combined[:len(LABELS)], save=False)
        return

    # Мои плейлисты
    if data == "my_playlists":
        playlists = get_user_playlists(user.id)
        if not playlists:
            await query.message.reply_text("У вас пока нет плейлистов.")
            return
        buttons = [[InlineKeyboardButton(f"🎵 {created_at}", callback_data=f"show_{pl_id}")]
                   for pl_id, created_at, _ in playlists]
        await query.message.reply_text("📋 *Ваши плейлисты:*", parse_mode="Markdown",
                                       reply_markup=InlineKeyboardMarkup(buttons))
        return

    # Показать плейлист
    if data.startswith("show_"):
        pid = int(data.split("_")[1])
        row = get_playlist_by_id(pid)
        if not row:
            await query.message.reply_text("Плейлист не найден.")
            return
        pl_id, username, created_at, tracks = row
        text = f"🎵 *Плейлист от {created_at}*\n\n"
        for line in tracks.split("\n"):
            text += f"• {line}\n"
        await query.message.reply_text(
            text, parse_mode="Markdown", disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Поделиться", switch_inline_query=f"playlist_{pl_id}")]
            ])
        )
        return

    # Еженедельный — вкл (из плейлиста)
    if data == "weekly_on":
        playlists = get_user_playlists(user.id)
        taste = playlists[0][2].split("\n")[0] if playlists else ""
        subscribe_weekly(user.id, user.username or user.first_name, taste)
        await query.message.reply_text("🔔 Подписка оформлена! Каждый понедельник в 09:00 буду присылать новый плейлист.")
        return

    # Еженедельный — вкл (из главного меню)
    if data == "weekly_on_start":
        playlists = get_user_playlists(user.id)
        taste = playlists[0][2].split("\n")[0] if playlists else "pop"
        subscribe_weekly(user.id, user.username or user.first_name, taste)
        await query.answer("✅ Подписка оформлена!", show_alert=True)
        return

    # Еженедельный — выкл
    if data == "weekly_off":
        unsubscribe_weekly(user.id)
        await query.message.reply_text("🔕 Подписка на еженедельный плейлист отменена.")
        return


# ─── Инлайн ───────────────────────────────────────────────────────────────────

async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.inline_query.query
    if not query.startswith("playlist_"):
        return
    try:
        pid = int(query.split("_")[1])
    except (IndexError, ValueError):
        return
    row = get_playlist_by_id(pid)
    if not row:
        return
    pl_id, username, created_at, tracks = row
    text = f"🎵 *Персональный плейлист* от {created_at}\n\n"
    for line in tracks.split("\n"):
        text += f"• {line}\n"
    await update.inline_query.answer([
        InlineQueryResultArticle(
            id=str(uuid.uuid4()),
            title=f"🎵 Плейлист от {created_at}",
            description="Поделиться персональным плейлистом",
            input_message_content=InputTextMessageContent(
                message_text=text, parse_mode="Markdown", disable_web_page_preview=True,
            ),
        )
    ], cache_time=0)


# ─── Еженедельная рассылка + факт дня ────────────────────────────────────────

async def send_weekly_playlists(bot) -> None:
    import random
    subscribers = get_all_weekly_subscribers()
    logger.info(f"Sending weekly playlists to {len(subscribers)} subscribers")
    for user_id, taste in subscribers:
        try:
            if not taste:
                continue
            track = await search_deezer(taste)
            if not track:
                continue
            name = track.get("title", "")
            artist = track.get("artist", {}).get("name", "")
            cover = track.get("album", {}).get("cover_big", "")
            preview = track.get("preview", "")
            yt = youtube_link(f"{artist} {name}")

            await bot.send_message(chat_id=user_id,
                                   text=f"🎵 *Ваш еженедельный плейлист*\n\nДобрый понедельник! 🎧",
                                   parse_mode="Markdown")
            if cover:
                await bot.send_photo(chat_id=user_id, photo=cover,
                                     caption=f"🎵 *{name}*\n👤 {artist}\n[YouTube Music]({yt})",
                                     parse_mode="Markdown")
            if preview:
                await bot.send_audio(chat_id=user_id, audio=preview, title=name, performer=artist)
        except Exception as e:
            logger.warning(f"Weekly send error for {user_id}: {e}")


async def send_daily_fact(bot) -> None:
    import random
    fact = random.choice(MUSIC_FACTS)
    users = get_all_users()
    for user_id in users:
        try:
            await bot.send_message(chat_id=user_id,
                                   text=f"🎵 *Факт дня о музыке*\n\n{fact}",
                                   parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Daily fact error for {user_id}: {e}")


# ─── Запуск ───────────────────────────────────────────────────────────────────

async def post_init(app: Application) -> None:
    """Set bot commands menu."""
    await app.bot.set_my_commands([
        ("start", "🎵 Создать новый плейлист"),
        ("history", "📋 Мои сохранённые плейлисты"),
        ("favorites", "⭐ Моё избранное"),
        ("profile", "👤 Мой музыкальный профиль"),
        ("top", "🏆 Топ треков среди пользователей"),
        ("mood", "🎭 Музыка по настроению"),
        ("find", "🔍 Найти песню по тексту"),
        ("weekly", "🔔 Еженедельный плейлист"),
        ("stats", "📊 Статистика бота"),
        ("fact", "🎵 Факт дня о музыке"),
        ("cancel", "❌ Отменить текущий опрос"),
        ("subscribers", "👥 Список подписчиков (админ)"),
    ])


def main() -> None:
    init_db()
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={i: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer)] for i in range(len(QUESTIONS))},
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CommandHandler("history", cmd_history),
            CommandHandler("profile", cmd_profile),
            CommandHandler("favorites", cmd_favorites),
            CommandHandler("top", cmd_top),
            CommandHandler("mood", cmd_mood),
            CommandHandler("find", cmd_find),
            CommandHandler("weekly", cmd_weekly),
            CommandHandler("stats", cmd_stats),
            CommandHandler("fact", cmd_fact),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("favorites", cmd_favorites))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("mood", cmd_mood))
    app.add_handler(CommandHandler("find", cmd_find))
    app.add_handler(CommandHandler("weekly", cmd_weekly))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("fact", cmd_fact))
    app.add_handler(CommandHandler("subscribers", cmd_subscribers))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(InlineQueryHandler(inline_query_handler))

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(send_weekly_playlists, CronTrigger(day_of_week="mon", hour=9, minute=0, timezone="Europe/Moscow"),
                      args=[app.bot], name="weekly_playlists")
    scheduler.add_job(send_daily_fact, CronTrigger(hour=10, minute=0, timezone="Europe/Moscow"),
                      args=[app.bot], name="daily_fact")
    scheduler.start()

    logger.info("Music bot started!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
