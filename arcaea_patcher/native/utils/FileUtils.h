#pragma once

#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Auto-locates files/domain.cfg under the app data dir:
 *   1. /data/user/0/<package from /proc/self/cmdline>/files/domain.cfg
 *   2. /data/data/<same package>/files/domain.cfg
 *   3. well-known package fallbacks (moe.neki.arc, moe.low.arc)
 * The result is cached; never returns NULL.
 */
const char *file_resolve_domain_config_path(void);

/* Opens the domain config for reading; NULL when the path is unusable. */
FILE *file_open_domain_config(const char *path);

#ifdef __cplusplus
}
#endif
