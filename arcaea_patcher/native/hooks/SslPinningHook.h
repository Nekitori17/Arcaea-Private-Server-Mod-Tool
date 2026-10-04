#pragma once

#include "HookManager.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Installs OpenSSL/BoringSSL verify-bypass hooks into module_base. */
void ssl_pinning_install(void *module_base);

/* Returns HookModule definition for registration with HookManager. */
const HookModule *ssl_pinning_get_module(void);

#ifdef __cplusplus
}
#endif
