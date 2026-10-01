#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/* Install all PLT hooks. Returns 1 if core DNS+connect hooks are live. */
int hook_engine_install_all(void);

/* Install into one already-resolved module base. */
int hook_engine_install_for(void *module_base);

#ifdef __cplusplus
}
#endif

