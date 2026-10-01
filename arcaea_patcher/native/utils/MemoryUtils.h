#pragma once

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Returns the base load address of a loaded module, or NULL if not found. */
void *mem_get_module_base(const char *module_name);

/* Returns the total mapped size (bounding box) of a module, or 0 if unknown. */
size_t mem_get_module_size(const char *module_name);

/*
 * Makes [addr, addr+size) writable (tries READ|WRITE first for Android 15 W^X,
 * falls back to READ|WRITE|EXEC). Returns 0 on success, -1 on failure.
 */
int mem_make_writable(void *addr, size_t size);

/*
 * Overwrites the GOT/PLT slot for `symbol_name` inside `module_base`.
 * On success stores the previous value into *orig_func (if non-NULL and
 * *orig_func is NULL) and returns 0. Returns -1 when the symbol is not
 * found in the PLT relocation tables (common for statically linked OpenSSL).
 */
int plt_hook_symbol(void *module_base, const char *symbol_name,
                    void *hook_func, void **orig_func);

#ifdef __cplusplus
}
#endif

