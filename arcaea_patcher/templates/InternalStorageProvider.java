package moe.low.arc.custom;

import android.database.Cursor;
import android.database.MatrixCursor;
import android.os.CancellationSignal;
import android.os.ParcelFileDescriptor;
import android.provider.DocumentsContract;
import android.provider.DocumentsProvider;
import android.webkit.MimeTypeMap;

import java.io.File;
import java.io.FileNotFoundException;

public class InternalStorageProvider extends DocumentsProvider {

    private static final String DEFAULT_ROOT_ID = "root";
    private static final String[] DEFAULT_ROOT_PROJECTION = new String[]{
            DocumentsContract.Root.COLUMN_ROOT_ID,
            DocumentsContract.Root.COLUMN_FLAGS,
            DocumentsContract.Root.COLUMN_ICON,
            DocumentsContract.Root.COLUMN_TITLE,
            DocumentsContract.Root.COLUMN_DOCUMENT_ID,
            DocumentsContract.Root.COLUMN_AVAILABLE_BYTES
    };
    private static final String[] DEFAULT_DOCUMENT_PROJECTION = new String[]{
            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_LAST_MODIFIED,
            DocumentsContract.Document.COLUMN_FLAGS,
            DocumentsContract.Document.COLUMN_SIZE
    };

    @Override
    public boolean onCreate() {
        return true;
    }

    /**
     * Helper method: Get the root directory (prevents code duplication)
     */
    private File getRootFile() {
        if (getContext() != null && getContext().getApplicationInfo().dataDir != null) {
            return new File(getContext().getApplicationInfo().dataDir);
        }
        return getContext().getFilesDir().getParentFile();
    }

    private File getFileForDocId(String documentId) throws FileNotFoundException {
        File root = getRootFile();
        File target = root;
        
        if (!DEFAULT_ROOT_ID.equals(documentId) && documentId != null && !documentId.isEmpty()) {
            target = new File(root, documentId);
        }
        
        if (!target.exists()) {
            throw new FileNotFoundException("Missing file for " + documentId);
        }
        if (!isPathSafe(root, target)) {
            // Block path traversal attacks
            throw new FileNotFoundException("Missing file for " + documentId);
        }
        return target;
    }

    private boolean isPathSafe(File root, File target) {
        try {
            String rootPath = root.getCanonicalPath();
            String targetPath = target.getCanonicalPath();
            return targetPath.equals(rootPath) || targetPath.startsWith(rootPath + File.separator);
        } catch (Exception e) {
            return false;
        }
    }

    private String getDocIdForFile(File file) {
        String path = file.getAbsolutePath();
        String rootPath = getRootFile().getAbsolutePath();
                            
        if (rootPath.equals(path)) {
            return DEFAULT_ROOT_ID;
        }
        
        // Prevent unsafe prefix matching
        String rootPrefix = rootPath.endsWith(File.separator) ? rootPath : rootPath + File.separator;
        if (path.startsWith(rootPrefix)) {
            return path.substring(rootPrefix.length());
        }
        return path;
    }

    @Override
    public Cursor queryRoots(String[] projection) throws FileNotFoundException {
        final MatrixCursor result = new MatrixCursor(projection != null ? projection : DEFAULT_ROOT_PROJECTION);
        File root = getRootFile();
        
        String appName = "Arcaea";
        int appIcon = android.R.drawable.ic_dialog_info;
        
        if (getContext() != null) {
            try {
                android.content.pm.PackageManager pm = getContext().getPackageManager();
                android.content.pm.ApplicationInfo appInfo = getContext().getApplicationInfo();
                
                CharSequence label = pm.getApplicationLabel(appInfo);
                if (label != null) {
                    appName = label.toString();
                }
                
                if (appInfo.icon != 0) {
                    appIcon = appInfo.icon;
                }
            } catch (Exception e) {

            }
        }

        final MatrixCursor.RowBuilder row = result.newRow();
        row.add(DocumentsContract.Root.COLUMN_ROOT_ID, DEFAULT_ROOT_ID);
        row.add(DocumentsContract.Root.COLUMN_DOCUMENT_ID, DEFAULT_ROOT_ID);
        
        row.add(DocumentsContract.Root.COLUMN_TITLE, appName);
        row.add(DocumentsContract.Root.COLUMN_FLAGS, 
                DocumentsContract.Root.FLAG_SUPPORTS_CREATE | 
                DocumentsContract.Root.FLAG_SUPPORTS_IS_CHILD |
                DocumentsContract.Root.FLAG_LOCAL_ONLY);
        row.add(DocumentsContract.Root.COLUMN_ICON, appIcon);
        
        row.add(DocumentsContract.Root.COLUMN_AVAILABLE_BYTES, root.getFreeSpace());
        return result;
    }

    /**
     * Required by FLAG_SUPPORTS_IS_CHILD (Android 11+).
     * Without this, persistable URI permission grants will throw SecurityException.
     */
    @Override
    public boolean isChildDocument(String parentDocumentId, String documentId) {
        try {
            File parent = getFileForDocId(parentDocumentId);
            File child = getFileForDocId(documentId);
            String parentPath = parent.getCanonicalPath();
            String childPath = child.getCanonicalPath();
            
            // A document is valid if it is the parent itself, 
            // or a child folder or file located within the parent.
            return parentPath.equals(childPath) || childPath.startsWith(parentPath + File.separator);
        } catch (Exception e) {
            return false;
        }
    }

