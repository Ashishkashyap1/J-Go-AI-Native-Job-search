"""
official.py — the LEGITIMATE half: posting text and images.

Uses LinkedIn's sanctioned member API with the `w_member_social` scope. This
is the only part of the whole tool that does not violate the User Agreement,
provided you registered your own app at linkedin.com/developers and the user
authorized it. Token is stored in the keyring.

Image posting is a 3-step dance:
  1. registerUpload  -> get an upload URL + asset urn
  2. PUT the image bytes to that URL
  3. create the post (ugcPost) referencing the asset urn
"""
from __future__ import annotations

from pathlib import Path

import httpx

from . import config

API = "https://api.linkedin.com"
REST = "https://api.linkedin.com/rest"
TOKEN_KEY = "oauth_access_token"
MEMBER_URN_KEY = "member_urn"        # urn:li:person:XXXX


def _auth_headers() -> dict:
    tok = config.get_secret(TOKEN_KEY)
    if not tok:
        raise RuntimeError("No OAuth token. Run `lnkd auth oauth` first.")
    return {
        "Authorization": f"Bearer {tok}",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": "202401",
    }


def _member_urn() -> str:
    urn = config.get_secret(MEMBER_URN_KEY)
    if urn:
        return urn
    # resolve via /userinfo (OpenID) and cache it
    r = httpx.get(f"{API}/v2/userinfo", headers=_auth_headers(), timeout=20)
    r.raise_for_status()
    urn = f"urn:li:person:{r.json()['sub']}"
    config.set_secret(MEMBER_URN_KEY, urn)
    return urn


def post_text(text: str, dry_run: bool = False) -> str:
    if dry_run:
        return "DRY:post_text"
    body = {
        "author": _member_urn(),
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }
    r = httpx.post(f"{API}/v2/ugcPosts", json=body,
                   headers={**_auth_headers(), "Content-Type": "application/json"},
                   timeout=30)
    r.raise_for_status()
    return r.headers.get("x-restli-id", "posted")


def post_image(text: str, image: Path, dry_run: bool = False) -> str:
    if dry_run:
        return "DRY:post_image"
    urn = _member_urn()

    # 1. register upload
    reg = httpx.post(
        f"{API}/v2/assets?action=registerUpload",
        json={
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": urn,
                "serviceRelationships": [
                    {"relationshipType": "OWNER",
                     "identifier": "urn:li:userGeneratedContent"}
                ],
            }
        },
        headers={**_auth_headers(), "Content-Type": "application/json"},
        timeout=30,
    )
    reg.raise_for_status()
    val = reg.json()["value"]
    asset = val["asset"]
    upload_url = (val["uploadMechanism"]
                  ["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]
                  ["uploadUrl"])

    # 2. PUT the bytes
    put = httpx.put(upload_url, content=image.read_bytes(),
                    headers={"Authorization": _auth_headers()["Authorization"]},
                    timeout=60)
    put.raise_for_status()

    # 3. create the post referencing the asset
    body = {
        "author": urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "IMAGE",
                "media": [{"status": "READY", "media": asset}],
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    r = httpx.post(f"{API}/v2/ugcPosts", json=body,
                   headers={**_auth_headers(), "Content-Type": "application/json"},
                   timeout=30)
    r.raise_for_status()
    return r.headers.get("x-restli-id", "posted")
