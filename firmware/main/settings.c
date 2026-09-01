#include <string.h>

#include "settings.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_log.h"

static const char *TAG = "settings";
static const char *NS  = "crown";

esp_err_t settings_init(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        /* 파티션이 꼬였거나 버전이 바뀌었으면 지우고 다시 만든다 */
        ESP_LOGW(TAG, "NVS 를 초기화합니다 (%s)", esp_err_to_name(err));
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    return err;
}

/* 없으면 빈 문자열로 둔다 */
static void get_str(nvs_handle_t h, const char *key, char *dst, size_t cap)
{
    size_t len = cap;
    if (nvs_get_str(h, key, dst, &len) != ESP_OK) {
        dst[0] = '\0';
    }
}

esp_err_t settings_load(settings_t *out)
{
    if (!out) return ESP_ERR_INVALID_ARG;
    memset(out, 0, sizeof(*out));

    nvs_handle_t h;
    esp_err_t err = nvs_open(NS, NVS_READONLY, &h);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        return ESP_OK;      /* 아직 아무것도 저장 안 됨 — 빈 설정이 정상 */
    }
    if (err != ESP_OK) return err;

    get_str(h, "ssid",   out->ssid,   sizeof(out->ssid));
    get_str(h, "pass",   out->pass,   sizeof(out->pass));
    get_str(h, "room",   out->room,   sizeof(out->room));
    get_str(h, "token",  out->token,  sizeof(out->token));
    get_str(h, "server", out->server, sizeof(out->server));

    nvs_close(h);
    return ESP_OK;
}

esp_err_t settings_save(const settings_t *s)
{
    if (!s) return ESP_ERR_INVALID_ARG;

    nvs_handle_t h;
    esp_err_t err = nvs_open(NS, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;

    err  = nvs_set_str(h, "ssid",   s->ssid);
    err |= nvs_set_str(h, "pass",   s->pass);
    err |= nvs_set_str(h, "room",   s->room);
    err |= nvs_set_str(h, "token",  s->token);
    err |= nvs_set_str(h, "server", s->server);

    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);

    if (err == ESP_OK) {
        /* 비밀번호는 로그에 남기지 않는다 */
        ESP_LOGI(TAG, "저장됨 ssid=%s room=%s server=%s",
                 s->ssid, s->room, s->server);
    }
    return err;
}

esp_err_t settings_clear(void)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(NS, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;

    err = nvs_erase_all(h);
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);

    ESP_LOGW(TAG, "설정을 모두 지웠습니다");
    return err;
}

bool settings_has_wifi(const settings_t *s)
{
    return s && s->ssid[0] != '\0';
}

bool settings_has_server(const settings_t *s)
{
    return s && s->server[0] != '\0' && s->room[0] != '\0';
}
