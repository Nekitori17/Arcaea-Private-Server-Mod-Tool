#include "ConfigResolver.h"

#include <stdio.h>
#include <string.h>

#include "FileUtils.h"

#define LOG_MODULE_TAG "Config"
#include "Logger.h"

static const char *s_default_pkgs[] = {"moe.neki.arc", "moe.low.arc"};
static char s_custom_fallbacks[CONFIG_MAX_FALLBACKS][128];
static size_t s_custom_fallback_count = 0;

int config_resolver_get_package_name(char *out_buf, size_t max_len) {
  return file_read_proc_cmdline(out_buf, max_len);
}

int config_resolver_add_fallback_package(const char *package_name) {
  if (!package_name || !package_name[0] || s_custom_fallback_count >= CONFIG_MAX_FALLBACKS)
    return 0;
  strncpy(s_custom_fallbacks[s_custom_fallback_count], package_name,
          sizeof(s_custom_fallbacks[0]) - 1);
  s_custom_fallbacks[s_custom_fallback_count][sizeof(s_custom_fallbacks[0]) - 1] = '\0';
  s_custom_fallback_count++;
  return 1;
}

int config_resolver_resolve_path(const char *filename, char *out_path, size_t out_size) {
  char pkg[128] = {0};
  char candidate[CONFIG_MAX_PATH];
  size_t i;

  if (!filename || !filename[0] || !out_path || out_size == 0)
    return 0;

  /* 1. Try detected package name from /proc/self/cmdline */
  if (config_resolver_get_package_name(pkg, sizeof(pkg)) && pkg[0]) {
    snprintf(candidate, sizeof(candidate), "/data/user/0/%s/files/%s", pkg, filename);
    if (file_exists(candidate)) {
      strncpy(out_path, candidate, out_size - 1);
      out_path[out_size - 1] = '\0';
      return 1;
    }
    snprintf(candidate, sizeof(candidate), "/data/data/%s/files/%s", pkg, filename);
    if (file_exists(candidate)) {
      strncpy(out_path, candidate, out_size - 1);
      out_path[out_size - 1] = '\0';
      return 1;
    }
  }

  /* 2. Try default well-known packages */
  for (i = 0; i < sizeof(s_default_pkgs) / sizeof(s_default_pkgs[0]); i++) {
    snprintf(candidate, sizeof(candidate), "/data/user/0/%s/files/%s", s_default_pkgs[i], filename);
    if (file_exists(candidate)) {
      strncpy(out_path, candidate, out_size - 1);
      out_path[out_size - 1] = '\0';
      return 1;
    }
    snprintf(candidate, sizeof(candidate), "/data/data/%s/files/%s", s_default_pkgs[i], filename);
    if (file_exists(candidate)) {
      strncpy(out_path, candidate, out_size - 1);
      out_path[out_size - 1] = '\0';
      return 1;
    }
  }

  /* 3. Try dynamically added fallback packages */
  for (i = 0; i < s_custom_fallback_count; i++) {
    snprintf(candidate, sizeof(candidate), "/data/user/0/%s/files/%s", s_custom_fallbacks[i], filename);
    if (file_exists(candidate)) {
      strncpy(out_path, candidate, out_size - 1);
      out_path[out_size - 1] = '\0';
      return 1;
    }
  }

  /* Fallback: format default path under primary package */
  if (pkg[0]) {
    snprintf(out_path, out_size, "/data/user/0/%s/files/%s", pkg, filename);
  } else {
    snprintf(out_path, out_size, "/data/user/0/moe.neki.arc/files/%s", filename);
  }
  return 0;
}

FILE *config_resolver_open(const char *filename, const char *mode) {
  char path[CONFIG_MAX_PATH];
  if (!filename || !filename[0] || !mode || !mode[0])
    return NULL;
  config_resolver_resolve_path(filename, path, sizeof(path));
  return fopen(path, mode);
}
