/*
 * 응원봉 모션 인식 엔진.
 *
 * 원리
 * ----
 * 1) 자이로로 예측하고 가속도로 보정하는 상보필터로 중력 방향 단위벡터를
 *    추정한다. 이렇게 하면 보드를 봉 안에 어떤 각도로 넣든, 그리고 흔드는
 *    도중 봉이 크게 기울어도 "위/아래"를 놓치지 않는다.
 * 2) 중력을 뺀 선형가속도를 중력축 성분(a_v)과 수평면 성분(a_h)으로 분해한다.
 *      - 상하로 찍기  → a_v 우세
 *      - 좌우로 흔들기 → a_h 우세
 * 3) 0.8초 슬라이딩 윈도우에서 RMS 에너지 / 피크 / 자이로 RMS / 스트로크
 *    횟수를 뽑고, 규칙 기반으로 분류한다. 스트로크가 2회 미만이거나 파고율
 *    (peak/rms)이 너무 높으면 진동이 아니라 단발 충격이므로 IDLE로 본다
 *    (봉을 책상에 툭 내려놓는 동작의 오인식 방지).
 *
 *    스트로크는 |선형가속도|의 임계 통과가 아니라 "방향 반전"으로 센다.
 *    호를 그리며 흔들 때는 원심가속도 때문에 가속도 크기가 0 근처로 절대
 *    떨어지지 않아서, 크기 기반 슈미트 트리거는 아예 동작하지 않는다.
 * 4) 격한 흔들기는 축과 무관한 에너지 임계로 판정하며, 최우선순위를 갖는다.
 */
#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "qmi8658.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    GESTURE_IDLE = 0,   /* 정지 또는 미미한 움직임 */
    GESTURE_SWAY_LR,    /* 양옆으로 흔들기 */
    GESTURE_PUMP_UD,    /* 위아래로 찍기 */
    GESTURE_VIGOROUS,   /* 격하게 흔들기 */
    GESTURE_COUNT
} gesture_t;

/* 튜닝 파라미터. 전부 gesture_default_config()에서 기본값을 받는다. */
typedef struct {
    float idle_rms_g;       /* 이 RMS 미만이면 IDLE (g) */
    float idle_exit_ratio;  /* IDLE 로 나갈 때 임계 완화 배율 (<1) */
    float axis_ratio;       /* 축 우세 판정 배율 (a_v vs a_h) */
    float vig_peak_g;       /* 격한 흔들기: 선형가속 피크 (g) */
    float vig_rms_g;        /* 격한 흔들기: 전체 RMS (g) */
    float vig_gyro_dps;     /* 격한 흔들기: 자이로 RMS (deg/s) */
    float vig_gyro_min_rms; /* 자이로 조건 사용 시 요구되는 최소 RMS (g) */
    float vig_hysteresis;   /* VIGOROUS 유지 시 임계 완화 배율 (<1) */
    float stroke_dead_g;    /* 스트로크 판정 데드밴드 (g) */
    float stroke_flip_dot;  /* 수평 방향 반전으로 볼 내적 임계 (<0) */
    float max_crest;        /* peak/rms 상한 — 넘으면 단발 충격으로 간주 */
    int   min_strokes;      /* 모션으로 인정할 최소 스트로크 수 */
    int   confirm_ticks;    /* 상태 전환 확정에 필요한 연속 틱 수 (1틱=50ms) */
    int   hold_ms;          /* 확정 후 최소 유지 시간 */
} gesture_config_t;

/* 분류 근거가 된 특징값. 임계 튜닝과 디버깅용. */
typedef struct {
    float rms_vertical;     /* g */
    float rms_horizontal;   /* g */
    float rms_total;        /* g */
    float peak_linear;      /* g */
    float rms_gyro;         /* deg/s */
    int   strokes;          /* 최근 0.8초 스트로크 수 */
    float stroke_rate;      /* 초당 스트로크 */
    float tilt_deg;         /* 봉 기울기 (중력축 기준, 참고용) */
} gesture_features_t;

typedef struct gesture_engine_t gesture_engine_t;

void gesture_default_config(gesture_config_t *cfg);

/* cfg가 NULL이면 기본값을 사용한다. */
gesture_engine_t *gesture_create(const gesture_config_t *cfg, float sample_hz);
void gesture_destroy(gesture_engine_t *eng);

/*
 * IMU 샘플 1개를 넣는다. 샘플링 주기마다 호출할 것.
 * 반환값은 현재 확정된 제스처(매 호출 유효).
 * changed가 NULL이 아니면 이번 호출에서 상태가 바뀌었는지 기록한다.
 */
gesture_t gesture_update(gesture_engine_t *eng, const qmi8658_data_t *s,
                         uint32_t now_ms, bool *changed);

gesture_t gesture_current(const gesture_engine_t *eng);

/* 0.0~1.0으로 정규화된 움직임 세기 (LED 이펙트 강도 변조용) */
float gesture_intensity(const gesture_engine_t *eng);

void gesture_get_features(const gesture_engine_t *eng, gesture_features_t *out);

const char *gesture_name(gesture_t g);

#ifdef __cplusplus
}
#endif
