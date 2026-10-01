#pragma once

#include <android/log.h>

// ---------------------------------------------------------------------------
// Tagged logging for libneki.so
// Format: [NekiHook::Tag] message  (logcat tag = "NekiHook::Tag")
// Usage:
//   #define LOG_MODULE_TAG "Main"
//   #include "Logger.h"
//   LOGI("hello %s", "world");
// ---------------------------------------------------------------------------

#ifndef APP_LOG_PREFIX
#define APP_LOG_PREFIX "NekiHook"
#endif

#ifndef LOG_MODULE_TAG
#define LOG_MODULE_TAG "General"
#endif

#define LOGD(...) \
    __android_log_print(ANDROID_LOG_DEBUG, APP_LOG_PREFIX "::" LOG_MODULE_TAG, __VA_ARGS__)
#define LOGI(...) \
    __android_log_print(ANDROID_LOG_INFO, APP_LOG_PREFIX "::" LOG_MODULE_TAG, __VA_ARGS__)
#define LOGW(...) \
    __android_log_print(ANDROID_LOG_WARN, APP_LOG_PREFIX "::" LOG_MODULE_TAG, __VA_ARGS__)
#define LOGE(...) \
    __android_log_print(ANDROID_LOG_ERROR, APP_LOG_PREFIX "::" LOG_MODULE_TAG, __VA_ARGS__)

