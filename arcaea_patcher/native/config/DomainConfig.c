#include "DomainConfig.h"

#include <arpa/inet.h>
#include <errno.h>
#include <string.h>

#include "FileUtils.h"
#include "StringUtils.h"

#define LOG_MODULE_TAG "Domain"
#include "Logger.h"

static DomainRule s_rules[DOMAIN_MAX_RULES];
static size_t s_count = 0;

void domain_config_clear(void) {
  memset(s_rules, 0, sizeof(s_rules));
  s_count = 0;
}

size_t domain_config_count(void) {
  return s_count;
}

const DomainRule *domain_config_get(size_t index) {
  return (index < s_count) ? &s_rules[index] : NULL;
}

const DomainRule *domain_config_find(const char *hostname) {
  size_t i;
  if (!hostname)
    return NULL;
  for (i = 0; i < s_count; i++) {
    if (str_host_equals(s_rules[i].original, hostname))
      return &s_rules[i];
  }
  return NULL;
}

size_t domain_config_find_index(const char *hostname) {
  size_t i;
  if (!hostname)
    return DOMAIN_NOT_FOUND;
  for (i = 0; i < s_count; i++) {
    if (str_host_equals(s_rules[i].original, hostname))
      return i;
  }
  return DOMAIN_NOT_FOUND;
}

int domain_config_load_stream(FILE *fp) {
  char line[512];
  if (!fp)
    return 0;

  s_count = 0;
  while (file_read_line(fp, line, sizeof(line)) >= 0 && s_count < DOMAIN_MAX_RULES) {
    char *delim;
    char *left;
    char *right;
    char orig_host[DOMAIN_MAX_HOST];
    char repl_host[DOMAIN_MAX_HOST];
    DomainRule *rule;

    left = str_trim(line);
    if (!left || left[0] == '#' || left[0] == '\0')
      continue;

    delim = strchr(left, '=');
    if (!delim)
      continue;
    *delim = '\0';
    right = delim + 1;

    str_sanitize_host(left);
    str_sanitize_host(right);

    left = str_trim(left);
    right = str_trim(right);
    if (!left[0] || !right[0])
      continue;

    rule = &s_rules[s_count];
    memset(rule, 0, sizeof(*rule));

    str_parse_host_port(left, orig_host, sizeof(orig_host), &rule->orig_port);
    str_parse_host_port(right, repl_host, sizeof(repl_host), &rule->repl_port);

    strncpy(rule->original, orig_host, sizeof(rule->original) - 1);
    strncpy(rule->replacement, repl_host, sizeof(rule->replacement) - 1);

    if (inet_pton(AF_INET, rule->replacement, &rule->repl_v4) == 1)
      rule->has_v4 = 1;
    if (inet_pton(AF_INET6, rule->replacement, &rule->repl_v6) == 1)
      rule->has_v6 = 1;

    LOGI("Rule[%zu]: %s%s -> %s%s", s_count, rule->original,
         rule->orig_port ? " (port-filtered)" : "", rule->replacement,
         rule->repl_port ? " (port-redirect)" : "");
    s_count++;
  }

  return (int)s_count;
}

int domain_config_load_file(const char *path) {
  FILE *fp;
  int count;

  if (!path || !path[0]) {
    LOGW("Empty domain config path");
    return 0;
  }

  fp = fopen(path, "r");
  if (!fp) {
    LOGW("Cannot open config at %s (errno=%d)", path, errno);
    return 0;
  }

  count = domain_config_load_stream(fp);
  fclose(fp);

  LOGI("Loaded %d domain rule(s) from %s", count, path);
  return count;
}
