# -*- coding: utf-8 -*-
"""
서버를 켜기 전에 필요한 것을 확인하고 안내하는 실행기.

배치 파일에 한글 안내를 넣었더니 콘솔에서 깨졌다. 배치 안에서 chcp 로
코드페이지를 바꾸면 cmd 가 파일을 읽던 위치가 어긋나 그 뒤 줄들의 앞글자를
먹어버린다("echo." 가 "cho." 가 된다).

그래서 배치는 영문만 남기고 사람에게 하는 말은 전부 여기서 한다. 파이썬은
윈도우 콘솔에 유니코드를 직접 쓰므로 코드페이지와 무관하게 한글이 제대로 나온다.
"""

import os
import subprocess
import sys


def line(ch="─", n=58):
    print("  " + ch * n)


def main():
    here = os.path.dirname(os.path.abspath(__file__))

    print()
    print("  응원봉 서버를 준비합니다...")
    print()

    # ── 필요한 것 확인 ────────────────────────────────────────────────
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        print("  처음 실행이라 필요한 것을 받고 있습니다. 1분쯤 걸립니다...")
        print()
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "--disable-pip-version-check", "aiohttp"]
        )
        if r.returncode != 0:
            print()
            print("  [!] 설치에 실패했습니다.")
            print("      인터넷 연결을 확인하고 다시 실행해 주세요.")
            print()
            input("  엔터를 누르면 닫힙니다...")
            return 1

    # ── 안내 ──────────────────────────────────────────────────────────
    try:
        os.system("cls")
    except Exception:
        pass

    print()
    line("=")
    print()
    print("    응원봉 서버가 켜졌습니다.")
    print()
    print("    이 창을 닫으면 서버도 꺼집니다.")
    print("    응원봉을 쓰는 동안에는 열어 두세요.")
    print()
    line("=")
    print()

    # ── 서버 ──────────────────────────────────────────────────────────
    try:
        r = subprocess.run([sys.executable, os.path.join(here, "server.py")])
    except KeyboardInterrupt:
        r = None

    print()
    print("  서버가 꺼졌습니다.")
    print()
    input("  엔터를 누르면 닫힙니다...")
    return 0 if r is None else r.returncode


if __name__ == "__main__":
    sys.exit(main())
