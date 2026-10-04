#include "DomainRedirectHook.h"

#include <arpa/inet.h>
#include <errno.h>
#include <netdb.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>

#include "DomainConfig.h"
#include "HookEngine.h"
#include "RouteCache.h"

#define LOG_MODULE_TAG "Redirect"
#include "Logger.h"

static int (*orig_getaddrinfo)(const char *, const char *,
                               const struct addrinfo *,
                               struct addrinfo **) = NULL;
static int (*orig_connect)(int, const struct sockaddr *, socklen_t) = NULL;
static struct hostent *(*orig_gethostbyname)(const char *) = NULL;
static struct hostent *(*orig_gethostbyname2)(const char *, int) = NULL;

static __thread struct hostent s_he;
static __thread struct in_addr s_he_addrs[1];
static __thread char *s_he_list[2];
static __thread char *s_he_aliases[1];
static __thread char s_he_name[DOMAIN_MAX_HOST];

/* Synthesizes a static hostent response for legacy resolver hooks. */
static struct hostent *make_redirect_hostent(const DomainRule *rule) {
  if (!rule || !rule->has_v4)
    return NULL;
  memset(&s_he, 0, sizeof(s_he));
  strncpy(s_he_name, rule->original, sizeof(s_he_name) - 1);
  s_he_name[sizeof(s_he_name) - 1] = '\0';
  s_he_addrs[0] = rule->repl_v4;
  s_he_list[0] = (char *)&s_he_addrs[0];
  s_he_list[1] = NULL;
  s_he.h_name = s_he_name;
  s_he.h_aliases = s_he_aliases;
  s_he.h_addrtype = AF_INET;
  s_he.h_length = sizeof(struct in_addr);
  s_he.h_addr_list = s_he_list;
  return &s_he;
}

/* Logs socket destination address and port for connection telemetry. */
static void log_socket_target(const char *prefix, int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
  char ip_str[INET6_ADDRSTRLEN] = {0};
  int port = 0;
  if (!addr)
    return;
  if (addr->sa_family == AF_INET && addrlen >= (socklen_t)sizeof(struct sockaddr_in)) {
    const struct sockaddr_in *sin = (const struct sockaddr_in *)addr;
    inet_ntop(AF_INET, &sin->sin_addr, ip_str, sizeof(ip_str));
    port = ntohs(sin->sin_port);
    LOGI("%s(fd=%d) target: %s:%d", prefix, sockfd, ip_str, port);
  } else if (addr->sa_family == AF_INET6 && addrlen >= (socklen_t)sizeof(struct sockaddr_in6)) {
    const struct sockaddr_in6 *sin6 = (const struct sockaddr_in6 *)addr;
    inet_ntop(AF_INET6, &sin6->sin6_addr, ip_str, sizeof(ip_str));
    port = ntohs(sin6->sin6_port);
    LOGI("%s(fd=%d) target: [%s]:%d", prefix, sockfd, ip_str, port);
  }
}

static int hook_getaddrinfo(const char *node, const char *service,
                            const struct addrinfo *hints,
                            struct addrinfo **res) {
  const DomainRule *rule;
  size_t rule_idx;
  int want_family;

  if (!orig_getaddrinfo)
    return EAI_FAIL;
  if (!node)
    return orig_getaddrinfo(node, service, hints, res);

  rule_idx = domain_config_find_index(node);
  if (rule_idx == DOMAIN_NOT_FOUND)
    return orig_getaddrinfo(node, service, hints, res);

  rule = domain_config_get(rule_idx);
  if (!rule)
    return orig_getaddrinfo(node, service, hints, res);

  /* Learn baseline IPs once for connect() redirection of cached lookups */
  route_cache_snapshot(rule_idx);

  /* If address family does not match literal IP, let connect-layer hook handle it */
  want_family = (hints && hints->ai_family != AF_UNSPEC) ? hints->ai_family : AF_UNSPEC;
  if (want_family != AF_UNSPEC && (rule->has_v4 || rule->has_v6)) {
    int family_ok = (want_family == AF_INET && rule->has_v4) ||
                    (want_family == AF_INET6 && rule->has_v6);
    if (!family_ok) {
      LOGW("getaddrinfo: %s requested family %d mismatch with replacement '%s'",
           node, want_family, rule->replacement);
      return orig_getaddrinfo(node, service, hints, res);
    }
  }

  // Port redirection
  if (rule->repl_port != 0) {
    char port_buf[8];
    snprintf(port_buf, sizeof(port_buf), "%d", rule->repl_port);
    LOGI("getaddrinfo: %s:%s -> %s:%s", node,
         (service && service[0]) ? service : "-", rule->replacement, port_buf);
    return orig_getaddrinfo(rule->replacement, port_buf, hints, res);
  }
  LOGI("getaddrinfo: %s -> %s", node, rule->replacement);
  return orig_getaddrinfo(rule->replacement, service, hints, res);
}

