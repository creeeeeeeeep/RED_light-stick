#pragma once

#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * 봉의 영구 설정. NVS 에 저장된다.
 *
 * 팬이 확장 설정 페이지에서 Web Serial 로 넣어주는 값들이다.
 * 봉은 이 값만 있으면 부팅 후 스스로 WiFi 에 붙어 서버로 이벤트를 보낸다.
 *
 * 주의: 배포본에서는 플래시 암호화(Development 모드)를 켜야 한다.
 *       안 켜면 USB 만 꽂아도 esptool read_flash 로 WiFi 비밀번호가 그대로
 *       덤프된다. 개발 중에는 편의를 위해 끄고 쓴다.
 */
typedef struct {
    char ssid[33];      /* WiFi SSID (최대 32자 + NUL) */
    char pass[65];      /* WiFi 비밀번호 (WPA2 최대 63자 + NUL) */
    char room[33];      /* 이 봉이 속한 방. 확장과 같은 값이어야 한다 */
    char token[65];     /* 서버 인증용 공유 비밀 */
    char server[128];   /* 예: http://192.168.0.10:8787 */
} settings_t;

/* NVS 초기화. app_main 초반에 한 번 부른다. */
esp_err_t settings_init(void);

/* 저장된 값을 읽는다. 없는 항목은 빈 문자열이 된다. */
esp_err_t settings_load(settings_t *out);

/* 통째로 저장한다. */
esp_err_t settings_save(const settings_t *s);

/* 전부 지운다 (공장 초기화). */
esp_err_t settings_clear(void);

/* WiFi 로 붙을 수 있을 만큼 값이 채워져 있는가 */
bool settings_has_wifi(const settings_t *s);

/* 서버로 보낼 수 있을 만큼 값이 채워져 있는가 */
bool settings_has_server(const settings_t *s);

#ifdef __cplusplus
}
#endif
