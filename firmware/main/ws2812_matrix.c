#include <string.h>
#include <stdlib.h>
#include <math.h>
#include <sys/param.h>

#include "ws2812_matrix.h"
#include "board_config.h"
#include "power.h"
#include "driver/rmt_tx.h"
#include "esp_log.h"
#include "esp_check.h"

static const char *TAG = "matrix";

#define RMT_RESOLUTION_HZ   10000000    /* 10MHz → 1틱 = 0.1us */

/* ---------------------------------------------------------------------------
 * WS2812 RMT 인코더 (ESP-IDF led_strip 예제와 동일한 구조)
 * ------------------------------------------------------------------------- */

typedef struct {
    rmt_encoder_t base;
    rmt_encoder_t *bytes_encoder;
    rmt_encoder_t *copy_encoder;
    int state;
    rmt_symbol_word_t reset_code;
} ws2812_encoder_t;

static size_t ws2812_encode(rmt_encoder_t *encoder, rmt_channel_handle_t channel,
                            const void *primary_data, size_t data_size,
                            rmt_encode_state_t *ret_state)
{
    ws2812_encoder_t *enc = __containerof(encoder, ws2812_encoder_t, base);
    rmt_encode_state_t session_state = RMT_ENCODING_RESET;
    rmt_encode_state_t state = RMT_ENCODING_RESET;
    size_t encoded_symbols = 0;

    switch (enc->state) {
    case 0:
        encoded_symbols += enc->bytes_encoder->encode(enc->bytes_encoder, channel,
                                                      primary_data, data_size, &session_state);
        if (session_state & RMT_ENCODING_COMPLETE) {
            enc->state = 1;
        }
        if (session_state & RMT_ENCODING_MEM_FULL) {
            state |= RMT_ENCODING_MEM_FULL;
            goto out;
        }
        __attribute__((fallthrough));
    case 1:
        encoded_symbols += enc->copy_encoder->encode(enc->copy_encoder, channel,
                                                     &enc->reset_code, sizeof(enc->reset_code),
                                                     &session_state);
        if (session_state & RMT_ENCODING_COMPLETE) {
            enc->state = 0;
            state |= RMT_ENCODING_COMPLETE;
        }
        if (session_state & RMT_ENCODING_MEM_FULL) {
            state |= RMT_ENCODING_MEM_FULL;
            goto out;
        }
        break;
    default:
        break;
    }

out:
    *ret_state = state;
    return encoded_symbols;
}

static esp_err_t ws2812_encoder_reset(rmt_encoder_t *encoder)
{
    ws2812_encoder_t *enc = __containerof(encoder, ws2812_encoder_t, base);
    rmt_encoder_reset(enc->bytes_encoder);
    rmt_encoder_reset(enc->copy_encoder);
    enc->state = 0;
    return ESP_OK;
}

static esp_err_t ws2812_encoder_del(rmt_encoder_t *encoder)
{
    ws2812_encoder_t *enc = __containerof(encoder, ws2812_encoder_t, base);
    rmt_del_encoder(enc->bytes_encoder);
    rmt_del_encoder(enc->copy_encoder);
    free(enc);
    return ESP_OK;
}

/* ---------------------------------------------------------------------------
 * 드라이버 상태
 * ------------------------------------------------------------------------- */

static rmt_channel_handle_t s_chan;
static rmt_encoder_handle_t s_encoder;
static uint8_t s_grb[MATRIX_PIXELS * 3];    /* 전송 버퍼 (WS2812는 G,R,B 순) */
static rgb_t   s_fb[MATRIX_PIXELS];         /* 프레임버퍼 (보정 전 원시값) */
static uint8_t s_gamma[256];
static float   s_last_ma;        /* 직전 프레임의 추정 전류 */

