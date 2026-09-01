#include <stdio.h>
#include <string.h>
#include <math.h>

#include "power.h"
#include "board_config.h"

#include "esp_log.h"
#include "esp_system.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "driver/usb_serial_jtag.h"

static const char *TAG = "power";

#define NVS_NS      "crown"
#define NVS_KEY     "led_step"

/*
 * 올라갈 수 있는 단계. 아래에서 위로만 배운다 — 브라운아웃을 겪으면 내려온다.
 *
 * 400 은 PC USB 2.0 포트에서도 안전한 값이고, 1200 은 2A 이상 주는 보조
 * 배터리를 상정한 값이다. 그 위로는 올리지 않는다. 전류를 더 흘릴 수 있는
 * 어댑터를 쓰더라도, 이 크기의 보드에서 그만한 열을 계속 내는 것은
 * 눈에 보이는 밝기 이득보다 손해가 크다.
 */
static const float STEPS[] = { 400.0f, 600.0f, 900.0f, 1200.0f };
#define NSTEPS  ((int)(sizeof(STEPS) / sizeof(STEPS[0])))

/* 부팅 직후에는 무조건 여기서 시작한다 */
#define BOOT_STEP       0
#define SETTLE_MS       4000

static int   s_target = 1;              /* 목표 단계 */
static int   s_now    = BOOT_STEP;      /* 지금 적용 중인 단계 */
static bool  s_learned = false;         /* 브라운아웃을 겪어 배운 값인가 */
static bool  s_usb_host = false;
static char  s_status[80] = "(초기화 전)";

static void save_step(int step)
{
    nvs_handle_t h;
    if (nvs_open(NVS_NS, NVS_READWRITE, &h) != ESP_OK) return;
    nvs_set_i8(h, NVS_KEY, (int8_t)step);
    nvs_commit(h);
    nvs_close(h);
}

static int load_step(void)
{
    nvs_handle_t h;
    if (nvs_open(NVS_NS, NVS_READONLY, &h) != ESP_OK) return -1;
    int8_t v = -1;
    if (nvs_get_i8(h, NVS_KEY, &v) != ESP_OK) v = -1;
    nvs_close(h);
    return v;
}

static void describe(void)
{
    const char *how = s_learned ? "학습됨"
                    : (s_target < 0) ? "급전 확인 중"
                    : (s_usb_host ? "PC 추정" : "충전기 추정");
    snprintf(s_status, sizeof(s_status), "%.0fmA (%s%s)",
             STEPS[s_now], how,
             (s_target >= 0 && s_now < s_target) ? ", 올라가는 중" : "");
}

void power_init(void)
{
    const int saved = load_step();
    const esp_reset_reason_t why = esp_reset_reason();

    if (why == ESP_RST_BROWNOUT) {
        /*
         * 전압이 주저앉아 죽었다. 직전에 쓰던 값이 이 급전 환경에는 과했다.
         * 한 단계 내려 적어두고, 다음부터는 추정 대신 이 값을 쓴다.
         */
        int step = (saved >= 0 ? saved : 1) - 1;
        if (step < 0) step = 0;
        s_target = step;
        s_learned = true;
        save_step(step);
        ESP_LOGW(TAG, "전압 강하로 재부팅했습니다 — LED 예산을 %.0fmA 로 낮춥니다",
                 STEPS[step]);

    } else if (saved >= 0 && saved < NSTEPS) {
        s_target = saved;
        s_learned = true;

    } else {
        /*
         * 처음 켜졌다. USB 호스트 여부로 추정할 텐데, 그 판정은 지금 할 수
         * 없다. 부팅 직후에는 USB 열거가 아직 끝나지 않아서 PC 에 꽂혀
         * 있어도 "호스트 없음" 으로 보인다. 그대로 믿으면 PC 포트에서
         * 충전기용 예산을 잡고 주저앉는다.
         *
         * 그래서 판정을 SETTLE_MS 뒤로 미룬다. 그때까지는 어디에 꽂혀
         * 있든 안전한 400mA 로 간다.
         */
        s_target = -1;                      /* 아직 모른다 */
    }

    s_now = BOOT_STEP;
    describe();
    if (s_target >= 0) {
        ESP_LOGI(TAG, "LED 예산: 시작 %.0fmA -> 목표 %.0fmA (학습값)",
                 STEPS[s_now], STEPS[s_target]);
    } else {
        ESP_LOGI(TAG, "LED 예산: 시작 %.0fmA, %d초 뒤 급전 환경을 보고 정합니다",
                 STEPS[s_now], SETTLE_MS / 1000);
    }
}

void power_tick(unsigned uptime_ms)
{
    /*
     * 부팅 직후는 WiFi 가 붙느라 전류가 가장 많이 튀는 구간이다. 그때 LED 까지
     * 최대로 쓰면 멀쩡한 급전 환경에서도 주저앉을 수 있다. 몇 초 지켜본 뒤
     * 올린다.
     */
    if (uptime_ms < SETTLE_MS) return;

    /* 이제는 USB 열거가 끝났다. 처음 켜진 봉이면 여기서 급전 환경을 정한다. */
    if (s_target < 0) {
        s_usb_host = usb_serial_jtag_is_connected();
        s_target = s_usb_host ? 1 : 2;      /* PC 600mA / 충전기 900mA */
        ESP_LOGI(TAG, "급전 환경: %s -> 목표 %.0fmA",
                 s_usb_host ? "PC (USB 호스트 있음)" : "충전기 (호스트 없음)",
                 STEPS[s_target]);
    }

    if (s_now < s_target) {
        s_now = s_target;
        describe();
        ESP_LOGI(TAG, "LED 예산을 %.0fmA 로 올립니다", STEPS[s_now]);
    }
}

float power_set_budget(float ma)
{
    if (ma <= 0.0f) {
        /* 자동으로 되돌린다 */
        nvs_handle_t h;
        if (nvs_open(NVS_NS, NVS_READWRITE, &h) == ESP_OK) {
            nvs_erase_key(h, NVS_KEY);
            nvs_commit(h);
            nvs_close(h);
        }
        s_learned = false;
        s_target = -1;
        s_now = BOOT_STEP;
        describe();
        ESP_LOGI(TAG, "LED 예산을 자동 추정으로 되돌립니다");
        return STEPS[s_now];
    }

    /* 가장 가까운 단계로 */
    int best = 0;
    for (int i = 1; i < NSTEPS; i++) {
        if (fabsf(STEPS[i] - ma) < fabsf(STEPS[best] - ma)) best = i;
    }
    s_target = best;
    s_now = best;
    s_learned = true;
    save_step(best);
    describe();
    ESP_LOGW(TAG, "LED 예산을 %.0fmA 로 직접 설정했습니다 — 발열과 리셋을 지켜보세요",
             STEPS[best]);
    return STEPS[best];
}

float power_budget_ma(void)
{
    return STEPS[s_now];
}

const char *power_status(void)
{
    return s_status;
}
