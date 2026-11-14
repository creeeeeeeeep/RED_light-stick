# -*- coding: utf-8 -*-
u"""
카페에 올릴 배포 묶음을 짓는다.

받는 사람이 폴더 이름만 보고도 순서를 알 수 있게 번호를 붙인다.
버전은 firmware/version.txt 에서 가져오므로, 버전을 올리고 다시 돌리면
파일 이름과 안내문이 같이 따라온다.

    py 배포묶음_만들기.py
"""
import io, os, re, sys, zipfile, shutil, glob

HERE = os.path.dirname(os.path.abspath(__file__))
VER = io.open(os.path.join(HERE, "firmware", "version.txt"), encoding="utf-8").read().strip()
NAME = u"RED응원봉_v%s" % VER
OUT = os.path.join(HERE, NAME + u".zip")

FIRMWARE_BIN = os.path.join(HERE, "server", "launchpad", u"cheerstick-%s-merged.bin" % VER)
LAUNCHPAD_URL = (u"https://espressif.github.io/esp-launchpad/?flashConfigURL="
                 u"https://creeeeeeeeep.github.io/RED_light-stick/server/launchpad/config.toml")

READ_ME = u"""RED 응원봉  v%(ver)s
======================================================================

흔들면 치지직 채팅에 이모티콘이 쌓이고, 버튼을 누르면 전송됩니다.
RED레드 채널 팬들을 위해 만든 것이라 무료이고, 파는 물건이 아닙니다.


순서
----------------------------------------------------------------------

  1. 3D 출력을 먼저 맡깁니다      → 1_3D출력 폴더
     가장 오래 걸립니다. 맡겨 놓고 나머지를 하세요.

  2. 보드에 펌웨어를 굽습니다      → 2_펌웨어 폴더
     ※ 반드시 조립 '전에' 하세요. 조립하면 보드의 USB 단자를 쓸 수 없습니다.

  3. 조립합니다                   → 조립설명서.pdf
     인쇄해서 옆에 두고 보시면 편합니다. 그림 10단계입니다.

  4. 컴퓨터 쪽을 준비합니다        → 3_중계프로그램, 4_크롬확장
     자세한 것은 설치가이드.html 을 여세요. 브라우저로 열립니다.

  5. 응원봉에 WiFi 를 넣습니다     → 설치가이드.html 의 5번


준비물 (출력물 말고)
----------------------------------------------------------------------

  Waveshare ESP32-S3-Matrix 보드        1개
  USB-C 끼움형 브레이크아웃             1개   (V · D- · D+ · G, 5.1k 내장)
  택트 스위치 6x6x5                     1개
  가는 전선                             4가닥
  납땜 인두, 본드, USB-C 케이블

  ※ 케이블은 '충전 전용'이 아니어야 합니다. 데이터가 통하는 것으로 쓰세요.
    휴대폰에 꽂았을 때 사진이 보이면 맞는 케이블입니다.


알아두실 것
----------------------------------------------------------------------

  * 응원봉을 쓰는 동안 컴퓨터가 켜져 있어야 합니다.
    중계 프로그램이 각자 컴퓨터에서 돌기 때문입니다. 바깥 서버로
    나가지 않으므로 누구의 서버도 필요하지 않습니다.

  * 흔드는 것은 '입력'만 합니다. 채팅으로 나가는 것은 응원봉의 버튼을
    눌렀을 때뿐입니다. 자동으로 보내는 기능은 없습니다.

  * 봉을 남에게 넘기실 때는 WiFi 설정을 지우고 주세요.
    비밀번호가 봉 안에 남아 있습니다. 2_펌웨어 의 '굽는법.txt' 참고.


소스
----------------------------------------------------------------------

  https://github.com/creeeeeeeeep/RED_light-stick

  전부 공개돼 있습니다. 무엇을 하는 프로그램인지 직접 확인하실 수 있습니다.
""" % {"ver": VER}

