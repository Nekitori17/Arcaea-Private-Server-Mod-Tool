#include "DomainParser.h"

#include <arpa/inet.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define LOG_MODULE_TAG "Domain"
#include "Logger.h"

static DomainRule s_rules[DOMAIN_MAX_RULES];
static size_t s_count = 0;
static char s_cfg_path[512] = {0};

static char *trim(char *s) {
  char *end;
  if (!s)
    return s;
  while (*s == ' ' || *s == '\t' || *s == '\r' || *s == '\n')
    s++;
  end = s + strlen(s);
  while (end > s && (end[-1] == ' ' || end[-1] == '\t' || end[-1] == '\r' ||
                     end[-1] == '\n'))
    end--;
  *end = '\0';
  return s;
}

/* Split "host[:port]" -> host + port (0 = none/any).
 * Bare IPv6 ("::1") is NOT split; only "[v6]:port" carries a port. */
static void split_host_port(char *in, char *host, size_t host_sz, int *port) {
  char *colon;
  long p;
  *port = 0;
  host[0] = '\0';
  if (!in || !host || host_sz == 0 || !port)
    return;
  if (in[0] == '[') {
    char *rb = strchr(in, ']');
    if (rb) {
      size_t n = (size_t)(rb - in - 1);
      if (n >= host_sz)
        n = host_sz - 1;
      memcpy(host, in + 1, n);
      host[n] = '\0';
      if (rb[1] == ':' && rb[2] != '\0') {
        p = strtol(rb + 2, NULL, 10);
        if (p > 0 && p <= 65535)
          *port = (int)p;
      }
      return;
    }
  }
  if (strchr(in, ':') != NULL && in[0] != '\0') {
    struct in6_addr tmp6;
    if (inet_pton(AF_INET6, in, &tmp6) == 1) {
      strncpy(host, in, host_sz - 1);
      host[host_sz - 1] = '\0';
      return;
    }
  }
  colon = strrchr(in, ':');
  if (colon && strchr(colon + 1, ':') == NULL && colon[1] != '\0') {
    char *end = NULL;
    p = strtol(colon + 1, &end, 10);
    if (end && *end == '\0' && p > 0 && p <= 65535) {
      *port = (int)p;
      *colon = '\0';
    }
  }
  strncpy(host, in, host_sz - 1);
  host[host_sz - 1] = '\0';
}

int domain_load(const char *config_path) {
  FILE *fp;
  char line[512];
  s_count = 0;
  if (!config_path || !config_path[0]) {
    LOGW("Empty domain config path");
    return 0;
  }
  fp = fopen(config_path, "r");
  if (!fp) {
    LOGW("No domain.cfg at %s (errno=%d); routing disabled", config_path,
         errno);
    return 0;
  }
  while (fgets(line, sizeof(line), fp) && s_count < DOMAIN_MAX_RULES) {
    char *delim, *left, *right;
    char orig_h[DOMAIN_MAX_HOST], repl_h[DOMAIN_MAX_HOST];
    DomainRule *r;
    line[strcspn(line, "\r\n")] = '\0';
    if (line[0] == '#' || line[0] == '\0')
      continue;
    delim = strchr(line, '=');
    if (!delim)
      continue;
    *delim = '\0';
    left = trim(line);
    right = trim(delim + 1);
    if (!left[0] || !right[0])
      continue;
    r = &s_rules[s_count];
    memset(r, 0, sizeof(*r));
    split_host_port(left, orig_h, sizeof(orig_h), &r->orig_port);
    split_host_port(right, repl_h, sizeof(repl_h), &r->repl_port);
    strncpy(r->original, orig_h, sizeof(r->original) - 1);
    strncpy(r->replacement, repl_h, sizeof(r->replacement) - 1);
    if (inet_pton(AF_INET, r->replacement, &r->repl_v4) == 1)
      r->has_v4 = 1;
    if (inet_pton(AF_INET6, r->replacement, &r->repl_v6) == 1)
      r->has_v6 = 1;
    LOGI("Rule[%zu]: %s%s -> %s%s", s_count, r->original,
         r->orig_port ? " (port-filtered)" : "", r->replacement,
         r->repl_port ? " (port-redirect)" : "");
    s_count++;
  }
  fclose(fp);
  LOGI("Loaded %zu domain rule(s) from %s", s_count, config_path);
  return (int)s_count;
}

const DomainRule *domain_find(const char *hostname) {
  size_t i;
  if (!hostname)
    return NULL;
  for (i = 0; i < s_count; i++) {
    if (strcmp(s_rules[i].original, hostname) == 0)
      return &s_rules[i];
  }
  return NULL;
}

size_t domain_count(void) { return s_count; }

const DomainRule *domain_get(size_t index) {
  return (index < s_count) ? &s_rules[index] : NULL;
}

const char *domain_resolve_config_path(void) {
  static const char *pkgs[] = {"moe.neki.arc", "moe.low.arc", NULL};
  char cmdline[256] = {0};
  FILE *fp;
  int i;
  if (s_cfg_path[0])
    return s_cfg_path;
  fp = fopen("/proc/self/cmdline", "r");
  if (fp) {
    size_t n = fread(cmdline, 1, sizeof(cmdline) - 1, fp);
    fclose(fp);
    if (n > 0) {
      cmdline[n] = '\0';
      snprintf(s_cfg_path, sizeof(s_cfg_path),
               "/data/user/0/%s/files/domain.cfg", cmdline);
      if (access(s_cfg_path, R_OK) == 0)
        return s_cfg_path;
      snprintf(s_cfg_path, sizeof(s_cfg_path), "/data/data/%s/files/domain.cfg",
               cmdline);
      return s_cfg_path;
    }
  }
  for (i = 0; pkgs[i]; i++) {
    snprintf(s_cfg_path, sizeof(s_cfg_path), "/data/user/0/%s/files/domain.cfg",
             pkgs[i]);
    if (access(s_cfg_path, R_OK) == 0)
      return s_cfg_path;
  }
  snprintf(s_cfg_path, sizeof(s_cfg_path),
           "/data/user/0/moe.neki.arc/files/domain.cfg");
  return s_cfg_path;
}
