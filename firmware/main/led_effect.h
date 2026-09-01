#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "gesture.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * 쌓인 개수를 화면에 어떻게 반영할지 결정하는 상태.
 *
 * 개수를 아래쪽 행으로 그리지 않고 화면 전체 밝기로 표현한다.
 * 행으로 그리면 8x8 에서 한 칸이 너무 작아 흔드는 도중에는 알아보기 어렵다.
 * 밝기는 눈에 바로 들어오고, 개수가 하나쯤 틀려도 문제가 되지 않는다.
 *
 * 항목별 종류는 들지 않는다. 봉은 개수만 세고 실제 큐는 채팅 입력창이
 * 들고 있기 때문이다. 봉이 목록을 따로 보관하면 통신이 한 번 어긋날 때
 * 브라우저와 영구히 다른 상태가 된다.
 */
typedef struct {
    int count;      /* 마지막 전송 이후 쌓은 개수 */
    int capacity;   /* 상한 */
} led_queue_view_t;

/*
 * 한 프레임을 프레임버퍼에 그린다 (flush는 호출자 책임).
 *   g         : 현재 제스처
 *   intensity : 0.0~1.0 움직임 세기. 속도 변조에 쓰인다.
 *   now_ms    : 단조 증가 밀리초
 *   q         : 쌓인 개수. NULL 이면 밝기 변조 없이 그린다.
 */
void led_effect_render(gesture_t g, float intensity, uint32_t now_ms,
                       const led_queue_view_t *q);

/* 제스처가 바뀐 순간 호출 — 애니메이션 위상을 리셋한다. */
void led_effect_on_gesture_change(gesture_t g, uint32_t now_ms);

/* 하나 쌓인 순간 호출 — 화면 전체가 짧게 번쩍인다. */
void led_effect_on_queue_add(uint32_t now_ms);

/* 전송(버튼) 순간 호출 — 흰색 섬광 후 아래로 쓸려나가는 연출을 시작한다. */
void led_effect_on_flush(uint32_t now_ms);

/* 전송 연출이 재생 중인지. 재생 중에는 모션 이펙트를 덮어쓴다. */
bool led_effect_flush_active(uint32_t now_ms);

#ifdef __cplusplus
}
#endif
