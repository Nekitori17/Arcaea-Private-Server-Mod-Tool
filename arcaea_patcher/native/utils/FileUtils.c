#include "FileUtils.h"

#include <string.h>
#include <unistd.h>

int file_exists(const char *path) {
  if (!path || !path[0])
    return 0;
  return access(path, R_OK) == 0;
}

int file_read_proc_cmdline(char *buf, size_t max_len) {
  FILE *fp;
  size_t n;
  if (!buf || max_len == 0)
    return 0;
  buf[0] = '\0';
  fp = fopen("/proc/self/cmdline", "r");
  if (!fp)
    return 0;
  n = fread(buf, 1, max_len - 1, fp);
  fclose(fp);
  if (n > 0) {
    buf[n] = '\0';
    return 1;
  }
  return 0;
}

int file_read_line(FILE *fp, char *buf, size_t max_len) {
  if (!fp || !buf || max_len == 0)
    return -1;
  if (!fgets(buf, (int)max_len, fp))
    return -1;
  buf[strcspn(buf, "\r\n")] = '\0';
  return (int)strlen(buf);
}
