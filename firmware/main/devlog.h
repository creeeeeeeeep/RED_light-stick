#pragma once

#include "settings.h"
#include "sdkconfig.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * 모션 로그를 서버로 흘려보낸다 (개발자 빌드 전용).
 *
 * 제스처 임계값을 맞추려면 실제로 흔든 데이터가 많이 필요한데, 시리얼로
 * 받으려면 USB 를 꽂고 있어야 한다. 그 상태로는 제대로 못 흔든다.
 * 그래서 봉이 WiFi 로 보내고 PC 가 CSV 로 쌓는다.
 *
 * 배포 빌드에서는 아래 함수들이 전부 빈 껍데기라 코드가 들어가지 않는다.
 *
 * 200Hz 로 도는 IMU 태스크에서 불리므로 devlog_line() 은 절대 블로킹하지
 * 않는다. 버퍼가 차면 그냥 버리고 몇 줄 버렸는지만 센다.
 */

#if CONFIG_CROWN_DEV

void devlog_start(const settings_t *s);
void devlog_settings_changed(const settings_t *s);
void devlog_line(const char *line);

/* 마지막 전송 결과 (STATUS 명령용) */
const char *devlog_status(void);

#else

static inline void devlog_start(const settings_t *s) { (void)s; }
static inline void devlog_settings_changed(const settings_t *s) { (void)s; }
static inline void devlog_line(const char *line) { (void)line; }
static inline const char *devlog_status(void) { return "(배포 빌드)"; }

#endif

#ifdef __cplusplus
}
#endif
