#pragma once

#ifdef __cplusplus
extern "C" {
#endif

#define HOOK_MAX_MODULES 16

typedef void (*hook_install_fn)(void *module_base);

typedef struct {
  const char *name;
  hook_install_fn install;
} HookModule;

/* Registers a hook module. Returns 1 on success, 0 on failure. */
int hook_manager_register(const HookModule *module);

/* Invokes install callbacks for all registered modules on module_base. */
void hook_manager_install_all(void *module_base);

/* Watches for target library load and installs registered hooks. */
int hook_manager_init(const char *target_library);

#ifdef __cplusplus
}
#endif
