#include "DomainParser.h"

#include <arpa/inet.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "FileUtils.h"

#define LOG_MODULE_TAG "Domain"
#include "Logger.h"

static DomainRule s_rules[DOMAIN_MAX_RULES];
static size_t s_count = 0;

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

// Hand-edited configs may contain control bytes or pasted quotes around an IP.
// Remove all control bytes (< 0x20) and double quotes so inet_pton() parses it
// correctly.
static int strip_host_junk(char *s) {
  char *dst;
  int removed = 0;
  if (!s)
    return 0;
  for (dst = s; *s; s++) {
    unsigned char c = (unsigned char)*s;
    if (c < 0x20 || c == '"') {
      removed++;
      continue;
    }
    *dst++ = *s;
  }
  *dst = '\0';
  return removed;
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

/* Case-insensitive hostname comparison; one trailing '.' on either side is
 * ignored ("Example.COM." == "example.com"). */
static int host_equals(const char *a, const char *b) {
  size_t la, lb, i;
  if (!a || !b)
    return 0;
  la = strlen(a);
  lb = strlen(b);
  while (la > 0 && a[la - 1] == '.')
    la--;
  while (lb > 0 && b[lb - 1] == '.')
    lb--;
  if (la != lb)
    return 0;
  for (i = 0; i < la; i++) {
    char ca = a[i];
    char cb = b[i];
    if (ca >= 'A' && ca <= 'Z')
      ca = (char)(ca + ('a' - 'A'));
    if (cb >= 'A' && cb <= 'Z')
      cb = (char)(cb + ('a' - 'A'));
    if (ca != cb)
      return 0;
  }
  return 1;
}

int domain_load(const char *config_path) {
  FILE *fp;
  char line[512];
  s_count = 0;
  if (!config_path || !config_path[0]) {
    LOGW("Empty domain config path");
    return 0;
  }
  fp = file_open_domain_config(config_path);
  if (!fp) {
    LOGW("No domain.cfg at %s (errno=%d); routing disabled", config_path, errno);
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
    if (strip_host_junk(left) + strip_host_junk(right) > 0)
      LOGW("Rule line carried control/quote bytes; sanitised before parsing");
    left = trim(left);
    right = trim(right);
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
  const DomainRule *rule;
  size_t i;
  if (!hostname)
    return NULL;
  for (i = 0; i < s_count; i++) {
    rule = &s_rules[i];
    if (host_equals(rule->original, hostname))
      return rule;
  }
  return NULL;
}

size_t domain_find_index(const char *hostname) {
  size_t i;
  if (!hostname)
    return DOMAIN_NOT_FOUND;
  for (i = 0; i < s_count; i++) {
    if (host_equals(s_rules[i].original, hostname))
      return i;
  }
  return DOMAIN_NOT_FOUND;
}

size_t domain_count(void) { return s_count; }

const DomainRule *domain_get(size_t index) {
  return (index < s_count) ? &s_rules[index] : NULL;
}
