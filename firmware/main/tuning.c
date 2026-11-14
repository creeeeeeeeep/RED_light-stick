#include <string.h>
#include <stdio.h>
#include <math.h>

#include "tuning.h"
#include "board_config.h"
#include "esp_log.h"

static const char *TAG = "tuning";

static gesture_engine_t  *s_eng;
static tuning_button_cb_t s_btn_cb;

/* 제스처 임계값. 엔진에 반영하기 전의 사본을 여기 들고 있는다. */
static gesture_config_t s_g;

/* 큐·버튼 쪽 값. board_config.h 의 값으로 시작한다. */
static int  s_add_ms       = QUEUE_ADD_INTERVAL_MS;
static int  s_arm_ms       = QUEUE_ARM_MS;
static int  s_gap_ms       = QUEUE_GAP_MS;
static int  s_qmax         = QUEUE_MAX;
static int  s_btn_gpio     = BUTTON_GPIO;
static int  s_btn_debounce = BUTTON_DEBOUNCE_MS;
static int  s_btn_low      = BUTTON_ACTIVE_LOW;

/*
 * 손잡이 표.
 *
 * 실수 하나로 다 받는다. 정수 항목은 반올림해서 넣는다 — 페이지에서
 * 슬라이더로 보내는 값이라 타입을 나눠 봐야 득이 없다.
 */
typedef struct {
    const char *key;
    float      *f;       /* 둘 중 하나만 채운다 */
    int        *i;
    float       lo, hi;
    const char *what;
} knob_t;

static const knob_t KNOBS[] = {
    /* ---- 모션 판정 ---- */
    { "idle_rms",      &s_g.idle_rms_g,       NULL, 0.01f,  1.00f, "이 RMS 미만이면 정지 (g)" },
    { "idle_exit",     &s_g.idle_exit_ratio,  NULL, 0.10f,  1.00f, "정지에서 빠져나올 때 완화 배율" },
    { "axis_ratio",    &s_g.axis_ratio,       NULL, 1.00f,  3.00f, "좌우/상하를 가르는 축 우세 배율" },
    { "vig_peak",      &s_g.vig_peak_g,       NULL, 1.00f, 12.00f, "격하게: 선형가속 피크 (g)" },
    { "vig_rms",       &s_g.vig_rms_g,        NULL, 0.50f,  6.00f, "격하게: 전체 RMS (g)" },
    { "vig_gyro",      &s_g.vig_gyro_dps,     NULL, 100.f, 2000.f, "격하게: 자이로 RMS (deg/s)" },
    { "vig_gyro_min",  &s_g.vig_gyro_min_rms, NULL, 0.05f,  2.00f, "자이로 조건에 요구되는 최소 RMS (g)" },
    { "vig_hyst",      &s_g.vig_hysteresis,   NULL, 0.30f,  1.00f, "격하게 유지 시 완화 배율" },
    { "stroke_dead",   &s_g.stroke_dead_g,    NULL, 0.01f,  1.00f, "스트로크 판정 데드밴드 (g)" },
    { "stroke_flip",   &s_g.stroke_flip_dot,  NULL, -1.00f, 0.00f, "방향 반전으로 볼 내적 임계" },
    { "max_crest",     &s_g.max_crest,        NULL, 1.50f, 20.00f, "peak/rms 상한 — 넘으면 단발 충격" },
    { "min_strokes",   NULL, &s_g.min_strokes,       1.f,    10.f, "모션으로 인정할 최소 스트로크 수" },
    { "confirm_ticks", NULL, &s_g.confirm_ticks,     1.f,    20.f, "전환 확정에 필요한 연속 틱 (1틱=50ms)" },
    { "hold_ms",       NULL, &s_g.hold_ms,           0.f,  5000.f, "확정 후 최소 유지 시간 (ms)" },

    /* ---- 이모티콘이 쌓이는 박자 ---- */
    { "add_ms",        NULL, &s_add_ms,            100.f,  5000.f, "흔드는 중 이 간격마다 1개 (ms)" },
    { "arm_ms",        NULL, &s_arm_ms,              0.f,  3000.f, "이만큼 유지해야 쌓기 시작 (ms)" },
    { "gap_ms",        NULL, &s_gap_ms,              0.f,  3000.f, "이하 공백은 끊긴 걸로 안 본다 (ms)" },
    { "queue_max",     NULL, &s_qmax,                1.f,    30.f, "한 번에 쌓을 수 있는 최대 개수" },

    /* ---- 버튼 ---- */
    { "btn_gpio",      NULL, &s_btn_gpio,            0.f,    48.f, "전송 버튼 GPIO 번호" },
    { "btn_debounce",  NULL, &s_btn_debounce,        5.f,   500.f, "버튼 디바운스 (ms)" },
    { "btn_low",       NULL, &s_btn_low,             0.f,     1.f, "눌렀을 때 LOW 면 1" },
};

