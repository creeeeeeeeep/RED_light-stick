/*
 * QST QMI8658C 6축 IMU 드라이버 (ESP-IDF i2c_master API).
 */
#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "driver/i2c_master.h"

#ifdef __cplusplus
extern "C" {
#endif

#define QMI8658_ADDR_LOW    0x6A    /* SA0 = GND */
#define QMI8658_ADDR_HIGH   0x6B    /* SA0 = VDD (Waveshare 보드 기본값) */

typedef struct {
    float ax, ay, az;   /* g */
    float gx, gy, gz;   /* deg/s, 바이어스 보정 적용됨 */
} qmi8658_data_t;

typedef struct qmi8658_dev_t qmi8658_dev_t;

/*
 * 버스를 스캔해 0x6B → 0x6A 순으로 QMI8658을 찾고 초기화한다.
 * 설정: 가속도 ±16g / 자이로 ±2048dps / 양쪽 ODR 500Hz / 내부 LPF ~27Hz.
 */
esp_err_t qmi8658_create(i2c_master_bus_handle_t bus, qmi8658_dev_t **out_dev);

/* 최신 6축 샘플 1개를 읽는다. */
esp_err_t qmi8658_read(qmi8658_dev_t *dev, qmi8658_data_t *out);

/*
 * 자이로 제로 바이어스 측정. 호출 중 보드를 완전히 정지시켜 둬야 한다.
 * 움직임이 감지되면 ESP_ERR_INVALID_STATE를 반환하고 바이어스는 갱신하지 않는다.
 */
esp_err_t qmi8658_calibrate_gyro(qmi8658_dev_t *dev, int samples);

uint8_t qmi8658_i2c_addr(const qmi8658_dev_t *dev);

#ifdef __cplusplus
}
#endif