BURN = u"""펌웨어 굽기
======================================================================

응원봉을 '조립하기 전에' 하세요.
조립하고 나면 보드의 USB 단자가 안으로 들어가 쓸 수 없습니다.


방법 1 — 인터넷이 되면 (쉬움)
----------------------------------------------------------------------

크롬이나 엣지에서 아래 주소를 엽니다.

%(url)s

  1. USB 케이블로 보드를 컴퓨터에 연결
  2. [Connect] 를 누르고 'USB JTAG/serial debug unit' 선택
  3. [Flash]

1~2분이면 끝납니다. 고를 파일도, 입력할 숫자도 없습니다.


방법 2 — 이 폴더의 파일로
----------------------------------------------------------------------

https://espressif.github.io/esp-launchpad/ 를 열고 위쪽 [DIY] 탭.

  1. [Connect] 로 보드 연결
  2. '플래시 주소' 줄이 여러 개면 한 줄만 남기고 나머지는 [x] 로 지웁니다
  3. 주소를 0x0 으로 고칩니다
     (처음에 0x1000 이라고 적혀 있는데 다른 기종용 값입니다)
  4. 파일은 이 폴더의  cheerstick-%(ver)s-merged.bin
  5. [프로그램]

  ※ [플래시 지우기] 는 누르지 않아도 됩니다.


다 됐는지
----------------------------------------------------------------------

보드에 불이 들어옵니다.

  파란 불이 천천히 숨쉰다   → 정상입니다. WiFi 설정이 아직 없다는 뜻이고,
                             조립을 마친 뒤 설치가이드 5번에서 넣습니다.
  주황 불이 천천히 숨쉰다   → WiFi 설정은 있는데 아직 못 붙은 상태입니다.
  아무 불도 안 들어온다     → 케이블이 충전 전용일 수 있습니다. 바꿔보세요.


목록이 비어 있어서 연결이 안 될 때
----------------------------------------------------------------------

거의 케이블 문제입니다. 충전만 되는 케이블로는 안 됩니다.
그래도 안 되면 크롬이나 엣지인지 확인하세요 (사파리·파이어폭스는 안 됩니다).


봉을 남에게 넘기실 때
----------------------------------------------------------------------

WiFi 비밀번호가 봉 안에 남아 있습니다. 위 방법대로 다시 구우면 지워집니다
(합친 파일이 설정 영역까지 덮어쓰기 때문입니다).
""" % {"url": LAUNCHPAD_URL, "ver": VER}

PRINT_MEMO = u"""3D 출력
======================================================================

출력목록.png 를 보시면 어떤 파일이 어떤 부품인지 한 눈에 보입니다.
모두 9개이고, 전부 1개씩입니다.


출력 대행에 맡길 때 (복사해서 붙여넣기)
----------------------------------------------------------------------

  서포트 없이, 파일 방향 그대로 출력해 주세요.
  손잡이(05)는 버튼이 함께 출력되는 구조라 두 덩어리를 합치면 안 됩니다.
  손잡이 · 트레이 · 뚜껑은 브림 넣어주세요.


소재와 색
----------------------------------------------------------------------

  01_dome_CLEAR      PETG 투명    돔. 첨탑까지 한 몸입니다
  02_crown_RED       ABS 레드     왕관
  03_boardseat_RED   ABS 레드     보드 받침
  05_handle_RED      ABS 레드     손잡이  ※ 버튼이 같이 출력됩니다
  07a_tray_RED       ABS 레드     트레이
  07b_lid_RED        ABS 레드     뚜껑
  07c_ring_RED       ABS 레드     링
  09_cross_YELLOW    PLA 노랑     십자. 눕혀서 출력
  16_key_RED         아무거나     링을 돌리는 공구


본드
----------------------------------------------------------------------

  왕관 - 손잡이 (ABS 끼리)       아세톤 또는 ABS 접착제
  돔 - 왕관, 십자 - 돔 (PETG)    순간접착제 또는 에폭시
                                 ※ PETG 에는 아세톤이 안 먹습니다


시험 조각 (선택)
----------------------------------------------------------------------

시험조각 폴더에 세 개가 있습니다. 끼워지는 정도만 확인하는 작은 조각이라
처음 한 번만 뽑아보시면 됩니다. 본체를 통째로 뽑고 나서 안 맞으면
아깝기 때문입니다.
"""


def add(z, src, dst):
    if not os.path.exists(src):
        print(u"  빠짐(없음): %s" % src)
        return False
    z.write(src, dst)
    return True