#define KNOB_COUNT (sizeof(KNOBS) / sizeof(KNOBS[0]))

static void push_to_engine(void)
{
    if (s_eng) gesture_set_config(s_eng, &s_g);
}

void tuning_attach(gesture_engine_t *eng)
{
    s_eng = eng;
    /* 엔진이 들고 있는 값이 진짜 기준이다. 사본을 거기 맞춘다. */
    if (eng) gesture_get_config(eng, &s_g);
    else     gesture_default_config(&s_g);
}

void tuning_set_button_cb(tuning_button_cb_t cb)
{
    s_btn_cb = cb;
}

bool tuning_set(const char *key, float value, char *err, size_t err_len)
{
    if (!key || !*key) {
        snprintf(err, err_len, "키가 필요합니다");
        return false;
    }

    for (size_t n = 0; n < KNOB_COUNT; n++) {
        const knob_t *k = &KNOBS[n];
        if (strcmp(k->key, key) != 0) continue;

        if (!(value >= k->lo && value <= k->hi)) {
            snprintf(err, err_len, "%s 는 %.2f ~ %.2f 사이여야 합니다", key, k->lo, k->hi);
            return false;
        }

        if (k->f) {
            *k->f = value;
            push_to_engine();
        } else {
            const int old = *k->i;
            const int nv  = (int)lroundf(value);
            *k->i = nv;

            if (k->i == &s_btn_gpio && s_btn_cb && old != nv) {
                s_btn_cb(old, nv);
            } else if (k->i == &s_g.min_strokes || k->i == &s_g.confirm_ticks ||
                       k->i == &s_g.hold_ms) {
                push_to_engine();
            }
        }
        ESP_LOGI(TAG, "%s = %.3f", key, (double)value);
        return true;
    }

    snprintf(err, err_len, "모르는 키: %s", key);
    return false;
}

void tuning_print_all(void)
{
    for (size_t n = 0; n < KNOB_COUNT; n++) {
        const knob_t *k = &KNOBS[n];
        const float v = k->f ? *k->f : (float)*k->i;
        /* 페이지가 줄 단위로 긁어가므로 형식을 바꾸지 말 것 */
        printf("ST tune_%s=%.4f %.4f %.4f %s\n",
               k->key, (double)v, (double)k->lo, (double)k->hi, k->what);
    }
    printf("ST tune_end=%d\n", (int)KNOB_COUNT);
    fflush(stdout);
}

void tuning_reset(void)
{
    gesture_default_config(&s_g);
    s_add_ms       = QUEUE_ADD_INTERVAL_MS;
    s_arm_ms       = QUEUE_ARM_MS;
    s_gap_ms       = QUEUE_GAP_MS;
    s_qmax         = QUEUE_MAX;
    s_btn_debounce = BUTTON_DEBOUNCE_MS;
    s_btn_low      = BUTTON_ACTIVE_LOW;

    if (s_btn_gpio != BUTTON_GPIO) {
        const int old = s_btn_gpio;
        s_btn_gpio = BUTTON_GPIO;
        if (s_btn_cb) s_btn_cb(old, s_btn_gpio);
    }
    push_to_engine();
    ESP_LOGI(TAG, "기본값으로 되돌렸습니다");
}

int  tuning_queue_add_ms(void)       { return s_add_ms; }
int  tuning_queue_arm_ms(void)       { return s_arm_ms; }
int  tuning_queue_gap_ms(void)       { return s_gap_ms; }
int  tuning_queue_max(void)          { return s_qmax; }
int  tuning_button_gpio(void)        { return s_btn_gpio; }
int  tuning_button_debounce_ms(void) { return s_btn_debounce; }
bool tuning_button_active_low(void)  { return s_btn_low != 0; }
