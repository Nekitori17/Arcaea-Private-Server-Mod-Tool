#pragma once

#include <netdb.h>
#include <netinet/in.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef int (*route_resolver_fn)(const char *, const char *,
                                 const struct addrinfo *,
                                 struct addrinfo **);

/* Sets libc getaddrinfo function pointer for DNS baseline queries. */
void route_cache_set_resolver(route_resolver_fn resolver);

/* Queries and caches real DNS addresses for the rule at rule_idx. */
void route_cache_snapshot(size_t rule_idx);

/* Warms the route cache for all loaded rules in a detached thread. */
void route_cache_snapshot_all_async(void);

/* Checks if ip matches an original resolved address for rule_idx. */
int route_cache_is_original_v4(size_t rule_idx, const struct in_addr *ip);
int route_cache_is_original_v6(size_t rule_idx, const struct in6_addr *ip);

#ifdef __cplusplus
}
#endif
