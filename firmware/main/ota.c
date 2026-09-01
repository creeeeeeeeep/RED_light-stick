#include <string.h>
#include <stdio.h>

#include "ota.h"
#include "net.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_app_desc.h"
#include "esp_ota_ops.h"
#include "esp_http_client.h"
#include "esp_https_ota.h"
#include "esp_crt_bundle.h"
#include "cJSON.h"

static const char *TAG = "ota";

/*
 * 새 펌웨어가 이만큼 살아 있으면 정상으로 본다.
 *
 * WiFi 연결을 조건에 넣지 않는 이유가 있다. 봉은 WiFi 없이도 응원봉으로
 * 동작해야 하고, 팬이 아직 WiFi 를 설정하지 않았을 수도 있다. 그걸 조건에
 * 넣으면 멀쩡한 펌웨어가 무한히 되돌려진다. 여기서 막으려는 것은 부팅하자마자
 * 죽는 펌웨어이므로, 살아 있는 시간만 보면 된다.
 */
#define VALIDATE_AFTER_MS   60000

#define CHECK_PERIOD_MS     (CONFIG_CROWN_OTA_CHECK_SEC * 1000)
#define JSON_MAX            512

static settings_t   s_cfg;
static char         s_last[96] = "(아직 없음)";
static TaskHandle_t s_task;

const char *ota_version(void)
{
    return esp_app_get_description()->version;
}

const char *ota_last_result(void)
{
    return s_last;
}

/* ---------------------------------------------------------------- 롤백 확정 */

/*
 * OTA 로 구운 직후의 첫 부팅은 "확인 대기" 상태다. 여기서 확정하지 않고
 * 재부팅되면 부트로더가 이전 슬롯으로 되돌린다.
 */
static void validate_if_pending(void)
{
    const esp_partition_t *run = esp_ota_get_running_partition();
    esp_ota_img_states_t st;
    if (esp_ota_get_state_partition(run, &st) != ESP_OK) return;
    if (st != ESP_OTA_IMG_PENDING_VERIFY) return;

    ESP_LOGI(TAG, "새 펌웨어 확인 대기 — %d초 지켜본다", VALIDATE_AFTER_MS / 1000);
    vTaskDelay(pdMS_TO_TICKS(VALIDATE_AFTER_MS));

    if (esp_ota_mark_app_valid_cancel_rollback() == ESP_OK) {
        ESP_LOGI(TAG, "펌웨어 %s 확정", ota_version());
    } else {
        ESP_LOGE(TAG, "확정 실패 — 되돌린다");
        esp_ota_mark_app_invalid_rollback_and_reboot();
    }
}

/* ------------------------------------------------------------ 서버에 물어보기 */

/* 응답 본문을 buf 에 담는다. 성공하면 HTTP 상태 코드. */
static int fetch(const char *url, char *buf, int cap)
{
    esp_http_client_config_t cfg = {
        .url = url,
        .method = HTTP_METHOD_GET,
        .timeout_ms = 5000,
        .crt_bundle_attach = esp_crt_bundle_attach,
    };
    esp_http_client_handle_t cli = esp_http_client_init(&cfg);
    if (!cli) return -1;

    int code = -1;
    if (esp_http_client_open(cli, 0) == ESP_OK) {
        esp_http_client_fetch_headers(cli);
        int n = esp_http_client_read_response(cli, buf, cap - 1);
        buf[n > 0 ? n : 0] = '\0';
        code = esp_http_client_get_status_code(cli);
    }
    esp_http_client_cleanup(cli);
    return code;
}

/*
 * a 가 b 보다 크면 1, 같으면 0, 작으면 -1. 형식이 다르면 2 (비교 불가).
 */
static int ver_cmp(const char *a, const char *b)
{
    int an[3] = { 0, 0, 0 }, bn[3] = { 0, 0, 0 };
    if (sscanf(a, "%d.%d.%d", &an[0], &an[1], &an[2]) < 1) return 2;
    if (sscanf(b, "%d.%d.%d", &bn[0], &bn[1], &bn[2]) < 1) return 2;
    for (int i = 0; i < 3; i++) {
        if (an[i] != bn[i]) return an[i] > bn[i] ? 1 : -1;
    }
    return 0;
}

