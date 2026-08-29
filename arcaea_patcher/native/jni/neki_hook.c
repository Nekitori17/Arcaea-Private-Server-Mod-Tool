#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <unistd.h>
#include <sys/mman.h>
#include <elf.h>
#include <android/log.h>
#include <jni.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <pthread.h>
#include <errno.h>
#include <ctype.h>

#define LOG_TAG "NekiHook"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)
#define LOGW(...) __android_log_print(ANDROID_LOG_WARN, LOG_TAG, __VA_ARGS__)

#define MAX_DOMAIN_MAPPINGS 64
#define MAX_HOST_LEN 256

typedef struct {
    char original[MAX_HOST_LEN];
    char target[MAX_HOST_LEN];
} DomainMapping;

static DomainMapping g_mappings[MAX_DOMAIN_MAPPINGS];
static int g_mapping_count = 0;
static volatile int g_hooks_installed = 0;
static volatile int g_hooking_in_progress = 0;

static char g_target_ip_fallback[64] = "192.168.1.150"; 
static int g_redirect_enabled = 1;

// Pointers to original functions
static int (*orig_getaddrinfo)(const char *, const char *, const struct addrinfo *, struct addrinfo **) = NULL;
static struct hostent *(*orig_gethostbyname)(const char *) = NULL;
static int (*orig_connect)(int, const struct sockaddr *, socklen_t) = NULL;

