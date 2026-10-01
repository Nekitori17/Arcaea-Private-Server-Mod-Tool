#include "HookEngine.h"

#include <pthread.h>
#include <stddef.h>
#include <unistd.h>

#include "DomainRedirectHook.h"
#include "MemoryUtils.h"
#include "SSLPinningHook.h"

#define LOG_MODULE_TAG "Engine"
#include "Logger.h"

#define TARGET_LIB "libcocos2dcpp.so"

static pthread_mutex_t s_lock = PTHREAD_MUTEX_INITIALIZER;
static int s_installed = 0;

int hook_engine_install_for(void *module_base) {
  if (!module_base)
    return 0;
  pthread_mutex_lock(&s_lock);
  if (s_installed) {
    pthread_mutex_unlock(&s_lock);
    LOGI("Hooks already installed; skipping");
    return 1;
  }
  LOGI("Installing PLT hooks into %s @ %p", TARGET_LIB, module_base);
  domain_redirect_install(module_base);
  ssl_pinning_install(module_base);
  s_installed = 1;
  pthread_mutex_unlock(&s_lock);
  LOGI("Hook install pass finished");
  return 1;
}

/* Retry thread: libcocos may load AFTER nativeInit (onCreate race). */
static void *retry_thread(void *arg) {
  int tries = 0;
  (void)arg;
  for (tries = 0; tries < 50; tries++) {
    void *base = mem_get_module_base(TARGET_LIB);
    if (base) {
      hook_engine_install_for(base);
      return NULL;
    }
    usleep(200 * 1000);
  }
  LOGE("Gave up waiting for %s after ~10s", TARGET_LIB);
  return NULL;
}

int hook_engine_install_all(void) {
  void *base = mem_get_module_base(TARGET_LIB);
  pthread_t tid;
  if (base)
    return hook_engine_install_for(base);
  LOGW("%s not loaded yet; retrying in background (~10s)", TARGET_LIB);
  if (pthread_create(&tid, NULL, retry_thread, NULL) == 0)
    pthread_detach(tid);
  else
    LOGE("Failed to spawn hook retry thread");
  return 0;
}
