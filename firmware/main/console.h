#pragma once

#include "settings.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * 시리얼 명령 파서.
 *
 * 확장 설정 페이지가 Web Serial 로 봉을 설정한다. 팬은 USB 를 이미 꽂은
 * 상태(펌웨어를 웹으로 굽기 때문)라, 그 자리에서 WiFi 까지 넣으면 단계가
 * 늘어나지 않는다.
 *
 * ---------------------------------------------------------------------------
 * 명령 (PC -> 봉)
 * ---------------------------------------------------------------------------
 *   PING                      살아있는지 확인
 *   SCAN                      주변 WiFi 목록
 *   WIFI <ssid> <password>    WiFi 저장 후 접속. 비밀번호에 공백이 있으면
 *                             따옴표로 감싼다:  WIFI "my ap" "pa ss"
 *   ROOM <code>               방 코드 (확장과 같아야 한다)
 *   TOKEN <token>             서버 인증 값
 *   SERVER <url>              예: http://192.168.0.10:8787
 *   STATUS                    현재 상태
 *   CLEAR                     설정 전부 삭제
 *
 * ---------------------------------------------------------------------------
 * 응답 (봉 -> PC) — 줄 단위, 접두사로 구분한다
 * ---------------------------------------------------------------------------
 *   OK <명령> [메시지]
 *   ERR <메시지>
 *   AP <rssi> <open|lock> <ssid>     SCAN 결과, 한 줄에 하나
 *   ST <키>=<값>                     STATUS 결과, 한 줄에 하나
 *
 * 제스처 로그(TUNE,...)와 같은 스트림에 섞이므로, 파서는 접두사로 구분한다.
 */
void console_start(void);

/* 설정이 바뀌면 알려준다 (main 이 WiFi 재접속 등에 쓴다) */
typedef void (*console_changed_cb_t)(const settings_t *s);
void console_set_changed_cb(console_changed_cb_t cb);

#ifdef __cplusplus
}
#endif
