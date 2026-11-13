"""
get_kakao_token.py - 카카오 OAuth 토큰 발급 및 .env 자동 저장 스크립트

사용법:
  python get_kakao_token.py <인가코드> [REDIRECT_URI]
예시:
  python get_kakao_token.py abc123code https://localhost:5000
"""

import sys
import os
import re
import urllib.request
import urllib.parse
import urllib.error
import json

ENV_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def load_env(env_path):
    config = {}
    if not os.path.exists(env_path):
        return config
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                config[key.strip()] = val.strip()
    return config


def update_env(env_path, key, value):
    lines = []
    found = False
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        # 기존 파일 끝에 줄바꿈이 없으면 추가
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] = new_lines[-1] + "\n"
        new_lines.append(f"{key}={value}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def issue_token(auth_code, redirect_uri, client_id, client_secret):
    url = "https://kauth.kakao.com/oauth/token"
    payload = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code": auth_code,
    }
    if client_secret:
        payload["client_secret"] = client_secret

    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            "User-Agent": "KakaoOAuthClient/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(err_body)
            error_code = err_json.get("error_code")
            desc = err_json.get("error_description")
            raise RuntimeError(f"HTTP {e.code} [{error_code}]: {desc}")
        except json.JSONDecodeError:
            raise RuntimeError(f"HTTP {e.code}: {err_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"네트워크 오류: {e.reason}")


def main():
    if len(sys.argv) < 2:
        print("사용법: python get_kakao_token.py <인가코드> [REDIRECT_URI]")
        sys.exit(1)

    auth_code = sys.argv[1].strip()
    redirect_uri = sys.argv[2].strip() if len(sys.argv) > 2 else "https://localhost:5000"

    env_config = load_env(ENV_FILE_PATH)
    client_id = env_config.get("KAKAO_REST_API_KEY")
    client_secret = env_config.get("KAKAO_CLIENT_SECRET")

    if not client_id:
        print(f"❌ 오류: {ENV_FILE_PATH} 파일에서 KAKAO_REST_API_KEY를 찾을 수 없습니다.")
        sys.exit(1)

    print(f"🔑 REST API 키 : {client_id}")
    print(f"🔒 클라이언트 시크릿 : {'*' * len(client_secret) if client_secret else '없음'}")
    print(f"🌐 Redirect URI : {redirect_uri}")
    print(f"🎟️ 인가 코드 : {auth_code[:10]}... (길이: {len(auth_code)})")
    print("\n카카오 서버에 리프레시 토큰 발급 요청 중...")

    try:
        res = issue_token(auth_code, redirect_uri, client_id, client_secret)
    except Exception as e:
        print(f"\n❌ 토큰 발급 실패: {e}")
        sys.exit(1)

    refresh_token = res.get("refresh_token")
    access_token = res.get("access_token")

    if not refresh_token:
        print("\n❌ 응답에 refresh_token이 포함되어 있지 않습니다:")
        print(json.dumps(res, indent=2, ensure_ascii=False))
        sys.exit(1)

    # .env 파일에 KAKAO_REFRESH_TOKEN 추가/업데이트
    update_env(ENV_FILE_PATH, "KAKAO_REFRESH_TOKEN", refresh_token)
    print(f"\n✅ 리프레시 토큰 발급 성공!")
    print(f"💾 .env 파일에 KAKAO_REFRESH_TOKEN이 자동으로 추가/업데이트되었습니다.")
    print(f"토큰 미리보기: {refresh_token[:15]}...{refresh_token[-10:]}")


if __name__ == "__main__":
    main()
