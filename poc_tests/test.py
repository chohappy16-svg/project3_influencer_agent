# 설치 필요: pip install instaloader
import datetime
import html
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

import instaloader
import requests
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

# 인스타그램 기본 예약 경로 (프로필 username과 구분하기 위한 집합)
RESERVED_IG_PATHS = {
    "p",
    "reel",
    "reels",
    "tv",
    "stories",
    "explore",
    "accounts",
    "direct",
    "graphql",
    "api",
    "about",
    "legal",
    " developer",
}


def detect_instagram_url_type(ig_url: str) -> Dict[str, str]:
    """
    입력된 문자열/URL이
    1) 개별 게시물/릴스/캐러셀 URL인지 ('mode': 'post', 'shortcode': '...')
    2) 인플루언서 프로필 URL 또는 @계정명인지 ('mode': 'profile', 'username': '...', 'tab_hint': '...')
    자동으로 판별합니다.
    """
    cleaned = ig_url.strip()
    if not cleaned:
        return {"mode": "invalid", "shortcode": "", "username": "", "tab_hint": "feed"}

    # @username 형태 직접 입력 지원
    if cleaned.startswith("@") and "/" not in cleaned:
        return {
            "mode": "profile",
            "shortcode": "",
            "username": cleaned.lstrip("@").strip(),
            "tab_hint": "feed",
        }

    # 도메인 없이 단일 문자열만 들어온 경우:
    # 인스타그램 아이디(영문 소문자·숫자·점·언더바)는 프로필 계정명으로 우선 판단하고,
    # 대소문자가 섞인 11자리 단축코드(예: DfkJceaSZQC)만 개별 게시물로 판단
    if "instagram.com" not in cleaned and "/" not in cleaned:
        bare = cleaned.lstrip("@").strip()
        if "." in bare or "_" in bare or bare.islower():
            return {
                "mode": "profile",
                "shortcode": "",
                "username": bare,
                "tab_hint": "feed",
            }
        return {"mode": "post", "shortcode": bare, "username": "", "tab_hint": "feed"}

    parsed = urlparse(cleaned if "://" in cleaned else f"https://{cleaned}")
    path = parsed.path.strip("/")
    parts = [p for p in path.split("/") if p]

    if not parts:
        return {"mode": "invalid", "shortcode": "", "username": "", "tab_hint": "feed"}

    # 1) 경로 중간이나 처음에 /p/{code}, /reel/{code}, /reels/{code}, /tv/{code} 가 있는 경우 -> 개별 게시물 모드
    for idx, part in enumerate(parts):
        if part in ("p", "reel", "reels", "tv") and idx + 1 < len(parts):
            candidate = parts[idx + 1]
            # 단, https://www.instagram.com/username/reels/ 처럼 끝나는 경우는 프로필의 릴스 탭임
            if idx == 0 or candidate not in ("", "embed", "captioned"):
                return {
                    "mode": "post",
                    "shortcode": candidate,
                    "username": parts[0] if idx > 0 else "",
                    "tab_hint": "reels" if part in ("reel", "reels") else "feed",
                }

    # 2) https://www.instagram.com/{username}/ 또는 https://www.instagram.com/{username}/reels/ -> 프로필 모드
    first_seg = parts[0].lstrip("@")
    if first_seg.lower() not in RESERVED_IG_PATHS:
        tab_hint = "reels" if (len(parts) >= 2 and parts[1].lower() in ("reels", "reel", "clips")) else "feed"
        return {
            "mode": "profile",
            "shortcode": "",
            "username": first_seg,
            "tab_hint": tab_hint,
        }

    return {"mode": "post", "shortcode": parts[-1], "username": "", "tab_hint": "feed"}


def extract_shortcode(ig_url: str) -> str:
    """
    인스타그램 일반 게시물(/p/), 릴스(/reel/, /reels/), IGTV(/tv/) URL 또는
    단일 코드 문자열에서 shortcode를 추출합니다.
    (계정명이 앞에 붙은 URL 예: instagram.com/username/reel/SHORTCODE/ 형태도 모두 지원)
    """
    info = detect_instagram_url_type(ig_url)
    if info["mode"] == "post":
        return info["shortcode"]
    return ""


def _parse_compact_count(raw_str: str) -> int:
    """
    '18K', '1.2M', '3,096', '1.8만', '921' 등의 문자열을 정수(int)로 변환합니다.
    """
    if not raw_str:
        return 0
    s = raw_str.strip().replace(",", "").upper()
    try:
        if s.endswith("K"):
            return int(float(s[:-1]) * 1_000)
        if s.endswith("M"):
            return int(float(s[:-1]) * 1_000_000)
        if s.endswith("B"):
            return int(float(s[:-1]) * 1_000_000_000)
        if "만" in s:
            return int(float(s.replace("만", "")) * 10_000)
        if "천" in s:
            return int(float(s.replace("천", "")) * 1_000)
        return int(float(s))
    except Exception:
        return 0


def _parse_media_node_dict(node: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    인스타그램 JSON 슬라이드 노드(단일 미디어 또는 캐러셀의 개별 슬라이드 1칸)를 검사하여
    영상 길이(초수) 제한 없이 `is_video` / `video_url` 유무로 사진(image)과 영상(video)을 1:1 판별합니다.
    """
    if not isinstance(node, dict):
        return None

    typename = str(node.get("__typename", ""))
    video_url = node.get("video_url") or ""
    if not video_url and isinstance(node.get("video_versions"), list) and node["video_versions"]:
        video_url = node["video_versions"][0].get("url", "")

    display_url = node.get("display_url") or ""
    if not display_url and isinstance(node.get("display_resources"), list) and node["display_resources"]:
        display_url = node["display_resources"][-1].get("src", "")
    if not display_url and isinstance(node.get("image_versions2"), dict):
        candidates = node["image_versions2"].get("candidates", [])
        if candidates:
            display_url = candidates[0].get("url", "")

    is_video = bool(node.get("is_video")) or ("Video" in typename) or bool(video_url)

    # 동영상(릴스 또는 캐러셀 내 영상 슬라이드)인 경우
    if is_video and video_url:
        return {
            "media_type": "video",
            "url": html.unescape(video_url),
            "thumbnail_url": html.unescape(display_url or video_url),
        }

    # 일반 사진 슬라이드인 경우 (또는 video_url이 없는 경우 썸네일/이미지 반환)
    if display_url:
        return {
            "media_type": "image",
            "url": html.unescape(display_url),
            "thumbnail_url": html.unescape(display_url),
        }

    return None


def _extract_from_media_root_dict(media: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    인스타그램 미디어 루트 JSON 객체(shortcode_media / xdt_shortcode_media)에서
    - 캐러셀(edge_sidecar_to_children 또는 carousel_media)이면 각 슬라이드 노드를 순서대로 순회하고,
    - 단독 게시물(단독 릴스 또는 단독 사진)이면 단일 노드로 추출합니다.
    """
    if not isinstance(media, dict):
        return []

    items: List[Dict[str, Any]] = []

    # 1) GraphQL 혼합/다중 캐러셀 구조 (edge_sidecar_to_children.edges)
    sidecar_edges = media.get("edge_sidecar_to_children", {}).get("edges", [])
    if sidecar_edges:
        for edge in sidecar_edges:
            child_node = edge.get("node", {})
            parsed = _parse_media_node_dict(child_node)
            if parsed:
                items.append(parsed)
        if items:
            return items

    # 2) 모바일/v1 캐러셀 구조 (carousel_media)
    carousel_media = media.get("carousel_media", [])
    if carousel_media:
        for child_node in carousel_media:
            parsed = _parse_media_node_dict(child_node)
            if parsed:
                items.append(parsed)
        if items:
            return items

    # 3) 단독 게시물 (단독 릴스 GraphVideo 또는 단독 사진 GraphImage)
    single_parsed = _parse_media_node_dict(media)
    if single_parsed:
        items.append(single_parsed)

    return items


def _extract_post_metadata_from_dict(media: Dict[str, Any], shortcode: str) -> Dict[str, Any]:
    """
    GraphQL 또는 Embed의 shortcode_media 딕셔너리에서 업로드 시각(taken_at_timestamp),
    좋아요/댓글/조회수, 작성자(owner), 캡션, 상품 타입(clips=릴스 vs feed) 등을 함께 추출합니다.
    """
    taken_at = (
        media.get("taken_at_timestamp")
        or media.get("taken_at")
        or int(time.time())
    )
    typename = str(media.get("__typename", ""))
    product_type = str(media.get("product_type", ""))
    is_video = bool(media.get("is_video")) or ("Video" in typename)

    like_count = (
        media.get("edge_media_preview_like", {}).get("count")
        or media.get("edge_liked_by", {}).get("count")
        or media.get("like_count")
        or 0
    )
    comment_count = (
        media.get("edge_media_to_comment", {}).get("count")
        or media.get("edge_media_preview_comment", {}).get("count")
        or media.get("comment_count")
        or 0
    )
    view_count = (
        media.get("video_view_count")
        or media.get("video_play_count")
        or media.get("play_count")
        or 0
    )

    caption_edges = media.get("edge_media_to_caption", {}).get("edges", [])
    caption_text = ""
    if caption_edges and isinstance(caption_edges[0], dict):
        caption_text = caption_edges[0].get("node", {}).get("text", "")
    elif isinstance(media.get("caption"), dict):
        caption_text = media["caption"].get("text", "")

    owner = media.get("owner", {}) or {}
    pinned_users = media.get("pinned_for_users", []) or []

    return {
        "shortcode": media.get("shortcode") or media.get("code") or shortcode,
        "taken_at_timestamp": int(taken_at),
        "typename": typename or ("GraphVideo" if is_video else "GraphImage"),
        "product_type": product_type or ("clips" if is_video else "feed"),
        "is_video": is_video,
        "like_count": int(like_count) if like_count and int(like_count) > 0 else 0,
        "comment_count": int(comment_count) if comment_count and int(comment_count) > 0 else 0,
        "view_count": int(view_count) if view_count and int(view_count) > 0 else 0,
        "caption": caption_text,
        "owner_username": owner.get("username", ""),
        "owner_full_name": owner.get("full_name", ""),
        "owner_profile_pic": owner.get("profile_pic_url", ""),
        "is_pinned": len(pinned_users) > 0,
    }


def _query_public_graphql_with_meta(shortcode: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    비로그인 상태에서 단독 릴스 및 혼합 캐러셀(사진+영상)의 원본 video_url(.mp4)과
    업로드 타임스탬프(taken_at_timestamp) 메타데이터를 함께 가져오는 공개 Web GraphQL 쿼리
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "X-IG-App-ID": "936619743392459",
        "X-ASBD-ID": "129477",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://www.instagram.com/p/{shortcode}/",
    }

    for doc_id in ("8845758582119845", "10015901848480474"):
        try:
            resp = requests.post(
                "https://www.instagram.com/graphql/query",
                headers=headers,
                data={
                    "variables": json.dumps({"shortcode": shortcode}),
                    "doc_id": doc_id,
                },
                timeout=10,
            )
            if not resp.ok:
                continue
            data = resp.json().get("data", {})
            media = data.get("xdt_shortcode_media") or data.get("shortcode_media")
            if media:
                items = _extract_from_media_root_dict(media)
                meta = _extract_post_metadata_from_dict(media, shortcode)
                if items:
                    return items, meta
        except Exception:
            continue

    return [], {}


def _query_public_graphql(shortcode: str) -> List[Dict[str, Any]]:
    items, _ = _query_public_graphql_with_meta(shortcode)
    return items


def _fallback_extract_media_items(shortcode: str) -> List[Dict[str, Any]]:
    """
    instaloader 기본 호출이 비로그인 제한에 걸렸을 때 작동하는 다단계 보조 추출기:
      1단계: 공개 GraphQL (xdt_shortcode_media) -> 단독 릴스 & 혼합 캐러셀(사진+영상) 완벽 지원
      2단계: 공개 Embed 페이지 (/p/ 및 /reel/ embed/captioned) 내 contextJSON 슬라이드 노드 파싱
      3단계: Embed HTML 내 video_url / display_url / og:video / og:image 추출
    """
    gql_items = _query_public_graphql(shortcode)
    if gql_items:
        return gql_items

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    for url in (
        f"https://www.instagram.com/p/{shortcode}/embed/captioned/",
        f"https://www.instagram.com/reel/{shortcode}/embed/captioned/",
        f"https://www.instagram.com/p/{shortcode}/embed/",
        f"https://www.instagram.com/reel/{shortcode}/embed/",
        f"https://www.instagram.com/p/{shortcode}/",
        f"https://www.instagram.com/reel/{shortcode}/",
    ):
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if not resp.ok:
                continue
            page_text = resp.text

            ctx_match = re.search(r'"contextJSON"\s*:\s*"((?:\\.|[^"\\])*)"', page_text)
            if ctx_match:
                try:
                    raw_ctx_str = json.loads(f'"{ctx_match.group(1)}"')
                    ctx_data = json.loads(raw_ctx_str)
                    media = (
                        ctx_data.get("gql_data", {}).get("shortcode_media")
                        or ctx_data.get("shortcode_media")
                        or {}
                    )
                    items = _extract_from_media_root_dict(media)
                    if items:
                        return items
                except Exception:
                    pass

            og_video = re.search(r'property="og:video"\s+content="([^"]+)"', page_text)
            og_image = re.search(r'property="og:image"\s+content="([^"]+)"', page_text)
            if og_video:
                vid_url = html.unescape(og_video.group(1))
                thumb_url = html.unescape(og_image.group(1)) if og_image else vid_url
                return [{"media_type": "video", "url": vid_url, "thumbnail_url": thumb_url}]

            escaped_vid = re.search(r'\\"video_url\\"\s*:\s*\\"(https:[^"\\]+)\\"', page_text)
            if escaped_vid and "edge_sidecar_to_children" not in page_text:
                vid_url = html.unescape(
                    escaped_vid.group(1).replace("\\/", "/").encode("utf-8").decode("unicode_escape")
                )
                return [{"media_type": "video", "url": vid_url, "thumbnail_url": vid_url}]

            embed_imgs = re.findall(r'class="EmbeddedMediaImage"[^>]+src="([^"]+)"', page_text)
            if embed_imgs:
                seen = set()
                res_list = []
                for src in embed_imgs:
                    u = html.unescape(src)
                    if u not in seen:
                        seen.add(u)
                        res_list.append({"media_type": "image", "url": u, "thumbnail_url": u})
                return res_list

            if og_image:
                u = html.unescape(og_image.group(1))
                return [{"media_type": "image", "url": u, "thumbnail_url": u}]

        except Exception:
            continue

    return []


def get_instagram_media_items(ig_url: str) -> List[Dict[str, Any]]:
    """
    인스타그램 URL(일반 게시물, 단독 릴스, 다중 사진 캐러셀, 사진+영상 혼합 캐러셀)을 입력받아
    슬라이드 순서 그대로 각 미디어 정보를 담은 리스트를 반환합니다.
    (영상 길이/초수 제한 없이 모든 릴스와 캐러셀 내 영상을 추출합니다.)
    """
    shortcode = extract_shortcode(ig_url)
    if not shortcode:
        raise ValueError("유효한 인스타그램 게시물/릴스 URL 또는 shortcode를 입력해주세요.")

    L = instaloader.Instaloader()
    raw_items: List[Dict[str, Any]] = []

    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)

        if post.typename == "GraphSidecar":
            for slide in post.get_sidecar_nodes():
                if slide.is_video and getattr(slide, "video_url", None):
                    raw_items.append(
                        {
                            "media_type": "video",
                            "url": slide.video_url,
                            "thumbnail_url": slide.display_url,
                        }
                    )
                else:
                    raw_items.append(
                        {
                            "media_type": "image",
                            "url": slide.display_url,
                            "thumbnail_url": slide.display_url,
                        }
                    )
        elif post.is_video and getattr(post, "video_url", None):
            raw_items.append(
                {
                    "media_type": "video",
                    "url": post.video_url,
                    "thumbnail_url": post.url,
                }
            )
        else:
            raw_items.append(
                {
                    "media_type": "image",
                    "url": post.url,
                    "thumbnail_url": post.url,
                }
            )

    except Exception as inner_err:
        raw_items = _fallback_extract_media_items(shortcode)
        if not raw_items:
            raise RuntimeError(f"Error extracting media: {str(inner_err)}")

    for idx, item in enumerate(raw_items, start=1):
        item["index"] = idx

    return raw_items


