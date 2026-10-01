#include "DomainRedirectHook.h"

#include <arpa/inet.h>
#include <errno.h>
#include <netdb.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>

#include "DomainParser.h"
#include "MemoryUtils.h"

#define LOG_MODULE_TAG "Redirect"
#include "Logger.h"

static int (*orig_getaddrinfo)(const char *, const char *,
                               const struct addrinfo *,
                               struct addrinfo **) = NULL;
static int (*orig_connect)(int, const struct sockaddr *, socklen_t) = NULL;
static struct hostent *(*orig_gethostbyname)(const char *) = NULL;
static struct hostent *(*orig_gethostbyname2)(const char *, int) = NULL;

#define MAX_KNOWN_V4 256
#define MAX_KNOWN_V6 64
static struct in_addr s_known_v4[MAX_KNOWN_V4];
static size_t s_known_v4_count = 0;
static struct in6_addr s_known_v6[MAX_KNOWN_V6];
static size_t s_known_v6_count = 0;

static void remember_v4(struct in_addr ip) {
    size_t i;
    for (i = 0; i < s_known_v4_count; i++)
        if (s_known_v4[i].s_addr == ip.s_addr) return;
    if (s_known_v4_count < MAX_KNOWN_V4)
        s_known_v4[s_known_v4_count++] = ip;
}

static void snapshot_original_ips(const char *host) {
    struct addrinfo hints, *res = NULL, *p;
    int rc;
    /* Avoid a duplicate real-DNS round-trip per matching lookup. */
    static char s_done[DOMAIN_MAX_RULES][DOMAIN_MAX_HOST];
    static size_t s_done_count = 0;
    size_t i, j;
    if (!orig_getaddrinfo || !host) return;
    for (i = 0; i < s_done_count; i++) {
        if (strcmp(s_done[i], host) == 0) return;
    }
    if (s_done_count < DOMAIN_MAX_RULES) {
        strncpy(s_done[s_done_count], host, DOMAIN_MAX_HOST - 1);
        s_done[s_done_count][DOMAIN_MAX_HOST - 1] = '\0';
        s_done_count++;
    }
    memset(&hints, 0, sizeof(hints));
    hints.ai_socktype = SOCK_STREAM;
    rc = orig_getaddrinfo(host, NULL, &hints, &res);
    if (rc != 0 || !res) return;
    for (p = res; p; p = p->ai_next) {
        if (p->ai_family == AF_INET &&
            p->ai_addrlen >= (socklen_t)sizeof(struct sockaddr_in)) {
            struct sockaddr_in *sin = (struct sockaddr_in *)p->ai_addr;
            remember_v4(sin->sin_addr);
        } else if (p->ai_family == AF_INET6 &&
            p->ai_addrlen >= (socklen_t)sizeof(struct sockaddr_in6)) {
            struct sockaddr_in6 *sin6 = (struct sockaddr_in6 *)p->ai_addr;
            int dup = 0;
            for (j = 0; j < s_known_v6_count; j++) {
                if (memcmp(&s_known_v6[j], &sin6->sin6_addr,
                           sizeof(struct in6_addr)) == 0) {
                    dup = 1;
                    break;
                }
            }
            if (!dup && s_known_v6_count < MAX_KNOWN_V6)
                s_known_v6[s_known_v6_count++] = sin6->sin6_addr;
        }
    }
    freeaddrinfo(res);
}

static int is_known_original_v4(struct in_addr ip) {
    size_t i;
    for (i = 0; i < s_known_v4_count; i++)
        if (s_known_v4[i].s_addr == ip.s_addr) return 1;
    return 0;
}

static int is_known_original_v6(const struct in6_addr *ip) {
    size_t i;
    for (i = 0; i < s_known_v6_count; i++) {
        if (memcmp(&s_known_v6[i], ip, sizeof(struct in6_addr)) == 0) return 1;
    }
    return 0;
}

static __thread struct hostent s_he;
static __thread struct in_addr s_he_addrs[1];
static __thread char *s_he_list[2];
static __thread char s_he_name[DOMAIN_MAX_HOST];

static struct hostent *make_redirect_hostent(const DomainRule *rule) {
    if (!rule || !rule->has_v4) return NULL;
    memset(&s_he, 0, sizeof(s_he));
    strncpy(s_he_name, rule->original, sizeof(s_he_name) - 1);
    s_he_addrs[0] = rule->repl_v4;
    s_he_list[0] = (char *)&s_he_addrs[0];
    s_he_list[1] = NULL;
    s_he.h_name = s_he_name;
    s_he.h_aliases = NULL;
    s_he.h_addrtype = AF_INET;
    s_he.h_length = sizeof(struct in_addr);
    s_he.h_addr_list = s_he_list;
    return &s_he;
}

