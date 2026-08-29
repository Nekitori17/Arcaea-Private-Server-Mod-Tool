#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/mman.h>
#include <elf.h>
#include <link.h>
#include <android/log.h>
#include <jni.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <errno.h>

#define TAG "NekiHook"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, TAG, __VA_ARGS__)
#define LOGW(...) __android_log_print(ANDROID_LOG_WARN, TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

#define MAX_DOMAIN_RULES 64
#define MAX_HOST_LEN     128
#define TARGET_LIB_NAME  "libcocos2dcpp.so"

/* -------------------------------------------------------------------------
 * Domain Routing Configuration
 * ------------------------------------------------------------------------- */

typedef struct {
    char original[MAX_HOST_LEN];
    char replacement[MAX_HOST_LEN];
    struct in_addr replacement_ipv4;
    int has_ipv4;
} DomainRule;

static DomainRule s_domain_rules[MAX_DOMAIN_RULES];
static size_t s_domain_rule_count = 0;
static int s_hooks_installed = 0;

/* -------------------------------------------------------------------------
 * Original Function Pointers
 * ------------------------------------------------------------------------- */

static int (*orig_getaddrinfo)(const char *, const char *, const struct addrinfo *, struct addrinfo **) = NULL;
static int (*orig_connect)(int, const struct sockaddr *, socklen_t) = NULL;

static void (*orig_SSL_CTX_set_verify)(void *, int, void *) = NULL;
static void (*orig_SSL_set_verify)(void *, int, void *) = NULL;
static void (*orig_SSL_CTX_set_custom_verify)(void *, int, void *) = NULL;
static int  (*orig_X509_verify_cert)(void *) = NULL;
static long (*orig_SSL_get_verify_result)(const void *) = NULL;

/* -------------------------------------------------------------------------
 * Configuration File Parser (domain.cfg)
 * ------------------------------------------------------------------------- */

static void parse_domain_config(const char *config_path) {
    s_domain_rule_count = 0;
    if (!config_path || strlen(config_path) == 0) {
        LOGW("Empty configuration path provided");
        return;
    }

    FILE *fp = fopen(config_path, "r");
    if (!fp) {
        LOGW("Failed to open domain config: %s (errno=%d)", config_path, errno);
        return;
    }

    char line[256];
    while (fgets(line, sizeof(line), fp) && s_domain_rule_count < MAX_DOMAIN_RULES) {
        // Strip trailing newline / carriage return characters
        line[strcspn(line, "\r\n")] = '\0';

        // Skip comments and empty lines
        if (line[0] == '#' || line[0] == '\0') {
            continue;
        }

        char *delim = strchr(line, '=');
        if (!delim) {
            continue;
        }

        *delim = '\0';
        char *orig_host = line;
        char *target_host = delim + 1;

        // Trim leading and trailing whitespace
        while (*orig_host == ' ') orig_host++;
        while (*target_host == ' ') target_host++;

        if (*orig_host == '\0' || *target_host == '\0') {
            continue;
        }

        DomainRule *rule = &s_domain_rules[s_domain_rule_count];
        strncpy(rule->original, orig_host, sizeof(rule->original) - 1);
        rule->original[sizeof(rule->original) - 1] = '\0';

        strncpy(rule->replacement, target_host, sizeof(rule->replacement) - 1);
        rule->replacement[sizeof(rule->replacement) - 1] = '\0';

        // Check if replacement is an IPv4 string literal
        if (inet_pton(AF_INET, rule->replacement, &rule->replacement_ipv4) == 1) {
            rule->has_ipv4 = 1;
        } else {
            rule->has_ipv4 = 0;
        }

        LOGI("Registered domain mapping [%zu]: %s -> %s",
             s_domain_rule_count, rule->original, rule->replacement);
        s_domain_rule_count++;
    }

    fclose(fp);
    LOGI("Loaded %zu domain routing rule(s) from %s", s_domain_rule_count, config_path);
}

/* -------------------------------------------------------------------------
 * Domain Routing Helpers
 * ------------------------------------------------------------------------- */

static const DomainRule *find_matching_rule(const char *hostname) {
    if (!hostname) return NULL;
    for (size_t i = 0; i < s_domain_rule_count; i++) {
        if (strcmp(s_domain_rules[i].original, hostname) == 0) {
            return &s_domain_rules[i];
        }
    }
    return NULL;
}

