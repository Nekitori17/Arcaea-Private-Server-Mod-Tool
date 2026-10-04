#pragma once

#include <stddef.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CONFIG_MAX_PATH 512
#define CONFIG_MAX_FALLBACKS 8

/* Returns detected package name from /proc/self/cmdline. */
int config_resolver_get_package_name(char *out_buf, size_t max_len);

/* Registers an extra fallback package for config lookup. */
int config_resolver_add_fallback_package(const char *package_name);

/*
 * Resolves full path for a config filename (e.g. "domain.cfg").
 * Searches internal data dirs, registered fallback packages, and storage.
 * Returns 1 if accessible, 0 if resolved to default fallback path.
 */
int config_resolver_resolve_path(const char *filename, char *out_path, size_t out_size);

/* Resolves and opens a config file in given mode ("r", etc.). Returns NULL on failure. */
FILE *config_resolver_open(const char *filename, const char *mode);

#ifdef __cplusplus
}
#endif
