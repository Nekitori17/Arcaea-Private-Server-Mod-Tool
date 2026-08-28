LOCAL_PATH := $(call my-dir)

include $(CLEAR_VARS)

LOCAL_MODULE := neki
LOCAL_SRC_FILES := neki_hook.c
LOCAL_LDLIBS := -llog
LOCAL_CFLAGS := -Wall -Wextra -O2

include $(BUILD_SHARED_LIBRARY)
