#pragma once

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*hook_installer_fn)(void *module_base);

/*
 * Executes install_fn when module_name is loaded.
 * Returns 1 if loaded and installed, 0 if deferred to background retry thread, -1 on error.
 */
int hook_engine_install_when_loaded(const char *module_name,
                                    hook_installer_fn install_fn);

/*
 * Replaces the GOT/PLT entry for symbol_name in module_base.
 * Saves previous pointer into *orig_func (if provided). Returns 0 on success, -1 on failure.
 */
int plt_hook_symbol(void *module_base, const char *symbol_name,
                    void *hook_func, void **orig_func);

#ifdef __cplusplus
}
#endif
