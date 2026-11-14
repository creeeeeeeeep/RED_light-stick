/*
 * 크라운 응원봉 펌웨어
 * Waveshare ESP32-S3-Matrix (8x8 WS2812 + QMI8658C 6축 IMU)
 *
 * 인식 모션 3종
 *   SWAY_LR  : 양옆으로 흔들기      → 빨강, 숨쉬듯
 *   PUMP_UD  : 위아래로 찍기        → 무지개가 계속 돌아간다
 *   VIGOROUS : 격하게 흔들기        → 금빛과 흰빛 사이로 빠르게 명멸
 *   (그 외)  : IDLE                → 깊은 호박색, 느리고 어둡게
 *
 * 보드가 확산 돔 안에 들어가므로 공간 패턴 대신 밝기의 리듬으로 구분하고,
 * 색은 화면을 가로지르는 완만한 그라데이션으로 낸다. led_effect.c 머리말 참고.
 */

#include <stdio.h>
#include <string.h>
#include <math.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "driver/i2c_master.h"
#include "driver/gpio.h"

#include "board_config.h"
#include "qmi8658.h"
#include "gesture.h"
#include "led_effect.h"
#include "ws2812_matrix.h"
#include "settings.h"
#include "net.h"
#include "console.h"
#include "ota.h"
#include "devlog.h"
#include "power.h"
#include "tuning.h"

static const char *TAG = "cheerstick";

/* IMU 태스크 → LED 태스크로 넘기는 공유 상태 */
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static gesture_t s_gesture = GESTURE_IDLE;
static float     s_intensity = 0.0f;
static bool      s_gesture_dirty = false;

/*
 * 쌓인 개수.
 *
 * 봉은 이모티콘 '목록'을 들지 않는다. 진짜 큐는 채팅 입력창이고, 봉이
 * 따로 목록을 보관하면 통신이 한 번 어긋날 때 브라우저와 영구히 다른
 * 상태가 된다(봉은 5개인데 입력창은 4개, 맞출 방법 없음).
 *
 * 그래서 흔들 때마다 서버로 바로 쏘고 잊는다. 여기서 세는 숫자는 오직
 * LED 밝기용이며, 하나쯤 틀려도 표시만 살짝 다를 뿐 전송에는 영향이 없다.
 * 전송하면 0 으로 돌아가므로 오차가 누적되지도 않는다.
 */
static int  s_sent_count = 0;
static bool s_queue_added = false;   /* 이번 프레임에 새로 쌓였는가 */
/*
 * 버튼을 누르고 있는 동안에만 쌓는다.
 *
 * 봉이 책상에 굴러다니거나 집어드는 것만으로도 모션이 잡혀서 입력창이
 * 지저분해졌다. 버튼으로 구간을 명시하면 그 일이 없어지고, "사람의 1회
 * 조작 = 채팅 1건" 이라는 치지직 전제에도 경계가 분명해진다.
 *
 * led_task 가 디바운스해서 쓰고, imu_task 가 읽는다.
 */
static bool s_button_down = false;

/* WiFi 설정이 저장돼 있는가. 안 붙었을 때 어떤 색으로 알릴지 가른다. */
static bool s_wifi_configured = false;

static inline uint32_t now_ms(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000);
}

/*
 * 하나 쌓았다고 기록한다. 여기서 세는 숫자는 오직 LED 밝기용이다.
 *
 * 상한에 닿아도 전송을 막지 않는다. 봉의 카운터와 채팅 입력창의 실제 개수는
 * 어긋날 수 있기 때문이다 — POST 가 한 번 실패하거나 확장이 잠깐 끊기면
 * 봉은 10을 셌는데 입력창에는 7개뿐인 상태가 된다. 그때 봉이 자기 숫자로
 * 막아버리면 흔들어도 아무 일도 일어나지 않고, 이유도 보이지 않는다.
 *
 * 진짜 상한은 확장이 안다. 입력창이 이미 가득 차 있으면 확장이 조용히
 * 거절하므로, 계속 보내는 쪽이 안전하다. 어긋나 있었다면 저절로 채워진다.
 *
 * 숫자만 QUEUE_MAX 에서 멈춘다. 밝기는 그 위로 올라갈 데가 없다.
 */