def main():
    if not os.path.exists(FIRMWARE_BIN):
        print(u"펌웨어가 없습니다: %s" % FIRMWARE_BIN)
        print(u"  crown.bat build 와 crown.bat launchpad 를 먼저 돌리세요.")
        return 1

    n = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        R = lambda *p: u"/".join((NAME,) + p)

        z.writestr(R(u"0_먼저읽어주세요.txt"), READ_ME.encode("utf-8-sig"))
        # 가이드는 깃허브에서 받은 폴더 구조를 설명한다. 이 묶음은 폴더 이름이
        # 다르므로 그 부분만 바꿔 넣는다 — 없는 폴더를 열라고 하면 거기서 막힌다.
        guide = io.open(os.path.join(HERE, "docs", u"설치가이드.html"), encoding="utf-8").read()
        TREE = chr(10).join([
            NAME + u"/",
            u"├── 0_먼저읽어주세요.txt",
            u"├── 1_3D출력/          ← 출력소에 맡길 파일",
            u"├── 2_펌웨어/          ← 조립 전에 굽습니다",
            u"├── <em>3_중계프로그램/</em>    ← 3번에서 씁니다",
            u"└── <em>4_크롬확장/</em>        ← 2번에서 씁니다",
        ])
        guide = re.sub(r'<div class="tree">[\s\S]*?</div>',
                       u'<div class="tree">' + TREE + u'</div>', guide, count=1)

        for a, b in (
            (u"<b>extension 폴더를 선택</b>",
             u"<b>4_크롬확장 폴더를 선택</b>"),
            (u"<span class=\"ui\">extension</span> 을 한 번",
             u"<span class=\"ui\">4_크롬확장</span> 을 한 번"),
            (u"<b>server</b> 안에 있는",
             u"<b>3_중계프로그램</b> 안에 있는"),
            (u"<div class=\"addr\">server / 응원봉_서버_켜기.bat</div>",
             u"<div class=\"addr\">3_중계프로그램 / 응원봉_서버_켜기.bat</div>"),
            (u"<b>server / launchpad / *-merged.bin</b>",
             u"<b>2_펌웨어</b> 안의 <b>*-merged.bin</b>"),
        ):
            guide = guide.replace(a, b)
        z.writestr(R(u"설치가이드.html"), guide.encode("utf-8"))
        n += 1
        n += add(z, os.path.join(HERE, "modeling", "RED_final", "manual",
                                 u"RED_응원봉_조립설명서.pdf"), R(u"조립설명서.pdf"))

        # 1 · 3D 출력
        z.writestr(R(u"1_3D출력", u"출력메모.txt"), PRINT_MEMO.encode("utf-8-sig"))
        n += add(z, os.path.join(HERE, "modeling", "RED_final", u"출력목록.png"),
                 R(u"1_3D출력", u"출력목록.png"))
        for p in sorted(glob.glob(os.path.join(HERE, "modeling", "RED_final", "print", "*.stl"))):
            base = os.path.basename(p)
            sub = u"시험조각" if "_test" in base else u""
            n += add(z, p, R(u"1_3D출력", sub, base) if sub else R(u"1_3D출력", base))

        # 2 · 펌웨어
        z.writestr(R(u"2_펌웨어", u"굽는법.txt"), BURN.encode("utf-8-sig"))
        n += add(z, FIRMWARE_BIN, R(u"2_펌웨어", os.path.basename(FIRMWARE_BIN)))

        # 3 · 중계 프로그램
        for f in ("server.py", "start_server.py", u"응원봉_서버_켜기.bat",
                  "monitor.html", "test.html", "config.example.json"):
            n += add(z, os.path.join(HERE, "server", f), R(u"3_중계프로그램", f))

        # 4 · 크롬 확장
        for f in ("manifest.json", "background.js", "content.js", "inject.js",
                  "popup.html", "popup.js", "setup.html", "setup.js"):
            n += add(z, os.path.join(HERE, "extension", f), R(u"4_크롬확장", f))
        for p in sorted(glob.glob(os.path.join(HERE, "extension", "icons", "*.png"))):
            n += add(z, p, R(u"4_크롬확장", "icons", os.path.basename(p)))

    print(u"만들었습니다: %s" % OUT)
    print(u"  파일 %d개 · %s bytes" % (n + 4, format(os.path.getsize(OUT), ",")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
