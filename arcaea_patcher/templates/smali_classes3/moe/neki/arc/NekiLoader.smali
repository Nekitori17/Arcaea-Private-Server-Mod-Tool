.class public Lmoe/neki/arc/NekiLoader;
.super Ljava/lang/Object;
.source "NekiLoader.java"


# static fields
.field private static final CONFIG_FILENAME:Ljava/lang/String; = "domain.cfg"

.field private static final TAG:Ljava/lang/String; = "NekiLoader"

.field private static volatile sInitialized:Z


# direct methods
.method static constructor <clinit>()V
    .locals 1

    .line 13
    const/4 v0, 0x0

    sput-boolean v0, Lmoe/neki/arc/NekiLoader;->sInitialized:Z

    return-void
.end method

.method public constructor <init>()V
    .locals 0

    .line 10
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method

.method public static declared-synchronized init(Landroid/content/Context;)V
    .locals 7

    const-class v0, Lmoe/neki/arc/NekiLoader;

    monitor-enter v0

    .line 24
    :try_start_3
    sget-boolean v1, Lmoe/neki/arc/NekiLoader;->sInitialized:Z

    if-eqz v1, :cond_10

    .line 25
    const-string p0, "NekiLoader"

    const-string v1, "NekiLoader already initialized, skipping"

    invoke-static {p0, v1}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I
    :try_end_e
    .catchall {:try_start_3 .. :try_end_e} :catchall_128

    .line 26
    monitor-exit v0

    return-void

    .line 29
    :cond_10
    if-nez p0, :cond_1b

    .line 30
    :try_start_12
    const-string p0, "NekiLoader"

    const-string v1, "Context is null, cannot initialize hook loader"

    invoke-static {p0, v1}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;)I
    :try_end_19
    .catchall {:try_start_12 .. :try_end_19} :catchall_128

    .line 31
    monitor-exit v0

    return-void

    .line 36
    :cond_1b
    :try_start_1b
    invoke-virtual {p0}, Landroid/content/Context;->getFilesDir()Ljava/io/File;

    move-result-object v1

    .line 37
    if-eqz v1, :cond_2a

    invoke-virtual {v1}, Ljava/io/File;->exists()Z

    move-result v2

    if-nez v2, :cond_2a

    .line 38
    invoke-virtual {v1}, Ljava/io/File;->mkdirs()Z

    .line 41
    :cond_2a
    new-instance v2, Ljava/io/File;

    const-string v3, "domain.cfg"

    invoke-direct {v2, v1, v3}, Ljava/io/File;-><init>(Ljava/io/File;Ljava/lang/String;)V

    .line 46
    invoke-virtual {v2}, Ljava/io/File;->exists()Z

    move-result v1

    if-eqz v1, :cond_5f

    invoke-virtual {v2}, Ljava/io/File;->length()J

    move-result-wide v3

    const-wide/16 v5, 0x0

    cmp-long v1, v3, v5

    if-lez v1, :cond_5f

    .line 47
    const-string p0, "NekiLoader"

    new-instance v1, Ljava/lang/StringBuilder;

    invoke-direct {v1}, Ljava/lang/StringBuilder;-><init>()V

    const-string v3, "Keeping existing domain.cfg: "

    invoke-virtual {v1, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v1

    invoke-virtual {v2}, Ljava/io/File;->getAbsolutePath()Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v1

    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v1

    invoke-static {p0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I
    :try_end_5d
    .catchall {:try_start_1b .. :try_end_5d} :catchall_109

    goto/16 :goto_d9

    .line 49
    :cond_5f
    :try_start_5f
    invoke-virtual {p0}, Landroid/content/Context;->getAssets()Landroid/content/res/AssetManager;

    move-result-object p0

    const-string v1, "domain.cfg"

    invoke-virtual {p0, v1}, Landroid/content/res/AssetManager;->open(Ljava/lang/String;)Ljava/io/InputStream;

    move-result-object p0
    :try_end_69
    .catch Ljava/lang/Exception; {:try_start_5f .. :try_end_69} :catch_bc
    .catchall {:try_start_5f .. :try_end_69} :catchall_109

    .line 50
    :try_start_69
    new-instance v1, Ljava/io/FileOutputStream;

    invoke-direct {v1, v2}, Ljava/io/FileOutputStream;-><init>(Ljava/io/File;)V
    :try_end_6e
    .catchall {:try_start_69 .. :try_end_6e} :catchall_b0

    .line 51
    const/16 v3, 0x1000

    :try_start_70
    new-array v3, v3, [B

    .line 53
    :goto_72
    invoke-virtual {p0, v3}, Ljava/io/InputStream;->read([B)I

    move-result v4

    const/4 v5, -0x1

    if-eq v4, v5, :cond_7e

    .line 54
    const/4 v5, 0x0

    invoke-virtual {v1, v3, v5, v4}, Ljava/io/OutputStream;->write([BII)V

    goto :goto_72

    .line 56
    :cond_7e
    invoke-virtual {v1}, Ljava/io/OutputStream;->flush()V
    :try_end_81
    .catchall {:try_start_70 .. :try_end_81} :catchall_a6

    .line 57
    :try_start_81
    invoke-virtual {v1}, Ljava/io/OutputStream;->close()V

    .line 58
    const-string v1, "NekiLoader"

    new-instance v3, Ljava/lang/StringBuilder;

    invoke-direct {v3}, Ljava/lang/StringBuilder;-><init>()V

    const-string v4, "Extracted domain.cfg to: "

    invoke-virtual {v3, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v3

    invoke-virtual {v2}, Ljava/io/File;->getAbsolutePath()Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v3, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v2

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v2

    invoke-static {v1, v2}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I
    :try_end_a0
    .catchall {:try_start_81 .. :try_end_a0} :catchall_b0

    .line 59
    if-eqz p0, :cond_a5

    :try_start_a2
    invoke-virtual {p0}, Ljava/io/InputStream;->close()V
    :try_end_a5
    .catch Ljava/lang/Exception; {:try_start_a2 .. :try_end_a5} :catch_bc
    .catchall {:try_start_a2 .. :try_end_a5} :catchall_109

    .line 62
    :cond_a5
    goto :goto_d9

    .line 50
    :catchall_a6
    move-exception v2

    :try_start_a7
    invoke-virtual {v1}, Ljava/io/OutputStream;->close()V
    :try_end_aa
    .catchall {:try_start_a7 .. :try_end_aa} :catchall_ab

    goto :goto_af

    :catchall_ab
    move-exception v1

    :try_start_ac
    invoke-virtual {v2, v1}, Ljava/lang/Throwable;->addSuppressed(Ljava/lang/Throwable;)V

    :goto_af
    throw v2
    :try_end_b0
    .catchall {:try_start_ac .. :try_end_b0} :catchall_b0

    .line 49
    :catchall_b0
    move-exception v1

    if-eqz p0, :cond_bb

    :try_start_b3
    invoke-virtual {p0}, Ljava/io/InputStream;->close()V
    :try_end_b6
    .catchall {:try_start_b3 .. :try_end_b6} :catchall_b7

    goto :goto_bb

    :catchall_b7
    move-exception p0

    :try_start_b8
    invoke-virtual {v1, p0}, Ljava/lang/Throwable;->addSuppressed(Ljava/lang/Throwable;)V

    :cond_bb
    :goto_bb
    throw v1
    :try_end_bc
    .catch Ljava/lang/Exception; {:try_start_b8 .. :try_end_bc} :catch_bc
    .catchall {:try_start_b8 .. :try_end_bc} :catchall_109

    .line 59
    :catch_bc
    move-exception p0

    .line 60
    :try_start_bd
    const-string v1, "NekiLoader"

    new-instance v2, Ljava/lang/StringBuilder;

    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V

    const-string v3, "No domain.cfg in assets or failed to extract. Proceeding with existing config: "

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v2

    .line 61
    invoke-virtual {p0}, Ljava/lang/Exception;->getMessage()Ljava/lang/String;

    move-result-object p0

    invoke-virtual {v2, p0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object p0

    invoke-virtual {p0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p0

    .line 60
    invoke-static {v1, p0}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;)I
    :try_end_d9
    .catchall {:try_start_bd .. :try_end_d9} :catchall_109

    .line 67
    :goto_d9
    :try_start_d9
    const-string p0, "neki"

    invoke-static {p0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V

    .line 68
    const-string p0, "NekiLoader"

    const-string v1, "libneki.so loaded successfully"

    invoke-static {p0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I
    :try_end_e5
    .catchall {:try_start_d9 .. :try_end_e5} :catchall_ff

    .line 73
    nop

    .line 77
    :try_start_e6
    invoke-static {}, Lmoe/neki/arc/NekiLoader;->nativeInit()V
    :try_end_e9
    .catchall {:try_start_e6 .. :try_end_e9} :catchall_f5

    .line 82
    nop

    .line 84
    const/4 p0, 0x1

    :try_start_eb
    sput-boolean p0, Lmoe/neki/arc/NekiLoader;->sInitialized:Z

    .line 85
    const-string p0, "NekiLoader"

    const-string v1, "NekiHook initialization completed successfully"

    invoke-static {p0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 89
    goto :goto_126

    .line 78
    :catchall_f5
    move-exception p0

    .line 79
    const-string v1, "NekiLoader"

    const-string v2, "nativeInit() failed - hooks may be partially installed or missing"

    invoke-static {v1, v2, p0}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I
    :try_end_fd
    .catchall {:try_start_eb .. :try_end_fd} :catchall_109

    .line 81
    monitor-exit v0

    return-void

    .line 69
    :catchall_ff
    move-exception p0

    .line 70
    :try_start_100
    const-string v1, "NekiLoader"

    const-string v2, "Failed to load libneki.so - domain routing and SSL bypass hooks will NOT be installed"

    invoke-static {v1, v2, p0}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I
    :try_end_107
    .catchall {:try_start_100 .. :try_end_107} :catchall_109

    .line 72
    monitor-exit v0

    return-void

    .line 87
    :catchall_109
    move-exception p0

    .line 88
    :try_start_10a
    const-string v1, "NekiLoader"

    new-instance v2, Ljava/lang/StringBuilder;

    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V

    const-string v3, "Fatal error during NekiHook initialization: "

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v2

    invoke-virtual {p0}, Ljava/lang/Throwable;->getMessage()Ljava/lang/String;

    move-result-object v3

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v2

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v2

    invoke-static {v1, v2, p0}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I
    :try_end_126
    .catchall {:try_start_10a .. :try_end_126} :catchall_128

    .line 90
    :goto_126
    monitor-exit v0

    return-void

    .line 23
    :catchall_128
    move-exception p0

    :try_start_129
    monitor-exit v0
    :try_end_12a
    .catchall {:try_start_129 .. :try_end_12a} :catchall_128

    throw p0
.end method

.method public static native nativeInit()V
.end method