static void queue_note_add(void)
{
    portENTER_CRITICAL(&s_lock);
    if (s_sent_count < tuning_queue_max()) {
        s_sent_count++;
    }
    s_queue_added = true;
    portEXIT_CRITICAL(&s_lock);
}

/* 개수를 0 으로 되돌리고 직전 값을 반환한다 */
static int queue_reset(void)
{
    int n;
    portENTER_CRITICAL(&s_lock);
    n = s_sent_count;
    s_sent_count = 0;
    portEXIT_CRITICAL(&s_lock);
    return n;
}

/* ------------------------------------------------------------------------- */

static i2c_master_bus_handle_t init_i2c(void)
{
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port                     = IMU_I2C_PORT,
        .sda_io_num                   = IMU_SDA_GPIO,
        .scl_io_num                   = IMU_SCL_GPIO,
        .clk_source                   = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt            = 7,
        .flags.enable_internal_pullup = true,
    };

    i2c_master_bus_handle_t bus = NULL;
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &bus));

    /* 배선 문제를 빨리 잡을 수 있도록 부팅 시 한 번 스캔한다 */
    char found[96] = "";
    size_t off = 0;
    for (uint8_t addr = 0x08; addr < 0x78; addr++) {
        if (i2c_master_probe(bus, addr, 20) == ESP_OK && off < sizeof(found) - 8) {
            off += snprintf(found + off, sizeof(found) - off, "0x%02X ", addr);
        }
    }
    ESP_LOGI(TAG, "I2C 스캔 (SDA=%d SCL=%d): %s", IMU_SDA_GPIO, IMU_SCL_GPIO,
             off ? found : "(응답 없음)");

    return bus;
}

/* 캘리브레이션 동안 파란 링을 돌려서 "만지지 말라"는 신호를 준다 */
static void show_calibrating(void)
{
    static const int ring_x[] = { 2, 3, 4, 5, 5, 5, 4, 3, 2, 2 };
    static const int ring_y[] = { 2, 2, 2, 2, 3, 4, 5, 5, 5, 4 };
    const int n = sizeof(ring_x) / sizeof(ring_x[0]);

    matrix_clear();
    for (int i = 0; i < n; i++) {
        matrix_set(ring_x[i], ring_y[i], (rgb_t){ 0, 30, 90 });
    }
    matrix_flush();
}

/* ------------------------------------------------------------------------- */