/*
 * 서버에 더 새 펌웨어가 있으면 url 을 out 에 담고 true.
 *
 * '다르면 받는다' 가 아니라 '더 새것이면 받는다' 여야 한다. 다르기만 하면
 * 받게 했더니, USB 로 새 펌웨어를 구운 직후 서버에 남아 있던 옛 버전으로
 * 5초 만에 되돌아갔다. 개발 중에는 USB 와 OTA 가 서로 싸운다.
 *
 * 되돌려야 할 때는 서버가 force 를 켠다. 그때만 옛 버전도 받는다.
 */
static bool find_update(char *out, int cap)
{
    char url[256];
    snprintf(url, sizeof(url), "%s/api/firmware?room=%s&ver=%s",
             s_cfg.server, s_cfg.room, ota_version());

    char body[JSON_MAX];
    int code = fetch(url, body, sizeof(body));
    if (code != 200) {
        snprintf(s_last, sizeof(s_last), "확인 실패 (HTTP %d)", code);
        return false;
    }

    cJSON *root = cJSON_Parse(body);
    if (!root) {
        snprintf(s_last, sizeof(s_last), "확인 실패 (JSON 아님)");
        return false;
    }

    bool found = false;
    const cJSON *ver = cJSON_GetObjectItemCaseSensitive(root, "version");
    const cJSON *loc = cJSON_GetObjectItemCaseSensitive(root, "url");

    const cJSON *force = cJSON_GetObjectItemCaseSensitive(root, "force");
    const bool forced = cJSON_IsTrue(force);

    if (cJSON_IsString(ver) && cJSON_IsString(loc) && ver->valuestring[0]) {
        const int cmp = ver_cmp(ver->valuestring, ota_version());

        if (cmp == 0) {
            snprintf(s_last, sizeof(s_last), "최신 (%s)", ota_version());
        } else if (cmp <= 0 && !forced) {
            /* 서버 쪽이 더 옛것이다. 지금 것을 지키고 놔둔다. */
            snprintf(s_last, sizeof(s_last), "서버가 더 옛것 (%s) — 유지",
                     ver->valuestring);
        } else {
            strlcpy(out, loc->valuestring, cap);
            snprintf(s_last, sizeof(s_last), "%s 받는 중", ver->valuestring);
            ESP_LOGI(TAG, "%s 펌웨어 %s (지금 %s)",
                     forced && cmp <= 0 ? "되돌리기" : "새", ver->valuestring, ota_version());
            found = true;
        }
    } else {
        snprintf(s_last, sizeof(s_last), "올라온 펌웨어 없음");
    }

    cJSON_Delete(root);
    return found;
}

static void download_and_reboot(const char *url)
{
    esp_http_client_config_t http = {
        .url = url,
        .timeout_ms = 15000,
        .keep_alive_enable = true,
        .crt_bundle_attach = esp_crt_bundle_attach,
    };
    esp_https_ota_config_t cfg = { .http_config = &http };

    ESP_LOGI(TAG, "받는 중: %s", url);
    esp_err_t err = esp_https_ota(&cfg);

    if (err != ESP_OK) {
        snprintf(s_last, sizeof(s_last), "굽기 실패: %s", esp_err_to_name(err));
        ESP_LOGE(TAG, "%s", s_last);
        return;
    }

    ESP_LOGI(TAG, "다 구웠다 — 재부팅");
    vTaskDelay(pdMS_TO_TICKS(500));   /* 로그가 나갈 틈 */
    esp_restart();
}

/* ------------------------------------------------------------------ 태스크 */

static void ota_task(void *arg)
{
    validate_if_pending();

    for (;;) {
        /*
         * 알림으로 깨거나 주기가 되면 깬다. ota_check_now() 가 알림을 보낸다.
         */
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(CHECK_PERIOD_MS));

        if (!net_is_connected() || !settings_has_server(&s_cfg)) continue;

        char url[256] = "";
        if (find_update(url, sizeof(url))) {
            download_and_reboot(url);
        }
    }
}

/* ---------------------------------------------------------------- 외부 API */

void ota_start(const settings_t *s)
{
    if (s) s_cfg = *s;
    if (s_task) return;

    /*
     * 스택이 넉넉해야 한다. TLS 핸드셰이크가 깊게 들어간다.
     */
    xTaskCreate(ota_task, "ota", 8192, NULL, 3, &s_task);
    ESP_LOGI(TAG, "펌웨어 %s, %d초마다 갱신 확인", ota_version(), CONFIG_CROWN_OTA_CHECK_SEC);
}

void ota_settings_changed(const settings_t *s)
{
    if (s) s_cfg = *s;
}

void ota_check_now(void)
{
    if (s_task) xTaskNotifyGive(s_task);
}
