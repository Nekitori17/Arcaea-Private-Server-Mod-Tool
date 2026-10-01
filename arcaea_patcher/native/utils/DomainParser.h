#pragma once

#include <netinet/in.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define DOMAIN_MAX_RULES 64
#define DOMAIN_MAX_HOST 128

typedef struct {
  char original[DOMAIN_MAX_HOST];
  char replacement[DOMAIN_MAX_HOST];
  int orig_port; /* 0 = any port */
  int repl_port; /* 0 = keep original port */
  struct in_addr repl_v4;
  int has_v4;
  struct in6_addr repl_v6;
  int has_v6;
} DomainRule;

/* Load "original[ :port]=replacement[ :port]" lines. Returns rule count. */
int domain_load(const char *config_path);

/* Exact hostname match, or NULL. */
const DomainRule *domain_find(const char *hostname);

size_t domain_count(void);
const DomainRule *domain_get(size_t index);

/* Auto-locate files/domain.cfg under the app data dir. Never returns NULL. */
const char *domain_resolve_config_path(void);

#ifdef __cplusplus
}
#endif