static void imu_task(void *arg)
{
    qmi8658_dev_t *imu = (qmi8658_dev_t *)arg;

    gesture_config_t cfg;
    gesture_default_config(&cfg);
    gesture_engine_t *eng = gesture_create(&cfg, (float)IMU_SAMPLE_HZ);
    if (!eng) {
        ESP_LOGE(TAG, "제스처 엔진 생성 실패");
        vTaskDelete(NULL);
        return;
    }

    /* 이 뒤로 TUNE 명령이 엔진에 값을 바로 꽂는다 */
    tuning_attach(eng);

    const TickType_t period = pdMS_TO_TICKS(1000 / IMU_SAMPLE_HZ);
    TickType_t last_wake = xTaskGetTickCount();
    uint32_t log_tick = 0;
    uint32_t last_add_ms = 0;
    uint32_t gesture_start_ms = 0;   /* 지금 모션이 이어지기 시작한 시각 */
    uint32_t idle_since = 0;         /* IDLE 로 빠진 시각. 0이면 흔드는 중 */
    bool     armed = false;          /* 유지 시간을 채워 쌓기 시작했는지 */
    gesture_t prev_gesture = GESTURE_IDLE;
    int read_errors = 0;

    ESP_LOGI(TAG, "제스처 엔진 시작 (%dHz 샘플링)", IMU_SAMPLE_HZ);

    for (;;) {
        vTaskDelayUntil(&last_wake, period);

        qmi8658_data_t sample;
        if (qmi8658_read(imu, &sample) != ESP_OK) {
            if (++read_errors % 200 == 1) {
                ESP_LOGW(TAG, "IMU 읽기 실패 (누적 %d회)", read_errors);
            }
            continue;
        }

        const uint32_t t = now_ms();
        bool changed = false;
        gesture_t g = gesture_update(eng, &sample, t, &changed);

        bool btn_down;
        portENTER_CRITICAL(&s_lock);
        s_gesture   = g;
        s_intensity = gesture_intensity(eng);
        if (changed) {
            s_gesture_dirty = true;
        }
        btn_down = s_button_down;
        portEXIT_CRITICAL(&s_lock);

        /*
         * 버튼을 놓고 있는 동안은 쌓지 않는다.
         *
         * 모션 판정과 LED 는 그대로 돈다 — 흔들면 색이 바뀌는 재미는 남기고,
         * 입력창에 들어가는 것만 버튼으로 막는다. 쌓인 개수는 LED 밝기의
         * 바닥값으로 보이므로 버튼을 쥐어야 차오르는 것이 눈에 보인다.
         */
        if (!btn_down) {
            armed = false;
            prev_gesture = GESTURE_IDLE;
            idle_since = 0;
            goto render;
        }

        /*
         * 흔드는 동안 일정 간격으로 큐에 쌓는다.
         *
         * 제스처가 '바뀔 때'가 아니라 '유지되는 동안' 쌓아야 "흔들수록 쌓인다"가
         * 된다. 간격을 두지 않으면 200Hz 로 순식간에 가득 차버린다.
         */
        if (g == GESTURE_IDLE) {
            /*
             * 흔드는 도중에도 판정은 IDLE 로 잠깐씩 빠진다. 방향을 바꾸는
             * 순간에는 실제로 거의 멈추기 때문이다. 그 찰나마다 처음부터
             * 다시 세면 박자가 끊기고, 다시 붙는 순간 한 개가 곧바로 들어가서
             * 두 개가 잇달아 올라가는 것처럼 보인다.
             *
             * 그래서 짧은 공백은 흔들기가 이어지는 중으로 본다.
             */
            if (!idle_since) idle_since = t ? t : 1;
            if ((t - idle_since) >= (uint32_t)tuning_queue_gap_ms()) {
                armed = false;
                prev_gesture = GESTURE_IDLE;
            }
        } else {
            idle_since = 0;

            /* 다른 모션으로 바뀌면 유지 시간을 처음부터 다시 잰다 */
            if (g != prev_gesture) {
                prev_gesture = g;
                gesture_start_ms = t;
                armed = false;
            }

            /*
             * 같은 모션을 QUEUE_ARM_MS 동안 유지해야 쌓기 시작한다.
             * 봉을 집어들거나 자세를 고치는 우연한 움직임을 걸러낸다.
             *
             * 한 번 걸리고 나면 그 뒤로는 간격만 본다. 흔드는 동안에는
             * 정확히 1초에 하나씩 일정하게 올라간다.
             */
            if (!armed && (t - gesture_start_ms) >= (uint32_t)tuning_queue_arm_ms()) {
                armed = true;
                last_add_ms = t - (uint32_t)tuning_queue_add_ms();   /* 첫 개는 곧바로 */
            }
            if (armed && (t - last_add_ms) >= (uint32_t)tuning_queue_add_ms()) {
                last_add_ms = t;
                queue_note_add();
                /* 쏘고 잊는다. 실제 전송은 net 태스크가 맡는다. */
                net_post_event("add", gesture_name(g));
                ESP_LOGI(TAG, "add (%s) — 누적 %d", gesture_name(g), s_sent_count);
            }
        }

    render:
        if (changed) {
            gesture_features_t f;
            gesture_get_features(eng, &f);
            ESP_LOGI(TAG, "→ %-8s  V=%.2f H=%.2f peak=%.2f gyro=%.0f strokes=%d",
                     gesture_name(g), f.rms_vertical, f.rms_horizontal,
                     f.peak_linear, f.rms_gyro, f.strokes);
        }

#if GESTURE_TUNE_LOG
        /* 임계값 튜닝용 CSV — 시리얼 로그를 그대로 캡처해 플롯하면 된다 */
        if (++log_tick >= IMU_SAMPLE_HZ / 20) {
            log_tick = 0;
            gesture_features_t f;
            gesture_get_features(eng, &f);
            char line[128];
            snprintf(line, sizeof(line),
                     "TUNE,%lu,%s,%.3f,%.3f,%.3f,%.3f,%.1f,%d,%.1f,%.0f,%d,%d",
                     (unsigned long)t, gesture_name(g),
                     f.rms_vertical, f.rms_horizontal, f.rms_total,
                     f.peak_linear, f.rms_gyro, f.strokes, f.tilt_deg, matrix_current_ma(),
                     btn_down ? 1 : 0, s_sent_count);
            printf("%s\n", line);
            /* 개발자 빌드에서만. 배포 빌드에서는 빈 함수라 통째로 사라진다. */
            devlog_line(line);
        }
#else
        (void)log_tick;
#endif
    }
}

