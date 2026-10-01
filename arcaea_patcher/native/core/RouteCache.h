#pragma once

#include <netdb.h>
#include <netinet/in.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Resolver used to learn the *original* addresses of a rule (normally the
 * saved libc getaddrinfo pointer from the redirect hook). */
typedef int (*route_resolver_fn)(const char *, const char *,
                                 const struct addrinfo *,
                                 struct addrinfo **);

/* Registers the resolver used by route_cache_snapshot(); set it before the
 * hooks can fire. Passing NULL disables snapshotting. */
void route_cache_set_resolver(route_resolver_fn resolver);

/* Resolves the original hostname of `rule_idx` once and remembers its
 * addresses (no-op on later calls / without a resolver). Thread-safe. */
void route_cache_snapshot(size_t rule_idx);

/* Warms the cache for every configured rule on a detached thread. */
void route_cache_snapshot_all_async(void);

/* 1 when `ip` is one of the original addresses previously learned for the
 * given rule index. */
int route_cache_is_original_v4(size_t rule_idx, const struct in_addr *ip);
int route_cache_is_original_v6(size_t rule_idx, const struct in6_addr *ip);

#ifdef __cplusplus
}
#endif
