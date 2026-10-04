#pragma once

#include <stddef.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Checks if a file exists and is readable. Returns 1 if accessible, 0 otherwise. */
int file_exists(const char *path);

/* Reads the process command line (package name) from /proc/self/cmdline into buf. */
int file_read_proc_cmdline(char *buf, size_t max_len);

/* Reads a single line from stream, stripping trailing CR/LF. Returns line length, or -1 on EOF. */
int file_read_line(FILE *fp, char *buf, size_t max_len);

#ifdef __cplusplus
}
#endif