/*
 * WiFi 가 안 붙었을 때 화면 전체로 알린다.
 *
 * 봉은 확산 돔 안에 들어가 있어서 작은 아이콘이나 애니메이션은 보이지 않는다.
 * 그래서 색 하나로 말한다 — 팬이 전원만 꽂고 "왜 아무것도 안 나가지" 하며
 * 헤매지 않도록.
 *
 *   파랑   WiFi 설정이 아예 없다          → 설정 페이지를 열어야 한다
 *   주황   설정은 있는데 아직 못 붙었다    → 비밀번호나 공유기를 확인
 *
 * 붙고 나면 이 화면은 사라지고 평소 이펙트로 돌아간다.
 */
static void render_no_wifi(uint32_t t, bool configured)
{
    /* 2.4초 주기의 느린 숨쉬기. 깜빡이면 고장처럼 보여서 일부러 느리게 둔다. */
    const float ph = (float)(t % 2400) / 2400.0f;
    float k = 0.35f + 0.65f * (0.5f - 0.5f * cosf(ph * 2.0f * 3.14159265f));

    const rgb_t c = configured
        ? (rgb_t){ (uint8_t)(150 * k), (uint8_t)(62 * k), 0 }    /* 주황 */
        : (rgb_t){ 0, (uint8_t)(70 * k), (uint8_t)(160 * k) };   /* 파랑 */

    for (int y = 0; y < MATRIX_H; y++) {
        for (int x = 0; x < MATRIX_W; x++) matrix_set(x, y, c);
    }
}

/* 핀 하나가 눌린 상태인지 */
static bool button_is_down(int gpio)
{
    int level = gpio_get_level(gpio);
    return tuning_button_active_low() ? (level == 0) : (level != 0);
}

/*
 * 디바운스된 버튼 상태를 돌려준다. 상태가 막 바뀐 프레임에서만 *changed 가 true.
 *
 * 눌림만 보던 것을 뗌까지 보도록 바꿨다. 누르면 쌓기 시작하고 떼면 전송하므로
 * 양쪽 엣지가 모두 필요하다.
 */
static bool button_poll(uint32_t t, bool *changed)
{
    static bool stable = false;      /* 디바운스가 끝난 상태 */
    static bool raw_prev = false;
    static uint32_t change_ms = 0;

    *changed = false;

    /* 납땜한 버튼과 내장 BOOT 버튼 중 아무거나 */
    bool raw = button_is_down(tuning_button_gpio()) || button_is_down(BUTTON_ONBOARD_GPIO);

    if (raw != raw_prev) {
        raw_prev = raw;
        change_ms = t;               /* 흔들림이 멎을 때까지 기다린다 */
        return stable;
    }
    if (raw != stable && (t - change_ms) >= (uint32_t)tuning_button_debounce_ms()) {
        stable = raw;
        *changed = true;
    }
    return stable;
}

static void handle_flush(uint32_t t)
{
    const int n = queue_reset();

    /*
     * 봉이 센 개수가 0이어도 보낸다. 봉이 재부팅됐거나 POST 가 몇 개
     * 어긋났으면 봉은 0인데 입력창에는 이모티콘이 남아 있을 수 있다.
     * 그때 버튼이 안 먹으면 손으로 지우는 수밖에 없다.
     *
     * 입력창이 정말 비어 있으면 확장이 알아서 거절한다. 개수를 아는 쪽은
     * 언제나 입력창이지 봉이 아니다.
     */
    net_post_event("send", NULL);
    ESP_LOGI(TAG, "전송 (봉이 센 개수 %d)", n);
    led_effect_on_flush(t);
}

/*
 * 버튼 핀을 입력으로 잡는다.
 *
 * 핀 번호를 실행 중에 바꿀 수 있어서(TUNE btn_gpio) 다시 부를 수 있게
 * 떼어 뒀다. 어느 패드에 납땜했는지 모를 때 굽지 않고 찾아볼 수 있다.
 */