// -----------------------------------------------------------------------------
// Memory & Module Helpers
// -----------------------------------------------------------------------------
static void *get_module_base(const char *module_name) {
    FILE *fp = fopen("/proc/self/maps", "r");
    if (!fp) return NULL;

    char line[512];
    void *base = NULL;
    while (fgets(line, sizeof(line), fp)) {
        if (strstr(line, module_name)) {
            unsigned long addr = 0, offset = 0;
            char perms[5] = {0};
            if (sscanf(line, "%lx-%*x %4s %lx", &addr, perms, &offset) == 3) {
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

static int make_writable(void *addr, size_t size) {
    long page_size = sysconf(_SC_PAGESIZE);
    void *page_start = (void *)((uintptr_t)addr & ~(page_size - 1));
    size_t page_count = ((uintptr_t)addr + size - (uintptr_t)page_start + page_size - 1) / page_size;
    
    // Try RW first to avoid W^X errors on Android 15+
    int ret = mprotect(page_start, page_count * page_size, PROT_READ | PROT_WRITE);
    if (ret != 0) {
        ret = mprotect(page_start, page_count * page_size, PROT_READ | PROT_WRITE | PROT_EXEC);
        if (ret != 0) {
            LOGE("mprotect failed for %p size=%zu errno=%d", addr, size, errno);
        }
    }
    return ret;
}

// -----------------------------------------------------------------------------
// PLT Hook Engine
// -----------------------------------------------------------------------------
#if defined(__aarch64__)
static int plt_hook(void *module_base, const char *symbol_name, void *new_func, void **orig_func) {
    if (!module_base || !symbol_name || !new_func) return -1;
    Elf64_Ehdr *ehdr = (Elf64_Ehdr *)module_base;
    Elf64_Phdr *phdr = (Elf64_Phdr *)((uint8_t *)module_base + ehdr->e_phoff);
    Elf64_Dyn *dyn = NULL;
    for (int i = 0; i < ehdr->e_phnum; i++) {
        if (phdr[i].p_type == PT_DYNAMIC) {
            dyn = (Elf64_Dyn *)((uint8_t *)module_base + phdr[i].p_vaddr); 
            break;
        }
    }
    if (!dyn) return -1;
    Elf64_Sym *dynsym = NULL; 
    const char *dynstr = NULL;
    Elf64_Rela *rela_plt = NULL; 
    size_t rela_plt_size = 0;

    for (Elf64_Dyn *d = dyn; d->d_tag != DT_NULL; d++) {
        switch (d->d_tag) {
            case DT_SYMTAB: dynsym = (Elf64_Sym *)((uint8_t *)module_base + d->d_un.d_ptr); break;
            case DT_STRTAB: dynstr = (const char *)((uint8_t *)module_base + d->d_un.d_ptr); break;
            case DT_JMPREL: rela_plt = (Elf64_Rela *)((uint8_t *)module_base + d->d_un.d_ptr); break;
            case DT_PLTRELSZ: rela_plt_size = d->d_un.d_val; break;
        }
    }
    if (!dynsym || !dynstr || !rela_plt || !rela_plt_size) return -1;
    size_t rela_count = rela_plt_size / sizeof(Elf64_Rela);
    for (size_t i = 0; i < rela_count; i++) {
        uint32_t sym_idx = ELF64_R_SYM(rela_plt[i].r_info);
        if (strcmp(dynstr + dynsym[sym_idx].st_name, symbol_name) == 0) {
            void **got_entry = (void **)((uint8_t *)module_base + rela_plt[i].r_offset);
            if (make_writable(got_entry, sizeof(void *)) != 0) return -1;
            
            if (orig_func && !*orig_func) {
                *orig_func = *got_entry;
            }
            *got_entry = new_func;
            LOGI("plt_hook OK: %s -> %p", symbol_name, new_func);
            return 0;
        }
    }
    return -1;
}
#else
static int plt_hook(void *module_base, const char *symbol_name, void *new_func, void **orig_func) {
    if (!module_base || !symbol_name || !new_func) return -1;
    Elf32_Ehdr *ehdr = (Elf32_Ehdr *)module_base;
    Elf32_Phdr *phdr = (Elf32_Phdr *)((uint8_t *)module_base + ehdr->e_phoff);
    Elf32_Dyn *dyn = NULL;
    for (int i = 0; i < ehdr->e_phnum; i++) {
        if (phdr[i].p_type == PT_DYNAMIC) {
            dyn = (Elf32_Dyn *)((uint8_t *)module_base + phdr[i].p_vaddr); 
            break;
        }
    }
    if (!dyn) return -1;
    Elf32_Sym *dynsym = NULL; 
    const char *dynstr = NULL;
    Elf32_Rel *rel_plt = NULL; 
    size_t rel_plt_size = 0;

    for (Elf32_Dyn *d = dyn; d->d_tag != DT_NULL; d++) {
        switch (d->d_tag) {
            case DT_SYMTAB: dynsym = (Elf32_Sym *)((uint8_t *)module_base + d->d_un.d_ptr); break;
            case DT_STRTAB: dynstr = (const char *)((uint8_t *)module_base + d->d_un.d_ptr); break;
            case DT_JMPREL: rel_plt = (Elf32_Rel *)((uint8_t *)module_base + d->d_un.d_ptr); break;
            case DT_PLTRELSZ: rel_plt_size = d->d_un.d_val; break;
        }
    }
    if (!dynsym || !dynstr || !rel_plt || !rel_plt_size) return -1;
    size_t rel_count = rel_plt_size / sizeof(Elf32_Rel);
    for (size_t i = 0; i < rel_count; i++) {
        uint32_t sym_idx = ELF32_R_SYM(rel_plt[i].r_info);
        if (strcmp(dynstr + dynsym[sym_idx].st_name, symbol_name) == 0) {
            void **got_entry = (void **)((uint8_t *)module_base + rel_plt[i].r_offset);
            if (make_writable(got_entry, sizeof(void *)) != 0) return -1;
            if (orig_func && !*orig_func) {
                *orig_func = *got_entry;
            }
            *got_entry = new_func;
            LOGI("plt_hook OK: %s -> %p", symbol_name, new_func);
            return 0;
        }
    }
    return -1;
}
#endif

// -----------------------------------------------------------------------------
// Domain Redirection Logic
// -----------------------------------------------------------------------------
static const char *get_mapped_domain(const char *hostname) {
    if (!hostname) return NULL;
    
    // Prioritize checking the dynamic mapping list loaded from the configuration.
    for (int i = 0; i < g_mapping_count; i++) {
        if (strcasecmp(hostname, g_mappings[i].original) == 0) {
            return g_mappings[i].target;
        }
    }
    
    // Default fallback for domains requiring redirection
    if (strstr(hostname, "lowiro.com") != NULL) {
        return g_target_ip_fallback;
    }
    
    return NULL;
}

static int hook_getaddrinfo(const char *node, const char *service, const struct addrinfo *hints, struct addrinfo **res) {
    const char *target = get_mapped_domain(node);
    const char *effective_host = target ? target : node;
    
    if (target) {
        LOGI("DNS Hook getaddrinfo: \"%s\" -> \"%s\"", node, target);
    }
    
    if (orig_getaddrinfo) {
        return orig_getaddrinfo(effective_host, service, hints, res);
    }
    return EAI_FAIL;
}

static struct hostent *hook_gethostbyname(const char *name) {
    const char *target = get_mapped_domain(name);
    const char *effective_name = target ? target : name;
    
    if (target) {
        LOGI("DNS Hook gethostbyname: \"%s\" -> \"%s\"", name, target);
    }
    
    if (orig_gethostbyname) {
        return orig_gethostbyname(effective_name);
    }
    return NULL;
}

static int hook_connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
    if (addr && addr->sa_family == AF_INET && g_redirect_enabled && strlen(g_target_ip_fallback) > 0) {
        struct sockaddr_in *sin = (struct sockaddr_in *)addr;
        int port = ntohs(sin->sin_port);
        char ip_str[INET_ADDRSTRLEN] = {0};
        inet_ntop(AF_INET, &(sin->sin_addr), ip_str, sizeof(ip_str));

        // Redirect HTTPS traffic (port 443) to the target IP
        if (port == 443) {
            struct in_addr custom_ip;
            if (inet_pton(AF_INET, g_target_ip_fallback, &custom_ip) == 1) {
                struct sockaddr_storage redirected;
                memcpy(&redirected, addr, sizeof(struct sockaddr_in));
                ((struct sockaddr_in *)&redirected)->sin_addr = custom_ip;
                
                LOGI("Socket Hook: redirecting %s:%d -> %s:%d", ip_str, port, g_target_ip_fallback, port);
                return orig_connect ? orig_connect(sockfd, (struct sockaddr *)&redirected, addrlen) : -1;
            }
        }
    }
    
    if (orig_connect) {
        return orig_connect(sockfd, addr, addrlen);
    }
    return -1;
}

// -----------------------------------------------------------------------------
// Config Loader
// -----------------------------------------------------------------------------
static void load_domain_config(const char *config_path) {
    if (!config_path || strlen(config_path) == 0) return;
    FILE *fp = fopen(config_path, "r");
    if (!fp) { 
        LOGW("Unable to open config: %s", config_path); 
        return; 
    }

    char line[512];
    g_mapping_count = 0;

    while (fgets(line, sizeof(line), fp)) {
        char *p = line; 
        while (*p == ' ' || *p == '\t') p++;
        if (*p == '#' || *p == ';' || *p == '\r' || *p == '\n' || *p == '\0') continue;
        
        char *eq = strchr(p, '='); 
        if (!eq) eq = strchr(p, ':');
        
        if (eq) {
            *eq = '\0';
            char *orig = p; 
            char *target = eq + 1;
            
            char *end = orig + strlen(orig) - 1; 
            while (end >= orig && (*end <= ' ' || *end == '\r' || *end == '\n')) *end-- = '\0';
            
            while (*target <= ' ' && *target != '\0') target++;
            end = target + strlen(target) - 1; 
            while (end >= target && (*end <= ' ' || *end == '\r' || *end == '\n')) *end-- = '\0';

            if (strlen(orig) > 0 && strlen(target) > 0 && g_mapping_count < MAX_DOMAIN_MAPPINGS) {
                strncpy(g_mappings[g_mapping_count].original, orig, MAX_HOST_LEN - 1);
                g_mappings[g_mapping_count].original[MAX_HOST_LEN - 1] = '\0';

                strncpy(g_mappings[g_mapping_count].target, target, MAX_HOST_LEN - 1);
                g_mappings[g_mapping_count].target[MAX_HOST_LEN - 1] = '\0';
                
                if (g_mapping_count == 0) {
                    strncpy(g_target_ip_fallback, target, sizeof(g_target_ip_fallback) - 1);
                    g_target_ip_fallback[sizeof(g_target_ip_fallback) - 1] = '\0';
                }
                
                LOGI("Domain mapping [%d]: %s -> %s", g_mapping_count, orig, target);
                g_mapping_count++;
            }
        }
    }
    fclose(fp);
    LOGI("Total mappings loaded: %d | Target IP: %s", g_mapping_count, g_target_ip_fallback);
}

// -----------------------------------------------------------------------------
// Hook Installation Logic
// -----------------------------------------------------------------------------
static int perform_hooks() {
    void *base = get_module_base("libcocos2dcpp.so");
    if (!base) {
        return 0;
    }

    LOGI("Target libcocos2dcpp.so found at %p. Installing redirection hooks...", base);

    plt_hook(base, "getaddrinfo", (void *)hook_getaddrinfo, (void **)&orig_getaddrinfo);
    plt_hook(base, "gethostbyname", (void *)hook_gethostbyname, (void **)&orig_gethostbyname);
    plt_hook(base, "connect", (void *)hook_connect, (void **)&orig_connect);

    g_hooks_installed = 1;
    LOGI("=== Domain Redirection Hooks installed successfully ===");
    return 1;
}

static void *wait_and_hook_thread(void *arg) {
    int retries = 0;
    while (!g_hooks_installed && retries < 100) {
        if (perform_hooks()) {
            break;
        }
        usleep(50000); // 50ms interval
        retries++;
    }
    g_hooking_in_progress = 0;
    return NULL;
}

static void install_hooks_internal() {
    if (g_hooks_installed) return;

    // Try to set directly first if the target library is already loaded
    if (perform_hooks()) {
        return;
    }
    
    // If not yet loaded, create a worker thread to wait for the library to load.
    if (!g_hooking_in_progress) {
        g_hooking_in_progress = 1;
        pthread_t th;
        if (pthread_create(&th, NULL, wait_and_hook_thread, NULL) == 0) {
            pthread_detach(th);
        } else {
            g_hooking_in_progress = 0;
            LOGE("Failed to create hook watcher thread");
        }
    }
}

// -----------------------------------------------------------------------------
// JNI Exports
// -----------------------------------------------------------------------------
JNIEXPORT void JNICALL Java_moe_low_arc_custom_NekiHookLoader_nativeInit(JNIEnv *env, jclass cls, jstring config_path) {
    if (config_path) {
        const char *path = (*env)->GetStringUTFChars(env, config_path, NULL);
        if (path) {
            load_domain_config(path);
            (*env)->ReleaseStringUTFChars(env, config_path, path);
        }
    }
    install_hooks_internal();
}

JNIEXPORT jint JNI_OnLoad(JavaVM *vm, void *reserved) {
    LOGI("libneki.so JNI_OnLoad");
    install_hooks_internal();
    return JNI_VERSION_1_6;
}