#include <jni.h>
#include <stddef.h>

#include "ConfigResolver.h"
#include "DomainConfig.h"
#include "DomainRedirectHook.h"
#include "HookManager.h"
#include "SslPinningHook.h"

#define LOG_MODULE_TAG "Main"
#include "Logger.h"

#define TARGET_LIB "libcocos2dcpp.so"
#define CONFIG_FILE "domain.cfg"

JNIEXPORT void JNICALL Java_moe_neki_arc_NekiLoader_nativeInit(JNIEnv *env,
                                                               jclass clazz) {
  char cfg_path[CONFIG_MAX_PATH] = {0};
  int found;
  (void)env;
  (void)clazz;

  LOGI("nativeInit (NekiLoader) -> resolving config and registering hooks");

  found = config_resolver_resolve_path(CONFIG_FILE, cfg_path, sizeof(cfg_path));
  LOGI("Domain config: %s (exists=%d)", cfg_path, found);

  domain_config_load_file(cfg_path);
  if (domain_config_count() == 0)
    LOGW("No redirect rules loaded; running as SSL-bypass-only");

  hook_manager_register(domain_redirect_get_module());
  hook_manager_register(ssl_pinning_get_module());

  hook_manager_init(TARGET_LIB);
}

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
  (void)vm;
  (void)reserved;
  LOGI("libneki.so JNI_OnLoad");
  return JNI_VERSION_1_6;
}
