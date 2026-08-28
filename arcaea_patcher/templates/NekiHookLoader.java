package moe.low.arc.custom;

import android.content.Context;
import android.util.Log;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;

public class NekiHookLoader {
    private static final String TAG = "NekiHookLoader";
    private static final String CONFIG_FILENAME = "domain.cfg";
    private static boolean sInitialized = false;

    // Keep only a single JNI function
    public static native void nativeInit(String configPath);

    public static synchronized void init(Context context) {
        if (sInitialized) {
            return;
        }

        if (context == null) {
            Log.w(TAG, "Context is null, cannot initialize domain hook");
            return;
        }

        try {
            File filesDir = context.getFilesDir();
            if (!filesDir.exists()) {
                filesDir.mkdirs();
            }

            File targetConfig = new File(filesDir, CONFIG_FILENAME);

            // FIX: Always extract and overwrite the domain.cfg file from the assets directory 
            // to prevent cache-related issues when the application is patched with a new IP/Config.
            try (InputStream in = context.getAssets().open(CONFIG_FILENAME)) {
                try (OutputStream out = new FileOutputStream(targetConfig)) {
                    byte[] buffer = new byte[4096];
                    int read;
                    while ((read = in.read(buffer)) != -1) {
                        out.write(buffer, 0, read);
                    }
                }
                Log.i(TAG, "Extracted/Updated domain.cfg from assets to " + targetConfig.getAbsolutePath());
            } catch (Exception e) {
                Log.d(TAG, "No domain.cfg found in assets. Will skip or use existing.");
            }

            // Load native library
            System.loadLibrary("neki");
            Log.i(TAG, "libneki.so loaded successfully");

            // Initialize hook with config file path
            String configPath = targetConfig.exists() ? targetConfig.getAbsolutePath() : "";
            nativeInit(configPath);
            
            sInitialized = true;
            Log.i(TAG, "Domain hook initialization complete");

        } catch (Throwable t) {
            Log.e(TAG, "Failed to initialize domain hook: " + t.getMessage(), t);
        }
    }
}