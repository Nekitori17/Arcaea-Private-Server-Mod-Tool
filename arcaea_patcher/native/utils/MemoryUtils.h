#pragma once

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Base load address of a module from /proc/self/maps, or NULL if unmapped. */
void *mem_get_module_base(const char *module_name);

/* Total mapped virtual size of a module, or 0 if unmapped. */
size_t mem_get_module_size(const char *module_name);

/* Sets page protection to RW (or RWX fallback) for [addr, addr+size). Returns 0 on success. */
int mem_make_writable(void *addr, size_t size);

#ifdef __cplusplus
}
#endif
