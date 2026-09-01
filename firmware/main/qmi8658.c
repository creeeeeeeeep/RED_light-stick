#include <string.h>
#include <math.h>
#include <stdlib.h>

#include "qmi8658.h"
#include "board_config.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

static const char *TAG = "qmi8658";

/* ---- 레지스터 맵 ---- */
#define REG_WHO_AM_I    0x00
#define REG_REVISION    0x01
#define REG_CTRL1       0x02
#define REG_CTRL2       0x03    /* accel: [6:4] full-scale, [3:0] ODR */
#define REG_CTRL3       0x04    /* gyro : [6:4] full-scale, [3:0] ODR */
#define REG_CTRL5       0x06    /* LPF  */
#define REG_CTRL7       0x08    /* 센서 enable */
#define REG_STATUS0     0x2E
#define REG_AX_L        0x35    /* AX_L..GZ_H 12바이트 연속 */
#define REG_RESET       0x60

#define WHO_AM_I_VALUE  0x05
#define RESET_CMD       0xB0

/* CTRL2: aFS=0b011(±16g), aODR=0b0100(500Hz) */
#define CTRL2_VALUE     0x34
/* CTRL3: gFS=0b111(±2048dps), gODR=0b0100(500Hz) */
#define CTRL3_VALUE     0x74
/* CTRL5: aLPF_EN + aLPF_MODE=0b10, gLPF_EN + gLPF_MODE=0b10 (≈ODR의 5.4% ≈ 27Hz) */
#define CTRL5_VALUE     0x55
/* CTRL7: gEN | aEN */
#define CTRL7_VALUE     0x03

/* 풀스케일에 대응하는 LSB 감도 */
#define ACC_LSB_PER_G   2048.0f     /* 32768 / 16 */
#define GYR_LSB_PER_DPS 16.0f       /* 32768 / 2048 */

struct qmi8658_dev_t {
    i2c_master_dev_handle_t handle;
    uint8_t addr;
    float gbias[3];         /* deg/s */
};

static esp_err_t reg_write(qmi8658_dev_t *dev, uint8_t reg, uint8_t val)
{
    uint8_t buf[2] = { reg, val };
    return i2c_master_transmit(dev->handle, buf, sizeof(buf), 100);
}

static esp_err_t reg_read(qmi8658_dev_t *dev, uint8_t reg, uint8_t *dst, size_t len)
{
    return i2c_master_transmit_receive(dev->handle, &reg, 1, dst, len, 100);
}

esp_err_t qmi8658_create(i2c_master_bus_handle_t bus, qmi8658_dev_t **out_dev)
{
    if (!bus || !out_dev) {
        return ESP_ERR_INVALID_ARG;
    }
    *out_dev = NULL;

    const uint8_t candidates[] = { QMI8658_ADDR_HIGH, QMI8658_ADDR_LOW };
    uint8_t addr = 0;
    for (size_t i = 0; i < sizeof(candidates); i++) {
        if (i2c_master_probe(bus, candidates[i], 100) == ESP_OK) {
            addr = candidates[i];
            break;
        }
    }
    if (addr == 0) {
        ESP_LOGE(TAG, "I2C 버스에서 QMI8658을 찾지 못했습니다 (SDA=%d SCL=%d, 0x6A/0x6B 모두 무응답)",
                 IMU_SDA_GPIO, IMU_SCL_GPIO);
        return ESP_ERR_NOT_FOUND;
    }

    qmi8658_dev_t *dev = calloc(1, sizeof(qmi8658_dev_t));
    if (!dev) {
        return ESP_ERR_NO_MEM;
    }
    dev->addr = addr;

    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address  = addr,
        .scl_speed_hz    = IMU_I2C_HZ,
    };
    esp_err_t err = i2c_master_bus_add_device(bus, &dev_cfg, &dev->handle);
    if (err != ESP_OK) {
        free(dev);
        return err;
    }

    uint8_t who = 0;
    err = reg_read(dev, REG_WHO_AM_I, &who, 1);
    if (err != ESP_OK || who != WHO_AM_I_VALUE) {
        ESP_LOGE(TAG, "WHO_AM_I 불일치: 0x%02X (기대값 0x%02X)", who, WHO_AM_I_VALUE);
        i2c_master_bus_rm_device(dev->handle);
        free(dev);
        return ESP_ERR_INVALID_RESPONSE;
    }

    /* 소프트 리셋 후 재설정 */
    reg_write(dev, REG_RESET, RESET_CMD);
    vTaskDelay(pdMS_TO_TICKS(50));

    /* CTRL1 bit6 = ADDR_AI: 버스트 리드를 위한 주소 자동 증가 */
    ESP_ERROR_CHECK(reg_write(dev, REG_CTRL1, 0x40));
    ESP_ERROR_CHECK(reg_write(dev, REG_CTRL2, CTRL2_VALUE));
    ESP_ERROR_CHECK(reg_write(dev, REG_CTRL3, CTRL3_VALUE));
    ESP_ERROR_CHECK(reg_write(dev, REG_CTRL5, CTRL5_VALUE));
    ESP_ERROR_CHECK(reg_write(dev, REG_CTRL7, CTRL7_VALUE));
    vTaskDelay(pdMS_TO_TICKS(20));

    /*
     * 주소 자동 증가가 실제로 켜졌는지 확인한다. 꺼져 있으면 버스트 리드가
     * 같은 바이트를 12번 반환해서 가속도값이 조용히 쓰레기가 된다.
     */
    uint8_t probe[2] = { 0, 0 };
    if (reg_read(dev, REG_WHO_AM_I, probe, 2) == ESP_OK && probe[1] == probe[0]) {
        ESP_LOGW(TAG, "ADDR_AI(주소 자동증가)가 동작하지 않는 것 같습니다 — 리비전을 확인하세요");
    }

    uint8_t rev = 0;
    reg_read(dev, REG_REVISION, &rev, 1);
    ESP_LOGI(TAG, "초기화 완료: addr=0x%02X rev=0x%02X, ±16g / ±2048dps / 500Hz", addr, rev);

    *out_dev = dev;
    return ESP_OK;
}

