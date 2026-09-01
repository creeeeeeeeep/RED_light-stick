#pragma once

#include <stdbool.h>
#include "esp_err.h"
#include "settings.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * WiFi 연결과 서버 전송.
 *
 * 전송은 반드시 비동기다. HTTP POST 한 번에 수십~수백 ms 가 걸리는데,
 * 200Hz 로 도는 IMU 태스크나 60fps LED 태스크가 그동안 멈추면 안 된다.
 * net_post_*() 는 큐에 넣고 즉시 돌아오며, 별도 태스크가 실제로 보낸다.
 *
 * 큐가 차면 가장 오래된 것부터 버린다. 응원봉 이벤트는 늦게 도착하느니
 * 사라지는 편이 낫다.
 */

/* WiFi 스택 초기화. app_main 에서 한 번. */
esp_err_t net_init(void);

/* 저장된 설정으로 접속 시도. 비동기이며 결과는 net_is_connected() 로 본다. */
esp_err_t net_start(const settings_t *s);

/* 설정이 바뀌었을 때 다시 붙는다. */
esp_err_t net_reconnect(const settings_t *s);

bool net_is_connected(void);

/* 연결된 경우 IP 문자열, 아니면 빈 문자열 */
const char *net_ip(void);

/* 주변 WiFi 스캔. 결과를 콜백으로 하나씩 넘긴다. 블로킹이다. */
typedef void (*net_scan_cb_t)(const char *ssid, int rssi, bool open);
esp_err_t net_scan(net_scan_cb_t cb);

/*
 * 서버로 이벤트를 보낸다 (큐에 넣고 즉시 반환).
 *   action : "add" | "send" | "clear"
 *   motion : action=="add" 일 때만 쓰인다 ("SWAY_LR" 등). 아니면 NULL.
 */
esp_err_t net_post_event(const char *action, const char *motion);

/*
 * 봉의 상태를 서버로 알린다 (IP, 펌웨어, 켜진 시간, 쌓인 개수).
 *
 * USB 를 꽂지 않아도 설정 페이지에서 봉이 살아 있는지 볼 수 있게 하려는
 * 것이다. 팬은 봉을 보조배터리에만 꽂아둘 테니, 시리얼로만 볼 수 있으면
 * 사실상 볼 수 없는 것과 같다.
 */
esp_err_t net_post_status(int count);

/* 마지막 전송 결과를 사람이 읽을 문자열로 (STATUS 명령용) */
const char *net_last_result(void);

#ifdef __cplusplus
}
#endif
