#include "devlog.h"

#if CONFIG_CROWN_DEV

#include <string.h>
#include <stdio.h>

#include "net.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_log.h"
#include "esp_http_client.h"

static const char *TAG = "devlog";

/*
 * 한 줄이 90바이트 남짓이고 20Hz 로 나온다 (초당 1.8KB).
 * 4KB 면 2초를 담으므로, WiFi 가 잠깐 버벅여도 버티고 남는다.
 */
#define BUF_SIZE        4096
#define FLUSH_MS        500
#define FLUSH_THRESHOLD (BUF_SIZE / 2)

static settings_t         s_cfg;
static SemaphoreHandle_t  s_lock;
static char               s_buf[BUF_SIZE];
static int                s_len;
static uint32_t           s_dropped;
static char               s_status[64] = "(아직 없음)";
static bool               s_running;

const char *devlog_status(void)
{
    return s_status;
}

/*
 * IMU 태스크(200Hz)에서 불린다. 절대 블로킹하지 않는다 —
 * 뮤텍스를 못 잡으면 그냥 그 줄을 버린다. 로그 한 줄 때문에 제스처
 * 판정이 밀리면 본말전도다.
 */
void devlog_line(const char *line)
{
    if (!s_running || !line) return;

    int n = strlen(line);
    if (xSemaphoreTake(s_lock, 0) != pdTRUE) {
        s_dropped++;
        return;
    }
    if (s_len + n + 1 <= BUF_SIZE) {
        memcpy(s_buf + s_len, line, n);
        s_len += n;
        s_buf[s_len++] = '\n';
    } else {
        s_dropped++;
    }
    xSemaphoreGive(s_lock);
}

static void post_chunk(const char *body, int len)
{
    char url[192];
    snprintf(url, sizeof(url), "%s/api/log", s_cfg.server);

    esp_http_client_config_t cfg = {
        .url = url,
        .method = HTTP_METHOD_POST,
        .timeout_ms = 4000,
    };
    esp_http_client_handle_t cli = esp_http_client_init(&cfg);
    if (!cli) return;

    esp_http_client_set_header(cli, "Content-Type", "text/plain");
    esp_http_client_set_header(cli, "X-Room", s_cfg.room);
    esp_http_client_set_header(cli, "X-Token", s_cfg.token);
    esp_http_client_set_post_field(cli, body, len);

    esp_err_t err = esp_http_client_perform(cli);
    if (err == ESP_OK) {
        snprintf(s_status, sizeof(s_status), "HTTP %d, %dB, 버림 %lu줄",
                 esp_http_client_get_status_code(cli), len, (unsigned long)s_dropped);
    } else {
        snprintf(s_status, sizeof(s_status), "%s", esp_err_to_name(err));
    }
    esp_http_client_cleanup(cli);
}

static void devlog_task(void *arg)
{
    /* 보내는 동안에도 새 줄이 쌓여야 하므로 따로 복사해 나간다 */
    static char out[BUF_SIZE];

    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(FLUSH_MS));

        if (!net_is_connected() || !settings_has_server(&s_cfg)) {
            /* 보낼 수 없으면 버퍼가 넘치지 않게 비운다 */
            if (xSemaphoreTake(s_lock, pdMS_TO_TICKS(10)) == pdTRUE) {
                if (s_len) s_dropped += 1;
                s_len = 0;
                xSemaphoreGive(s_lock);
            }
            continue;
        }

        int n = 0;
        if (xSemaphoreTake(s_lock, pdMS_TO_TICKS(10)) == pdTRUE) {
            n = s_len;
            if (n) memcpy(out, s_buf, n);
            s_len = 0;
            xSemaphoreGive(s_lock);
        }
        if (n > 0) post_chunk(out, n);
    }
}

void devlog_start(const settings_t *s)
{
    if (s) s_cfg = *s;
    if (s_running) return;

    s_lock = xSemaphoreCreateMutex();
    if (!s_lock) {
        ESP_LOGE(TAG, "뮤텍스 생성 실패 — 로그 전송을 끈다");
        return;
    }
    s_running = true;
    xTaskCreate(devlog_task, "devlog", 5120, NULL, 2, NULL);
    ESP_LOGI(TAG, "모션 로그를 %s/api/log 로 보낸다", s_cfg.server[0] ? s_cfg.server : "(서버 미설정)");
}

void devlog_settings_changed(const settings_t *s)
{
    if (s) s_cfg = *s;
}

#endif  /* CONFIG_CROWN_DEV */
