#include "MemoryUtils.h"

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define LOG_MODULE_TAG "Memory"
#include "Logger.h"

/* Matches exact module name in /proc/self/maps path to prevent substring false positives. */
static int line_matches_module(const char *line, const char *module_name) {
  size_t name_len;
  const char *p;
  if (!line || !module_name || module_name[0] == '\0')
    return 0;
  name_len = strlen(module_name);
  p = strstr(line, module_name);
  while (p != NULL) {
    int left_ok = (p == line) || (p[-1] == '/');
    const char *after = p + name_len;
    int right_ok = (*after == '\0' || *after == ' ' || *after == '\t' ||
                    *after == '\n' || *after == '-' || *after == ':');
    if (left_ok && right_ok)
      return 1;
    if (left_ok && *after == '.' && strncmp(after, ".so", 3) == 0 &&
        (after[3] == '\0' || after[3] == ' ' || after[3] == '\t' || after[3] == '\n'))
      return 1;
    p = strstr(p + 1, module_name);
  }
  return 0;
}

void *mem_get_module_base(const char *module_name) {
  FILE *fp;
  char line[640];
  void *base = NULL;
  if (!module_name || module_name[0] == '\0')
    return NULL;
  fp = fopen("/proc/self/maps", "r");
  if (!fp) {
    LOGE("Failed to open /proc/self/maps (errno=%d)", errno);
    return NULL;
  }
  while (fgets(line, sizeof(line), fp)) {
    if (line_matches_module(line, module_name)) {
      unsigned long long start = 0, offset = 0;
      char perms[5] = {0};
      if (sscanf(line, "%llx-%*llx %4s %llx", &start, perms, &offset) == 3) {
        if (offset == 0 && start != 0) {
          base = (void *)(uintptr_t)start;
          break;
        }
      }
    }
  }
  fclose(fp);
  if (base)
    LOGI("Module %s base=%p", module_name, base);
  else
    LOGW("Module %s not found in maps", module_name);
  return base;
}

size_t mem_get_module_size(const char *module_name) {
  FILE *fp;
  char line[640];
  uintptr_t lo = 0, hi = 0;
  if (!module_name || !module_name[0])
    return 0;
  fp = fopen("/proc/self/maps", "r");
  if (!fp)
    return 0;
  while (fgets(line, sizeof(line), fp)) {
    if (line_matches_module(line, module_name)) {
      unsigned long long s = 0, e = 0;
      if (sscanf(line, "%llx-%llx", &s, &e) == 2) {
        if (lo == 0 || (uintptr_t)s < lo)
          lo = (uintptr_t)s;
        if ((uintptr_t)e > hi)
          hi = (uintptr_t)e;
      }
    }
  }
  fclose(fp);
  return (hi > lo) ? (size_t)(hi - lo) : 0;
}

int mem_make_writable(void *addr, size_t size) {
  long page_size;
  uintptr_t page_start;
  size_t total;
  int ret;
  if (!addr || size == 0)
    return -1;
  page_size = sysconf(_SC_PAGESIZE);
  if (page_size <= 0)
    page_size = 4096;
  page_start = (uintptr_t)addr & ~((uintptr_t)page_size - 1);
  total = (((uintptr_t)addr + size - page_start + (size_t)page_size - 1) /
           (size_t)page_size) *
          (size_t)page_size;
  ret = mprotect((void *)page_start, total, PROT_READ | PROT_WRITE);
  if (ret != 0) {
    ret = mprotect((void *)page_start, total, PROT_READ | PROT_WRITE | PROT_EXEC);
    if (ret != 0)
      LOGE("mprotect failed %p size=%zu errno=%d", addr, size, errno);
  }
  return ret;
}