/* -------------------------------------------------------------------------
 * Hook Implementations: Network & DNS Redirection
 * ------------------------------------------------------------------------- */

static int hook_getaddrinfo(const char *node, const char *service,
                           const struct addrinfo *hints, struct addrinfo **res) {
    const char *effective_node = node;

    if (node) {
        const DomainRule *rule = find_matching_rule(node);
        if (rule) {
            effective_node = rule->replacement;
            LOGI("getaddrinfo: Redirected \"%s\" -> \"%s\"", node, effective_node);
        }
    }

    if (orig_getaddrinfo) {
        return orig_getaddrinfo(effective_node, service, hints, res);
    }
    return EAI_FAIL;
}

static int hook_connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
    if (addr && addr->sa_family == AF_INET && s_domain_rule_count > 0) {
        struct sockaddr_in *sin = (struct sockaddr_in *)addr;
        int port = ntohs(sin->sin_port);

        // For HTTPS port 443, check if redirection is active with an IPv4 target
        if (port == 443) {
            for (size_t i = 0; i < s_domain_rule_count; i++) {
                if (s_domain_rules[i].has_ipv4) {
                    struct sockaddr_in redirected_addr;
                    memcpy(&redirected_addr, addr, sizeof(struct sockaddr_in));
                    redirected_addr.sin_addr = s_domain_rules[i].replacement_ipv4;

                    LOGI("connect: Redirected socket %d to %s:443",
                         sockfd, s_domain_rules[i].replacement);

                    if (orig_connect) {
                        return orig_connect(sockfd, (struct sockaddr *)&redirected_addr, addrlen);
                    }
                    return -1;
                }
            }
        }
    }

    if (orig_connect) {
        return orig_connect(sockfd, addr, addrlen);
    }
    return -1;
}

/* -------------------------------------------------------------------------
 * Hook Implementations: SSL / TLS Pinning Bypass
 * ------------------------------------------------------------------------- */

static void hook_SSL_CTX_set_verify(void *ctx, int mode, void *callback) {
    // Mode 0 = SSL_VERIFY_NONE
    LOGI("SSL_CTX_set_verify: Forcing SSL_VERIFY_NONE (original mode=%d)", mode);
    if (orig_SSL_CTX_set_verify) {
        orig_SSL_CTX_set_verify(ctx, 0, NULL);
    }
}

static void hook_SSL_set_verify(void *ssl, int mode, void *callback) {
    LOGI("SSL_set_verify: Forcing SSL_VERIFY_NONE (original mode=%d)", mode);
    if (orig_SSL_set_verify) {
        orig_SSL_set_verify(ssl, 0, NULL);
    }
}

static void hook_SSL_CTX_set_custom_verify(void *ctx, int mode, void *callback) {
    LOGI("SSL_CTX_set_custom_verify: Forcing SSL_VERIFY_NONE (original mode=%d)", mode);
    if (orig_SSL_CTX_set_custom_verify) {
        orig_SSL_CTX_set_custom_verify(ctx, 0, NULL);
    }
}

static int hook_X509_verify_cert(void *ctx) {
    LOGI("X509_verify_cert: Bypassed certificate chain verification (returning 1)");
    return 1;
}

static long hook_SSL_get_verify_result(const void *ssl) {
    // 0 == X509_V_OK
    LOGI("SSL_get_verify_result: Returning X509_V_OK (0)");
    return 0;
}

/* -------------------------------------------------------------------------
 * ELF Memory & PLT Hooking Subsystem (32-bit & 64-bit Architecture Aware)
 * ------------------------------------------------------------------------- */

