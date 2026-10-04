#include "StringUtils.h"

#include <arpa/inet.h>
#include <ctype.h>
#include <stdlib.h>
#include <string.h>

char *str_trim(char *s) {
  char *end;
  if (!s)
    return NULL;
  while (*s == ' ' || *s == '\t' || *s == '\r' || *s == '\n')
    s++;
  end = s + strlen(s);
  while (end > s && (end[-1] == ' ' || end[-1] == '\t' || end[-1] == '\r' || end[-1] == '\n'))
    end--;
  *end = '\0';
  return s;
}

int str_sanitize_host(char *s) {
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

int str_host_equals(const char *a, const char *b) {
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
    if (tolower((unsigned char)a[i]) != tolower((unsigned char)b[i]))
      return 0;
  }
  return 1;
}

void str_parse_host_port(const char *input, char *out_host, size_t host_size, int *out_port) {
  char buf[256];
  char *colon;
  char *rb;
  long port_val;

  if (out_port)
    *out_port = 0;
  if (!out_host || host_size == 0)
    return;
  out_host[0] = '\0';
  if (!input || !input[0])
    return;

  strncpy(buf, input, sizeof(buf) - 1);
  buf[sizeof(buf) - 1] = '\0';

  /* Format: [ipv6]:port or [ipv6] */
  if (buf[0] == '[') {
    rb = strchr(buf, ']');
    if (rb) {
      size_t len = (size_t)(rb - buf - 1);
      if (len >= host_size)
        len = host_size - 1;
      memcpy(out_host, buf + 1, len);
      out_host[len] = '\0';
      if (rb[1] == ':' && rb[2] != '\0' && out_port) {
        port_val = strtol(rb + 2, NULL, 10);
        if (port_val > 0 && port_val <= 65535)
          *out_port = (int)port_val;
      }
      return;
    }
  }

  /* Format: bare IPv6 literal (e.g. ::1 or 2001:db8::1) */
  if (strchr(buf, ':') != NULL) {
    struct in6_addr tmp6;
    if (inet_pton(AF_INET6, buf, &tmp6) == 1) {
      strncpy(out_host, buf, host_size - 1);
      out_host[host_size - 1] = '\0';
      return;
    }
  }

  /* Format: host:port or ipv4:port */
  colon = strrchr(buf, ':');
  if (colon && strchr(colon + 1, ':') == NULL && colon[1] != '\0') {
    char *end = NULL;
    port_val = strtol(colon + 1, &end, 10);
    if (end && *end == '\0' && port_val > 0 && port_val <= 65535) {
      if (out_port)
        *out_port = (int)port_val;
      *colon = '\0';
    }
  }

  strncpy(out_host, buf, host_size - 1);
  out_host[host_size - 1] = '\0';
}