esp_err_t matrix_init(void)
{
    /*
     * 감마 보정과 밝기 상한을 하나의 룩업 테이블로 합친다. 두 단계를 따로
     * 8비트로 처리하면 반올림이 두 번 일어나 어두운 구간이 통째로 0이 된다.
     */
    for (int i = 0; i < 256; i++) {
        float v = powf(i / 255.0f, LED_GAMMA) * LED_MAX_BRIGHTNESS;
        s_gamma[i] = (uint8_t)(v + 0.5f);
    }

    rmt_tx_channel_config_t chan_cfg = {
        .clk_src           = RMT_CLK_SRC_DEFAULT,
        .gpio_num          = LED_GPIO,
        .mem_block_symbols = 64,
        .resolution_hz     = RMT_RESOLUTION_HZ,
        .trans_queue_depth = 4,
    };
    ESP_RETURN_ON_ERROR(rmt_new_tx_channel(&chan_cfg, &s_chan), TAG, "RMT 채널 생성 실패");

    ws2812_encoder_t *enc = calloc(1, sizeof(ws2812_encoder_t));
    ESP_RETURN_ON_FALSE(enc, ESP_ERR_NO_MEM, TAG, "인코더 할당 실패");

    enc->base.encode = ws2812_encode;
    enc->base.del    = ws2812_encoder_del;
    enc->base.reset  = ws2812_encoder_reset;

    /* WS2812B: T0H 0.3us / T0L 0.9us, T1H 0.9us / T1L 0.3us */
    rmt_bytes_encoder_config_t bytes_cfg = {
        .bit0 = { .level0 = 1, .duration0 = 3, .level1 = 0, .duration1 = 9 },
        .bit1 = { .level0 = 1, .duration0 = 9, .level1 = 0, .duration1 = 3 },
        .flags.msb_first = 1,
    };
    ESP_RETURN_ON_ERROR(rmt_new_bytes_encoder(&bytes_cfg, &enc->bytes_encoder), TAG, "bytes 인코더 실패");

    rmt_copy_encoder_config_t copy_cfg = {};
    ESP_RETURN_ON_ERROR(rmt_new_copy_encoder(&copy_cfg, &enc->copy_encoder), TAG, "copy 인코더 실패");

    /* 리셋(latch) 구간: 총 200us — 데이터시트 최소 50us보다 넉넉히 */
    enc->reset_code = (rmt_symbol_word_t){
        .level0 = 0, .duration0 = 1000,
        .level1 = 0, .duration1 = 1000,
    };

    s_encoder = &enc->base;
    ESP_RETURN_ON_ERROR(rmt_enable(s_chan), TAG, "RMT enable 실패");

    matrix_clear();
    matrix_flush();
    ESP_LOGI(TAG, "%dx%d WS2812 초기화 완료 (GPIO%d, 최대밝기 %d)",
             MATRIX_W, MATRIX_H, LED_GPIO, LED_MAX_BRIGHTNESS);
    return ESP_OK;
}

/* 논리 좌표 (x,y) → 스트립 인덱스 */
static inline int xy_to_index(int x, int y)
{
#if MATRIX_FLIP_X
    x = MATRIX_W - 1 - x;
#endif
#if MATRIX_FLIP_Y
    y = MATRIX_H - 1 - y;
#endif
#if MATRIX_SERPENTINE
    if (y & 1) {
        x = MATRIX_W - 1 - x;
    }
#endif
    return y * MATRIX_W + x;
}

void matrix_clear(void)
{
    memset(s_fb, 0, sizeof(s_fb));
}

void matrix_fade(float scale)
{
    if (scale <= 0.0f) {
        matrix_clear();
        return;
    }
    if (scale >= 1.0f) {
        return;
    }
    for (int i = 0; i < MATRIX_PIXELS; i++) {
        s_fb[i].r = (uint8_t)(s_fb[i].r * scale);
        s_fb[i].g = (uint8_t)(s_fb[i].g * scale);
        s_fb[i].b = (uint8_t)(s_fb[i].b * scale);
    }
}

void matrix_set(int x, int y, rgb_t c)
{
    if (x < 0 || x >= MATRIX_W || y < 0 || y >= MATRIX_H) {
        return;
    }
    s_fb[xy_to_index(x, y)] = c;
}

void matrix_add(int x, int y, rgb_t c)
{
    if (x < 0 || x >= MATRIX_W || y < 0 || y >= MATRIX_H) {
        return;
    }
    rgb_t *p = &s_fb[xy_to_index(x, y)];
    p->r = (uint8_t)MIN(255, p->r + c.r);
    p->g = (uint8_t)MIN(255, p->g + c.g);
    p->b = (uint8_t)MIN(255, p->b + c.b);
}

void matrix_add_soft(float x, float y, rgb_t c)
{
    int x0 = (int)floorf(x);
    int y0 = (int)floorf(y);
    float fx = x - x0;
    float fy = y - y0;

    const float w[4] = {
        (1.0f - fx) * (1.0f - fy),
        fx * (1.0f - fy),
        (1.0f - fx) * fy,
        fx * fy,
    };
    const int px[4] = { x0, x0 + 1, x0, x0 + 1 };
    const int py[4] = { y0, y0, y0 + 1, y0 + 1 };

    for (int i = 0; i < 4; i++) {
        if (w[i] > 0.002f) {
            matrix_add(px[i], py[i], rgb_scale(c, w[i]));
        }
    }
}

/*
 * 프레임 전류 추정.
 *
 * WS2812 의 채널 전류는 PWM 듀티에 거의 비례하므로, 감마·밝기 보정을 모두
 * 거친 최종 출력값의 합으로 계산한다. 여기에 LED 대기 전류를 더한다.
 */
