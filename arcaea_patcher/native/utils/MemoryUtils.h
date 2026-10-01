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

#ifdef __cplusplus
}
#endif
