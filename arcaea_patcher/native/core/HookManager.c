#include "HookManager.h"

#include <stddef.h>

#include "HookEngine.h"

#define LOG_MODULE_TAG "Manager"
#include "Logger.h"

static const HookModule *s_modules[HOOK_MAX_MODULES];
static size_t s_module_count = 0;

int hook_manager_register(const HookModule *module) {
  if (!module || !module->install || s_module_count >= HOOK_MAX_MODULES) {
    LOGE("Failed to register hook module '%s'", module ? module->name : "(null)");
    return 0;
  }
  s_modules[s_module_count++] = module;
  LOGI("Registered hook module: %s (%zu total)", module->name ? module->name : "unnamed",
       s_module_count);
  return 1;
}

void hook_manager_install_all(void *module_base) {
  size_t i;
  if (!module_base)
    return;
  LOGI("Executing install for %zu registered hook module(s)...", s_module_count);
  for (i = 0; i < s_module_count; i++) {
    const HookModule *m = s_modules[i];
    if (m && m->install) {
      LOGI("Installing module [%zu/%zu]: %s", i + 1, s_module_count,
           m->name ? m->name : "unnamed");
      m->install(module_base);
    }
  }
  LOGI("All hook modules installed");
}

int hook_manager_init(const char *target_library) {
  int rc;
  if (!target_library || !target_library[0])
    return -1;
  rc = hook_engine_install_when_loaded(target_library, hook_manager_install_all);
  if (rc == 0)
    LOGW("Hooks deferred until %s is loaded", target_library);
  else if (rc < 0)
    LOGE("Hook engine failed to initialize for %s", target_library);
  return rc;
}