    @Override
    public Cursor queryDocument(String documentId, String[] projection) throws FileNotFoundException {
        final MatrixCursor result = new MatrixCursor(projection != null ? projection : DEFAULT_DOCUMENT_PROJECTION);
        includeFile(result, documentId, null);
        return result;
    }

    @Override
    public Cursor queryChildDocuments(String parentDocumentId, String[] projection, String sortOrder) throws FileNotFoundException {
        final MatrixCursor result = new MatrixCursor(projection != null ? projection : DEFAULT_DOCUMENT_PROJECTION);
        final File parent = getFileForDocId(parentDocumentId);
        File[] children = parent.listFiles();
        if (children != null) {
            for (File file : children) {
                includeFile(result, null, file);
            }
        }
        return result;
    }

    @Override
    public ParcelFileDescriptor openDocument(String documentId, String mode, CancellationSignal signal) throws FileNotFoundException {
        final File file = getFileForDocId(documentId);
        final int accessMode;
        if ("r".equals(mode)) {
            accessMode = ParcelFileDescriptor.MODE_READ_ONLY;
        } else if ("w".equals(mode) || "wt".equals(mode)) {
            accessMode = ParcelFileDescriptor.MODE_WRITE_ONLY | ParcelFileDescriptor.MODE_CREATE | ParcelFileDescriptor.MODE_TRUNCATE;
        } else if ("wa".equals(mode)) {
            accessMode = ParcelFileDescriptor.MODE_WRITE_ONLY | ParcelFileDescriptor.MODE_CREATE | ParcelFileDescriptor.MODE_APPEND;
        } else if ("rw".equals(mode)) {
            accessMode = ParcelFileDescriptor.MODE_READ_WRITE | ParcelFileDescriptor.MODE_CREATE;
        } else if ("rwt".equals(mode)) {
            accessMode = ParcelFileDescriptor.MODE_READ_WRITE | ParcelFileDescriptor.MODE_CREATE | ParcelFileDescriptor.MODE_TRUNCATE;
        } else {
            throw new IllegalArgumentException("Invalid mode: " + mode);
        }
        return ParcelFileDescriptor.open(file, accessMode);
    }

    @Override
    public String createDocument(String documentId, String mimeType, String displayName) throws FileNotFoundException {
        File parent = getFileForDocId(documentId);
        
        // Sanitize file name to prevent path traversal
        String safeDisplayName = displayName.replace("/", "").replace("\\", "");
        File file = new File(parent, safeDisplayName);
        
        // Double-check the resulting path stays within root
        if (!isPathSafe(getRootFile(), file)) {
            throw new FileNotFoundException("Invalid document display name.");
        }
        
        try {
            if (DocumentsContract.Document.MIME_TYPE_DIR.equals(mimeType)) {
                file.mkdir();
            } else {
                file.createNewFile();
            }
            return getDocIdForFile(file);
        } catch (Exception e) {
            throw new FileNotFoundException("Failed to create document: " + e.getMessage());
        }
    }

    @Override
    public void deleteDocument(String documentId) throws FileNotFoundException {
        File file = getFileForDocId(documentId);
        if (!deleteRecursively(file)) {
            throw new FileNotFoundException("Failed to delete document");
        }
    }

    private boolean deleteRecursively(File file) {
        if (file.isDirectory()) {
            File[] children = file.listFiles();
            // Null check prevents NPE when directory cannot be listed
            if (children != null) {
                for (File child : children) {
                    deleteRecursively(child);
                }
            }
        }
        return file.delete();
    }

    @Override
    public String getDocumentType(String documentId) throws FileNotFoundException {
        File file = getFileForDocId(documentId);
        return getTypeForFile(file);
    }
    
    /**
     * Determines MIME type directly from a File object (avoids redundant docId lookup in loops)
     */
    private String getTypeForFile(File file) {
        if (file.isDirectory()) {
            return DocumentsContract.Document.MIME_TYPE_DIR;
        }
        return getTypeForName(file.getName());
    }

    private String getTypeForName(String name) {
        final int lastDot = name.lastIndexOf('.');
        if (lastDot >= 0) {
            final String extension = name.substring(lastDot + 1).toLowerCase();
            final String mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(extension);
            if (mime != null) {
                return mime;
            }
        }
        return "application/octet-stream";
    }

    private void includeFile(MatrixCursor result, String docId, File file) throws FileNotFoundException {
        if (docId == null) {
            docId = getDocIdForFile(file);
        } else {
            file = getFileForDocId(docId);
        }

        int flags = 0;
        if (file.isDirectory()) {
            flags |= DocumentsContract.Document.FLAG_DIR_SUPPORTS_CREATE;
        }
        flags |= DocumentsContract.Document.FLAG_SUPPORTS_WRITE;
        flags |= DocumentsContract.Document.FLAG_SUPPORTS_DELETE;

        final MatrixCursor.RowBuilder row = result.newRow();
        row.add(DocumentsContract.Document.COLUMN_DOCUMENT_ID, docId);
        row.add(DocumentsContract.Document.COLUMN_DISPLAY_NAME, file.getName());
        row.add(DocumentsContract.Document.COLUMN_SIZE, file.length());
        // Use File object directly instead of re-resolving from docId for performance
        row.add(DocumentsContract.Document.COLUMN_MIME_TYPE, getTypeForFile(file));
        row.add(DocumentsContract.Document.COLUMN_LAST_MODIFIED, file.lastModified());
        row.add(DocumentsContract.Document.COLUMN_FLAGS, flags);
    }
}