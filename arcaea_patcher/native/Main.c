#include <jni.h>
#include <stddef.h>

#include "core/HookEngine.h"
#include "utils/DomainParser.h"

#define LOG_MODULE_TAG "Main"
#include "utils/Logger.h"

JNIEXPORT void JNICALL Java_moe_neki_arc_NekiLoader_nativeInit(JNIEnv *env,
                                                               jclass clazz) {
  const char *cfg;
  (void)env;
  (void)clazz;
  LOGI("nativeInit (NekiLoader) -> loading domain.cfg + installing hooks");
  cfg = domain_resolve_config_path();
  LOGI("Using domain config: %s", cfg ? cfg : "(null)");
  domain_load(cfg);
  if (domain_count() == 0)
    LOGW("No redirect rules; running as SSL-bypass-only");
  hook_engine_install_all();
}

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
  (void)vm;
  (void)reserved;
  LOGI("libneki.so JNI_OnLoad");
  return JNI_VERSION_1_6;
}
