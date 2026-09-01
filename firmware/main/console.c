#include <string.h>
#include <stdio.h>
#include <ctype.h>
#include <stdlib.h>

#include "console.h"
#include "net.h"
#include "board_config.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/usb_serial_jtag.h"
#include "driver/gpio.h"
#include "ota.h"
#include "devlog.h"
#include "power.h"
#include "esp_log.h"

static const char *TAG = "console";

#define CMD_LINE_MAX 256

static settings_t s_cfg;
static console_changed_cb_t s_changed_cb;

void console_set_changed_cb(console_changed_cb_t cb)
{
    s_changed_cb = cb;
}

/* ------------------------------------------------------------------ 유틸 */

/*
 * 다음 토큰을 잘라낸다. 따옴표로 감싼 경우 공백을 포함할 수 있다.
 * WiFi SSID 나 비밀번호에 공백이 흔해서 필요하다.
 *   WIFI "my ap" "pa ss"
 */
static char *next_token(char **p)
{
    char *s = *p;
    while (*s == ' ' || *s == '\t') s++;
    if (!*s) { *p = s; return NULL; }

    char *start;
    if (*s == '"') {
        start = ++s;
        while (*s && *s != '"') s++;
    } else {
        start = s;
        while (*s && *s != ' ' && *s != '\t') s++;
    }
    if (*s) { *s = '\0'; s++; }
    *p = s;
    return start;
}

static void reply_ok(const char *cmd, const char *msg)
{
    if (msg && *msg) printf("OK %s %s\n", cmd, msg);
    else             printf("OK %s\n", cmd);
    fflush(stdout);
}

static void reply_err(const char *msg)
{
    printf("ERR %s\n", msg);
    fflush(stdout);
}

static void on_ap(const char *ssid, int rssi, bool open)
{
    if (!ssid || !*ssid) return;
    printf("AP %d %s %s\n", rssi, open ? "open" : "lock", ssid);
    fflush(stdout);
}

/* 비밀번호는 절대 그대로 내보내지 않는다 */
static void print_status(void)
{
    printf("ST ssid=%s\n",   s_cfg.ssid[0]   ? s_cfg.ssid   : "(없음)");
    printf("ST pass=%s\n",   s_cfg.pass[0]   ? "(설정됨)"    : "(없음)");
    printf("ST room=%s\n",   s_cfg.room[0]   ? s_cfg.room   : "(없음)");
    printf("ST token=%s\n",  s_cfg.token[0]  ? "(설정됨)"    : "(없음)");
    printf("ST server=%s\n", s_cfg.server[0] ? s_cfg.server : "(없음)");
    printf("ST wifi=%s\n",   net_is_connected() ? "connected" : "disconnected");
    printf("ST ip=%s\n",     net_ip()[0] ? net_ip() : "-");
    printf("ST lastpost=%s\n", net_last_result());
    printf("ST queuemax=%d\n", QUEUE_MAX);
    printf("ST fw=%s\n", ota_version());
    printf("ST ota=%s\n", ota_last_result());
    printf("ST devlog=%s\n", devlog_status());
    printf("ST ledbudget=%s\n", power_status());
    fflush(stdout);
}

static void notify_changed(void)
{
    if (settings_save(&s_cfg) != ESP_OK) {
        reply_err("저장 실패");
        return;
    }
    if (s_changed_cb) s_changed_cb(&s_cfg);
}

/* ------------------------------------------------------------- 명령 처리 */