static void *find_module_base_address(const char *module_name) {
    FILE *fp = fopen("/proc/self/maps", "r");
    if (!fp) {
        LOGE("Failed to open /proc/self/maps");
        return NULL;
    }

    char line[512];
    void *base = NULL;
    while (fgets(line, sizeof(line), fp)) {
        if (strstr(line, module_name)) {
            uintptr_t addr = 0;
            uintptr_t offset = 0;
            char perms[5] = {0};

#if defined(__LP64__)
            if (sscanf(line, "%lx-%*x %4s %lx", &addr, perms, &offset) == 3) {
#else
            if (sscanf(line, "%x-%*x %4s %x", &addr, perms, &offset) == 3) {
#endif
                if (offset == 0) {
                    base = (void *)addr;
                    break;
                }
            }
        }
    }
    fclose(fp);
    return base;
}

static int set_memory_writable(void *addr, size_t size) {
    long page_size = sysconf(_SC_PAGESIZE);
    uintptr_t page_start = (uintptr_t)addr & ~(page_size - 1);
    size_t page_count = ((uintptr_t)addr + size - page_start + page_size - 1) / page_size;

    // Try RW first to comply with W^X enforcement on Android 15+
    int ret = mprotect((void *)page_start, page_count * page_size, PROT_READ | PROT_WRITE);
    if (ret != 0) {
        ret = mprotect((void *)page_start, page_count * page_size, PROT_READ | PROT_WRITE | PROT_EXEC);
        if (ret != 0) {
            LOGE("mprotect failed for %p size=%zu (errno=%d)", addr, size, errno);
        }
    }
    return ret;
}

static int plt_hook_symbol(void *module_base, const char *symbol_name,
                          void *hook_func, void **orig_func) {
    if (!module_base || !symbol_name || !hook_func) {
        return -1;
    }

    ElfW(Ehdr) *ehdr = (ElfW(Ehdr) *)module_base;
    ElfW(Phdr) *phdr = (ElfW(Phdr) *)((uint8_t *)module_base + ehdr->e_phoff);
    ElfW(Dyn)  *dyn  = NULL;

    for (int i = 0; i < ehdr->e_phnum; i++) {
        if (phdr[i].p_type == PT_DYNAMIC) {
            dyn = (ElfW(Dyn) *)((uint8_t *)module_base + phdr[i].p_vaddr);
            break;
        }
    }

    if (!dyn) {
        LOGE("PT_DYNAMIC table not found in module");
        return -1;
    }

    ElfW(Sym)  *dynsym      = NULL;
    const char *dynstr      = NULL;
    void       *plt_rel     = NULL;
    size_t      plt_rel_sz  = 0;
    int         rel_type    = DT_REL;

    for (ElfW(Dyn) *d = dyn; d->d_tag != DT_NULL; d++) {
        switch (d->d_tag) {
            case DT_SYMTAB:
                dynsym = (ElfW(Sym) *)((uint8_t *)module_base + d->d_un.d_ptr);
                break;
            case DT_STRTAB:
                dynstr = (const char *)((uint8_t *)module_base + d->d_un.d_ptr);
                break;
            case DT_JMPREL:
                plt_rel = (void *)((uint8_t *)module_base + d->d_un.d_ptr);
                break;
            case DT_PLTRELSZ:
                plt_rel_sz = d->d_un.d_val;
                break;
            case DT_PLTREL:
                rel_type = (int)d->d_un.d_val;
                break;
            default:
                break;
        }
    }

    if (!dynsym || !dynstr || !plt_rel || !plt_rel_sz) {
        LOGE("Failed to parse dynamic tables for symbol '%s'", symbol_name);
        return -1;
    }

    // Process RELA entries (standard on 64-bit architectures)
    if (rel_type == DT_RELA) {
        ElfW(Rela) *rela = (ElfW(Rela) *)plt_rel;
        size_t count = plt_rel_sz / sizeof(ElfW(Rela));

        for (size_t i = 0; i < count; i++) {
#if defined(__LP64__)
            uint32_t sym_idx = ELF64_R_SYM(rela[i].r_info);
#else
            uint32_t sym_idx = ELF32_R_SYM(rela[i].r_info);
#endif
            const char *name = dynstr + dynsym[sym_idx].st_name;
            if (strcmp(name, symbol_name) == 0) {
                void **got_slot = (void **)((uint8_t *)module_base + rela[i].r_offset);

                if (set_memory_writable(got_slot, sizeof(void *)) != 0) {
                    LOGE("Failed to make GOT entry writable for %s", symbol_name);
                    return -1;
                }

                if (orig_func && *orig_func == NULL) {
                    *orig_func = *got_slot;
                }

                *got_slot = hook_func;
                LOGI("Hooked PLT symbol [RELA]: %s (%p -> %p)", symbol_name, orig_func ? *orig_func : NULL, hook_func);
                return 0;
            }
        }
    }
    // Process REL entries (standard on 32-bit architectures)
    else {
        ElfW(Rel) *rel = (ElfW(Rel) *)plt_rel;
        size_t count = plt_rel_sz / sizeof(ElfW(Rel));

        for (size_t i = 0; i < count; i++) {
#if defined(__LP64__)
            uint32_t sym_idx = ELF64_R_SYM(rel[i].r_info);
#else
            uint32_t sym_idx = ELF32_R_SYM(rel[i].r_info);
#endif
            const char *name = dynstr + dynsym[sym_idx].st_name;
            if (strcmp(name, symbol_name) == 0) {
                void **got_slot = (void **)((uint8_t *)module_base + rel[i].r_offset);

                if (set_memory_writable(got_slot, sizeof(void *)) != 0) {
                    LOGE("Failed to make GOT entry writable for %s", symbol_name);
                    return -1;
                }

                if (orig_func && *orig_func == NULL) {
                    *orig_func = *got_slot;
                }

                *got_slot = hook_func;
                LOGI("Hooked PLT symbol [REL]: %s (%p -> %p)", symbol_name, orig_func ? *orig_func : NULL, hook_func);
                return 0;
            }
        }
    }

    LOGW("PLT symbol '%s' not matched in relocation tables", symbol_name);
    return -1;
}

/* -------------------------------------------------------------------------
 * Hook Installation Controller
 * ------------------------------------------------------------------------- */

static void install_all_plt_hooks(void) {
    if (s_hooks_installed) {
        LOGI("Hooks already installed, skipping");
        return;
    }

    void *engine_base = find_module_base_address(TARGET_LIB_NAME);
    if (!engine_base) {
        LOGE("Could not locate %s base address in /proc/self/maps", TARGET_LIB_NAME);
        return;
    }

    LOGI("Installing PLT hooks into %s at base %p", TARGET_LIB_NAME, engine_base);

    // 1. Network & DNS Hooks
    plt_hook_symbol(engine_base, "getaddrinfo", (void *)hook_getaddrinfo, (void **)&orig_getaddrinfo);
    plt_hook_symbol(engine_base, "connect", (void *)hook_connect, (void **)&orig_connect);

    // 2. OpenSSL / BoringSSL Pinning Bypass Hooks
    plt_hook_symbol(engine_base, "SSL_CTX_set_verify", (void *)hook_SSL_CTX_set_verify, (void **)&orig_SSL_CTX_set_verify);
    plt_hook_symbol(engine_base, "SSL_set_verify", (void *)hook_SSL_set_verify, (void **)&orig_SSL_set_verify);
    plt_hook_symbol(engine_base, "SSL_CTX_set_custom_verify", (void *)hook_SSL_CTX_set_custom_verify, (void **)&orig_SSL_CTX_set_custom_verify);
    plt_hook_symbol(engine_base, "X509_verify_cert", (void *)hook_X509_verify_cert, (void **)&orig_X509_verify_cert);
    plt_hook_symbol(engine_base, "SSL_get_verify_result", (void *)hook_SSL_get_verify_result, (void **)&orig_SSL_get_verify_result);

    s_hooks_installed = 1;
    LOGI("All requested PLT hooks installed successfully");
}

/* -------------------------------------------------------------------------
 * JNI Entry Points
 * ------------------------------------------------------------------------- */

JNIEXPORT void JNICALL Java_moe_low_arc_custom_NekiHookLoader_nativeInit(
        JNIEnv *env, jclass cls, jstring config_path) {
    LOGI("nativeInit invoked from NekiHookLoader");

    if (config_path != NULL) {
        const char *c_path = (*env)->GetStringUTFChars(env, config_path, NULL);
        if (c_path) {
            parse_domain_config(c_path);
            (*env)->ReleaseStringUTFChars(env, config_path, c_path);
        }
    }

    install_all_plt_hooks();
}

JNIEXPORT jint JNI_OnLoad(JavaVM *vm, void *reserved) {
    LOGI("libneki.so JNI_OnLoad initialized");
    return JNI_VERSION_1_6;
}