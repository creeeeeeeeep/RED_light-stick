idf_component_register(
    SRCS "main.c"
         "qmi8658.c"
         "ws2812_matrix.c"
         "gesture.c"
         "led_effect.c"
         "settings.c"
         "net.c"
         "console.c"
         "ota.c"
         "devlog.c"
         "power.c"
    INCLUDE_DIRS "."
    REQUIRES driver esp_timer nvs_flash esp_wifi esp_netif esp_event
             esp_http_client esp_https_ota app_update esp_app_format json mbedtls
)

target_compile_options(${COMPONENT_LIB} PRIVATE -ffast-math)
