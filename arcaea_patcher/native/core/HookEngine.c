#include "HookEngine.h"

#include <dlfcn.h>
#include <elf.h>
#include <link.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "MemoryUtils.h"

#define LOG_MODULE_TAG "Engine"
#include "Logger.h"

#define RETRY_ATTEMPTS 50
#define RETRY_DELAY_US (200 * 1000)

static pthread_mutex_t s_lock = PTHREAD_MUTEX_INITIALIZER;
static int s_installed = 0;

/* --- Deferred module installation ---------------------------------------- */

typedef struct {
  const char *module_name;
  hook_installer_fn install_fn;
} retry_ctx_t;

/* Returns 1 for the caller that must run the installer, 0 otherwise. */
static int claim_install(void) {
  int claimed;
  pthread_mutex_lock(&s_lock);
  claimed = !s_installed;
  if (claimed)
    s_installed = 1;
  pthread_mutex_unlock(&s_lock);
  return claimed;
}

static void run_installer(const char *module_name, hook_installer_fn install_fn,
                          void *module_base) {
  LOGI("Installing PLT hooks into %s @ %p", module_name, module_base);
  install_fn(module_base);
  LOGI("Hook install pass finished");
}

static void *retry_thread(void *arg) {
  retry_ctx_t *ctx = (retry_ctx_t *)arg;
  int tries;
  for (tries = 0; tries < RETRY_ATTEMPTS; tries++) {
    void *base = mem_get_module_base(ctx->module_name);
    if (base) {
      if (claim_install())
        run_installer(ctx->module_name, ctx->install_fn, base);
      free(ctx);
      return NULL;
    }
    usleep(RETRY_DELAY_US);
  }
  LOGE("Gave up waiting for %s after ~%ds", ctx->module_name,
       (RETRY_ATTEMPTS * RETRY_DELAY_US) / 1000000);
  free(ctx);
  return NULL;
}

int hook_engine_install_when_loaded(const char *module_name,
                                    hook_installer_fn install_fn) {
  void *base;
  retry_ctx_t *ctx;
  pthread_t tid;
  if (!module_name || !install_fn)
    return -1;
  base = mem_get_module_base(module_name);
  if (base) {
    if (claim_install())
      run_installer(module_name, install_fn, base);
    else
      LOGI("Hooks already installed; skipping");
    return 1;
  }
  LOGW("%s not loaded yet; retrying in background (~10s)", module_name);
  ctx = (retry_ctx_t *)malloc(sizeof(*ctx));
  if (!ctx) {
    LOGE("Out of memory allocating retry context");
    return -1;
  }
  ctx->module_name = module_name;
  ctx->install_fn = install_fn;
  if (pthread_create(&tid, NULL, retry_thread, ctx) != 0) {
    LOGE("Failed to spawn hook retry thread");
    free(ctx);
    return -1;
  }
  pthread_detach(tid);
  return 0;
}

/* --- GOT/PLT hooking ------------------------------------------------------ */

/* load_bias = runtime_base - min_vaddr; handles absolute VA and RVA. */
static uint8_t *dyn_resolve(void *base, uintptr_t load_bias, ElfW(Addr) v) {
  uintptr_t uv = (uintptr_t)v;
  uintptr_t b = (uintptr_t)base;
  if (uv >= b && uv < b + 256u * 1024u * 1024u)
    return (uint8_t *)uv;
  return (uint8_t *)(uv + load_bias);
}

/* Pick the original implementation for a GOT slot.
 * With lazy binding the slot may still hold a PLT resolver stub that lives
 * inside the target module; calling it would bounce back into the hook, so
 * dlsym() is preferred in that case. Resolved in-module pointers (e.g.
 * statically linked OpenSSL exporting its own symbols) are kept as-is. */
static void *pick_original_addr(const char *symbol, void *slot_value,
                                uintptr_t mod_lo, uintptr_t mod_hi) {
  uintptr_t cand = (uintptr_t)slot_value;
  if (cand >= mod_lo && cand < mod_hi) {
    void *resolved = dlsym(RTLD_DEFAULT, symbol);
    uintptr_t res = (uintptr_t)resolved;
    if (resolved && (res < mod_lo || res >= mod_hi)) {
      LOGW("GOT slot for '%s' at %p looks unresolved; using dlsym %p", symbol,
           slot_value, resolved);
      return resolved;
    }
    if (resolved && resolved != slot_value)
      LOGW("GOT slot for '%s' is in-module (%p) but dlsym differs (%p); "
           "keeping GOT value", symbol, slot_value, resolved);
  }
  return slot_value;
}

static int hook_rela(void *base, uintptr_t bias, void *rel, size_t sz,
                     const char *want, ElfW(Sym) * sym, const char *str,
                     size_t strsz, void *fn, void **orig, uintptr_t mod_lo,
                     uintptr_t mod_hi) {
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
      *orig = pick_original_addr(want, *slot, mod_lo, mod_hi);
    *slot = fn;
    __builtin___clear_cache((char *)slot, (char *)slot + sizeof(void *));
    return 1;
  }
  return 0;
}

static int hook_rel(void *base, uintptr_t bias, void *rel, size_t sz,
                    const char *want, ElfW(Sym) * sym, const char *str,
                    size_t strsz, void *fn, void **orig, uintptr_t mod_lo,
                    uintptr_t mod_hi) {
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
      *orig = pick_original_addr(want, *slot, mod_lo, mod_hi);
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
  uintptr_t mod_lo = 0, mod_hi = 0;
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
  /* Address span of this module, used to spot unresolved PLT stubs. */
  mod_lo = (uintptr_t)module_base;
  mod_hi = mod_lo;
  for (i = 0; i < ehdr->e_phnum; i++) {
    uintptr_t seg_lo, seg_hi;
    if (phdr[i].p_type != PT_LOAD)
      continue;
    seg_lo = (uintptr_t)(phdr[i].p_vaddr + bias);
    seg_hi = seg_lo + (uintptr_t)phdr[i].p_memsz;
    if (seg_lo < mod_lo)
      mod_lo = seg_lo;
    if (seg_hi > mod_hi)
      mod_hi = seg_hi;
  }
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
                   dynstr, strsz, hook_func, orig_func, mod_lo, mod_hi);
  else
    rc = hook_rel(module_base, bias, plt_rel, plt_sz, symbol_name, dynsym,
                  dynstr, strsz, hook_func, orig_func, mod_lo, mod_hi);
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
