package moe.neki.arc;

import android.content.Context;
import android.util.Log;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;

public class NekiHookLoader {
    private static final String TAG = "NekiHookLoader";
    private static final String CONFIG_FILENAME = "domain.cfg";
    private static volatile boolean sInitialized = false;

    // JNI entry point implemented in libneki.so (neki_hook.c)
    public static native void nativeInit(String configPath);

    /**
     * Initializes the domain routing and SSL bypass subsystem.
     * 
     * @param context Application or Activity context
     */
    public static synchronized void init(Context context) {
        if (sInitialized) {
            Log.d(TAG, "NekiHookLoader already initialized, skipping");
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

            // 2. Extract/update domain.cfg from APK assets to internal storage
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
                Log.w(TAG, "No domain.cfg in assets or failed to extract. Proceeding with existing config: " + e.getMessage());
            }

            // 3. Pre-load main game engine library (cocos2dcpp) to prevent race condition
            // where libneki.so searches /proc/self/maps before cocos2dcpp is loaded
            try {
                System.loadLibrary("cocos2dcpp");
                Log.i(TAG, "libcocos2dcpp.so pre-loaded successfully");
            } catch (Throwable t) {
                // If it fails or is already loaded by the engine lifecycle, log and continue
                Log.d(TAG, "libcocos2dcpp.so pre-load skipped: " + t.getMessage());
            }

            // 4. Load the native hook library
            System.loadLibrary("neki");
            Log.i(TAG, "libneki.so loaded successfully");

            // 5. Pass configuration file path and install PLT hooks
            String configPath = targetConfig.exists() ? targetConfig.getAbsolutePath() : "";
            nativeInit(configPath);

            sInitialized = true;
            Log.i(TAG, "NekiHook initialization completed successfully");

        } catch (Throwable t) {
            Log.e(TAG, "Fatal error during NekiHook initialization: " + t.getMessage(), t);
        }
    }
}