static void handle_line(char *line)
{
    char *p = line;
    char *cmd = next_token(&p);
    if (!cmd || !*cmd) return;

    for (char *c = cmd; *c; c++) *c = toupper((unsigned char)*c);

    if (!strcmp(cmd, "PING")) {
        reply_ok("PING", "crown");

    } else if (!strcmp(cmd, "SCAN")) {
        /*
         * 스캔은 몇 초 걸린다. 이 태스크만 멈추므로 LED 나 제스처에는
         * 영향이 없다.
         */
        esp_err_t err = net_scan(on_ap);
        if (err == ESP_OK) reply_ok("SCAN", "");
        else               reply_err(esp_err_to_name(err));

    } else if (!strcmp(cmd, "WIFI")) {
        char *ssid = next_token(&p);
        char *pass = next_token(&p);
        if (!ssid || !*ssid) { reply_err("SSID 가 필요합니다"); return; }

        strlcpy(s_cfg.ssid, ssid, sizeof(s_cfg.ssid));
        strlcpy(s_cfg.pass, pass ? pass : "", sizeof(s_cfg.pass));
        notify_changed();
        reply_ok("WIFI", s_cfg.ssid);

    } else if (!strcmp(cmd, "ROOM")) {
        char *v = next_token(&p);
        if (!v || !*v) { reply_err("방 코드가 필요합니다"); return; }
        strlcpy(s_cfg.room, v, sizeof(s_cfg.room));
        notify_changed();
        reply_ok("ROOM", s_cfg.room);

    } else if (!strcmp(cmd, "TOKEN")) {
        char *v = next_token(&p);
        if (!v || !*v) { reply_err("토큰이 필요합니다"); return; }
        strlcpy(s_cfg.token, v, sizeof(s_cfg.token));
        notify_changed();
        reply_ok("TOKEN", "");

    } else if (!strcmp(cmd, "SERVER")) {
        char *v = next_token(&p);
        if (!v || !*v) { reply_err("주소가 필요합니다"); return; }
        if (strncmp(v, "http://", 7) && strncmp(v, "https://", 8)) {
            reply_err("http:// 또는 https:// 로 시작해야 합니다");
            return;
        }
        strlcpy(s_cfg.server, v, sizeof(s_cfg.server));
        notify_changed();
        reply_ok("SERVER", s_cfg.server);

    } else if (!strcmp(cmd, "BTN")) {
        /*
         * 납땜한 버튼이 실제로 그 패드에 붙었는지 확인하는 용도.
         * 누르지 않으면 1, 누른 채로 실행하면 0 이어야 한다.
         */
        printf("ST btn_soldered_gpio%d=%d\n", BUTTON_GPIO, gpio_get_level(BUTTON_GPIO));
        printf("ST btn_onboard_gpio%d=%d\n",  BUTTON_ONBOARD_GPIO, gpio_get_level(BUTTON_ONBOARD_GPIO));
        fflush(stdout);
        reply_ok("BTN", "누른 채로 다시 실행하면 0 이어야 합니다");

    } else if (!strcmp(cmd, "LED")) {
        /*
         * LED 900      예산을 900mA 로 (가장 가까운 단계로 맞춰진다)
         * LED auto     학습값을 지우고 자동 추정으로
         */
        char *v = next_token(&p);
        if (!v || !*v) { reply_err("LED <mA> 또는 LED auto"); return; }
        float ma = (!strcmp(v, "auto") || !strcmp(v, "AUTO")) ? 0.0f : (float)atof(v);
        float got = power_set_budget(ma);
        char msg[48];
        snprintf(msg, sizeof(msg), "%.0fmA", got);
        reply_ok("LED", msg);

    } else if (!strcmp(cmd, "UPDATE")) {
        ota_check_now();
        reply_ok("UPDATE", "갱신 확인 요청됨");

    } else if (!strcmp(cmd, "STATUS")) {
        print_status();
        reply_ok("STATUS", "");

    } else if (!strcmp(cmd, "CLEAR")) {
        settings_clear();
        memset(&s_cfg, 0, sizeof(s_cfg));
        reply_ok("CLEAR", "재부팅하세요");

    } else {
        reply_err("알 수 없는 명령");
    }
}

/* ------------------------------------------------------------------ 태스크 */

static void console_task(void *arg)
{
    char line[CMD_LINE_MAX];
    int len = 0;

    settings_load(&s_cfg);
    printf("OK READY crown\n");
    fflush(stdout);

    for (;;) {
        uint8_t ch;
        int n = usb_serial_jtag_read_bytes(&ch, 1, pdMS_TO_TICKS(200));
        if (n <= 0) continue;

        if (ch == '\r') continue;
        if (ch == '\n') {
            line[len] = '\0';
            if (len) handle_line(line);
            len = 0;
            continue;
        }
        /* 줄이 넘치면 통째로 버린다. 잘린 명령을 실행하면 위험하다. */
        if (len < CMD_LINE_MAX - 1) {
            line[len++] = (char)ch;
        } else {
            len = 0;
            reply_err("명령이 너무 깁니다");
        }
    }
}

void console_start(void)
{
    /*
     * 콘솔이 USB-Serial-JTAG 이라 출력은 printf 로 나가지만, 입력을 받으려면
     * 드라이버를 직접 설치해야 한다.
     */
    usb_serial_jtag_driver_config_t cfg = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
    esp_err_t err = usb_serial_jtag_driver_install(&cfg);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "USB 시리얼 드라이버 설치 실패: %s", esp_err_to_name(err));
        return;
    }
    xTaskCreate(console_task, "console", 4096, NULL, 4, NULL);
}
