/*
 * 8x8 WS2812B 매트릭스 드라이버 (RMT 커스텀 인코더, 외부 컴포넌트 의존성 없음).
 *
 * 프레임버퍼는 원시 밝기로 관리하고, flush 시점에 감마 보정과
 * LED_MAX_BRIGHTNESS 상한을 한 번에 적용한다.
 */
#pragma once

#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint8_t r, g, b;
} rgb_t;

esp_err_t matrix_init(void);

/* 프레임버퍼 전체를 0으로 */
void matrix_clear(void);

/* 프레임버퍼 전체를 s배 (0.0~1.0) — 잔상 트레일용 */
void matrix_fade(float scale);

/* (x, y)에 색을 덮어쓴다. 좌상단이 (0,0). 범위 밖 좌표는 무시. */
void matrix_set(int x, int y, rgb_t c);

/* (x, y)에 색을 가산 합성(saturating add). */
void matrix_add(int x, int y, rgb_t c);

/*
 * 부동소수 좌표에 점을 찍는다. 인접 4픽셀에 가중 분배해서
 * 스윕 이펙트가 계단처럼 튀지 않게 한다.
 */
void matrix_add_soft(float x, float y, rgb_t c);

/*
 * 프레임버퍼를 LED로 전송하고 완료까지 대기.
 *
 * 전송 직전에 프레임의 실제 전류를 추정하고, LED_BUDGET_MA 를 넘으면
 * 프레임 전체에 배율을 곱해 끌어내린다. 이 경로를 우회하는 방법은 없다.
 */
esp_err_t matrix_flush(void);

/* 직전 프레임의 추정 전류(mA). 제한이 걸렸다면 제한 후 값이다. */
float matrix_current_ma(void);

/*
 * 이 색들로 화면을 채울 때, 전력 예산에 눌리지 않고 쓸 수 있는 최대 배율.
 *
 * flush 단계에도 전류 제한이 있지만 그건 마지막 안전장치다. 거기서 눌리면
 * 밝은 구간이 전부 같은 값에 붙어 버려서 밝기 변화가 사라지는데, 확산 돔
 * 안에서는 그 변화가 모션을 구분하는 유일한 단서다. 그래서 그리기 전에
 * 미리 상한을 구해 그 안에서만 움직인다.
 *
 * 픽셀마다 색이 달라도 된다 — 그라데이션을 쓰려면 그래야 한다.
 */
float matrix_headroom(const rgb_t *px, int n);

/* HSV → RGB (h: 0~255 순환, s/v: 0~255) */
rgb_t hsv2rgb(uint8_t h, uint8_t s, uint8_t v);

/* c의 각 채널을 scale(0.0~1.0)배 */
rgb_t rgb_scale(rgb_t c, float scale);

#ifdef __cplusplus
}
#endif