static void apply_button_pins(void)
{
    const bool low = tuning_button_active_low();
    const gpio_config_t btn_cfg = {
        .pin_bit_mask = (1ULL << tuning_button_gpio()) | (1ULL << BUTTON_ONBOARD_GPIO),
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = low ? GPIO_PULLUP_ENABLE : GPIO_PULLUP_DISABLE,
        .pull_down_en = low ? GPIO_PULLDOWN_DISABLE : GPIO_PULLDOWN_ENABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&btn_cfg));
    ESP_LOGI(TAG, "전송 버튼: GPIO%d (납땜) / GPIO%d (내장) — 눌림=%s",
             tuning_button_gpio(), BUTTON_ONBOARD_GPIO, low ? "LOW" : "HIGH");
}

/* TUNE btn_gpio 로 핀이 바뀌면 불린다 */
static void on_button_pin_changed(int old_gpio, int new_gpio)
{
    ESP_LOGI(TAG, "버튼 핀 GPIO%d → GPIO%d", old_gpio, new_gpio);
    if (old_gpio != BUTTON_ONBOARD_GPIO) gpio_reset_pin((gpio_num_t)old_gpio);
    apply_button_pins();
}

static void led_task(void *arg)
{
    (void)arg;

    apply_button_pins();
    tuning_set_button_cb(on_button_pin_changed);

    const TickType_t period = pdMS_TO_TICKS(1000 / LED_FRAME_HZ);
    TickType_t last_wake = xTaskGetTickCount();
    uint32_t last_status_ms = 0;

    for (;;) {
        vTaskDelayUntil(&last_wake, period);

        const uint32_t t = now_ms();
        power_tick(t);

        /*
         * 봉이 살아 있다고 주기적으로 알린다.
         *
         * 팬은 봉을 보조배터리에만 꽂아둘 테니, 시리얼로만 상태를 볼 수 있으면
         * 사실상 볼 수 없는 것과 같다. 서버를 거쳐 설정 페이지에 뜨게 한다.
         *
         * WiFi 가 없으면 net 쪽에서 알아서 버리므로 여기서 따로 확인하지 않는다.
         */
        if (!last_status_ms || (t - last_status_ms) >= STATUS_REPORT_MS) {
            last_status_ms = t ? t : 1;
            int n;
            portENTER_CRITICAL(&s_lock);
            n = s_sent_count;
            portEXIT_CRITICAL(&s_lock);
            net_post_status(n);
        }

        bool btn_changed;
        const bool btn_down = button_poll(t, &btn_changed);
        if (btn_changed) {
            portENTER_CRITICAL(&s_lock);
            s_button_down = btn_down;
            portEXIT_CRITICAL(&s_lock);

            if (btn_down) {
                ESP_LOGI(TAG, "버튼 눌림 — 흔드는 대로 쌓는다");
            } else {
                handle_flush(t);     /* 떼면 전송 */
            }
        }

        gesture_t g;
        float intensity;
        bool changed, added;
        int qcount;

        portENTER_CRITICAL(&s_lock);
        g = s_gesture;
        intensity = s_intensity;
        changed = s_gesture_dirty;
        s_gesture_dirty = false;
        added = s_queue_added;
        s_queue_added = false;
        qcount = s_sent_count;
        portEXIT_CRITICAL(&s_lock);

        if (changed) {
            /* 이펙트가 서로 번지지 않도록 전환 시 프레임버퍼를 비운다 */
            matrix_clear();
            led_effect_on_gesture_change(g, t);
        }
        if (added) {
            led_effect_on_queue_add(t);
        }

        const led_queue_view_t view = {
            .count = qcount,
            .capacity = tuning_queue_max(),
        };

        /*
         * WiFi 가 안 붙어 있으면 그걸 먼저 알린다. 이 상태에서는 흔들어도
         * 서버로 아무것도 못 가므로, 평소 이펙트를 보여주면 잘 되는 줄 안다.
         */
        if (!net_is_connected()) {
            matrix_clear();
            render_no_wifi(t, s_wifi_configured);
        } else {
            led_effect_render(g, intensity, t, &view);
        }
        matrix_flush();
    }
}

/* ------------------------------------------------------------------------- */

