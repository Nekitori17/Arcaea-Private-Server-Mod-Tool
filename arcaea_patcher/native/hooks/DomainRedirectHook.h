#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/* Install getaddrinfo/gethostbyname/connect redirects into module_base. */
void domain_redirect_install(void *module_base);

#ifdef __cplusplus
}
#endif