static int hook_getaddrinfo(const char *node, const char *service,
                            const struct addrinfo *hints,
                            struct addrinfo **res) {
    const DomainRule *rule;
    if (!orig_getaddrinfo) return EAI_FAIL;
    if (!node) return orig_getaddrinfo(node, service, hints, res);
    rule = domain_find(node);
    if (!rule) return orig_getaddrinfo(node, service, hints, res);
    snapshot_original_ips(node);
    LOGI("getaddrinfo: %s -> %s", node, rule->replacement);
    if (rule->repl_port != 0 && (service == NULL || service[0] == '\0')) {
        char port_buf[8];
        snprintf(port_buf, sizeof(port_buf), "%d", rule->repl_port);
        return orig_getaddrinfo(rule->replacement, port_buf, hints, res);
    }
    return orig_getaddrinfo(rule->replacement, service, hints, res);
}

static struct hostent *hook_gethostbyname(const char *name) {
    const DomainRule *rule;
    if (!name) return orig_gethostbyname ? orig_gethostbyname(name) : NULL;
    rule = domain_find(name);
    if (!rule || !rule->has_v4)
        return orig_gethostbyname ? orig_gethostbyname(name) : NULL;
    LOGI("gethostbyname: %s -> %s", name, rule->replacement);
    return make_redirect_hostent(rule);
}

static struct hostent *hook_gethostbyname2(const char *name, int af) {
    const DomainRule *rule;
    if (!name) return orig_gethostbyname2 ? orig_gethostbyname2(name, af) : NULL;
    rule = domain_find(name);
    if (!rule || af != AF_INET || !rule->has_v4)
        return orig_gethostbyname2 ? orig_gethostbyname2(name, af) : NULL;
    LOGI("gethostbyname2: %s -> %s", name, rule->replacement);
    return make_redirect_hostent(rule);
}

static int hook_connect(int sockfd, const struct sockaddr *addr,
                        socklen_t addrlen) {
    if (!orig_connect) { errno = ENOTCONN; return -1; }
    if (addr && addr->sa_family == AF_INET &&
        addrlen >= (socklen_t)sizeof(struct sockaddr_in) &&
        domain_count() > 0) {
        const struct sockaddr_in *sin = (const struct sockaddr_in *)addr;
        int port = ntohs(sin->sin_port);
        size_t i;
        for (i = 0; i < domain_count(); i++) {
            const DomainRule *r = domain_get(i);
            struct sockaddr_in dst;
            if (!r || !r->has_v4) continue;
            if (r->orig_port != 0 && r->orig_port != port) continue;
            if (s_known_v4_count > 0 &&
                !is_known_original_v4(sin->sin_addr)) continue;
            memcpy(&dst, sin, sizeof(dst));
            dst.sin_addr = r->repl_v4;
            if (r->repl_port != 0) dst.sin_port = htons((uint16_t)r->repl_port);
            LOGI("connect: :%d -> %s:%d (rule %s)", port, r->replacement,
                 r->repl_port ? r->repl_port : port, r->original);
            return orig_connect(sockfd, (struct sockaddr *)&dst, addrlen);
        }
    }
    if (addr && addr->sa_family == AF_INET6 &&
        addrlen >= (socklen_t)sizeof(struct sockaddr_in6) &&
        domain_count() > 0) {
        const struct sockaddr_in6 *sin6 = (const struct sockaddr_in6 *)addr;
        int port = ntohs(sin6->sin6_port);
        size_t i;
        for (i = 0; i < domain_count(); i++) {
            const DomainRule *r = domain_get(i);
            struct sockaddr_in6 dst6;
            if (!r || !r->has_v6) continue;
            if (r->orig_port != 0 && r->orig_port != port) continue;
            if (s_known_v6_count > 0 &&
                !is_known_original_v6(&sin6->sin6_addr)) continue;
            memcpy(&dst6, sin6, sizeof(dst6));
            dst6.sin6_addr = r->repl_v6;
            if (r->repl_port != 0)
                dst6.sin6_port = htons((uint16_t)r->repl_port);
            LOGI("connect6: -> %s:%d (rule %s)", r->replacement,
                 r->repl_port ? r->repl_port : port, r->original);
            return orig_connect(sockfd, (struct sockaddr *)&dst6, addrlen);
        }
    }
    return orig_connect(sockfd, addr, addrlen);
}

void domain_redirect_install(void *module_base) {
    int ok = 0, total = 0;
    if (!module_base) return;
    LOGI("Installing domain-redirect hooks...");
    total++;
    if (plt_hook_symbol(module_base, "getaddrinfo", (void *)hook_getaddrinfo,
                        (void **)&orig_getaddrinfo) == 0) ok++;
    total++;
    if (plt_hook_symbol(module_base, "connect", (void *)hook_connect,
                        (void **)&orig_connect) == 0) ok++;
    if (plt_hook_symbol(module_base, "gethostbyname",
                        (void *)hook_gethostbyname,
                        (void **)&orig_gethostbyname) == 0) {
        ok++; total++;
    } else {
        LOGW("gethostbyname not imported; skipping (ok)");
    }
    if (plt_hook_symbol(module_base, "gethostbyname2",
                        (void *)hook_gethostbyname2,
                        (void **)&orig_gethostbyname2) == 0) {
        ok++; total++;
    } else {
        LOGW("gethostbyname2 not imported; skipping (ok)");
    }
    LOGI("Domain-redirect hooks: %d/%d installed", ok, total);
    if (!orig_getaddrinfo || !orig_connect)
        LOGW("Core DNS/connect hooks missing; redirect may be partial");
}


