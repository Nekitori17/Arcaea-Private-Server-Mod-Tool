package moe.neki.arc;

import android.content.Context;
import android.util.Log;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileReader;
import java.io.InputStream;
import java.io.OutputStream;

public class NekiLoader {
    private static final String TAG = "NekiLoader";
    private static final String CONFIG_FILENAME = "domain.cfg";
    private static volatile boolean sInitialized = false;

    // JNI entry point implemented in libneki.so (Main.c)
    public static native void nativeInit();

    /**
     * Initializes the domain routing and SSL bypass subsystem.
     *
     * @param context Application or Activity context
     */
    public static synchronized void init(Context context) {
        if (sInitialized) {
            Log.d(TAG, "NekiLoader already initialized, skipping");
            return;
        }

        if (context == null) {
            Log.w(TAG, "Context is null, cannot initialize hook loader");
            return;
        }

        try {
            // 1. Prepare target internal storage directory
            File filesDir = context.getFilesDir();
            if (filesDir != null && !filesDir.exists()) {
                filesDir.mkdirs();
            }

            File targetConfig = new File(filesDir, CONFIG_FILENAME);

            if (targetConfig.exists() && targetConfig.length() > 0) {
                if (isValidConfig(targetConfig)) {
                    Log.i(TAG, "Keeping existing domain.cfg: " + targetConfig.getAbsolutePath());
                } else {
                    Log.w(TAG, "Existing domain.cfg is invalid; re-extracting from assets");
                    extractDomainConfig(context, targetConfig);
                }
            } else {
                extractDomainConfig(context, targetConfig);
            }

            // 3. Load the native hook library
            try {
                System.loadLibrary("neki");
                Log.i(TAG, "libneki.so loaded successfully");
            } catch (Throwable t) {
                Log.e(TAG, "Failed to load libneki.so - domain routing and SSL " +
                        "bypass hooks will NOT be installed", t);
                return;
            }

            // 4. Install the native hooks
            try {
                nativeInit();
            } catch (Throwable t) {
                Log.e(TAG, "nativeInit() failed - hooks may be partially " +
                        "installed or missing", t);
                return;
            }

            sInitialized = true;
            Log.i(TAG, "NekiHook initialization completed successfully");

        } catch (Throwable t) {
            Log.e(TAG, "Fatal error during NekiHook initialization: " + t.getMessage(), t);
        }
    }

    /** Copies domain.cfg from the APK assets into internal storage. */
    private static void extractDomainConfig(Context context, File targetConfig) {
        try (InputStream in = context.getAssets().open(CONFIG_FILENAME)) {
            try (OutputStream out = new FileOutputStream(targetConfig)) {
                byte[] buffer = new byte[4096];
                int bytesRead;
                while ((bytesRead = in.read(buffer)) != -1) {
                    out.write(buffer, 0, bytesRead);
                }
                out.flush();
            }
            Log.i(TAG, "Extracted domain.cfg to: " + targetConfig.getAbsolutePath());
        } catch (Exception e) {
            Log.w(TAG, "No domain.cfg in assets or failed to extract. " +
                    "Proceeding with existing config: " + e.getMessage());
        }
    }

    /**
     * Validates that every rule line is {@code host=replacement} and that the
     * replacement is free of control bytes / quotes. Returns false for empty or
     * malformed content so the caller can restore the bundled default.
     */
    private static boolean isValidConfig(File file) {
        if (file == null || !file.exists() || file.length() == 0) {
            return false;
        }
        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
            String line;
            boolean anyRule = false;
            while ((line = reader.readLine()) != null) {
                String trimmed = line.trim();
                if (trimmed.isEmpty() || trimmed.startsWith("#")) {
                    continue;
                }
                int eq = trimmed.indexOf('=');
                if (eq <= 0 || eq == trimmed.length() - 1) {
                    return false;
                }
                String host = trimmed.substring(0, eq).trim();
                String value = trimmed.substring(eq + 1).trim();
                if (host.isEmpty() || value.isEmpty()) {
                    return false;
                }
                for (int i = 0; i < value.length(); i++) {
                    char c = value.charAt(i);
                    if (c < 0x20 || c == '"') {
                        return false;
                    }
                }
                anyRule = true;
            }
            return anyRule;
        } catch (Exception e) {
            return false;
        }
    }
}
