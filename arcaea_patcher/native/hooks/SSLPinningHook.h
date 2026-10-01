#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/* Install OpenSSL/BoringSSL verify-bypass hooks into module_base. */
void ssl_pinning_install(void *module_base);

#ifdef __cplusplus
}
#endif

