#include "MemoryUtils.h"

#include <elf.h>
#include <errno.h>
#include <link.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define LOG_MODULE_TAG "Memory"
#include "Logger.h"

/* Strict match: "libfoo.so" must not match "libfoobar.so". */
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
    if (left_ok && right_ok) {
      if (*after == '\0' || *after == ' ' || *after == '\t' || *after == '\n')
        return 1;
      /* Accept "libfoo.so" + end/space, reject "libfoobar.so". */
      if (*after == '-' || *after == ':')
        return 1;
    }
    /* Extra guard for ".so" boundary: allow "X.so" but not "X.soY". */
    if (left_ok && *after == '.' && strncmp(after, ".so", 3) == 0 &&
        (after[3] == '\0' || after[3] == ' ' || after[3] == '\t' ||
         after[3] == '\n'))
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
    LOGW("Module %s not found in maps (yet)", module_name);
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
    ret =
        mprotect((void *)page_start, total, PROT_READ | PROT_WRITE | PROT_EXEC);
    if (ret != 0)
      LOGE("mprotect failed %p size=%zu errno=%d", addr, size, errno);
  }
  return ret;
}
/* load_bias = runtime_base - min_vaddr; handles absolute VA and RVA. */
static uint8_t *dyn_resolve(void *base, uintptr_t load_bias, ElfW(Addr) v) {
  uintptr_t uv = (uintptr_t)v;
  uintptr_t b = (uintptr_t)base;
  if (uv >= b && uv < b + 256u * 1024u * 1024u)
    return (uint8_t *)uv;
  return (uint8_t *)(uv + load_bias);
}

static int hook_rela(void *base, uintptr_t bias, void *rel, size_t sz,
                     const char *want, ElfW(Sym) * sym, const char *str,
                     size_t strsz, void *fn, void **orig) {
  ElfW(Rela) *a = (ElfW(Rela) *)rel;
  size_t n = sz / sizeof(ElfW(Rela));
  size_t k;
  if (n > 100000) {
    return -2;
  }
  for (k = 0; k < n; k++) {
#if defined(__LP64__)
    uint32_t id = (uint32_t)ELF64_R_SYM(a[k].r_info);
#else
    uint32_t id = (uint32_t)ELF32_R_SYM(a[k].r_info);
#endif
    void **slot;
    if (sym[id].st_name >= strsz)
      continue;
    if (strcmp(str + sym[id].st_name, want) != 0)
      continue;
    slot = (void **)dyn_resolve(base, bias, (ElfW(Addr))a[k].r_offset);
    if (mem_make_writable(slot, sizeof(void *)) != 0)
      return -1;
    if (orig && *orig == NULL)
      *orig = *slot;
    *slot = fn;
    __builtin___clear_cache((char *)slot, (char *)slot + sizeof(void *));
    return 1;
  }
  return 0;
}

