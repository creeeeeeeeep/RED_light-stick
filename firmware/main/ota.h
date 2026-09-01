#pragma once

#include <stdbool.h>
#include "esp_err.h"
#include "settings.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * WiFi 펌웨어 갱신 (OTA).
 *
 * 봉이 서버에 물어보는 방식이다. 봉은 아무 포트도 열지 않는다.
 *
 *   1. GET  {server}/api/firmware?room=..&ver=..   →  {"version":"..","url":".."}
 *   2. 버전이 다르면 url 에서 받아 놀고 있는 슬롯에 굽는다
 *   3. 다음 부팅을 그 슬롯으로 지정하고 재부팅
 *   4. 새 펌웨어가 정상 동작하면 스스로 "확정" 한다. 확정 전에 죽으면
 *      부트로더가 이전 슬롯으로 되돌린다 (CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE)
 *
 * 밀어넣는 방식(봉이 HTTP 서버를 여는 것)을 쓰지 않는 이유는, 그러면 팬의
 * 집 네트워크마다 펌웨어를 받아 실행하는 포트가 하나씩 열리기 때문이다.
 * 물어보는 쪽은 스트리머 서버만 믿으면 되고 열린 포트가 없다.
 */

/* app_main 에서 한 번. 백그라운드 태스크를 띄운다. */
void ota_start(const settings_t *s);

/* 설정이 바뀌면 알려준다 (서버 주소 변경 등) */
void ota_settings_changed(const settings_t *s);

/* 다음 확인을 기다리지 않고 지금 확인한다 (시리얼 UPDATE 명령용) */
void ota_check_now(void);

/* 지금 돌고 있는 펌웨어 버전 */
const char *ota_version(void);

/* 마지막 갱신 시도 결과를 사람이 읽을 문자열로 (STATUS 명령용) */
const char *ota_last_result(void);

#ifdef __cplusplus
}
#endif
