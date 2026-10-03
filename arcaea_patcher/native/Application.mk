APP_ABI := armeabi-v7a arm64-v8a
APP_PLATFORM := android-21
APP_BUILD_SCRIPT := Android.mk
APP_OPTIM := release
APP_CFLAGS := -Oz -flto -ffunction-sections -fdata-sections -fvisibility=hidden -DNDEBUG
APP_LDFLAGS := -flto -Wl,--gc-sections -Wl,--icf=all -Wl,-s
APP_STRIP_MODE := --strip-all