static struct hostent *hook_gethostbyname(const char *name) {
  const DomainRule *rule;
  size_t rule_idx;
  if (!name)
    return orig_gethostbyname ? orig_gethostbyname(name) : NULL;
  rule_idx = domain_config_find_index(name);
  if (rule_idx == DOMAIN_NOT_FOUND)
    return orig_gethostbyname ? orig_gethostbyname(name) : NULL;
  rule = domain_config_get(rule_idx);
  if (!rule || !rule->has_v4)
    return orig_gethostbyname ? orig_gethostbyname(name) : NULL;
  route_cache_snapshot(rule_idx);
  LOGI("gethostbyname: %s -> %s", name, rule->replacement);
  return make_redirect_hostent(rule);
}

static struct hostent *hook_gethostbyname2(const char *name, int af) {
  const DomainRule *rule;
  size_t rule_idx;
  if (!name)
    return orig_gethostbyname2 ? orig_gethostbyname2(name, af) : NULL;
  rule_idx = domain_config_find_index(name);
  if (rule_idx == DOMAIN_NOT_FOUND)
    return orig_gethostbyname2 ? orig_gethostbyname2(name, af) : NULL;
  rule = domain_config_get(rule_idx);
  if (!rule || af != AF_INET || !rule->has_v4)
    return orig_gethostbyname2 ? orig_gethostbyname2(name, af) : NULL;
  route_cache_snapshot(rule_idx);
  LOGI("gethostbyname2: %s -> %s", name, rule->replacement);
  return make_redirect_hostent(rule);
}

/* Wraps orig_connect and reports real failures with errno. Non-blocking
   progress states (EINPROGRESS/EINTR/EALREADY/EISCONN) are not failures. */
static int do_connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
  int rc = orig_connect(sockfd, addr, addrlen);
  if (rc != 0 && errno != EINPROGRESS && errno != EINTR && errno != EALREADY &&
      errno != EISCONN) {
    LOGW("connect failed (fd=%d): errno=%d (%s)", sockfd, errno, strerror(errno));
  }
  return rc;
}

