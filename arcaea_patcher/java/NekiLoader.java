package moe.neki.arc;

import android.content.Context;
import android.util.Log;
import java.io.File;
import java.io.FileOutputStream;
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

            // 2. Extract domain.cfg from APK assets only when it is missing,
            //    so runtime edits made in internal storage are preserved.
            //    Delete the file to restore the APK default.
            if (targetConfig.exists() && targetConfig.length() > 0) {
                Log.i(TAG, "Keeping existing domain.cfg: " + targetConfig.getAbsolutePath());
            } else {
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
}
