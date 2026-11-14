/*
 * 실행 중에 바꿀 수 있는 손잡이들.
 *
 * 크라운을 달면 질량과 길이가 달라져서 모션 임계값을 다시 잡아야 한다.
 * 굽고 → 흔들어보고 → 고치고 → 다시 굽기를 반복하면 한 바퀴에 몇 분씩
 * 걸린다. 여기 모아 두고 시리얼로 바꾸면 봉을 든 채로 즉시 확인된다.
 *
 * **NVS 에 저장하지 않는다.** 재부팅하면 빌드에 박힌 값으로 돌아간다.
 * 좋은 값을 찾으면 gesture.c 와 board_config.h 에 적어 넣고 다시 굽는다.
 * 팬에게 나가는 봉이 각자 다른 값을 들고 있으면 안 되기 때문이다.
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include "gesture.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 버튼 핀이 바뀌면 GPIO 를 다시 잡아야 한다 */
typedef void (*tuning_button_cb_t)(int old_gpio, int new_gpio);

/*
 * 제스처 엔진을 붙인다. imu_task 가 엔진을 만든 직후에 부른다.
 * 이 뒤로 tuning_set() 이 엔진에 값을 바로 꽂는다.
 */
void tuning_attach(gesture_engine_t *eng);
void tuning_set_button_cb(tuning_button_cb_t cb);

/*
 * 값 하나를 바꾼다. 키를 모르거나 범위를 벗어나면 false 를 돌려주고
 * err 에 이유를 적는다.
 */
bool tuning_set(const char *key, float value, char *err, size_t err_len);

/* 지금 값을 전부 "ST tune_<키>=<값>" 으로 찍는다. 튜닝 페이지가 이걸 읽는다. */
void tuning_print_all(void);

/* 빌드에 박힌 기본값으로 되돌린다 */
void tuning_reset(void);

/* main.c 가 매 프레임 읽어가는 값들 */
int tuning_queue_add_ms(void);
int tuning_queue_arm_ms(void);
int tuning_queue_gap_ms(void);
int tuning_queue_max(void);
int tuning_button_gpio(void);
int tuning_button_debounce_ms(void);
bool tuning_button_active_low(void);

#ifdef __cplusplus
}
#endif