/* 시리얼로 설정이 바뀌면 WiFi 를 다시 붙인다 */
static void on_settings_changed(const settings_t *s)
{
    if (s) s_wifi_configured = settings_has_wifi(s);
    net_reconnect(s);
    ota_settings_changed(s);
    devlog_settings_changed(s);
}

void app_main(void)
{
    ESP_LOGI(TAG, "크라운 응원봉 부팅");

    ESP_ERROR_CHECK(settings_init());
    power_init();          /* matrix 보다 먼저 — 첫 프레임부터 예산이 적용된다 */
    ESP_ERROR_CHECK(matrix_init());

    i2c_master_bus_handle_t bus = init_i2c();

    qmi8658_dev_t *imu = NULL;
    esp_err_t err = qmi8658_create(bus, &imu);
    if (err != ESP_OK) {
        /* IMU가 없어도 벽돌이 되지는 않게 — 빨간 화면으로 고장을 알린다 */
        ESP_LOGE(TAG, "IMU 초기화 실패 (%s). 배선/핀 설정을 확인하세요.", esp_err_to_name(err));
        for (;;) {
            matrix_clear();
            for (int i = 0; i < MATRIX_W; i++) {
                matrix_set(i, i, (rgb_t){ 120, 0, 0 });
                matrix_set(MATRIX_W - 1 - i, i, (rgb_t){ 120, 0, 0 });
            }
            matrix_flush();
            vTaskDelay(pdMS_TO_TICKS(500));
            matrix_clear();
            matrix_flush();
            vTaskDelay(pdMS_TO_TICKS(500));
        }
    }

    /*
     * 정지 상태를 확인할 때까지 캘리브레이션을 반복한다.
     *
     * 단순히 바이어스 정확도 때문만이 아니다. 제스처 엔진은 부팅 직후
     * 0.4초 평균으로 중력 방향을 잡는데, 그때 이미 흔들고 있으면 원심
     * 가속도가 섞여 초기 방향이 크게 틀어진다. 그 뒤로는 흔드는 동안
     * 보정 게이트가 닫혀 있어 회복에 수 초가 걸리고, 그동안 좌우와 상하가
     * 뒤바뀌어 보인다. 정지 상태에서 출발하는 것이 가장 확실한 예방책이다.
     */
    ESP_LOGI(TAG, "자이로 캘리브레이션 — 봉을 가만히 두세요");
    for (int attempt = 1; ; attempt++) {
        show_calibrating();
        esp_err_t cal = qmi8658_calibrate_gyro(imu, 200);
        if (cal == ESP_OK) {
            break;
        }
        if (attempt >= 10) {
            ESP_LOGW(TAG, "정지 상태를 확인하지 못했습니다 — 그대로 진행합니다");
            break;
        }
        ESP_LOGI(TAG, "움직임이 감지되어 다시 시도합니다 (%d회)", attempt);
        /* 재시도 사이에 매트릭스를 한 번 깜빡여서 대기 중임을 보여준다 */
        matrix_clear();
        matrix_flush();
        vTaskDelay(pdMS_TO_TICKS(200));
    }

    matrix_clear();
    matrix_flush();

    /*
     * 네트워크와 시리얼 콘솔을 올린다.
     *
     * WiFi 설정이 아직 없어도 실패로 보지 않는다. 팬이 시리얼로 넣어줄
     * 때까지 봉은 그냥 이펙트만 돌리며 기다리면 된다.
     */
    ESP_ERROR_CHECK(net_init());

    settings_t cfg;
    settings_load(&cfg);
    s_wifi_configured = settings_has_wifi(&cfg);
    net_start(&cfg);
    ota_start(&cfg);
    devlog_start(&cfg);

    console_set_changed_cb(on_settings_changed);
    console_start();

    if (!settings_has_wifi(&cfg)) {
        ESP_LOGW(TAG, "WiFi 미설정 — 확장 설정 페이지에서 등록하세요");
    }

    /* IMU는 코어1에 고정해서 Wi-Fi/시스템 작업과 타이밍이 겹치지 않게 한다 */
    xTaskCreatePinnedToCore(imu_task, "imu", 4096, imu, 6, NULL, 1);
    xTaskCreatePinnedToCore(led_task, "led", 4096, NULL, 4, NULL, 0);
}