esp_err_t qmi8658_read(qmi8658_dev_t *dev, qmi8658_data_t *out)
{
    if (!dev || !out) {
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t raw[12];
    esp_err_t err = reg_read(dev, REG_AX_L, raw, sizeof(raw));
    if (err != ESP_OK) {
        return err;
    }

    int16_t v[6];
    for (int i = 0; i < 6; i++) {
        v[i] = (int16_t)((uint16_t)raw[i * 2] | ((uint16_t)raw[i * 2 + 1] << 8));
    }

    out->ax = v[0] / ACC_LSB_PER_G;
    out->ay = v[1] / ACC_LSB_PER_G;
    out->az = v[2] / ACC_LSB_PER_G;
    out->gx = v[3] / GYR_LSB_PER_DPS - dev->gbias[0];
    out->gy = v[4] / GYR_LSB_PER_DPS - dev->gbias[1];
    out->gz = v[5] / GYR_LSB_PER_DPS - dev->gbias[2];

    return ESP_OK;
}

esp_err_t qmi8658_calibrate_gyro(qmi8658_dev_t *dev, int samples)
{
    if (!dev || samples <= 0) {
        return ESP_ERR_INVALID_ARG;
    }

    /* 기존 바이어스를 걷어내고 원시값 기준으로 다시 측정한다. */
    float saved[3] = { dev->gbias[0], dev->gbias[1], dev->gbias[2] };
    dev->gbias[0] = dev->gbias[1] = dev->gbias[2] = 0.0f;

    double sum[3] = { 0, 0, 0 };
    float peak = 0.0f;
    int n = 0;

    for (int i = 0; i < samples; i++) {
        qmi8658_data_t d;
        if (qmi8658_read(dev, &d) == ESP_OK) {
            sum[0] += d.gx;
            sum[1] += d.gy;
            sum[2] += d.gz;
            float mag = sqrtf(d.gx * d.gx + d.gy * d.gy + d.gz * d.gz);
            if (mag > peak) {
                peak = mag;
            }
            n++;
        }
        vTaskDelay(pdMS_TO_TICKS(5));
    }

    if (n < samples / 2) {
        memcpy(dev->gbias, saved, sizeof(saved));
        return ESP_FAIL;
    }
    /* 정지 상태에서 40dps를 넘으면 손에 들고 흔든 것 — 캘리브레이션을 버린다. */
    if (peak > 40.0f) {
        memcpy(dev->gbias, saved, sizeof(saved));
        ESP_LOGW(TAG, "캘리브레이션 중 움직임 감지 (peak %.1f dps) — 이전 바이어스 유지", peak);
        return ESP_ERR_INVALID_STATE;
    }

    dev->gbias[0] = (float)(sum[0] / n);
    dev->gbias[1] = (float)(sum[1] / n);
    dev->gbias[2] = (float)(sum[2] / n);
    ESP_LOGI(TAG, "자이로 바이어스: %.2f / %.2f / %.2f dps",
             dev->gbias[0], dev->gbias[1], dev->gbias[2]);
    return ESP_OK;
}

uint8_t qmi8658_i2c_addr(const qmi8658_dev_t *dev)
{
    return dev ? dev->addr : 0;
}