static int hook_rel(void *base, uintptr_t bias, void *rel, size_t sz,
                    const char *want, ElfW(Sym) * sym, const char *str,
                    size_t strsz, void *fn, void **orig) {
  ElfW(Rel) *r = (ElfW(Rel) *)rel;
  size_t n = sz / sizeof(ElfW(Rel));
  size_t k;
  if (n > 100000) {
    return -2;
  }
  for (k = 0; k < n; k++) {
#if defined(__LP64__)
    uint32_t id = (uint32_t)ELF64_R_SYM(r[k].r_info);
#else
    uint32_t id = (uint32_t)ELF32_R_SYM(r[k].r_info);
#endif
    void **slot;
    if (sym[id].st_name >= strsz)
      continue;
    if (strcmp(str + sym[id].st_name, want) != 0)
      continue;
    slot = (void **)dyn_resolve(base, bias, (ElfW(Addr))r[k].r_offset);
    if (mem_make_writable(slot, sizeof(void *)) != 0)
      return -1;
    if (orig && *orig == NULL)
      *orig = *slot;
    *slot = fn;
    __builtin___clear_cache((char *)slot, (char *)slot + sizeof(void *));
    return 1;
  }
  return 0;
}
int plt_hook_symbol(void *module_base, const char *symbol_name, void *hook_func,
                    void **orig_func) {
  ElfW(Ehdr) * ehdr;
  ElfW(Phdr) * phdr;
  ElfW(Dyn) *dyn = NULL;
  ElfW(Sym) *dynsym = NULL;
  const char *dynstr = NULL;
  size_t strsz = 0;
  void *plt_rel = NULL;
  size_t plt_sz = 0;
  int rel_type = DT_RELA;
  uintptr_t min_vaddr = (uintptr_t)-1;
  uintptr_t bias = 0;
  ElfW(Dyn) * d;
  int i, rc;
  if (!module_base || !symbol_name || !hook_func)
    return -1;
  ehdr = (ElfW(Ehdr) *)module_base;
  if (ehdr->e_ident[0] != 0x7f || ehdr->e_ident[1] != 'E' ||
      ehdr->e_ident[2] != 'L' || ehdr->e_ident[3] != 'F')
    return -1;
  if (ehdr->e_phoff == 0 || ehdr->e_phnum == 0 || ehdr->e_phnum > 64)
    return -1;
  phdr = (ElfW(Phdr) *)((uint8_t *)module_base + ehdr->e_phoff);
  for (i = 0; i < ehdr->e_phnum; i++) {
    if (phdr[i].p_type == PT_LOAD && phdr[i].p_vaddr < min_vaddr)
      min_vaddr = (uintptr_t)phdr[i].p_vaddr;
    if (phdr[i].p_type == PT_DYNAMIC)
      dyn = (ElfW(Dyn) *)((uint8_t *)module_base + phdr[i].p_vaddr);
  }
  if (min_vaddr == (uintptr_t)-1 || !dyn)
    return -1;
  bias = (uintptr_t)module_base - min_vaddr;
  if ((uintptr_t)dyn < (uintptr_t)module_base ||
      (uintptr_t)dyn > (uintptr_t)module_base + 256u * 1024u * 1024u) {
    for (i = 0; i < ehdr->e_phnum; i++) {
      if (phdr[i].p_type == PT_DYNAMIC) {
        dyn = (ElfW(Dyn) *)(uintptr_t)((uintptr_t)phdr[i].p_vaddr + bias);
        break;
      }
    }
  }
  for (d = dyn; d->d_tag != DT_NULL; d++) {
    switch (d->d_tag) {
    case DT_SYMTAB:
      dynsym = (ElfW(Sym) *)dyn_resolve(module_base, bias, d->d_un.d_ptr);
      break;
    case DT_STRTAB:
      dynstr = (const char *)dyn_resolve(module_base, bias, d->d_un.d_ptr);
      break;
    case DT_STRSZ:
      strsz = (size_t)d->d_un.d_val;
      break;
    case DT_JMPREL:
      plt_rel = (void *)dyn_resolve(module_base, bias, d->d_un.d_ptr);
      break;
    case DT_PLTRELSZ:
      plt_sz = (size_t)d->d_un.d_val;
      break;
    case DT_PLTREL:
      rel_type = (int)d->d_un.d_val;
      break;
    default:
      break;
    }
  }
  if (!dynsym || !dynstr || !plt_rel || !plt_sz || !strsz)
    return -1;
  if (rel_type == DT_RELA)
    rc = hook_rela(module_base, bias, plt_rel, plt_sz, symbol_name, dynsym,
                   dynstr, strsz, hook_func, orig_func);
  else
    rc = hook_rel(module_base, bias, plt_rel, plt_sz, symbol_name, dynsym,
                  dynstr, strsz, hook_func, orig_func);
  if (rc == 1) {
    LOGI("Hooked PLT [%s]: %s (%p -> %p)", rel_type == DT_RELA ? "RELA" : "REL",
         symbol_name, orig_func ? *orig_func : NULL, hook_func);
    return 0;
  }
  if (rc == -2)
    LOGE("Absurd PLT count for '%s'", symbol_name);
  else if (rc == 0)
    LOGW("PLT '%s' not matched", symbol_name);
  return -1;
}
