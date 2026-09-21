import json
import logging
import os
import re
import aiohttp
from dotenv import load_dotenv

load_dotenv()

with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load()

BOT_TOKEN = os.getenv("BOT_TOKEN")
FB_TOKENS = [t.strip() for t in os.getenv("FB_TOKENS", "").split(",") if t.strip()]

TIK_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
}

HTTP_SESSION: aiohttp.ClientSession | None = None
logger = logging.getLogger("MultiToolBot")


def load_template(template_name: str, **kwargs) -> str:
    path = os.path.join("templates", template_name)
    with open(path, "r", encoding="utf-8") as file:
        content = file.read()
    return content.format(**kwargs)


async def get_http_session() -> aiohttp.ClientSession:
    global HTTP_SESSION
    if HTTP_SESSION is None or HTTP_SESSION.closed:
        HTTP_SESSION = aiohttp.ClientSession(headers=TIK_HEADERS)
    return HTTP_SESSION


async def close_http_session():
    global HTTP_SESSION
    if HTTP_SESSION and not HTTP_SESSION.closed:
        await HTTP_SESSION.close()


def estimate_fb_creation(uid: str) -> str:
    if not uid.isdigit():
        return "Không công khai"
    val = int(uid)
    if val < 1000000000:
        return "Trước năm 2010"
    for p, y in [("10001", "2016-2017"), ("10002", "2017-2018"), ("10003", "2018-2019"),
                ("10004", "2019-2020"), ("10005", "2020-2021"), ("10006", "2021-2022")]:
        if str(val).startswith(p):
            return f"Năm {y}"
    if str(val).startswith(("6155", "6156")):
        return "Năm 2024 - 2025"
    return "Năm 2025 - 2026" if str(val).startswith("6157") else "Bảo mật cao"


async def get_fb_id(input_str: str) -> str | None:
    clean = input_str.strip()
    if clean.isdigit():
        return clean
    match = re.search(r"[?&]id=(\d+)", clean)
    if match:
        return match.group(1)
    clean_url = clean.split("?")[0].rstrip("/")
    path_match = re.search(r"(?:facebook\.com|fb\.me|fb\.com)/([a-zA-Z0-9.]+)", clean_url)
    username = path_match.group(1) if path_match else clean

    session = await get_http_session()
    for token in FB_TOKENS:
        try:
            url = f"https://graph.facebook.com/{username}?fields=id&access_token={token}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "id" in data:
                        return str(data["id"])
        except Exception:
            pass
    return None


async def fetch_fb_info(uid: str) -> dict | None:
    session = await get_http_session()
    result = {"id": uid, "name": None, "gender": None, "followers": None, "hometown": None, "location": None, "about": None, "work": None, "education": None, "verified": False, "username": None}
    for token in FB_TOKENS:
        try:
            url = f"https://graph.facebook.com/{uid}?fields=id,name,gender,is_verified,username,about,hometown,location,work,education&access_token={token}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                res = await resp.json()
                if res and "name" in res:
                    result.update(res)
                    result["hometown"] = res.get("hometown", {}).get("name") if isinstance(res.get("hometown"), dict) else None
                    result["location"] = res.get("location", {}).get("name") if isinstance(res.get("location"), dict) else None
                    break
        except Exception:
            pass
    return result if result.get("name") else None


async def resolve_tiktok_url(url: str) -> str:
    session = await get_http_session()
    if any(k in url for k in ["vt.tiktok.com", "vm.tiktok.com"]):
        try:
            async with session.head(url.strip(), allow_redirects=True, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                return str(resp.url)
        except Exception:
            pass
    return url.strip()


async def tikwm_req(params: dict):
    session = await get_http_session()
    try:
        async with session.post(CONFIG["api"]["tikwm"], data=params, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data and data.get("code") == 0:
                    return data
    except Exception:
        pass
    return None


async def fetch_tiktok_user_info(username: str) -> dict:
    session = await get_http_session()
    clean = username.strip().lstrip("@")
    try:
        async with session.get(f"{CONFIG['api']['tik_info']}{clean}", timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        return {"error": str(e)}
    return {"error": "API unreachable"}
