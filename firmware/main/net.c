#include <string.h>
#include <stdio.h>

#include "net.h"
#include "ota.h"
#include "power.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/event_groups.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_log.h"
#include "esp_http_client.h"

static const char *TAG = "net";

#define WIFI_CONNECTED_BIT  BIT0
#define POST_QUEUE_LEN      12
#define MAX_RETRY           5

typedef struct {
    char action[8];
    char motion[16];
    int  count;        /* action=="status" 일 때 쌓인 개수 */
} post_evt_t;

static EventGroupHandle_t s_events;
static QueueHandle_t      s_queue;
static settings_t         s_cfg;
static char               s_ip[16] = "";
static char               s_last[64] = "(아직 없음)";
static int                s_retry = 0;
static bool               s_started = false;

/* ------------------------------------------------------------------ 이벤트 */

static void on_wifi(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();

    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        s_ip[0] = '\0';
        xEventGroupClearBits(s_events, WIFI_CONNECTED_BIT);
        /*
         * 무한 재시도하면 비밀번호가 틀렸을 때 로그가 끝없이 쌓인다.
         * 일정 횟수 뒤에는 멈추고, 설정이 바뀔 때 다시 시도한다.
         */
        if (s_retry < MAX_RETRY) {
            s_retry++;
            ESP_LOGW(TAG, "재연결 시도 %d/%d", s_retry, MAX_RETRY);
            esp_wifi_connect();
        } else {
            ESP_LOGE(TAG, "WiFi 연결 실패 — SSID/비밀번호를 확인하세요");
        }

    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *e = (ip_event_got_ip_t *)data;
        snprintf(s_ip, sizeof(s_ip), IPSTR, IP2STR(&e->ip_info.ip));
        s_retry = 0;
        ESP_LOGI(TAG, "연결됨: %s", s_ip);
        xEventGroupSetBits(s_events, WIFI_CONNECTED_BIT);
    }
}

/* -------------------------------------------------------------- 전송 태스크 */

static void do_post(const post_evt_t *e)
{
    if (!settings_has_server(&s_cfg)) {
        snprintf(s_last, sizeof(s_last), "서버 설정 없음");
        return;
    }

    char url[160];
    snprintf(url, sizeof(url), "%s/api/stick", s_cfg.server);

    char body[320];
    if (!strcmp(e->action, "status")) {
        /*
         * 봉이 스스로 알리는 상태. USB 를 꽂지 않아도 설정 페이지에서
         * 봉이 살아 있는지, 어느 IP 인지, 어떤 펌웨어인지 볼 수 있게 한다.
         */
        snprintf(body, sizeof(body),
                 "{\"room\":\"%s\",\"token\":\"%s\",\"action\":\"status\","
                 "\"ip\":\"%s\",\"fw\":\"%s\",\"uptime\":%lu,\"count\":%d,\"led\":\"%s\"}",
                 s_cfg.room, s_cfg.token, s_ip, ota_version(),
                 (unsigned long)(esp_timer_get_time() / 1000000), e->count,
                 power_status());
    } else if (e->motion[0]) {
        snprintf(body, sizeof(body),
                 "{\"room\":\"%s\",\"token\":\"%s\",\"action\":\"%s\",\"motion\":\"%s\"}",
                 s_cfg.room, s_cfg.token, e->action, e->motion);
    } else {
        snprintf(body, sizeof(body),
                 "{\"room\":\"%s\",\"token\":\"%s\",\"action\":\"%s\"}",
                 s_cfg.room, s_cfg.token, e->action);
    }

    esp_http_client_config_t cfg = {
        .url = url,
        .method = HTTP_METHOD_POST,
        .timeout_ms = 3000,
    };
    esp_http_client_handle_t cli = esp_http_client_init(&cfg);
    if (!cli) {
        snprintf(s_last, sizeof(s_last), "클라이언트 생성 실패");
        return;
    }

    esp_http_client_set_header(cli, "Content-Type", "application/json");
    esp_http_client_set_post_field(cli, body, strlen(body));

    esp_err_t err = esp_http_client_perform(cli);
    if (err == ESP_OK) {
        int code = esp_http_client_get_status_code(cli);
        snprintf(s_last, sizeof(s_last), "%s -> HTTP %d", e->action, code);
        if (code >= 400) {
            ESP_LOGW(TAG, "서버가 거부: HTTP %d (%s)", code, body);
        }
    } else {
        snprintf(s_last, sizeof(s_last), "%s -> %s", e->action, esp_err_to_name(err));
        ESP_LOGW(TAG, "전송 실패: %s", esp_err_to_name(err));
    }
    esp_http_client_cleanup(cli);
}

