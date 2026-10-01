#include "FileUtils.h"

#include <stdio.h>
#include <unistd.h>

static char s_cfg_path[512] = {0};

const char *file_resolve_domain_config_path(void) {
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

FILE *file_open_domain_config(const char *path) {
  if (!path || !path[0])
    return NULL;
  return fopen(path, "r");
}
