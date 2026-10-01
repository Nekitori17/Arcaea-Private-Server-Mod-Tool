#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/* Called with the resolved load base of a module once it is available. */
typedef void (*hook_installer_fn)(void *module_base);

/*
 * Runs `install_fn` as soon as `module_name` is loaded:
 *   - returns 1 when the module is mapped and the installer ran now (or had
 *     already run before);
 *   - returns 0 when the module is not loaded yet; a detached thread keeps
 *     retrying for ~10s and runs the installer later;
 *   - returns -1 on invalid arguments / thread failure.
 * The installer runs at most once even when called concurrently.
 * `module_name` must stay valid (static storage) until install_fn has run.
 */
int hook_engine_install_when_loaded(const char *module_name,
                                    hook_installer_fn install_fn);

/*
 * Overwrites the GOT/PLT slot for `symbol_name` inside `module_base`.
 * On success stores the previous value into *orig_func (if non-NULL and
 * *orig_func is NULL) and returns 0. When the GOT slot still points at a
 * lazy-binding resolver stub inside the module, dlsym() is used as the
 * original instead. Returns -1 when the symbol is not found in the PLT
 * relocation tables (common for statically linked OpenSSL).
 */
int plt_hook_symbol(void *module_base, const char *symbol_name,
                    void *hook_func, void **orig_func);

#ifdef __cplusplus
}
#endif
