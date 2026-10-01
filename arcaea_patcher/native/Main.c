#include <jni.h>
#include <stddef.h>

#include "core/HookEngine.h"
#include "hooks/DomainRedirectHook.h"
#include "hooks/SSLPinningHook.h"
#include "utils/DomainParser.h"
#include "utils/FileUtils.h"

#define LOG_MODULE_TAG "Main"
#include "utils/Logger.h"

#define TARGET_LIB "libcocos2dcpp.so"

/* Runs once, on the thread that first sees TARGET_LIB loaded. */
static void install_hooks_into(void *module_base) {
  domain_redirect_install(module_base);
  ssl_pinning_install(module_base);
}

JNIEXPORT void JNICALL Java_moe_neki_arc_NekiLoader_nativeInit(JNIEnv *env,
                                                               jclass clazz) {
  const char *cfg;
  int rc;
  (void)env;
  (void)clazz;
  LOGI("nativeInit (NekiLoader) -> loading domain.cfg + installing hooks");
  cfg = file_resolve_domain_config_path();
  LOGI("Using domain config: %s", cfg ? cfg : "(null)");
  domain_load(cfg);
  if (domain_count() == 0)
    LOGW("No redirect rules; running as SSL-bypass-only");
  rc = hook_engine_install_when_loaded(TARGET_LIB, install_hooks_into);
  if (rc == 0)
    LOGW("Hooks deferred until %s is loaded", TARGET_LIB);
  else if (rc < 0)
    LOGE("Hook engine could not start");
}

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
  (void)vm;
  (void)reserved;
  LOGI("libneki.so JNI_OnLoad");
  return JNI_VERSION_1_6;
}