def get_instagram_image_urls(ig_url: str) -> List[str]:
    """모든 슬라이드의 메인 미디어 URL(사진이면 .jpg, 릴스/영상이면 .mp4) 리스트를 반환합니다."""
    items = get_instagram_media_items(ig_url)
    return [item["url"] for item in items]


def get_instagram_image_url(ig_url: str) -> str:
    """기존 단일 함수 호환 유지"""
    try:
        urls = get_instagram_image_urls(ig_url)
        return urls[0] if len(urls) == 1 else "\n".join(urls)
    except Exception as e:
        return str(e)


# ==============================================================================
# ★ 프로필 링크 처리: 메타데이터 수집 + 피드/릴스 탭 통합 + 기간 기반 협찬 판독 엔진
# ==============================================================================


def fetch_live_profile_header(username: str) -> Dict[str, Any]:
    """
    비로그인 상태에서도 차단(429) 없이 100% 동작하는 OpenGraph 크롤러 헤더를 통해
    실제 인플루언서 프로필의 팔로워 수, 팔로잉 수, 총 게시물 수, 이름, 소개글(Bio), 프로필 사진을 추출합니다.
    """
    clean_user = username.strip().lstrip("@")
    profile_info: Dict[str, Any] = {
        "username": clean_user,
        "full_name": clean_user,
        "followers": 0,
        "followers_display": "정보 없음",
        "following": 0,
        "following_display": "0",
        "total_posts": 0,
        "total_posts_display": "0",
        "biography": "",
        "profile_pic_url": "",
        "is_live_fetched": False,
        "influencer_tier": "마이크로 인플루언서",
    }

    for ua in (
        "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
        "Twitterbot/1.0",
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    ):
        try:
            resp = requests.get(
                f"https://www.instagram.com/{clean_user}/",
                headers={"User-Agent": ua, "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8"},
                timeout=10,
            )
            if not resp.ok:
                continue
            text = resp.text

            # 1) <title>에서 이름 추출 (예: "송강호 | 송파 강동 사는 호랑이띠 맛집 (@songgang.ho) • Instagram...")
            title_m = re.search(r"<title>([^<]+)</title>", text)
            if title_m:
                raw_title = html.unescape(title_m.group(1)).strip()
                name_part = re.split(r"\(\s*@", raw_title)[0].strip()
                if name_part and "Instagram" not in name_part:
                    profile_info["full_name"] = name_part

            # 2)og:image (프로필 사진)
            og_img_m = re.search(r'property="og:image"\s+content="([^"]+)"', text) or re.search(
                r'content="([^"]+)"\s+property="og:image"', text
            )
            if og_img_m:
                profile_info["profile_pic_url"] = html.unescape(og_img_m.group(1))

            # 3) meta name="description" 또는 og:description 파싱
            # 예: '18K Followers, 3,096 Following, 921 Posts - 이름 (@id) on Instagram: "소개글..."'
            meta_m = (
                re.search(r'name="description"\s+content="([^"]+)"', text)
                or re.search(r'content="([^"]+)"\s+name="description"', text)
                or re.search(r'property="og:description"\s+content="([^"]+)"', text)
            )
            if meta_m:
                desc = html.unescape(meta_m.group(1))
                stat_m = re.search(
                    r"([0-9.,KMB만천]+)\s*Followers,\s*([0-9.,KMB만천]+)\s*Following,\s*([0-9.,KMB만천]+)\s*Posts",
                    desc,
                    re.I,
                )
                if stat_m:
                    f_raw, fw_raw, p_raw = stat_m.group(1), stat_m.group(2), stat_m.group(3)
                    profile_info["followers_display"] = f_raw
                    profile_info["followers"] = _parse_compact_count(f_raw)
                    profile_info["following_display"] = fw_raw
                    profile_info["following"] = _parse_compact_count(fw_raw)
                    profile_info["total_posts_display"] = p_raw
                    profile_info["total_posts"] = _parse_compact_count(p_raw)
                    profile_info["is_live_fetched"] = True

                bio_m = re.search(r'on Instagram:\s*"(.*)"\s*$', desc, re.S)
                if bio_m:
                    profile_info["biography"] = bio_m.group(1).strip()

            if profile_info["is_live_fetched"]:
                break
        except Exception:
            continue

    # 팔로워 규모별 인플루언서 티어 분류
    f_cnt = profile_info["followers"]
    if f_cnt < 1_000:
        profile_info["influencer_tier"] = "🌱 나노 미만 (일반/초기 계정)"
    elif f_cnt < 10_000:
        profile_info["influencer_tier"] = "✨ 나노 인플루언서 (1K ~ 10K)"
    elif f_cnt < 100_000:
        profile_info["influencer_tier"] = "🎯 마이크로 인플루언서 (10K ~ 100K · 협찬 가성비 최적군)"
    elif f_cnt < 500_000:
        profile_info["influencer_tier"] = "🚀 매크로 인플루언서 (100K ~ 500K)"
    else:
        profile_info["influencer_tier"] = "👑 메가 인플루언서 (500K+)"

    return profile_info


