#include "SSLPinningHook.h"

#include <stddef.h>

#include "MemoryUtils.h"

#define LOG_MODULE_TAG "SSL"
#include "Logger.h"

static void (*orig_CTX_set_verify)(void *, int, void *) = NULL;
static void (*orig_set_verify)(void *, int, void *) = NULL;
static void (*orig_CTX_custom_verify)(void *, int, void *) = NULL;
static int (*orig_X509_verify)(void *) = NULL;
static long (*orig_get_verify_result)(const void *) = NULL;
static void (*orig_CTX_cert_verify_cb)(void *, void *, void *) = NULL;
static void (*orig_set1_host)(void *, const char *) = NULL;
static int (*orig_X509_check_host)(void *, const char *, size_t, unsigned,
                                   void **) = NULL;

static void hook_CTX_set_verify(void *ctx, int mode, void *cb) {
  (void)mode;
  (void)cb;
  LOGI("SSL_CTX_set_verify -> VERIFY_NONE");
  if (orig_CTX_set_verify)
    orig_CTX_set_verify(ctx, 0, NULL);
}

static void hook_set_verify(void *ssl, int mode, void *cb) {
  (void)mode;
  (void)cb;
  LOGI("SSL_set_verify -> VERIFY_NONE");
  if (orig_set_verify)
    orig_set_verify(ssl, 0, NULL);
}

static void hook_CTX_custom_verify(void *ctx, int mode, void *cb) {
  (void)mode;
  (void)cb;
  LOGI("SSL_CTX_set_custom_verify -> VERIFY_NONE");
  if (orig_CTX_custom_verify)
    orig_CTX_custom_verify(ctx, 0, NULL);
}

static int hook_X509_verify(void *ctx) {
  (void)ctx;
  LOGI("X509_verify_cert -> 1 (bypass)");
  return 1;
}

static long hook_get_verify_result(const void *ssl) {
  (void)ssl;
  return 0; /* X509_V_OK: keep quiet to avoid log spam per request */
}

static void hook_CTX_cert_verify_cb(void *ctx, void *cb, void *arg) {
  (void)cb;
  (void)arg;
  LOGI("SSL_CTX_set_cert_verify_callback -> NULL");
  if (orig_CTX_cert_verify_cb)
    orig_CTX_cert_verify_cb(ctx, NULL, NULL);
}

static void hook_set1_host(void *ssl, const char *host) {
  LOGI("SSL_set1_host(%s) -> cleared (allow Reqable MITM)",
       host ? host : "(null)");
  /* Intentionally do NOT forward the expected hostname. */
  (void)ssl;
}

static int hook_X509_check_host(void *cert, const char *host, size_t len,
                                unsigned flags, void **peer) {
  (void)cert;
  (void)host;
  (void)len;
  (void)flags;
  (void)peer;
  LOGI("X509_check_host -> 1 (bypass)");
  return 1;
}

void ssl_pinning_install(void *module_base) {
  int ok = 0, total = 0;
  if (!module_base)
    return;
  LOGI("Installing SSL-pinning bypass hooks...");
#define TRY(sym, hook, orig)                                                   \
  do {                                                                         \
    total++;                                                                   \
    if (plt_hook_symbol(module_base, sym, (void *)(hook), (void **)(orig)) ==  \
        0)                                                                     \
      ok++;                                                                    \
    else                                                                       \
      LOGW(sym " not in PLT (static-linked? covered by elf_patcher)");         \
  } while (0)
  TRY("SSL_CTX_set_verify", hook_CTX_set_verify, &orig_CTX_set_verify);
  TRY("SSL_set_verify", hook_set_verify, &orig_set_verify);
  TRY("SSL_CTX_set_custom_verify", hook_CTX_custom_verify,
      &orig_CTX_custom_verify);
  TRY("X509_verify_cert", hook_X509_verify, &orig_X509_verify);
  TRY("SSL_get_verify_result", hook_get_verify_result, &orig_get_verify_result);
  TRY("SSL_CTX_set_cert_verify_callback", hook_CTX_cert_verify_cb,
      &orig_CTX_cert_verify_cb);
  TRY("SSL_set1_host", hook_set1_host, &orig_set1_host);
  TRY("X509_check_host", hook_X509_check_host, &orig_X509_check_host);
#undef TRY
  LOGI("SSL hooks: %d/%d installed", ok, total);
  if (ok == 0)
    LOGW("No SSL PLT imports (expected: OpenSSL static-linked); "
         "native elf_patcher + Java smali + NSC still apply");
}