static void net_task(void *arg)
{
    post_evt_t e;
    for (;;) {
        if (xQueueReceive(s_queue, &e, portMAX_DELAY) != pdTRUE) continue;

        if (!net_is_connected()) {
            /* 연결이 없으면 조용히 버린다. 쌓아뒀다 몰아 보내면 도배가 된다. */
            snprintf(s_last, sizeof(s_last), "WiFi 미연결 — %s 버림", e.action);
            continue;
        }
        do_post(&e);
    }
}

/* ---------------------------------------------------------------- 외부 API */

esp_err_t net_init(void)
{
    s_events = xEventGroupCreate();
    s_queue  = xQueueCreate(POST_QUEUE_LEN, sizeof(post_evt_t));
    if (!s_events || !s_queue) return ESP_ERR_NO_MEM;

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t ic = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&ic));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &on_wifi, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &on_wifi, NULL, NULL));

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));

    /* 전송 태스크는 우선순위를 낮게 — IMU/LED 를 방해하면 안 된다 */
    xTaskCreate(net_task, "net", 4096, NULL, 3, NULL);
    return ESP_OK;
}

esp_err_t net_start(const settings_t *s)
{
    if (!s) return ESP_ERR_INVALID_ARG;
    s_cfg = *s;

    if (!s_started) {
        ESP_ERROR_CHECK(esp_wifi_start());
        s_started = true;
    }
    if (!settings_has_wifi(s)) {
        ESP_LOGW(TAG, "WiFi 설정이 없습니다. 시리얼로 WIFI 명령을 보내세요.");
        return ESP_OK;
    }
    return net_reconnect(s);
}

esp_err_t net_reconnect(const settings_t *s)
{
    if (!s) return ESP_ERR_INVALID_ARG;
    s_cfg = *s;
    s_retry = 0;

    wifi_config_t wc = { 0 };
    strlcpy((char *)wc.sta.ssid, s->ssid, sizeof(wc.sta.ssid));
    strlcpy((char *)wc.sta.password, s->pass, sizeof(wc.sta.password));

    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wc));
    esp_wifi_disconnect();
    ESP_LOGI(TAG, "접속 시도: %s", s->ssid);
    return esp_wifi_connect();
}

bool net_is_connected(void)
{
    if (!s_events) return false;
    return (xEventGroupGetBits(s_events) & WIFI_CONNECTED_BIT) != 0;
}

const char *net_ip(void)
{
    return s_ip;
}

esp_err_t net_scan(net_scan_cb_t cb)
{
    if (!cb) return ESP_ERR_INVALID_ARG;
    if (!s_started) {
        ESP_ERROR_CHECK(esp_wifi_start());
        s_started = true;
    }

    wifi_scan_config_t sc = { .show_hidden = false };
    esp_err_t err = esp_wifi_scan_start(&sc, true);   /* 블로킹 */
    if (err != ESP_OK) return err;

    uint16_t n = 0;
    esp_wifi_scan_get_ap_num(&n);
    if (n == 0) return ESP_OK;
    if (n > 30) n = 30;

    wifi_ap_record_t *recs = calloc(n, sizeof(wifi_ap_record_t));
    if (!recs) return ESP_ERR_NO_MEM;

    err = esp_wifi_scan_get_ap_records(&n, recs);
    if (err == ESP_OK) {
        for (int i = 0; i < n; i++) {
            cb((const char *)recs[i].ssid, recs[i].rssi,
               recs[i].authmode == WIFI_AUTH_OPEN);
        }
    }
    free(recs);
    return err;
}

esp_err_t net_post_event(const char *action, const char *motion)
{
    if (!action || !s_queue) return ESP_ERR_INVALID_ARG;

    post_evt_t e = { 0 };
    strlcpy(e.action, action, sizeof(e.action));
    if (motion) strlcpy(e.motion, motion, sizeof(e.motion));

    /*
     * 큐가 차 있으면 가장 오래된 것을 버리고 새 것을 넣는다.
     * 흔들기 이벤트는 늦게 도착하느니 사라지는 편이 낫다.
     */
    if (xQueueSend(s_queue, &e, 0) != pdTRUE) {
        post_evt_t drop;
        xQueueReceive(s_queue, &drop, 0);
        xQueueSend(s_queue, &e, 0);
        ESP_LOGW(TAG, "전송 큐가 가득 참 — 오래된 이벤트를 버립니다");
    }
    return ESP_OK;
}

esp_err_t net_post_status(int count)
{
    if (!s_queue) return ESP_ERR_INVALID_STATE;

    post_evt_t e = { 0 };
    strlcpy(e.action, "status", sizeof(e.action));
    e.count = count;

    /* 상태는 밀려도 그만이다. 큐가 차 있으면 그냥 건너뛴다. */
    xQueueSend(s_queue, &e, 0);
    return ESP_OK;
}

const char *net_last_result(void)
{
    return s_last;
}