static float estimate_ma(const uint8_t *grb, int pixels)
{
    uint32_t sum = 0;
    for (int i = 0; i < pixels * 3; i++) {
        sum += grb[i];
    }
    return (sum / 255.0f) * LED_MA_PER_CHANNEL + pixels * LED_QUIESCENT_MA;
}

/*
 * 예산을 넘으면 프레임 전체에 같은 배율을 곱한다.
 *
 * 채널별로 자르지 않고 전체를 균일하게 줄여야 색이 유지된다. 특정 채널만
 * 깎으면 흰색이 색깔로 변해 버린다.
 *
 * 이 경로를 우회하는 방법을 만들지 않는다. 모든 출력은 여기를 지난다.
 */
static float apply_power_limit(uint8_t *grb, int pixels)
{
    float ma = estimate_ma(grb, pixels);
    const float budget = power_budget_ma();
    if (ma <= budget) {
        return ma;
    }

    /* 대기 전류는 못 줄이므로 가변분에만 배율을 적용한다 */
    const float fixed = pixels * LED_QUIESCENT_MA;
    const float budget_var = budget - fixed;
    if (budget_var <= 0.0f) {
        memset(grb, 0, pixels * 3);   /* 예산이 대기 전류보다 작다 — 다 끈다 */
        return fixed;
    }

    const float scale = budget_var / (ma - fixed);
    for (int i = 0; i < pixels * 3; i++) {
        grb[i] = (uint8_t)(grb[i] * scale);
    }
    return estimate_ma(grb, pixels);
}

/*
 * 배율 k 는 감마 이전에 곱해지므로 전류는 k^감마 에 비례한다.
 * 감마 LUT 로 프레임 비용을 구하고 거기서 역산한다.
 *
 * 0.97 은 반올림 여유다. 딱 맞춰 계산하면 몇 mA 씩 넘어 그 프레임만 눌리고,
 * 밝기가 튄다.
 */
float matrix_headroom(const rgb_t *px, int n)
{
    uint32_t sum = 0;
    for (int i = 0; i < n; i++) {
        sum += s_gamma[px[i].r] + s_gamma[px[i].g] + s_gamma[px[i].b];
    }

    const float var = power_budget_ma() - n * LED_QUIESCENT_MA;
    if (var <= 0.0f) return 0.0f;

    const float full = (sum / 255.0f) * LED_MA_PER_CHANNEL;
    if (full <= var) return 1.0f;

    return 0.97f * powf(var / full, 1.0f / LED_GAMMA);
}

esp_err_t matrix_flush(void)
{
    for (int i = 0; i < MATRIX_PIXELS; i++) {
        s_grb[i * 3 + 0] = s_gamma[s_fb[i].g];
        s_grb[i * 3 + 1] = s_gamma[s_fb[i].r];
        s_grb[i * 3 + 2] = s_gamma[s_fb[i].b];
    }

    s_last_ma = apply_power_limit(s_grb, MATRIX_PIXELS);

    rmt_transmit_config_t tx_cfg = { .loop_count = 0 };
    ESP_RETURN_ON_ERROR(rmt_transmit(s_chan, s_encoder, s_grb, sizeof(s_grb), &tx_cfg),
                        TAG, "RMT 전송 실패");
    return rmt_tx_wait_all_done(s_chan, 100);
}

float matrix_current_ma(void)
{
    return s_last_ma;
}

rgb_t rgb_scale(rgb_t c, float scale)
{
    if (scale <= 0.0f) {
        return (rgb_t){ 0, 0, 0 };
    }
    if (scale > 1.0f) {
        scale = 1.0f;
    }
    return (rgb_t){
        .r = (uint8_t)(c.r * scale),
        .g = (uint8_t)(c.g * scale),
        .b = (uint8_t)(c.b * scale),
    };
}

rgb_t hsv2rgb(uint8_t h, uint8_t s, uint8_t v)
{
    if (s == 0) {
        return (rgb_t){ v, v, v };
    }

    uint8_t region    = h / 43;             /* 0..5 */
    uint8_t remainder = (h - region * 43) * 6;

    uint8_t p = (uint8_t)((v * (255 - s)) >> 8);
    uint8_t q = (uint8_t)((v * (255 - ((s * remainder) >> 8))) >> 8);
    uint8_t t = (uint8_t)((v * (255 - ((s * (255 - remainder)) >> 8))) >> 8);

    switch (region) {
    case 0:  return (rgb_t){ v, t, p };
    case 1:  return (rgb_t){ q, v, p };
    case 2:  return (rgb_t){ p, v, t };
    case 3:  return (rgb_t){ p, q, v };
    case 4:  return (rgb_t){ t, p, v };
    default: return (rgb_t){ v, p, q };
    }
}
