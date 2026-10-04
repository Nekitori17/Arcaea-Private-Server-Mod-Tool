#pragma once

#include <netinet/in.h>
#include <stddef.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

#define DOMAIN_MAX_RULES 64
#define DOMAIN_MAX_HOST 128
#define DOMAIN_NOT_FOUND ((size_t)-1)

typedef struct {
  char original[DOMAIN_MAX_HOST];
  char replacement[DOMAIN_MAX_HOST];
  int orig_port; /* 0 = match any port */
  int repl_port; /* 0 = preserve original port */
  struct in_addr repl_v4;
  int has_v4;
  struct in6_addr repl_v6;
  int has_v6;
} DomainRule;

/* Loads redirect rules from a file path. Returns number of rules loaded. */
int domain_config_load_file(const char *path);

/* Loads redirect rules from an open stream. Returns number of rules loaded. */
int domain_config_load_stream(FILE *fp);

/* Returns number of currently loaded rules. */
size_t domain_config_count(void);

/* Returns pointer to rule at index, or NULL if out of bounds. */
const DomainRule *domain_config_get(size_t index);

/* Finds rule matching hostname (case-insensitive, ignoring trailing dot). */
const DomainRule *domain_config_find(const char *hostname);

/* Returns rule index matching hostname, or DOMAIN_NOT_FOUND. */
size_t domain_config_find_index(const char *hostname);

/* Clears all loaded rules. */
void domain_config_clear(void);

#ifdef __cplusplus
}
#endif