static int hook_connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
  size_t i;
  if (!orig_connect) {
    errno = ENOTCONN;
    return -1;
  }

  log_socket_target("connect", sockfd, addr, addrlen);

  if (addr && domain_config_count() > 0) {
    if (addr->sa_family == AF_INET &&
        addrlen >= (socklen_t)sizeof(struct sockaddr_in)) {
      const struct sockaddr_in *sin = (const struct sockaddr_in *)addr;
      int port = ntohs(sin->sin_port);
      for (i = 0; i < domain_config_count(); i++) {
        const DomainRule *r = domain_config_get(i);
        struct sockaddr_in dst;
        int is_original;
        int is_replacement;
        if (!r || !r->has_v4)
          continue;
        is_original = route_cache_is_original_v4(i, &sin->sin_addr);
        is_replacement = (r->repl_v4.s_addr == sin->sin_addr.s_addr);
        if (!is_original && !is_replacement)
          continue;
        if (is_original) {
          if (r->orig_port != 0 && r->orig_port != port)
            continue;
          memcpy(&dst, sin, sizeof(dst));
          dst.sin_addr = r->repl_v4;
          if (r->repl_port != 0)
            dst.sin_port = htons((uint16_t)r->repl_port);
          LOGI("redirect: :%d -> %s:%d (%s)", port, r->replacement,
               r->repl_port ? r->repl_port : port, r->original);
          return do_connect(sockfd, (struct sockaddr *)&dst, addrlen);
        }
        /* Destination already is the replacement IP: only fix the port when
           getaddrinfo was not the path that resolved this connection. */
        if (r->repl_port == 0 || port == r->repl_port)
          continue;
        memcpy(&dst, sin, sizeof(dst));
        dst.sin_port = htons((uint16_t)r->repl_port);
        LOGI("redirect-port: %s:%d -> %s:%d (%s)", r->replacement, port,
             r->replacement, r->repl_port, r->original);
        return do_connect(sockfd, (struct sockaddr *)&dst, addrlen);
      }
    } else if (addr->sa_family == AF_INET6 &&
               addrlen >= (socklen_t)sizeof(struct sockaddr_in6)) {
      const struct sockaddr_in6 *sin6 = (const struct sockaddr_in6 *)addr;
      int port = ntohs(sin6->sin6_port);
      for (i = 0; i < domain_config_count(); i++) {
        const DomainRule *r = domain_config_get(i);
        struct sockaddr_in6 dst6;
        int is_original;
        int is_replacement;
        if (!r || !r->has_v6)
          continue;
        is_original = route_cache_is_original_v6(i, &sin6->sin6_addr);
        is_replacement = (memcmp(&r->repl_v6, &sin6->sin6_addr,
                                 sizeof(struct in6_addr)) == 0);
        if (!is_original && !is_replacement)
          continue;
        if (is_original) {
          if (r->orig_port != 0 && r->orig_port != port)
            continue;
          memcpy(&dst6, sin6, sizeof(dst6));
          dst6.sin6_addr = r->repl_v6;
          if (r->repl_port != 0)
            dst6.sin6_port = htons((uint16_t)r->repl_port);
          LOGI("redirect6: -> %s:%d (%s)", r->replacement,
               r->repl_port ? r->repl_port : port, r->original);
          return do_connect(sockfd, (struct sockaddr *)&dst6, addrlen);
        }
        if (r->repl_port == 0 || port == r->repl_port)
          continue;
        memcpy(&dst6, sin6, sizeof(dst6));
        dst6.sin6_port = htons((uint16_t)r->repl_port);
        LOGI("redirect6-port: %s:%d -> :%d (%s)", r->replacement, port,
             r->repl_port, r->original);
        return do_connect(sockfd, (struct sockaddr *)&dst6, addrlen);
      }
    }
  }
  return do_connect(sockfd, addr, addrlen);
}

void domain_redirect_install(void *module_base) {
  int ok = 0, total = 0;
  if (!module_base)
    return;
  LOGI("Installing domain-redirect hooks...");

  total++;
  if (plt_hook_symbol(module_base, "getaddrinfo", (void *)hook_getaddrinfo,
                      (void **)&orig_getaddrinfo) == 0)
    ok++;

  total++;
  if (plt_hook_symbol(module_base, "connect", (void *)hook_connect,
                      (void **)&orig_connect) == 0)
    ok++;

  if (plt_hook_symbol(module_base, "gethostbyname", (void *)hook_gethostbyname,
                      (void **)&orig_gethostbyname) == 0) {
    ok++;
    total++;
  }

  if (plt_hook_symbol(module_base, "gethostbyname2", (void *)hook_gethostbyname2,
                      (void **)&orig_gethostbyname2) == 0) {
    ok++;
    total++;
  }

  LOGI("Domain-redirect hooks: %d/%d installed", ok, total);
  if (!orig_getaddrinfo || !orig_connect)
    LOGW("Core DNS/connect hooks missing; redirect may be partial");

  route_cache_set_resolver(orig_getaddrinfo);
  if (domain_config_count() > 0 && orig_getaddrinfo)
    route_cache_snapshot_all_async();
}

static const HookModule s_domain_module = {
  .name = "DomainRedirect",
  .install = domain_redirect_install,
};

const HookModule *domain_redirect_get_module(void) {
  return &s_domain_module;
}
