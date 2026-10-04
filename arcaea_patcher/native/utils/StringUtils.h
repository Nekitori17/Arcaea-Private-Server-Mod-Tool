#pragma once

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Trims leading and trailing whitespace in-place. */
char *str_trim(char *s);

/* Removes double quotes and control characters (< 0x20) in-place. Returns count removed. */
int str_sanitize_host(char *s);

/* Case-insensitive hostname comparison, ignoring a single trailing dot. */
int str_host_equals(const char *a, const char *b);

/* Splits "host[:port]" or "[ipv6]:port" into host and port. Port is 0 if unspecified. */
void str_parse_host_port(const char *input, char *out_host, size_t host_size, int *out_port);

#ifdef __cplusplus
}
#endif
