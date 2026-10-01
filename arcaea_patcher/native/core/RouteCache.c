#include "RouteCache.h"

#include <pthread.h>
#include <string.h>
#include <sys/socket.h>

#include "DomainParser.h"

#define LOG_MODULE_TAG "Route"
#include "Logger.h"

/* Original (pre-redirect) addresses learned from one real DNS lookup per
 * rule. connect() only rewrites destinations listed here for the *same*
 * rule, so unrelated connections can never be hijacked. */
#define MAX_ORIG_V4_PER_RULE 4
#define MAX_ORIG_V6_PER_RULE 2

static struct in_addr s_orig_v4[DOMAIN_MAX_RULES][MAX_ORIG_V4_PER_RULE];
static size_t s_orig_v4_count[DOMAIN_MAX_RULES];
static struct in6_addr s_orig_v6[DOMAIN_MAX_RULES][MAX_ORIG_V6_PER_RULE];
static size_t s_orig_v6_count[DOMAIN_MAX_RULES];
static int s_snap_tried[DOMAIN_MAX_RULES];

static route_resolver_fn s_resolver = NULL;
static pthread_mutex_t s_lock = PTHREAD_MUTEX_INITIALIZER;

/* Both helpers expect s_lock to be held. */
static void remember_v4(size_t rule_idx, struct in_addr ip) {
  size_t i;
  for (i = 0; i < s_orig_v4_count[rule_idx]; i++) {
    if (s_orig_v4[rule_idx][i].s_addr == ip.s_addr)
      return;
  }
  if (s_orig_v4_count[rule_idx] < MAX_ORIG_V4_PER_RULE)
    s_orig_v4[rule_idx][s_orig_v4_count[rule_idx]++] = ip;
}

static void remember_v6(size_t rule_idx, const struct in6_addr *ip) {
  size_t i;
  for (i = 0; i < s_orig_v6_count[rule_idx]; i++) {
    if (memcmp(&s_orig_v6[rule_idx][i], ip, sizeof(struct in6_addr)) == 0)
      return;
  }
  if (s_orig_v6_count[rule_idx] < MAX_ORIG_V6_PER_RULE)
    s_orig_v6[rule_idx][s_orig_v6_count[rule_idx]++] = *ip;
}

void route_cache_set_resolver(route_resolver_fn resolver) {
  pthread_mutex_lock(&s_lock);
  s_resolver = resolver;
  pthread_mutex_unlock(&s_lock);
}

void route_cache_snapshot(size_t rule_idx) {
  struct addrinfo hints, *res = NULL, *p;
  route_resolver_fn resolver;
  size_t n4 = 0, n6 = 0;
  const DomainRule *rule;
  int rc;
  if (rule_idx >= DOMAIN_MAX_RULES)
    return;
  rule = domain_get(rule_idx);
  if (!rule || !rule->original[0])
    return;
  pthread_mutex_lock(&s_lock);
  resolver = s_resolver;
  if (!resolver || s_snap_tried[rule_idx]) {
    pthread_mutex_unlock(&s_lock);
    return;
  }
  s_snap_tried[rule_idx] = 1;
  pthread_mutex_unlock(&s_lock);

  memset(&hints, 0, sizeof(hints));
  hints.ai_socktype = SOCK_STREAM;
  rc = resolver(rule->original, NULL, &hints, &res);
  if (rc != 0 || !res) {
    pthread_mutex_lock(&s_lock);
    s_snap_tried[rule_idx] = 0; /* allow a later retry */
    pthread_mutex_unlock(&s_lock);
    return;
  }
  pthread_mutex_lock(&s_lock);
  for (p = res; p; p = p->ai_next) {
    if (p->ai_family == AF_INET &&
        p->ai_addrlen >= (socklen_t)sizeof(struct sockaddr_in)) {
      const struct sockaddr_in *sin = (const struct sockaddr_in *)p->ai_addr;
      remember_v4(rule_idx, sin->sin_addr);
    } else if (p->ai_family == AF_INET6 &&
               p->ai_addrlen >= (socklen_t)sizeof(struct sockaddr_in6)) {
      const struct sockaddr_in6 *sin6 =
          (const struct sockaddr_in6 *)p->ai_addr;
      remember_v6(rule_idx, &sin6->sin6_addr);
    }
  }
  n4 = s_orig_v4_count[rule_idx];
  n6 = s_orig_v6_count[rule_idx];
  pthread_mutex_unlock(&s_lock);
  freeaddrinfo(res);
  LOGI("rule[%zu] %s snapshot: v4=%zu v6=%zu", rule_idx, rule->original, n4,
       n6);
}

static void *warm_thread(void *arg) {
  size_t i;
  (void)arg;
  for (i = 0; i < domain_count(); i++)
    route_cache_snapshot(i);
  return NULL;
}

void route_cache_snapshot_all_async(void) {
  pthread_t tid;
  if (pthread_create(&tid, NULL, warm_thread, NULL) == 0)
    pthread_detach(tid);
  else
    LOGW("Snapshot thread not started; will snapshot on first lookup");
}

int route_cache_is_original_v4(size_t rule_idx, const struct in_addr *ip) {
  size_t i, n;
  int found = 0;
  if (rule_idx >= DOMAIN_MAX_RULES)
    return 0;
  pthread_mutex_lock(&s_lock);
  n = s_orig_v4_count[rule_idx];
  for (i = 0; i < n; i++) {
    if (s_orig_v4[rule_idx][i].s_addr == ip->s_addr) {
      found = 1;
      break;
    }
  }
  pthread_mutex_unlock(&s_lock);
  return found;
}

int route_cache_is_original_v6(size_t rule_idx, const struct in6_addr *ip) {
  size_t i, n;
  int found = 0;
  if (rule_idx >= DOMAIN_MAX_RULES)
    return 0;
  pthread_mutex_lock(&s_lock);
  n = s_orig_v6_count[rule_idx];
  for (i = 0; i < n; i++) {
    if (memcmp(&s_orig_v6[rule_idx][i], ip, sizeof(struct in6_addr)) == 0) {
      found = 1;
      break;
    }
  }
  pthread_mutex_unlock(&s_lock);
  return found;
}
