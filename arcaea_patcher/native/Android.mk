LOCAL_PATH := $(call my-dir)

include $(CLEAR_VARS)

LOCAL_MODULE := neki
LOCAL_SRC_FILES := Main.c \
	core/HookEngine.c \
	core/RouteCache.c \
	hooks/DomainRedirectHook.c \
	hooks/SSLPinningHook.c \
	utils/MemoryUtils.c \
	utils/DomainParser.c \
	utils/FileUtils.c

LOCAL_C_INCLUDES := $(LOCAL_PATH) $(LOCAL_PATH)/core $(LOCAL_PATH)/hooks $(LOCAL_PATH)/utils
										
LOCAL_LDLIBS := -llog -ldl
LOCAL_CFLAGS := -Wall -Wextra -O2 -fPIC -DANDROID -Wno-unused-parameter

include $(BUILD_SHARED_LIBRARY)