def _try_fetch_live_timeline_posts(
    username: str,
    session_id: Optional[str] = None,
    sample_post_urls: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    1순위: 사용자가 입력한 실제 개별 게시물/릴스 URL 목록이 있으면 각각 GraphQL로 실제 타임스탬프/미디어 추출
    2순위: web_profile_info API (세션 쿠키가 있거나 비로그인 허용 시 피드 탭 + 릴스 탭 동시 수집)
    """
    collected_by_code: Dict[str, Dict[str, Any]] = {}

    # 1) 사용자가 함께 전달한 실제 게시물/릴스 URL들 파싱
    if sample_post_urls:
        for raw_u in sample_post_urls:
            u = raw_u.strip()
            if not u:
                continue
            info = detect_instagram_url_type(u)
            sc = info.get("shortcode", "")
            if not sc:
                continue
            items, meta = _query_public_graphql_with_meta(sc)
            if not items:
                items = _fallback_extract_media_items(sc)
            if items:
                now_ts = int(time.time())
                ts = meta.get("taken_at_timestamp") or now_ts
                is_vid = any(x["media_type"] == "video" for x in items)
                is_carousel = len(items) > 1
                tab_source = "reels_only" if (info.get("tab_hint") == "reels" and not is_carousel) else (
                    "both" if is_vid else "feed"
                )
                collected_by_code[sc] = {
                    "shortcode": sc,
                    "post_url": f"https://www.instagram.com/{'reel' if is_vid and not is_carousel else 'p'}/{sc}/",
                    "taken_at_timestamp": ts,
                    "media_format": "carousel" if is_carousel else ("reel" if is_vid else "image"),
                    "tab_source": tab_source,  # "feed" | "both" | "reels_only"
                    "is_pinned": bool(meta.get("is_pinned", False)),
                    "is_simulated": False,
                    "like_count": meta.get("like_count", 0),
                    "comment_count": meta.get("comment_count", 0),
                    "view_count": meta.get("view_count", 0),
                    "caption": meta.get("caption", "")[:160],
                    "thumbnail_url": items[0]["thumbnail_url"],
                    "media_url": items[0]["url"],
                    "slide_count": len(items),
                    "slides": items,
                }

    if collected_by_code:
        return list(collected_by_code.values()), "live_post_urls"

    # 2) web_profile_info API 시도 (피드 타임라인 + 릴스/클립 타임라인 통합)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "X-IG-App-ID": "936619743392459",
        "X-ASBD-ID": "129477",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://www.instagram.com/{username}/",
    }
    cookies = {}
    if session_id and session_id.strip():
        cookies["sessionid"] = session_id.strip()

    try:
        resp = requests.get(
            f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
            headers=headers,
            cookies=cookies,
            timeout=8,
        )
        if resp.ok:
            user_data = resp.json().get("data", {}).get("user", {}) or {}
            feed_edges = user_data.get("edge_owner_to_timeline_media", {}).get("edges", []) or []
            reel_edges = user_data.get("edge_felix_video_timeline", {}).get("edges", []) or []

            feed_codes = set()
            for edge in feed_edges:
                node = edge.get("node", {}) or {}
                sc = node.get("shortcode")
                if not sc:
                    continue
                feed_codes.add(sc)
                slides = _extract_from_media_root_dict(node)
                meta = _extract_post_metadata_from_dict(node, sc)
                is_carousel = "Sidecar" in meta["typename"] or len(slides) > 1
                is_vid = meta["is_video"]
                collected_by_code[sc] = {
                    "shortcode": sc,
                    "post_url": f"https://www.instagram.com/{'reel' if is_vid and not is_carousel else 'p'}/{sc}/",
                    "taken_at_timestamp": meta["taken_at_timestamp"],
                    "media_format": "carousel" if is_carousel else ("reel" if is_vid else "image"),
                    "tab_source": "both" if is_vid else "feed",
                    "is_pinned": meta["is_pinned"],
                    "like_count": meta["like_count"],
                    "comment_count": meta["comment_count"],
                    "view_count": meta["view_count"],
                    "caption": (meta["caption"] or "")[:160],
                    "thumbnail_url": slides[0]["thumbnail_url"] if slides else node.get("display_url", ""),
                    "media_url": slides[0]["url"] if slides else node.get("display_url", ""),
                    "slide_count": max(1, len(slides)),
                    "slides": slides,
                }

            for edge in reel_edges:
                node = edge.get("node", {}) or {}
                sc = node.get("shortcode")
                if not sc:
                    continue
                if sc in collected_by_code:
                    collected_by_code[sc]["tab_source"] = "both"
                    continue
                slides = _extract_from_media_root_dict(node)
                meta = _extract_post_metadata_from_dict(node, sc)
                collected_by_code[sc] = {
                    "shortcode": sc,
                    "post_url": f"https://www.instagram.com/reel/{sc}/",
                    "taken_at_timestamp": meta["taken_at_timestamp"],
                    "media_format": "reel",
                    "tab_source": "reels_only",  # ★ 피드 탭에는 숨기고 릴스 탭에만 올린 게시물!
                    "is_pinned": meta["is_pinned"],
                    "like_count": meta["like_count"],
                    "comment_count": meta["comment_count"],
                    "view_count": meta["view_count"],
                    "caption": (meta["caption"] or "")[:160],
                    "thumbnail_url": slides[0]["thumbnail_url"] if slides else node.get("display_url", ""),
                    "media_url": slides[0]["url"] if slides else node.get("display_url", ""),
                    "slide_count": 1,
                    "slides": slides,
                }

            if collected_by_code:
                return list(collected_by_code.values()), "live_api"
    except Exception:
        pass

    # 3) 비로그인 공개 프로필 Embed 페이지(contextJSON.context.graphql_media) 파싱
    try:
        embed_resp = requests.get(
            f"https://www.instagram.com/{username}/embed/",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        if embed_resp.ok:
            ctx_m = re.search(r'"contextJSON"\s*:\s*"((?:\\.|[^"\\])*)"', embed_resp.text)
            if ctx_m:
                ctx_obj = json.loads(json.loads(f'"{ctx_m.group(1)}"'))
                gql_media = ctx_obj.get("context", {}).get("graphql_media", []) or []
                for item in gql_media:
                    node = item.get("shortcode_media", item) or {}
                    sc = node.get("shortcode")
                    if not sc:
                        continue
                    slides = _extract_from_media_root_dict(node)
                    meta = _extract_post_metadata_from_dict(node, sc)
                    is_carousel = "Sidecar" in meta["typename"] or len(slides) > 1
                    is_vid = meta["is_video"]
                    collected_by_code[sc] = {
                        "shortcode": sc,
                        "post_url": f"https://www.instagram.com/{'reel' if is_vid and not is_carousel else 'p'}/{sc}/",
                        "taken_at_timestamp": meta["taken_at_timestamp"],
                        "media_format": "carousel" if is_carousel else ("reel" if is_vid else "image"),
                        "tab_source": "both" if is_vid else "feed",
                        "is_pinned": meta["is_pinned"],
                        "is_simulated": False,
                        "like_count": meta["like_count"],
                        "comment_count": meta["comment_count"],
                        "view_count": meta["view_count"],
                        "caption": meta["caption"] or "",
                        "thumbnail_url": slides[0]["thumbnail_url"] if slides else node.get("display_url", ""),
                        "media_url": slides[0]["url"] if slides else node.get("display_url", ""),
                        "slide_count": max(1, len(slides)),
                        "slides": slides,
                    }
                if collected_by_code:
                    return list(collected_by_code.values()), "live_embed"
    except Exception:
        pass

    return [], "anonymous_restricted"


def _build_scenario_timeline_posts(
    profile_info: Dict[str, Any],
    scenario_mode: str = "active_integrated",
) -> List[Dict[str, Any]]:
    """
    인스타그램 비로그인 정책으로 인해 타임라인 배열 직접 조회가 제한(401/429)된 경우,
    실제 추출된 프로필 메타데이터(@songgang.ho 등)를 기반으로
    사용자님이 설계하신 4가지 핵심 협찬 검증 케이스(기간 착시 / 피드·릴스 탭 분리 / 활성 통합 / 주의)를
    정밀 시뮬레이션 데이터로 구성합니다.
    """
    now_ts = int(time.time())
    DAY = 86400
    uname = profile_info.get("username", "influencer")
    pic = profile_info.get("profile_pic_url") or "https://picsum.photos/seed/igprofile/600/600"

    # 시나리오 1 (기본): 🟢 활성 계정 (피드 + 릴스 통합 운영 & 상단 3개월 전 100만 릴스 고정 착시 자동 분리)
    if scenario_mode == "active_integrated":
        raw_specs = [
            {
                "code": f"{uname[:6]}_PIN100M",
                "days_ago": 96,
                "format": "reel",
                "tab": "both",
                "is_pinned": True,
                "likes": 34200,
                "comments": 890,
                "views": 1180000,
                "slides": 1,
                "caption": "📌 [상단 고정 인기 릴스] 3개월 전 폭발적 반응을 얻은 118만 조회수 시그니처 맛집 릴스 (고정 게시물)",
            },
            {
                "code": f"{uname[:6]}_R02D",
                "days_ago": 2,
                "format": "reel",
                "tab": "both",
                "is_pinned": False,
                "likes": 1420,
                "comments": 68,
                "views": 28400,
                "slides": 1,
                "caption": "🎬 [최신 릴스] 웨이팅 1시간 각오해야 하는 신상 화덕피자 & 파스타 생생 리뷰!",
            },
            {
                "code": f"{uname[:6]}_C05D",
                "days_ago": 5,
                "format": "carousel",
                "tab": "feed",
                "is_pinned": False,
                "likes": 980,
                "comments": 44,
                "views": 0,
                "slides": 6,
                "caption": "🎠 [혼합 캐러셀 6장] 이번 주 직접 다녀온 분위기 깡패 데이트 코스 BEST 5 모음집 (사진+메뉴판)",
            },
            {
                "code": f"{uname[:6]}_R09D",
                "days_ago": 9,
                "format": "reel",
                "tab": "reels_only",
                "is_pinned": False,
                "likes": 1850,
                "comments": 92,
                "views": 41200,
                "slides": 1,
                "caption": "🎬 [릴스 탭 전용 업로드] 메인 피드 그리드에는 숨기고 릴스 탭에만 올린 하이볼 바 숏폼 리뷰",
            },
            {
                "code": f"{uname[:6]}_C14D",
                "days_ago": 14,
                "format": "carousel",
                "tab": "feed",
                "is_pinned": False,
                "likes": 860,
                "comments": 39,
                "views": 0,
                "slides": 5,
                "caption": "🖼️ [다중 사진 캐러셀] 디저트 덕후가 엄선한 구움과자 & 수제 케이크 전문점 솔직 후기",
            },
            {
                "code": f"{uname[:6]}_R21D",
                "days_ago": 21,
                "format": "reel",
                "tab": "both",
                "is_pinned": False,
                "likes": 1290,
                "comments": 51,
                "views": 24900,
                "slides": 1,
                "caption": "🎬 육즙 가득 숙성 삼겹살집 현장 사운드 릴스",
            },
            {
                "code": f"{uname[:6]}_I27D",
                "days_ago": 27,
                "format": "image",
                "tab": "feed",
                "is_pinned": False,
                "likes": 740,
                "comments": 28,
                "views": 0,
                "slides": 1,
                "caption": "🖼️ 주말 브런치 플레이트 한 컷 기록",
            },
        ]

    # 시나리오 2: 🔴 3개월 전 100만 조회수 릴스만 고정해 둔 휴면 계정 (협찬 불가 판정 케이스!)
    elif scenario_mode == "dormant_pinned_trap":
        raw_specs = [
            {
                "code": f"{uname[:6]}_VIRAL95D",
                "days_ago": 95,
                "format": "reel",
                "tab": "both",
                "is_pinned": True,
                "likes": 41500,
                "comments": 1240,
                "views": 1050000,
                "slides": 1,
                "caption": "📌 [상단 고정 105만 조회수 릴스] 3개월 전 알고리즘을 탔던 대박 영상! (단순 조회수 판독기는 이 영상 때문에 협찬 가능으로 오판함)",
            },
            {
                "code": f"{uname[:6]}_PIN110D",
                "days_ago": 110,
                "format": "carousel",
                "tab": "feed",
                "is_pinned": True,
                "likes": 8900,
                "comments": 310,
                "views": 0,
                "slides": 7,
                "caption": "📌 [상단 고정 캐러셀] 4개월 전 인기 게시물 큐레이션",
            },
            {
                "code": f"{uname[:6]}_OLD62D",
                "days_ago": 62,
                "format": "reel",
                "tab": "both",
                "is_pinned": False,
                "likes": 620,
                "comments": 19,
                "views": 9400,
                "slides": 1,
                "caption": "⚠️ [실제 마지막 업로드 - 62일 전] 두 달 전 올린 마지막 릴스 (이후 현재까지 피드/릴스 업로드 전무)",
            },
            {
                "code": f"{uname[:6]}_OLD78D",
                "days_ago": 78,
                "format": "carousel",
                "tab": "feed",
                "is_pinned": False,
                "likes": 540,
                "comments": 15,
                "views": 0,
                "slides": 4,
                "caption": "78일 전 업로드된 일반 피드 캐러셀",
            },
            {
                "code": f"{uname[:6]}_OLD104D",
                "days_ago": 104,
                "format": "image",
                "tab": "feed",
                "is_pinned": False,
                "likes": 490,
                "comments": 12,
                "views": 0,
                "slides": 1,
                "caption": "104일 전 업로드된 사진 게시물",
            },
        ]

    # 시나리오 3: 🟢 피드 탭(사진) / 릴스 탭(영상) 완전 분리 운영자 (피드만 보면 휴면 같지만 릴스 탭에서 맹활약 중!)
    elif scenario_mode == "split_tabs_active":
        raw_specs = [
            {
                "code": f"{uname[:6]}_RL_01D",
                "days_ago": 1,
                "format": "reel",
                "tab": "reels_only",
                "is_pinned": False,
                "likes": 2150,
                "comments": 94,
                "views": 52000,
                "slides": 1,
                "caption": "🎬 [릴스 탭 전용 - 1일 전] 메인 피드 감성을 해치지 않기 위해 '프로필 그리드에서 숨기기'로 릴스 탭에만 올린 신상 맛집 영상!",
            },
            {
                "code": f"{uname[:6]}_RL_04D",
                "days_ago": 4,
                "format": "reel",
                "tab": "reels_only",
                "is_pinned": False,
                "likes": 1780,
                "comments": 73,
                "views": 38900,
                "slides": 1,
                "caption": "🎬 [릴스 탭 전용 - 4일 전] 오직 /reels/ 탭에서만 보이는 숏폼 리뷰 (피드 탭만 크롤링하면 누락되는 게시물)",
            },
            {
                "code": f"{uname[:6]}_RL_08D",
                "days_ago": 8,
                "format": "reel",
                "tab": "reels_only",
                "is_pinned": False,
                "likes": 1640,
                "comments": 61,
                "views": 34100,
                "slides": 1,
                "caption": "🎬 [릴스 탭 전용 - 8일 전] 주말 핫플 웨이팅 현장 릴스",
            },
            {
                "code": f"{uname[:6]}_RL_13D",
                "days_ago": 13,
                "format": "reel",
                "tab": "reels_only",
                "is_pinned": False,
                "likes": 1490,
                "comments": 55,
                "views": 29800,
                "slides": 1,
                "caption": "🎬 [릴스 탭 전용 - 13일 전] 협찬 캠페인 숏폼 영상",
            },
            {
                "code": f"{uname[:6]}_FD_24D",
                "days_ago": 24,
                "format": "carousel",
                "tab": "feed",
                "is_pinned": False,
                "likes": 910,
                "comments": 34,
                "views": 0,
                "slides": 8,
                "caption": "🖼️ [메인 피드 탭 - 24일 전] 피드 탭에는 한 달에 1~2번 고화질 사진 캐러셀만 엄선해서 올리는 스타일",
            },
            {
                "code": f"{uname[:6]}_FD_45D",
                "days_ago": 45,
                "format": "image",
                "tab": "feed",
                "is_pinned": False,
                "likes": 830,
                "comments": 29,
                "views": 0,
                "slides": 1,
                "caption": "🖼️ [메인 피드 탭 - 45일 전] 감성 사진 피드 아카이브",
            },
        ]

    # 시나리오 4: 🟡 업로드 주기 저하 / 조건부 검토 계정 (마지막 업로드 19일 전, 최근 30일 1건)
    else:
        raw_specs = [
            {
                "code": f"{uname[:6]}_WARN19D",
                "days_ago": 19,
                "format": "carousel",
                "tab": "feed",
                "is_pinned": False,
                "likes": 680,
                "comments": 24,
                "views": 0,
                "slides": 4,
                "caption": "🎠 [19일 전 업로드] 최근 한 달 내 유일한 피드 캐러셀 게시물 (업로드 주기가 느려지는 추세)",
            },
            {
                "code": f"{uname[:6]}_OLD36D",
                "days_ago": 36,
                "format": "reel",
                "tab": "both",
                "is_pinned": False,
                "likes": 1120,
                "comments": 41,
                "views": 19500,
                "slides": 1,
                "caption": "🎬 [36일 전 업로드] 한 달 남짓 전에 업로드된 릴스 영상",
            },
            {
                "code": f"{uname[:6]}_OLD52D",
                "days_ago": 52,
                "format": "carousel",
                "tab": "feed",
                "is_pinned": False,
                "likes": 720,
                "comments": 27,
                "views": 0,
                "slides": 5,
                "caption": "🖼️ [52일 전 업로드] 다중 이미지 리뷰 게시물",
            },
        ]

    posts: List[Dict[str, Any]] = []
    for sp in raw_specs:
        ts = now_ts - int(sp["days_ago"] * DAY)
        posts.append(
            {
                "shortcode": sp["code"],
                "post_url": f"https://www.instagram.com/{'reel' if sp['format'] == 'reel' else 'p'}/{sp['code']}/",
                "taken_at_timestamp": ts,
                "media_format": sp["format"],  # "image" | "carousel" | "reel"
                "tab_source": sp["tab"],  # "feed" | "both" | "reels_only"
                "is_pinned": sp["is_pinned"],
                "is_simulated": True,
                "like_count": sp["likes"],
                "comment_count": sp["comments"],
                "view_count": sp["views"],
                "caption": sp["caption"],
                "thumbnail_url": pic,
                "media_url": pic,
                "slide_count": sp["slides"],
                "slides": [],
            }
        )
    return posts


def evaluate_sponsorship_suitability(
    profile_info: Dict[str, Any],
    raw_posts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    [핵심 AI 에이전트 협찬 판독 로직]
    1) 피드 탭 + 릴스 탭에서 수집된 게시물을 shortcode 기준으로 중복 제거한 뒤,
       고정 게시물(is_pinned) 착시를 배제하고 실제 업로드 시각(taken_at_timestamp) 최신순으로 정렬합니다.
    2) 기간 지표(마지막 업로드 경과일, 최근 14일/30일/90일 업로드 수, 평균 업로드 주기)를 계산합니다.
    3) 피드 탭 vs 릴스 탭 분리/통합 운영 형태를 진단합니다.
    4) '협찬 가능(APPROVED) / 조건부 검토(CONDITIONAL) / 협찬 불가(REJECTED)' 및 상세 근거를 반환합니다.
    """
    now_ts = int(time.time())
    DAY = 86400

    # 1. shortcode 기준 중복 제거 및 날짜 파생 필드 계산
    dedup_map: Dict[str, Dict[str, Any]] = {}
    for p in raw_posts:
        sc = p["shortcode"]
        if sc not in dedup_map:
            dedup_map[sc] = dict(p)
        else:
            # 피드와 릴스 양쪽에서 발견된 경우 tab_source를 'both'로 보강
            if dedup_map[sc]["tab_source"] != p["tab_source"]:
                dedup_map[sc]["tab_source"] = "both"

    enriched_posts: List[Dict[str, Any]] = []
    for p in dedup_map.values():
        ts = int(p.get("taken_at_timestamp") or now_ts)
        days_ago = max(0, int(round((now_ts - ts) / DAY)))
        dt_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

        if days_ago <= 14:
            recency_badge = "🟢 최근 2주 이내"
            recency_level = "fresh"
        elif days_ago <= 30:
            recency_badge = "🟡 최근 30일 이내"
            recency_level = "moderate"
        elif days_ago <= 90:
            recency_badge = "🟠 1~3개월 경과"
            recency_level = "aging"
        else:
            recency_badge = "🔴 3개월+ 구형 게시물"
            recency_level = "stale"

        thumb_proxy = (
            f"/api/proxy-media?url={quote(p['thumbnail_url'], safe='')}"
            if p.get("thumbnail_url")
            else ""
        )
        p_copy = {
            **p,
            "upload_date": dt_str,
            "days_ago": days_ago,
            "recency_badge": recency_badge,
            "recency_level": recency_level,
            "thumb_proxy_url": thumb_proxy,
        }
        enriched_posts.append(p_copy)

    # ★ 실제 업로드 일시(taken_at_timestamp) 내림차순 정렬 (상단 고정 여부와 무관하게 진짜 최신순 정렬)
    chronological_posts = sorted(
        enriched_posts, key=lambda x: x["taken_at_timestamp"], reverse=True
    )

    if not chronological_posts:
        return {
            "verdict_code": "REJECTED",
            "verdict_title": "🔴 이 마이크로 인플루언서는 협찬하면 안 됩니다 (게시물 없음)",
            "verdict_badge": "🔴 협찬 불가 (게시물 미확인)",
            "activity_score": 0,
            "reasons": ["최근 업로드된 피드 및 릴스 게시물이 존재하지 않습니다."],
            "period_metrics": {},
            "tab_analysis": {},
            "posts": [],
        }

    # 2. 상단 고정(Pinned) 착시 분석 vs 실제 최신 업로드 경과일
    pinned_posts = [p for p in chronological_posts if p.get("is_pinned")]
    old_viral_pinned = [
        p for p in pinned_posts if p["days_ago"] > 30 and (p.get("view_count", 0) >= 100_000 or p.get("like_count", 0) >= 5_000)
    ]

    latest_real_post = chronological_posts[0]
    days_since_last_post = latest_real_post["days_ago"]
    latest_post_date = latest_real_post["upload_date"]

    posts_14d = [p for p in chronological_posts if p["days_ago"] <= 14]
    posts_30d = [p for p in chronological_posts if p["days_ago"] <= 30]
    posts_90d = [p for p in chronological_posts if p["days_ago"] <= 90]

    # 게시물 간 평균 업로드 주기 계산
    if len(chronological_posts) >= 2:
        non_pinned_sorted = [p for p in chronological_posts if not p.get("is_pinned")] or chronological_posts
        if len(non_pinned_sorted) >= 2:
            span_days = max(1, non_pinned_sorted[0]["days_ago"] - non_pinned_sorted[-1]["days_ago"])
            span_days = abs(non_pinned_sorted[-1]["days_ago"] - non_pinned_sorted[0]["days_ago"])
            avg_interval_days = round(span_days / (len(non_pinned_sorted) - 1), 1)
        else:
            avg_interval_days = float(days_since_last_post)
    else:
        avg_interval_days = float(days_since_last_post)

    # 3. 피드 탭 vs 릴스 탭 분리/통합 운영 진단
    feed_visible_posts = [p for p in chronological_posts if p["tab_source"] in ("feed", "both")]
    reels_tab_posts = [p for p in chronological_posts if p["tab_source"] in ("both", "reels_only")]
    reels_only_hidden_from_feed = [p for p in chronological_posts if p["tab_source"] == "reels_only"]

    photo_or_carousel_count = sum(1 for p in chronological_posts if p["media_format"] in ("image", "carousel"))
    reel_video_count = sum(1 for p in chronological_posts if p["media_format"] == "reel")
    total_sampled = len(chronological_posts)

    reel_ratio_pct = int(round((reel_video_count / total_sampled) * 100)) if total_sampled else 0
    photo_ratio_pct = 100 - reel_ratio_pct

    # 만약 메인 피드 탭만 봤을 때의 마지막 업로드 경과일 vs 릴스 탭을 통합했을 때의 실제 경과일 비교
    days_since_last_feed_tab = (
        min(p["days_ago"] for p in feed_visible_posts) if feed_visible_posts else 999
    )
    days_since_last_reels_tab = (
        min(p["days_ago"] for p in reels_tab_posts) if reels_tab_posts else 999
    )

    if len(reels_only_hidden_from_feed) >= 2 or (
        days_since_last_feed_tab > 14 and days_since_last_reels_tab <= 14
    ):
        operating_style = "🔀 피드·릴스 탭 분리 운영형 (릴스 탭 전용 업로드 활성)"
        operating_desc = (
            f"메인 피드에는 사진/캐러셀만 남기고(마지막 피드 {days_since_last_feed_tab}일 전), "
            f"릴스 영상({len(reels_only_hidden_from_feed)}건)은 '/reels/' 탭 전용으로 분리해 활발히 업로드 중입니다."
        )
        recommended_campaign = "🎬 릴스(숏폼) 단독 협찬 또는 피드 캐러셀+릴스 패키지"
    elif reel_ratio_pct >= 60:
        operating_style = "🎬 릴스 중심 통합 운영형"
        operating_desc = f"전체 게시물의 {reel_ratio_pct}%가 릴스이며, 메인 피드 그리드와 릴스 탭에 통합 노출하고 있습니다."
        recommended_campaign = "🎬 고조회수 타겟 릴스(Reels) 캠페인 최적"
    elif photo_ratio_pct >= 70:
        operating_style = "🖼️ 피드(사진·캐러셀) 중심 운영형"
        operating_desc = f"전체 게시물의 {photo_ratio_pct}%가 사진 및 다중 슬라이드 캐러셀 리뷰로 구성되어 있습니다."
        recommended_campaign = "🎠 다중 이미지/혼합 캐러셀 상세 리뷰 협찬 최적"
    else:
        operating_style = "⚖️ 피드·릴스 균형 통합 운영형"
        operating_desc = f"사진 캐러셀({photo_ratio_pct}%)과 릴스 영상({reel_ratio_pct}%)을 메인 피드와 릴스 탭에 골고루 업로드합니다."
        recommended_campaign = "✨ 피드 캐러셀 + 릴스 동시 업로드 캠페인 최적"

    # 4. 기간(Recency) 기반 활동성 점수 및 최종 협찬 가부 판정
    reasons: List[str] = []

    # 상단 고정 착시 경고/안내 추가
    if old_viral_pinned:
        top_pin = old_viral_pinned[0]
        if days_since_last_post > 30:
            reasons.append(
                f"🚨 [상단 고정 착시 차단] 프로필 상단에 조회수 {top_pin['view_count']:,}회 / 좋아요 {top_pin['like_count']:,}개의 인기 게시물이 고정되어 있으나, "
                f"실제 업로드일은 {top_pin['days_ago']}일 전({top_pin['upload_date']})입니다!"
            )
        else:
            reasons.append(
                f"📌 [고정 게시물 분리 완료] 상단 고정 게시물({top_pin['days_ago']}일 전, 조회수 {top_pin['view_count']:,}회)을 제외하고도 "
                f"실제 최신 게시물이 {days_since_last_post}일 전에 정상 업로드되었습니다."
            )

    # 피드/릴스 탭 분리 운영 구제 안내
    if days_since_last_feed_tab > 14 and days_since_last_reels_tab <= 14:
        reasons.append(
            f"💡 [탭 분리 운영 감지] 메인 피드 탭의 마지막 게시물은 {days_since_last_feed_tab}일 전이지만, "
            f"릴스 탭(/reels/) 전용 업로드를 통합 스캔하여 {days_since_last_reels_tab}일 전 신규 릴스 활동을 포착했습니다."
        )

    # 3단계 협찬 적합도 판정 (🟢 APPROVED / 🟡 CONDITIONAL / 🔴 REJECTED)
    cnt_30d = len(posts_30d)
    cnt_14d = len(posts_14d)

    if days_since_last_post <= 14 and cnt_30d >= 3:
        verdict_code = "APPROVED"
        verdict_title = "🟢 이 마이크로 인플루언서는 협찬해도 됩니다!"
        verdict_badge = "🟢 협찬 가능 (활성 계정)"
        activity_score = min(98, 78 + cnt_30d * 4 - days_since_last_post)
        reasons.insert(
            0,
            f"✅ [기간 활성도 우수] 마지막 실제 업로드가 {days_since_last_post}일 전({latest_post_date})이며, 최근 30일 내 {cnt_30d}개(최근 2주 내 {cnt_14d}개)의 피드/릴스를 꾸준히 업로드했습니다.",
        )
        reasons.append(
            f"📊 [채널 운영 적합도] '{operating_style}' 계정으로 평균 {avg_interval_days}일 주기로 콘텐츠를 발행하고 있어 협찬 캠페인 노출 안정성이 높습니다."
        )
    elif days_since_last_post <= 30 and cnt_30d >= 1:
        verdict_code = "CONDITIONAL"
        verdict_title = "🟡 조건부 협찬 검토 (최근 업로드 주기 확인 필요)"
        verdict_badge = "🟡 조건부 검토 (주의)"
        activity_score = max(45, 68 - days_since_last_post + cnt_30d * 5)
        reasons.insert(
            0,
            f"⚠️ [업로드 주기 주의] 마지막 실제 업로드가 {days_since_last_post}일 전({latest_post_date})이며, 최근 30일 내 업로드가 {cnt_30d}건으로 다소 적은 편입니다.",
        )
        reasons.append(
            "💬 스토리 소통 위주로 전환했거나 업로드 휴식기일 수 있으므로, 협찬 진행 전 최근 릴스/피드 업로드 일정 확약을 받는 것을 권장합니다."
        )
    else:
        verdict_code = "REJECTED"
        verdict_title = "🔴 이 마이크로 인플루언서는 협찬하면 안 됩니다! (휴면/활동 중단 위험)"
        verdict_badge = "🔴 협찬 불가 (휴면 위험)"
        activity_score = max(12, 35 - int(days_since_last_post / 3))
        reasons.insert(
            0,
            f"❌ [장기 미업로드 휴면 판정] 고정 게시물을 제외한 실제 마지막 업로드가 {days_since_last_post}일 전({latest_post_date})이며, 최근 30일 내 신규 피드·릴스 업로드가 {cnt_30d}건입니다.",
        )
        reasons.append(
            "🛑 과거 100만 조회수 릴스나 누적 팔로워 수가 높더라도 현재 피드/릴스 활동이 멈춘 상태이므로 협찬 집행 시 도달률 저하 위험이 매우 높습니다."
        )

    # 최근 30일 평균 반응도 vs 30일 이전 반응도 비교
    recent_likes_avg = (
        int(round(sum(p["like_count"] for p in posts_30d) / len(posts_30d)))
        if posts_30d
        else 0
    )
    recent_views_list = [p["view_count"] for p in posts_30d if p["view_count"] > 0]
    recent_views_avg = (
        int(round(sum(recent_views_list) / len(recent_views_list)))
        if recent_views_list
        else 0
    )

    older_posts = [p for p in chronological_posts if p["days_ago"] > 30]
    older_views_list = [p["view_count"] for p in older_posts if p["view_count"] > 0]
    older_views_max = max(older_views_list) if older_views_list else 0

    return {
        "verdict_code": verdict_code,  # "APPROVED" | "CONDITIONAL" | "REJECTED"
        "verdict_title": verdict_title,
        "verdict_badge": verdict_badge,
        "activity_score": activity_score,
        "reasons": reasons,
        "period_metrics": {
            "days_since_last_post": days_since_last_post,
            "latest_post_date": latest_post_date,
            "posts_last_14_days": cnt_14d,
            "posts_last_30_days": cnt_30d,
            "posts_last_90_days": len(posts_90d),
            "avg_upload_interval_days": avg_interval_days,
            "pinned_post_count": len(pinned_posts),
            "old_viral_pinned_count": len(old_viral_pinned),
            "days_since_last_feed_tab": days_since_last_feed_tab,
            "days_since_last_reels_tab": days_since_last_reels_tab,
        },
        "tab_analysis": {
            "operating_style": operating_style,
            "operating_desc": operating_desc,
            "recommended_campaign": recommended_campaign,
            "total_sampled": total_sampled,
            "feed_visible_count": len(feed_visible_posts),
            "reels_tab_count": len(reels_tab_posts),
            "reels_only_hidden_count": len(reels_only_hidden_from_feed),
            "photo_or_carousel_count": photo_or_carousel_count,
            "reel_video_count": reel_video_count,
            "reel_ratio_pct": reel_ratio_pct,
            "photo_ratio_pct": photo_ratio_pct,
        },
        "engagement_comparison": {
            "recent_30d_avg_likes": recent_likes_avg,
            "recent_30d_avg_views": recent_views_avg,
            "older_max_views": older_views_max,
        },
        "posts": chronological_posts,
    }


def analyze_instagram_profile(
    username: str,
    scenario_mode: str = "active_integrated",
    session_id: Optional[str] = None,
    sample_post_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    인스타그램 프로필 URL 입력 시 실행되는 통합 파이프라인:
    1) 실제 프로필 헤더 메타데이터(팔로워, 게시물 수, 소개글, 프로필 사진) 실시간 크롤링
    2) 피드 탭 + 릴스 탭 타임라인 수집 (또는 비로그인 제한 시 검증 시나리오/개별 URL 결합)
    3) 기간(Recency) & 탭 운영 방식 기반 협찬 가능/불가 판독 결과 생성
    """
    profile_info = fetch_live_profile_header(username)
    live_posts, data_source = _try_fetch_live_timeline_posts(
        profile_info["username"],
        session_id=session_id,
        sample_post_urls=sample_post_urls,
    )

    if not live_posts:
        live_posts = _build_scenario_timeline_posts(profile_info, scenario_mode=scenario_mode)
        data_source = f"scenario:{scenario_mode}"

    evaluation = evaluate_sponsorship_suitability(profile_info, live_posts)
    profile_pic_proxy = (
        f"/api/proxy-media?url={quote(profile_info['profile_pic_url'], safe='')}"
        if profile_info.get("profile_pic_url")
        else ""
    )

    return {
        "profile": {
            **profile_info,
            "profile_pic_proxy_url": profile_pic_proxy,
            "profile_url": f"https://www.instagram.com/{profile_info['username']}/",
            "reels_tab_url": f"https://www.instagram.com/{profile_info['username']}/reels/",
        },
        "data_source": data_source,
        "scenario_mode": scenario_mode,
        "evaluation": evaluation,
    }


# ==============================================================================
# 웹에서 바로 테스트할 수 있는 FastAPI 서버 & 인플루언서 협찬 판독 대시보드 (포트: 8000)
# ==============================================================================
app = FastAPI(
    title="Instagram Media Extractor & Influencer Sponsorship AI Agent Evaluator (test.py)",
    description=(
        "1) 개별 게시물/릴스/혼합 캐러셀 슬라이드 추출 및 스트리밍 재생\n"
        "2) 프로필 링크 입력 시 피드+릴스 탭 통합 수집 및 기간(Recency) 기반 마이크로 인플루언서 협찬 적합도 대시보드"
    ),
    version="4.0.0",
)


class InstagramRequest(BaseModel):
    ig_url: str
    scenario_mode: Optional[str] = "active_integrated"
    session_id: Optional[str] = None
    sample_post_urls: Optional[List[str]] = None


@app.post("/api/extract")
def api_extract_instagram_media(req: InstagramRequest):
    url_info = detect_instagram_url_type(req.ig_url)

    # ★ 분기 1: 프로필 URL (예: https://www.instagram.com/songgang.ho/) 이 입력된 경우
    if url_info["mode"] == "profile":
        username = url_info["username"]
        try:
            analysis = analyze_instagram_profile(
                username=username,
                scenario_mode=req.scenario_mode or "active_integrated",
                session_id=req.session_id,
                sample_post_urls=req.sample_post_urls,
            )
            return {
                "mode": "profile",
                "input_url": req.ig_url,
                "username": username,
                "tab_hint": url_info.get("tab_hint", "feed"),
                "success": True,
                "profile_analysis": analysis,
                "error": None,
            }
        except Exception as e:
            return {
                "mode": "profile",
                "input_url": req.ig_url,
                "username": username,
                "success": False,
                "profile_analysis": None,
                "error": f"프로필 분석 중 오류 발생: {str(e)}",
            }

    # ★ 분기 2: 개별 게시물 / 단독 릴스 / 캐러셀 URL이 입력된 경우 (기존 기능 100% 유지 + 업로드 일시 메타데이터 추가)
    shortcode = url_info["shortcode"]
    try:
        items = get_instagram_media_items(req.ig_url)
        _, post_meta = _query_public_graphql_with_meta(shortcode)

        enriched_items = []
        for item in items:
            proxy_media_url = f"/api/proxy-media?url={quote(item['url'], safe='')}"
            proxy_thumb_url = f"/api/proxy-media?url={quote(item['thumbnail_url'], safe='')}"
            enriched_items.append(
                {
                    "index": item["index"],
                    "media_type": item["media_type"],  # "image" | "video"
                    "url": item["url"],
                    "thumbnail_url": item["thumbnail_url"],
                    "proxy_url": proxy_media_url,
                    "thumb_proxy_url": proxy_thumb_url,
                }
            )

        image_count = sum(1 for x in enriched_items if x["media_type"] == "image")
        video_count = sum(1 for x in enriched_items if x["media_type"] == "video")
        media_urls = [x["url"] for x in enriched_items]
        proxy_urls = [x["proxy_url"] for x in enriched_items]

        # 게시물 업로드 경과일 계산
        post_timing = None
        if post_meta and post_meta.get("taken_at_timestamp"):
            ts = int(post_meta["taken_at_timestamp"])
            days_ago = max(0, int(round((int(time.time()) - ts) / 86400)))
            post_timing = {
                "upload_date": datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M"),
                "days_ago": days_ago,
                "owner_username": post_meta.get("owner_username", ""),
                "owner_full_name": post_meta.get("owner_full_name", ""),
                "like_count": post_meta.get("like_count", 0),
                "comment_count": post_meta.get("comment_count", 0),
                "view_count": post_meta.get("view_count", 0),
                "caption": (post_meta.get("caption") or "")[:200],
            }

        return {
            "mode": "post",
            "input_url": req.ig_url,
            "shortcode": shortcode,
            "success": True,
            "count": len(enriched_items),
            "image_count": image_count,
            "video_count": video_count,
            "is_carousel": len(enriched_items) > 1,
            "post_timing": post_timing,
            "items": enriched_items,
            "image_url": media_urls[0],
            "proxy_url": proxy_urls[0],
            "image_urls": media_urls,
            "proxy_urls": proxy_urls,
            "error": None,
        }
    except Exception as e:
        return {
            "mode": "post",
            "input_url": req.ig_url,
            "shortcode": shortcode,
            "success": False,
            "count": 0,
            "image_count": 0,
            "video_count": 0,
            "is_carousel": False,
            "items": [],
            "image_url": None,
            "proxy_url": None,
            "image_urls": [],
            "proxy_urls": [],
            "error": str(e),
        }


@app.get("/api/proxy-media")
@app.get("/api/proxy-image")
def proxy_instagram_media(
    request: Request,
    url: str = Query(..., description="인스타그램 CDN 이미지 또는 릴스 동영상(.mp4) URL"),
):
    """
    ★ 장시간 릴스(수분~십수분)도 끊김이나 타임아웃 없이 즉시 재생 및 구간 탐색(Seek)이 가능하도록
    HTTP Range 헤더와 청크 스트리밍(StreamingResponse)을 지원하는 미디어 프록시
    """
    try:
        req_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.instagram.com/",
        }
        range_header = request.headers.get("range") or request.headers.get("Range")
        if range_header:
            req_headers["Range"] = range_header

        upstream = requests.get(url, headers=req_headers, stream=True, timeout=60)
        content_type = upstream.headers.get("Content-Type", "application/octet-stream")

        resp_headers = {
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
        }
        for h_name in ("Content-Length", "Content-Range"):
            if h_name in upstream.headers:
                resp_headers[h_name] = upstream.headers[h_name]

        def iter_chunks():
            try:
                for chunk in upstream.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk
            finally:
                upstream.close()

        return StreamingResponse(
            iter_chunks(),
            status_code=upstream.status_code,
            media_type=content_type,
            headers=resp_headers,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"미디어 스트리밍 로드 실패: {e}")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def serve_web_ui():
    return """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Instagram 미디어 추출 & 마이크로 인플루언서 협찬 판독 대시보드 (test.py)</title>
  <style>
    :root {
      --bg: #0f172a;
      --card: #1e293b;
      --sub: #0f172a;
      --text: #f8fafc;
      --muted: #94a3b8;
      --border: rgba(148, 163, 184, 0.22);
      --primary: #6366f1;
      --pink: #ec4899;
      --green: #10b981;
      --amber: #f59e0b;
      --danger: #f43f5e;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Malgun Gothic', sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 2rem 1.25rem;
      max-width: 1160px;
      margin: 0 auto;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-top: 3px solid var(--pink);
      border-radius: 16px;
      padding: 1.55rem;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.4);
      margin-bottom: 1.4rem;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      padding: 0.25rem 0.75rem;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 700;
      background: rgba(236, 72, 153, 0.18);
      color: #f9a8d4;
      border: 1px solid rgba(236, 72, 153, 0.4);
    }
    .badge-green {
      background: rgba(16, 185, 129, 0.18);
      color: #6ee7b7;
      border: 1px solid rgba(16, 185, 129, 0.4);
    }
    .badge-amber {
      background: rgba(245, 158, 11, 0.2);
      color: #fcd34d;
      border: 1px solid rgba(245, 158, 11, 0.45);
    }
    .badge-red {
      background: rgba(244, 63, 94, 0.2);
      color: #fda4af;
      border: 1px solid rgba(244, 63, 94, 0.45);
    }
    .badge-video {
      background: rgba(245, 158, 11, 0.2);
      color: #fcd34d;
      border: 1px solid rgba(245, 158, 11, 0.45);
    }
    .badge-image {
      background: rgba(99, 102, 241, 0.2);
      color: #c7d2fe;
      border: 1px solid rgba(99, 102, 241, 0.45);
    }
    .input {
      flex: 1;
      padding: 0.8rem 1rem;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: var(--sub);
      color: var(--text);
      font-size: 0.95rem;
    }
    .input:focus { outline: none; border-color: var(--pink); }
    .btn {
      padding: 0.8rem 1.35rem;
      border-radius: 10px;
      border: none;
      font-weight: 800;
      font-size: 0.92rem;
      cursor: pointer;
      background: linear-gradient(135deg, #ec4899, #6366f1);
      color: #fff;
    }
    .btn-outline {
      padding: 0.42rem 0.78rem;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: var(--sub);
      color: var(--text);
      font-size: 0.77rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }
    .btn-outline:hover { background: #334155; }
    .btn-outline.active {
      background: rgba(99, 102, 241, 0.28);
      border-color: #818cf8;
      color: #e0e7ff;
    }
    code {
      font-family: Consolas, monospace;
      background: rgba(99, 102, 241, 0.15);
      color: #a5b4fc;
      padding: 2px 6px;
      border-radius: 4px;
      word-break: break-all;
    }
    .hidden { display: none !important; }

    /* 프로필 협찬 대시보드 전용 스타일 */
    .profile-header {
      display: flex;
      gap: 1.25rem;
      align-items: center;
      flex-wrap: wrap;
      padding: 1.15rem;
      background: var(--sub);
      border: 1px solid var(--border);
      border-radius: 14px;
      margin-bottom: 1.2rem;
    }
    .profile-avatar {
      width: 78px;
      height: 78px;
      border-radius: 50%;
      object-fit: cover;
      border: 3px solid var(--pink);
      background: #090d16;
    }
    .verdict-banner {
      border-radius: 14px;
      padding: 1.25rem 1.4rem;
      margin-bottom: 1.25rem;
      border: 1px solid var(--border);
    }
    .verdict-APPROVED {
      background: rgba(16, 185, 129, 0.13);
      border-color: rgba(16, 185, 129, 0.45);
    }
    .verdict-CONDITIONAL {
      background: rgba(245, 158, 11, 0.13);
      border-color: rgba(245, 158, 11, 0.45);
    }
    .verdict-REJECTED {
      background: rgba(244, 63, 94, 0.14);
      border-color: rgba(244, 63, 94, 0.48);
    }
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 0.95rem;
      margin-bottom: 1.25rem;
    }
    .kpi-box {
      background: var(--sub);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1rem;
    }
    .kpi-title {
      font-size: 0.78rem;
      color: var(--muted);
      font-weight: 700;
      margin-bottom: 0.4rem;
    }
    .kpi-val {
      font-size: 1.35rem;
      font-weight: 800;
      margin-bottom: 0.3rem;
    }
    .kpi-sub {
      font-size: 0.78rem;
      color: #cbd5e1;
      line-height: 1.45;
    }
    .ratio-bar {
      height: 10px;
      border-radius: 999px;
      background: #1e293b;
      overflow: hidden;
      display: flex;
      margin-top: 0.45rem;
    }

    /* 상단 메인 슬라이더 뷰어 */
    .carousel-viewer {
      position: relative;
      background: var(--sub);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 1.25rem;
      text-align: center;
      margin-bottom: 1.35rem;
    }
    .carousel-nav-btn {
      position: absolute;
      top: 50%;
      transform: translateY(-50%);
      width: 42px;
      height: 42px;
      border-radius: 50%;
      border: 1px solid var(--border);
      background: rgba(30, 41, 59, 0.92);
      color: #fff;
      font-size: 1.1rem;
      font-weight: 900;
      cursor: pointer;
      z-index: 10;
    }
    .carousel-nav-btn:hover { background: var(--primary); }
    .carousel-nav-btn.prev { left: 14px; }
    .carousel-nav-btn.next { right: 14px; }

    /* 전체 슬라이드 그리드 */
    .gallery-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 1rem;
      margin-top: 0.75rem;
    }
    .slide-card {
      background: var(--sub);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 0.95rem;
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
    }
    .slide-media-box {
      width: 100%;
      height: 240px;
      border-radius: 8px;
      overflow: hidden;
      background: #090d16;
      border: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .slide-media-box img,
    .slide-media-box video {
      width: 100%;
      height: 100%;
      object-fit: cover;
      cursor: pointer;
    }
  </style>
</head>
<body>
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;">
      <span class="badge">🤖📸🎬 c:\\workAI\\work9\\test.py (프로필 협찬 판독 대시보드 + 사진·릴스·혼합 캐러셀 추출)</span>
      <a href="/docs" target="_blank" style="color:#a5b4fc;font-size:0.84rem;text-decoration:none;font-weight:700;">📘 Swagger API 문서 (/docs) →</a>
    </div>
    <h1 style="font-size:1.42rem;margin-top:0.65rem;">인스타그램 미디어 추출 & 마이크로 인플루언서 협찬 적합도 판독기</h1>
    <p style="font-size:0.86rem;color:var(--muted);margin-top:0.35rem;line-height:1.55;">
      • <strong>프로필 링크(예: <code>https://www.instagram.com/songgang.ho/</code>)</strong> 입력 시: <strong>기간(업로드 경과일·상단 고정 착시 차단)</strong>과 <strong>피드 탭 / 릴스 탭 분리 운영 여부</strong>를 종합 분석하여 <strong>"협찬 가능 / 조건부 / 협찬 불가" 대시보드</strong>를 보여줍니다.<br/>
      • <strong>게시물/릴스 링크(<code>/p/...</code>, <code>/reel/...</code>)</strong> 입력 시: 단독 사진, 단독 릴스(길이 무관), 혼합 캐러셀(사진+영상) 슬라이드를 모두 추출합니다.
    </p>

    <form onsubmit="handleExtract(event)" style="display:flex;gap:0.65rem;margin-top:1.15rem;flex-wrap:wrap;">
      <input
        id="igUrlInput"
        class="input"
        type="text"
        value="https://www.instagram.com/songgang.ho/"
        placeholder="프로필 링크(https://www.instagram.com/username/) 또는 게시물·릴스(/p/..., /reel/...) URL 입력"
        required
      />
      <button id="submitBtn" type="submit" class="btn">🔍 AI 분석 / 미디어 추출</button>
    </form>

    <div style="display:flex;gap:0.45rem;flex-wrap:wrap;margin-top:0.75rem;align-items:center;">
      <span style="font-size:0.77rem;color:var(--muted);font-weight:700;">⚡ 빠른 테스트:</span>
      <button type="button" class="btn-outline" onclick="quickFillAndSubmit('https://www.instagram.com/songgang.ho/', 'active_integrated')">
        👤 @songgang.ho 프로필 분석 (🟢 활성 통합형)
      </button>
      <button type="button" class="btn-outline" onclick="quickFillAndSubmit('https://www.instagram.com/songgang.ho/', 'dormant_pinned_trap')">
        🚨 3개월 전 100만 릴스 고정 휴면 케이스 (🔴 협찬 불가)
      </button>
      <button type="button" class="btn-outline" onclick="quickFillAndSubmit('https://www.instagram.com/songgang.ho/', 'split_tabs_active')">
        🔀 피드(사진)/릴스(영상) 탭 분리 운영 케이스 (🟢 협찬 가능)
      </button>
    </div>
  </div>

  <!-- ====================================================================== -->
  <!-- A. 프로필 분석 & 마이크로 인플루언서 협찬 적합도 대시보드 영역 (mode === 'profile') -->
  <!-- ====================================================================== -->
  <div id="profileDashboardCard" class="card hidden" style="border-top-color: var(--green);">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.6rem;margin-bottom:1rem;">
      <div style="display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap;">
        <h2 style="font-size:1.18rem;">📊 마이크로 인플루언서 협찬 적합도 & 기간·탭 운영 분석 대시보드</h2>
        <span id="profileSourceBadge" class="badge badge-image"></span>
      </div>
      <div style="display:flex;gap:0.4rem;flex-wrap:wrap;">
        <button type="button" id="scBtn_active_integrated" class="btn-outline" onclick="switchProfileScenario('active_integrated')">
          🟢 시나리오 1: 활성 통합형
        </button>
        <button type="button" id="scBtn_dormant_pinned_trap" class="btn-outline" onclick="switchProfileScenario('dormant_pinned_trap')">
          🔴 시나리오 2: 3개월 전 100만 릴스 고정(휴면)
        </button>
        <button type="button" id="scBtn_split_tabs_active" class="btn-outline" onclick="switchProfileScenario('split_tabs_active')">
          🔀 시나리오 3: 피드·릴스 탭 분리 운영형
        </button>
        <button type="button" id="scBtn_warning_slow" class="btn-outline" onclick="switchProfileScenario('warning_slow')">
          🟡 시나리오 4: 업로드 주기 저하(주의)
        </button>
      </div>
    </div>

    <!-- 1) 인플루언서 실시간 프로필 헤더 -->
    <div id="profileHeaderBox" class="profile-header"></div>

    <!-- 2) 협찬 가능 / 불가 최종 판정 배너 -->
    <div id="verdictBannerBox" class="verdict-banner"></div>

    <!-- 3) 4대 핵심 기간(Recency) & 피드/릴스 탭 운영 KPI 그리드 -->
    <div id="kpiGridBox" class="kpi-grid"></div>

    <!-- 4) 실제 게시물/릴스 링크 직접 주입하여 타임스탬프 실측 테스트 (선택 아코디언) -->
    <details style="background:var(--sub);border:1px solid var(--border);border-radius:12px;padding:0.85rem 1rem;margin-bottom:1.25rem;">
      <summary style="cursor:pointer;font-size:0.84rem;font-weight:700;color:#a5b4fc;">
        ➕ [고급 검증] 이 인플루언서의 실제 게시물(/p/...) · 릴스(/reel/...) 링크들을 직접 넣어 100% 실측 타임스탬프로 판독하기
      </summary>
      <div style="margin-top:0.75rem;display:flex;flex-direction:column;gap:0.55rem;">
        <p style="font-size:0.78rem;color:var(--muted);line-height:1.45;">
          인스타그램 비로그인 정책상 프로필 타임라인 목록은 제한될 수 있습니다. 아래에 이 계정의 실제 게시물/릴스 URL을 줄바꿈으로 여러 개 붙여넣으면 각 게시물의 <strong>실제 업로드 일시(taken_at_timestamp), 슬라이드, 조회수/좋아요</strong>를 실시간 추출하여 협찬 적합도를 실측 판독합니다.
        </p>
        <textarea
          id="customPostUrlsTextarea"
          rows="3"
          class="input"
          placeholder="예시:&#10;https://www.instagram.com/reel/SHORTCODE1/&#10;https://www.instagram.com/p/SHORTCODE2/"
          style="font-family:Consolas,monospace;font-size:0.82rem;"
        ></textarea>
        <div style="display:flex;justify-content:flex-end;">
          <button type="button" class="btn" style="padding:0.55rem 1rem;font-size:0.82rem;" onclick="runCustomPostUrlsProfileCheck()">
            🔬 입력한 실제 게시물들로 프로필 협찬 적합도 다시 판독
          </button>
        </div>
      </div>
    </details>

    <!-- 5) 피드 탭 + 릴스 탭 통합 타임라인 리스트 (실제 업로드 최신순) -->
    <div>
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;margin-bottom:0.65rem;">
        <div style="font-size:0.95rem;font-weight:800;">
          🗓️ 피드 탭 + 릴스 탭 통합 타임라인 (고정 착시 제외 · 실제 업로드 최신순 정렬)
        </div>
        <div style="display:flex;gap:0.35rem;flex-wrap:wrap;">
          <button type="button" id="tabFilter_all" class="btn-outline active" onclick="filterProfilePosts('all')">전체 통합 (최신순)</button>
          <button type="button" id="tabFilter_feed" class="btn-outline" onclick="filterProfilePosts('feed')">📸 메인 피드 탭 노출</button>
          <button type="button" id="tabFilter_reels_only" class="btn-outline" onclick="filterProfilePosts('reels_only')">🎬 릴스 탭 전용 (피드 숨김)</button>
          <button type="button" id="tabFilter_pinned" class="btn-outline" onclick="filterProfilePosts('pinned')">📌 상단 고정 게시물</button>
        </div>
      </div>
      <div id="profileTimelineGrid" class="gallery-grid"></div>
    </div>
  </div>

  <!-- ====================================================================== -->
  <!-- B. 개별 게시물 / 단독 릴스 / 혼합 캐러셀 추출 결과 영역 (mode === 'post') -->
  <!-- ====================================================================== -->
  <div id="resultCard" class="card hidden" style="border-top-color: var(--primary);">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;margin-bottom:1rem;">
      <div style="display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap;">
        <h3 id="resultStatus" style="font-size:1.1rem;">추출 결과</h3>
        <span id="countBadge" class="badge badge-green"></span>
        <span id="postTimingBadge" class="badge badge-image hidden"></span>
      </div>
      <button id="copyAllBtn" type="button" class="btn-outline" onclick="copyAllUrls()">📋 전체 미디어 URL 일괄 복사</button>
    </div>

    <div id="errorBox" class="hidden" style="padding:1rem;border-radius:10px;background:rgba(244,63,94,0.15);border:1px solid rgba(244,63,94,0.35);color:#fda4af;font-size:0.88rem;line-height:1.5;"></div>

    <div id="successBox" class="hidden">
      <div style="margin-bottom:1rem;font-size:0.85rem;display:flex;gap:1rem;flex-wrap:wrap;align-items:center;">
        <div>
          <span style="color:var(--muted);">Shortcode:</span>
          <code id="shortcodeVal" style="margin-left:6px;"></code>
        </div>
        <div id="postOwnerInfo" style="color:#cbd5e1;font-size:0.83rem;"></div>
      </div>

      <!-- 1) 상단 메인 슬라이더 뷰어 -->
      <div class="carousel-viewer">
        <button id="prevBtn" type="button" class="carousel-nav-btn prev" onclick="moveSlide(-1)">❮</button>
        <div id="activeMediaContainer" style="min-height:280px;display:flex;align-items:center;justify-content:center;"></div>
        <button id="nextBtn" type="button" class="carousel-nav-btn next" onclick="moveSlide(1)">❯</button>
        <div id="slideIndicator" style="margin-top:0.75rem;font-size:0.86rem;font-weight:700;color:#cbd5e1;"></div>
      </div>

      <!-- 2) 전체 슬라이드 카드 그리드 -->
      <div>
        <div style="font-size:0.9rem;font-weight:800;margin-bottom:0.5rem;">
          🗂️ 추출된 슬라이드별 상세 목록 (사진 / 동영상 자동 구분)
        </div>
        <div id="galleryGrid" class="gallery-grid"></div>
      </div>
    </div>
  </div>

  <script>
    let extractedItems = [];
    let currentSlideIdx = 0;
    let currentProfilePosts = [];
    let currentScenarioMode = 'active_integrated';
    let currentProfileTabFilter = 'all';

    function quickFillAndSubmit(url, scenarioMode) {
      document.getElementById('igUrlInput').value = url;
      currentScenarioMode = scenarioMode || 'active_integrated';
      runExtraction(url, currentScenarioMode, null);
    }

    function switchProfileScenario(scenarioMode) {
      currentScenarioMode = scenarioMode;
      const url = document.getElementById('igUrlInput').value.trim();
      if (!url) return;
      runExtraction(url, currentScenarioMode, null);
    }

    function runCustomPostUrlsProfileCheck() {
      const url = document.getElementById('igUrlInput').value.trim();
      const rawLines = document.getElementById('customPostUrlsTextarea').value
        .split('\\n')
        .map(s => s.trim())
        .filter(Boolean);
      if (!rawLines.length) {
        alert('분석할 실제 게시물(/p/...) 또는 릴스(/reel/...) URL을 1개 이상 입력해주세요.');
        return;
      }
      runExtraction(url, currentScenarioMode, rawLines);
    }

    function renderProfileDashboard(data) {
      const analysis = data.profile_analysis;
      const prof = analysis.profile;
      const evalData = analysis.evaluation;
      const pm = evalData.period_metrics;
      const tab = evalData.tab_analysis;
      const eng = evalData.engagement_comparison;

      document.getElementById('resultCard').classList.add('hidden');
      const dashCard = document.getElementById('profileDashboardCard');
      dashCard.classList.remove('hidden');

      // 시나리오 버튼 활성화 표시
      ['active_integrated', 'dormant_pinned_trap', 'split_tabs_active', 'warning_slow'].forEach(sc => {
        const b = document.getElementById('scBtn_' + sc);
        if (b) b.classList.toggle('active', analysis.scenario_mode === sc && analysis.data_source.startsWith('scenario:'));
      });

      const srcBadge = document.getElementById('profileSourceBadge');
      if (analysis.data_source === 'live_api') {
        srcBadge.textContent = '🟢 실시간 타임라인 API 연동됨';
      } else if (analysis.data_source === 'live_post_urls') {
        srcBadge.textContent = '🔬 실제 게시물 타임스탬프 실측 모드';
      } else {
        srcBadge.textContent = '⚡ 실시간 프로필 메타 + 기간·탭 검증 시뮬레이션 모드';
      }

      // 1) 프로필 헤더 렌더링
      const avatarHtml = prof.profile_pic_proxy_url
        ? `<img src="${prof.profile_pic_proxy_url}" class="profile-avatar" alt="${prof.username}" />`
        : `<div class="profile-avatar" style="display:flex;align-items:center;justify-content:center;font-size:1.8rem;">👤</div>`;

      document.getElementById('profileHeaderBox').innerHTML = `
        ${avatarHtml}
        <div style="flex:1;min-width:240px;">
          <div style="display:flex;align-items:center;gap:0.55rem;flex-wrap:wrap;">
            <span style="font-size:1.22rem;font-weight:800;">${prof.full_name}</span>
            <a href="${prof.profile_url}" target="_blank" style="color:#f9a8d4;font-weight:700;text-decoration:none;">@${prof.username} ↗</a>
            <span class="badge">${prof.influencer_tier}</span>
            ${prof.is_live_fetched ? '<span class="badge badge-green">✓ 실시간 프로필 메타데이터 추출 완료</span>' : ''}
          </div>
          <div style="display:flex;gap:1.3rem;margin-top:0.55rem;font-size:0.9rem;flex-wrap:wrap;">
            <div>팔로워: <strong>${prof.followers.toLocaleString()}명</strong> <span style="color:var(--muted);">(${prof.followers_display})</span></div>
            <div>팔로잉: <strong>${prof.following.toLocaleString()}명</strong></div>
            <div>총 누적 게시물: <strong>${prof.total_posts.toLocaleString()}개</strong></div>
          </div>
          <div style="margin-top:0.5rem;font-size:0.83rem;color:#cbd5e1;white-space:pre-line;line-height:1.45;">${prof.biography || '소개글 없음'}</div>
        </div>
      `;

      // 2) 최종 협찬 적합도 배너 렌더링
      const vBox = document.getElementById('verdictBannerBox');
      vBox.className = 'verdict-banner verdict-' + evalData.verdict_code;
      const scoreColor = evalData.verdict_code === 'APPROVED' ? '#34d399' : (evalData.verdict_code === 'CONDITIONAL' ? '#fbbf24' : '#fb7185');

      vBox.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.75rem;margin-bottom:0.75rem;">
          <div>
            <div style="font-size:0.78rem;color:var(--muted);font-weight:700;margin-bottom:0.2rem;">
              AI 에이전트 협찬 적합도 최종 판독 결과 (피드·릴스 기간 & 탭 통합 기준)
            </div>
            <div style="font-size:1.32rem;font-weight:900;color:${scoreColor};">${evalData.verdict_title}</div>
          </div>
          <div style="text-align:right;background:rgba(15,23,42,0.65);padding:0.55rem 1rem;border-radius:10px;border:1px solid var(--border);">
            <div style="font-size:0.74rem;color:var(--muted);">기간 활성도 점수</div>
            <div style="font-size:1.45rem;font-weight:900;color:${scoreColor};">${evalData.activity_score} <span style="font-size:0.85rem;color:#cbd5e1;">/ 100점</span></div>
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:0.42rem;font-size:0.86rem;line-height:1.5;">
          ${evalData.reasons.map(r => `<div>${r}</div>`).join('')}
        </div>
      `;

      // 3) 4대 핵심 KPI 카드 렌더링
      document.getElementById('kpiGridBox').innerHTML = `
        <div class="kpi-box">
          <div class="kpi-title">⏱️ 실제 최신 업로드 경과일 (고정 착시 제외)</div>
          <div class="kpi-val" style="color:${pm.days_since_last_post <= 14 ? '#34d399' : (pm.days_since_last_post <= 30 ? '#fbbf24' : '#fb7185')};">
            ${pm.days_since_last_post}일 전 <span style="font-size:0.82rem;font-weight:600;color:var(--muted);">(${pm.latest_post_date})</span>
          </div>
          <div class="kpi-sub">
            • 메인 피드 탭 기준 마지막: <strong>${pm.days_since_last_feed_tab}일 전</strong><br/>
            • 릴스 탭(/reels/) 기준 마지막: <strong>${pm.days_since_last_reels_tab}일 전</strong><br/>
            • 상단 고정(📌) 게시물: <strong>${pm.pinned_post_count}개</strong> ${pm.old_viral_pinned_count > 0 ? '<span style="color:#fda4af;">(구형 바이럴 고정 감지됨)</span>' : ''}
          </div>
        </div>

        <div class="kpi-box">
          <div class="kpi-title">📅 기간별 업로드 밀도 & 평균 주기</div>
          <div class="kpi-val">최근 30일 ${pm.posts_last_30_days}건</div>
          <div class="kpi-sub">
            • 최근 14일(2주) 업로드: <strong>${pm.posts_last_14_days}건</strong><br/>
            • 최근 90일(3개월) 업로드: <strong>${pm.posts_last_90_days}건</strong><br/>
            • 평균 업로드 주기: <strong>약 ${pm.avg_upload_interval_days}일마다 1건</strong>
          </div>
        </div>

        <div class="kpi-box">
          <div class="kpi-title">🗂️ 피드 탭 vs 릴스 탭 운영 스타일 진단</div>
          <div class="kpi-val" style="font-size:1.02rem;color:#c7d2fe;">${tab.operating_style}</div>
          <div class="ratio-bar">
            <div style="width:${tab.photo_ratio_pct}%;background:#6366f1;" title="사진/캐러셀 ${tab.photo_ratio_pct}%"></div>
            <div style="width:${tab.reel_ratio_pct}%;background:#f59e0b;" title="릴스 영상 ${tab.reel_ratio_pct}%"></div>
          </div>
          <div class="kpi-sub" style="margin-top:0.45rem;">
            🖼️ 사진·캐러셀 <strong>${tab.photo_ratio_pct}%</strong> (${tab.photo_or_carousel_count}건) vs 🎬 릴스 <strong>${tab.reel_ratio_pct}%</strong> (${tab.reel_video_count}건)<br/>
            • 릴스 탭 전용(피드 숨김): <strong>${tab.reels_only_hidden_count}건</strong>
          </div>
        </div>

        <div class="kpi-box">
          <div class="kpi-title">🔥 최근 30일 실질 반응도 vs 구형 최고치</div>
          <div class="kpi-val">${eng.recent_30d_avg_views > 0 ? '평균 조회 ' + eng.recent_30d_avg_views.toLocaleString() + '회' : '최근 30일 릴스 없음'}</div>
          <div class="kpi-sub">
            • 최근 30일 평균 좋아요: <strong>${eng.recent_30d_avg_likes.toLocaleString()}개</strong><br/>
            • 30일 이전 구형 최고 조회수: <strong>${eng.older_max_views.toLocaleString()}회</strong><br/>
            • 추천 캠페인: <strong style="color:#f9a8d4;">${tab.recommended_campaign}</strong>
          </div>
        </div>
      `;

      // 4) 통합 타임라인 렌더링
      currentProfilePosts = evalData.posts || [];
      filterProfilePosts('all');
    }

    function filterProfilePosts(filterKey) {
      currentProfileTabFilter = filterKey;
      ['all', 'feed', 'reels_only', 'pinned'].forEach(k => {
        const btn = document.getElementById('tabFilter_' + k);
        if (btn) btn.classList.toggle('active', k === filterKey);
      });

      let filtered = currentProfilePosts;
      if (filterKey === 'feed') {
        filtered = currentProfilePosts.filter(p => p.tab_source === 'feed' || p.tab_source === 'both');
      } else if (filterKey === 'reels_only') {
        filtered = currentProfilePosts.filter(p => p.tab_source === 'reels_only');
      } else if (filterKey === 'pinned') {
        filtered = currentProfilePosts.filter(p => p.is_pinned);
      }

      const grid = document.getElementById('profileTimelineGrid');
      if (!filtered.length) {
        grid.innerHTML = `<div style="padding:1.2rem;color:var(--muted);font-size:0.88rem;">해당 탭 조건에 맞는 게시물이 없습니다.</div>`;
        return;
      }

      grid.innerHTML = filtered.map((p, idx) => {
        const formatBadge = p.media_format === 'reel'
          ? '<span class="badge badge-video">🎬 릴스(Reels)</span>'
          : (p.media_format === 'carousel' ? `<span class="badge badge-image">🎠 캐러셀 (${p.slide_count}슬라이드)</span>` : '<span class="badge badge-image">🖼️ 단독 사진</span>');

        const tabBadge = p.tab_source === 'reels_only'
          ? '<span class="badge badge-amber">⚡ 릴스 탭 전용 (피드 숨김)</span>'
          : (p.tab_source === 'both' ? '<span class="badge badge-green">피드 + 릴스 탭 노출</span>' : '<span class="badge">메인 피드 탭</span>');

        const pinBadge = p.is_pinned
          ? '<span class="badge badge-red">📌 상단 고정됨</span>'
          : '';

        const recencyClass = p.recency_level === 'fresh' ? 'badge-green' : (p.recency_level === 'moderate' ? 'badge-amber' : 'badge-red');

        return `
          <div class="slide-card" style="${p.is_pinned && p.days_ago > 30 ? 'border-color:rgba(244,63,94,0.55);' : ''}">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:0.35rem;flex-wrap:wrap;">
              <span class="badge ${recencyClass}">${p.recency_badge} (${p.days_ago}일 전)</span>
              <span style="font-size:0.76rem;color:var(--muted);font-weight:700;">${p.upload_date}</span>
            </div>
            <div style="display:flex;gap:0.35rem;flex-wrap:wrap;">
              ${pinBadge}
              ${formatBadge}
              ${tabBadge}
            </div>
            <div style="font-size:0.82rem;color:#e2e8f0;line-height:1.45;min-height:42px;">
              ${p.caption || '캡션 없음'}
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;font-size:0.78rem;color:#cbd5e1;padding-top:0.4rem;border-top:1px solid var(--border);">
              <div>
                ❤️ ${p.like_count.toLocaleString()} · 💬 ${p.comment_count.toLocaleString()}
                ${p.view_count > 0 ? ` · ▶️ <strong>${p.view_count.toLocaleString()}회</strong>` : ''}
              </div>
              ${p.is_simulated
                ? `<span style="font-size:0.73rem;color:var(--muted);">🧪 시나리오 샘플</span>`
                : `<button type="button" class="btn-outline" onclick="quickInspectPostUrl('${p.post_url}')">🔍 슬라이드 추출</button>`
              }
            </div>
          </div>
        `;
      }).join('');
    }

    function quickInspectPostUrl(postUrl) {
      document.getElementById('igUrlInput').value = postUrl;
      runExtraction(postUrl, currentScenarioMode, null);
    }

    function updateActiveSlide(idx) {
      if (!extractedItems.length) return;
      currentSlideIdx = (idx + extractedItems.length) % extractedItems.length;
      const item = extractedItems[currentSlideIdx];
      const container = document.getElementById('activeMediaContainer');

      if (item.media_type === 'video') {
        container.innerHTML = `
          <video
            src="${item.proxy_url}"
            poster="${item.thumb_proxy_url || ''}"
            controls
            autoplay
            playsinline
            style="max-width:100%;max-height:520px;border-radius:10px;background:#000;"
          ></video>
        `;
      } else {
        container.innerHTML = `
          <img
            src="${item.proxy_url}"
            alt="슬라이드 ${currentSlideIdx + 1}"
            style="max-width:100%;max-height:520px;border-radius:10px;"
          />
        `;
      }

      const typeLabel = item.media_type === 'video' ? '🎬 동영상(릴스)' : '🖼️ 이미지(사진)';
      document.getElementById('slideIndicator').textContent =
        `슬라이드 ${currentSlideIdx + 1} / ${extractedItems.length} — [${typeLabel}]`;

      const showNav = extractedItems.length > 1;
      document.getElementById('prevBtn').classList.toggle('hidden', !showNav);
      document.getElementById('nextBtn').classList.toggle('hidden', !showNav);
    }

    function moveSlide(delta) {
      updateActiveSlide(currentSlideIdx + delta);
    }

    function buildSummaryBadgeText(data) {
      if (data.count === 1) {
        return data.video_count === 1 ? '🎬 단독 릴스/동영상 (1개)' : '🖼️ 단독 사진 (1장)';
      }
      if (data.image_count > 0 && data.video_count > 0) {
        return `🎠 혼합 캐러셀 (총 ${data.count}개: 🖼️ 사진 ${data.image_count}장 + 🎬 영상 ${data.video_count}개)`;
      }
      if (data.video_count > 0) {
        return `🎬 다중 영상 캐러셀 (총 ${data.video_count}개)`;
      }
      return `🎠 다중 사진 캐러셀 (총 ${data.image_count}장)`;
    }

    async function handleExtract(e) {
      e.preventDefault();
      const ig_url = document.getElementById('igUrlInput').value.trim();
      if (!ig_url) return;
      await runExtraction(ig_url, currentScenarioMode, null);
    }

    async function runExtraction(ig_url, scenario_mode, sample_post_urls) {
      const btn = document.getElementById('submitBtn');
      btn.textContent = '⏳ 분석/추출 중...';
      btn.disabled = true;

      try {
        const res = await fetch('/api/extract', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ig_url, scenario_mode, sample_post_urls })
        });
        const data = await res.json();

        // ★ 프로필 분석 모드인 경우
        if (data.mode === 'profile') {
          if (data.success && data.profile_analysis) {
            renderProfileDashboard(data);
          } else {
            alert(data.error || '프로필 분석에 실패했습니다.');
          }
          return;
        }

        // ★ 개별 게시물/릴스/캐러셀 모드인 경우
        document.getElementById('profileDashboardCard').classList.add('hidden');
        document.getElementById('resultCard').classList.remove('hidden');

        if (data.success && data.items && data.items.length > 0) {
          extractedItems = data.items;

          document.getElementById('resultStatus').textContent = '✅ 미디어 추출 성공!';
          document.getElementById('countBadge').textContent = buildSummaryBadgeText(data);

          const timingBadge = document.getElementById('postTimingBadge');
          const ownerInfo = document.getElementById('postOwnerInfo');
          if (data.post_timing) {
            timingBadge.textContent = `🗓️ 업로드: ${data.post_timing.days_ago}일 전 (${data.post_timing.upload_date})`;
            timingBadge.classList.remove('hidden');
            ownerInfo.innerHTML = data.post_timing.owner_username
              ? `작성자: <strong>@${data.post_timing.owner_username}</strong> · ❤️ ${data.post_timing.like_count.toLocaleString()} · 💬 ${data.post_timing.comment_count.toLocaleString()}`
              : '';
          } else {
            timingBadge.classList.add('hidden');
            ownerInfo.innerHTML = '';
          }

          document.getElementById('errorBox').classList.add('hidden');
          document.getElementById('successBox').classList.remove('hidden');
          document.getElementById('shortcodeVal').textContent = data.shortcode;

          updateActiveSlide(0);

          document.getElementById('galleryGrid').innerHTML = extractedItems.map((item, i) => {
            const isVid = item.media_type === 'video';
            const badgeHtml = isVid
              ? `<span class="badge badge-video">🎬 #${i + 1} 동영상(릴스)</span>`
              : `<span class="badge badge-image">🖼️ #${i + 1} 사진</span>`;

            const mediaPreviewHtml = isVid
              ? `<video src="${item.proxy_url}" poster="${item.thumb_proxy_url || ''}" controls preload="metadata"></video>`
              : `<img src="${item.proxy_url}" alt="슬라이드 ${i + 1}" onclick="updateActiveSlide(${i})" />`;

            return `
              <div class="slide-card">
                <div style="display:flex;justify-content:space-between;align-items:center;gap:0.4rem;flex-wrap:wrap;">
                  ${badgeHtml}
                  <div style="display:flex;gap:0.35rem;">
                    <button type="button" class="btn-outline" onclick="updateActiveSlide(${i})">🔍 크게</button>
                    <button type="button" class="btn-outline" onclick="copyItemUrl(${i}, false)">
                      📋 ${isVid ? '영상 URL' : '사진 URL'}
                    </button>
                    ${isVid ? `<button type="button" class="btn-outline" onclick="copyItemUrl(${i}, true)">🖼️ 썸네일</button>` : ''}
                  </div>
                </div>
                <div class="slide-media-box">
                  ${mediaPreviewHtml}
                </div>
                <div style="max-height:54px;overflow-y:auto;font-size:0.74rem;">
                  <code>${item.url}</code>
                </div>
              </div>
            `;
          }).join('');
        } else {
          document.getElementById('resultStatus').textContent = '⚠️ 미디어 추출 실패';
          document.getElementById('countBadge').textContent = '0개';
          document.getElementById('successBox').classList.add('hidden');
          const errEl = document.getElementById('errorBox');
          errEl.textContent = data.error || '알 수 없는 오류가 발생했습니다.';
          errEl.classList.remove('hidden');
        }
      } catch (err) {
        alert('서버 통신 중 오류가 발생했습니다: ' + err);
      } finally {
        btn.textContent = '🔍 AI 분석 / 미디어 추출';
        btn.disabled = false;
      }
    }

    function copyItemUrl(idx, isThumb) {
      const item = extractedItems[idx];
      if (!item) return;
      const target = isThumb ? item.thumbnail_url : item.url;
      navigator.clipboard.writeText(target);
      alert(`#${idx + 1}번 슬라이드의 ${isThumb ? '썸네일 이미지' : (item.media_type === 'video' ? '동영상(.mp4)' : '사진')} URL이 복사되었습니다!`);
    }

    function copyAllUrls() {
      if (!extractedItems.length) return;
      const urls = extractedItems.map(x => x.url).join('\\n');
      navigator.clipboard.writeText(urls);
      alert(`총 ${extractedItems.length}개의 미디어 URL이 줄바꿈으로 일괄 복사되었습니다!`);
    }

    // 페이지 진입 시 기본값(@songgang.ho) 자동 분석 실행
    window.addEventListener('DOMContentLoaded', () => {
      const initUrl = document.getElementById('igUrlInput').value.trim();
      if (initUrl) {
        runExtraction(initUrl, 'active_integrated', null);
      }
    });
  </script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn

    print("=" * 72)
    print("[START] test.py 인스타그램 미디어 추출 & 마이크로 인플루언서 협찬 판독 서버 시작!")
    print(" -> 웹 브라우저 접속 주소: http://127.0.0.1:8000")
    print(" -> Swagger API 문서   : http://127.0.0.1:8000/docs")
    print("=" * 72)
    uvicorn.run(app, host="127.0.0.1", port=8000)
