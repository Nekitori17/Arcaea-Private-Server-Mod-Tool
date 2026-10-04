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

    .line 15
    const/4 v0, 0x0

    sput-boolean v0, Lmoe/neki/arc/NekiLoader;->sInitialized:Z

    return-void
.end method

.method public constructor <init>()V
    .locals 0

    .line 12
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method

.method private static extractDomainConfig(Landroid/content/Context;Ljava/io/File;)V
    .locals 5

    .line 85
    const-string v0, "NekiLoader"

    :try_start_2
    invoke-virtual {p0}, Landroid/content/Context;->getAssets()Landroid/content/res/AssetManager;

    move-result-object p0

    const-string v1, "domain.cfg"

    invoke-virtual {p0, v1}, Landroid/content/res/AssetManager;->open(Ljava/lang/String;)Ljava/io/InputStream;

    move-result-object p0
    :try_end_c
    .catch Ljava/lang/Exception; {:try_start_2 .. :try_end_c} :catch_5d

    .line 86
    :try_start_c
    new-instance v1, Ljava/io/FileOutputStream;

    invoke-direct {v1, p1}, Ljava/io/FileOutputStream;-><init>(Ljava/io/File;)V
    :try_end_11
    .catchall {:try_start_c .. :try_end_11} :catchall_51

    .line 87
    const/16 v2, 0x1000

    :try_start_13
    new-array v2, v2, [B

    .line 89
    :goto_15
    invoke-virtual {p0, v2}, Ljava/io/InputStream;->read([B)I

    move-result v3

    const/4 v4, -0x1

    if-eq v3, v4, :cond_21

    .line 90
    const/4 v4, 0x0

    invoke-virtual {v1, v2, v4, v3}, Ljava/io/OutputStream;->write([BII)V

    goto :goto_15

    .line 92
    :cond_21
    invoke-virtual {v1}, Ljava/io/OutputStream;->flush()V
    :try_end_24
    .catchall {:try_start_13 .. :try_end_24} :catchall_47

    .line 93
    :try_start_24
    invoke-virtual {v1}, Ljava/io/OutputStream;->close()V

    .line 94
    new-instance v1, Ljava/lang/StringBuilder;

    invoke-direct {v1}, Ljava/lang/StringBuilder;-><init>()V

    const-string v2, "Extracted domain.cfg to: "

    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v1

    invoke-virtual {p1}, Ljava/io/File;->getAbsolutePath()Ljava/lang/String;

    move-result-object p1

    invoke-virtual {v1, p1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p1

    invoke-static {v0, p1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I
    :try_end_41
    .catchall {:try_start_24 .. :try_end_41} :catchall_51

    .line 95
    if-eqz p0, :cond_46

    :try_start_43
    invoke-virtual {p0}, Ljava/io/InputStream;->close()V
    :try_end_46
    .catch Ljava/lang/Exception; {:try_start_43 .. :try_end_46} :catch_5d

    .line 98
    :cond_46
    goto :goto_78

    .line 86
    :catchall_47
    move-exception p1

    :try_start_48
    invoke-virtual {v1}, Ljava/io/OutputStream;->close()V
    :try_end_4b
    .catchall {:try_start_48 .. :try_end_4b} :catchall_4c

    goto :goto_50

    :catchall_4c
    move-exception v1

    :try_start_4d
    invoke-virtual {p1, v1}, Ljava/lang/Throwable;->addSuppressed(Ljava/lang/Throwable;)V

    :goto_50
    throw p1
    :try_end_51
    .catchall {:try_start_4d .. :try_end_51} :catchall_51

    .line 85
    :catchall_51
    move-exception p1

    if-eqz p0, :cond_5c

    :try_start_54
    invoke-virtual {p0}, Ljava/io/InputStream;->close()V
    :try_end_57
    .catchall {:try_start_54 .. :try_end_57} :catchall_58

    goto :goto_5c

    :catchall_58
    move-exception p0

    :try_start_59
    invoke-virtual {p1, p0}, Ljava/lang/Throwable;->addSuppressed(Ljava/lang/Throwable;)V

    :cond_5c
    :goto_5c
    throw p1
    :try_end_5d
    .catch Ljava/lang/Exception; {:try_start_59 .. :try_end_5d} :catch_5d

    .line 95
    :catch_5d
    move-exception p0

    .line 96
    new-instance p1, Ljava/lang/StringBuilder;

    invoke-direct {p1}, Ljava/lang/StringBuilder;-><init>()V

    const-string v1, "No domain.cfg in assets or failed to extract. Proceeding with existing config: "

    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object p1

    .line 97
    invoke-virtual {p0}, Ljava/lang/Exception;->getMessage()Ljava/lang/String;

    move-result-object p0

    invoke-virtual {p1, p0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object p0

    invoke-virtual {p0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p0

    .line 96
    invoke-static {v0, p0}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;)I

    .line 99
    :goto_78
    return-void
.end method

.method public static declared-synchronized init(Landroid/content/Context;)V
    .locals 7

    const-class v0, Lmoe/neki/arc/NekiLoader;

    monitor-enter v0

    .line 26
    :try_start_3
    sget-boolean v1, Lmoe/neki/arc/NekiLoader;->sInitialized:Z

    if-eqz v1, :cond_10

    .line 27
    const-string p0, "NekiLoader"

    const-string v1, "NekiLoader already initialized, skipping"

    invoke-static {p0, v1}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I
    :try_end_e
    .catchall {:try_start_3 .. :try_end_e} :catchall_c1

    .line 28
    monitor-exit v0

    return-void

    .line 31
    :cond_10
    if-nez p0, :cond_1b

    .line 32
    :try_start_12
    const-string p0, "NekiLoader"

    const-string v1, "Context is null, cannot initialize hook loader"

    invoke-static {p0, v1}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;)I
    :try_end_19
    .catchall {:try_start_12 .. :try_end_19} :catchall_c1

    .line 33
    monitor-exit v0

    return-void

    .line 38
    :cond_1b
    :try_start_1b
    invoke-virtual {p0}, Landroid/content/Context;->getFilesDir()Ljava/io/File;

    move-result-object v1

    .line 39
    if-eqz v1, :cond_2a

    invoke-virtual {v1}, Ljava/io/File;->exists()Z

    move-result v2

    if-nez v2, :cond_2a

    .line 40
    invoke-virtual {v1}, Ljava/io/File;->mkdirs()Z

    .line 43
    :cond_2a
    new-instance v2, Ljava/io/File;

    const-string v3, "domain.cfg"

    invoke-direct {v2, v1, v3}, Ljava/io/File;-><init>(Ljava/io/File;Ljava/lang/String;)V

    .line 45
    invoke-virtual {v2}, Ljava/io/File;->exists()Z

    move-result v1

    if-eqz v1, :cond_6f

    invoke-virtual {v2}, Ljava/io/File;->length()J

    move-result-wide v3

    const-wide/16 v5, 0x0

    cmp-long v1, v3, v5

    if-lez v1, :cond_6f

    .line 46
    invoke-static {v2}, Lmoe/neki/arc/NekiLoader;->isValidConfig(Ljava/io/File;)Z

    move-result v1

    if-eqz v1, :cond_64

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

    goto :goto_72

    .line 49
    :cond_64
    const-string v1, "NekiLoader"

    const-string v3, "Existing domain.cfg is invalid; re-extracting from assets"

    invoke-static {v1, v3}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;)I

    .line 50
    invoke-static {p0, v2}, Lmoe/neki/arc/NekiLoader;->extractDomainConfig(Landroid/content/Context;Ljava/io/File;)V

    goto :goto_72

    .line 53
    :cond_6f
    invoke-static {p0, v2}, Lmoe/neki/arc/NekiLoader;->extractDomainConfig(Landroid/content/Context;Ljava/io/File;)V
    :try_end_72
    .catchall {:try_start_1b .. :try_end_72} :catchall_a2

    .line 58
    :goto_72
    :try_start_72
    const-string p0, "neki"

    invoke-static {p0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V

    .line 59
    const-string p0, "NekiLoader"

    const-string v1, "libneki.so loaded successfully"

    invoke-static {p0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I
    :try_end_7e
    .catchall {:try_start_72 .. :try_end_7e} :catchall_98

    .line 64
    nop

    .line 68
    :try_start_7f
    invoke-static {}, Lmoe/neki/arc/NekiLoader;->nativeInit()V
    :try_end_82
    .catchall {:try_start_7f .. :try_end_82} :catchall_8e

    .line 73
    nop

    .line 75
    const/4 p0, 0x1

    :try_start_84
    sput-boolean p0, Lmoe/neki/arc/NekiLoader;->sInitialized:Z

    .line 76
    const-string p0, "NekiLoader"

    const-string v1, "NekiHook initialization completed successfully"

    invoke-static {p0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 80
    goto :goto_bf

    .line 69
    :catchall_8e
    move-exception p0

    .line 70
    const-string v1, "NekiLoader"

    const-string v2, "nativeInit() failed - hooks may be partially installed or missing"

    invoke-static {v1, v2, p0}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I
    :try_end_96
    .catchall {:try_start_84 .. :try_end_96} :catchall_a2

    .line 72
    monitor-exit v0

    return-void

    .line 60
    :catchall_98
    move-exception p0

    .line 61
    :try_start_99
    const-string v1, "NekiLoader"

    const-string v2, "Failed to load libneki.so - domain routing and SSL bypass hooks will NOT be installed"

    invoke-static {v1, v2, p0}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I
    :try_end_a0
    .catchall {:try_start_99 .. :try_end_a0} :catchall_a2

    .line 63
    monitor-exit v0

    return-void

    .line 78
    :catchall_a2
    move-exception p0

    .line 79
    :try_start_a3
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
    :try_end_bf
    .catchall {:try_start_a3 .. :try_end_bf} :catchall_c1

    .line 81
    :goto_bf
    monitor-exit v0

    return-void

    .line 25
    :catchall_c1
    move-exception p0

    :try_start_c2
    monitor-exit v0
    :try_end_c3
    .catchall {:try_start_c2 .. :try_end_c3} :catchall_c1

    throw p0
.end method

.method private static isValidConfig(Ljava/io/File;)Z
    .locals 6

    .line 107
    const/4 v0, 0x0

    if-eqz p0, :cond_a3

    invoke-virtual {p0}, Ljava/io/File;->exists()Z

    move-result v1

    if-eqz v1, :cond_a3

    invoke-virtual {p0}, Ljava/io/File;->length()J

    move-result-wide v1

    const-wide/16 v3, 0x0

    cmp-long v5, v1, v3

    if-nez v5, :cond_15

    goto/16 :goto_a3

    .line 110
    :cond_15
    :try_start_15
    new-instance v1, Ljava/io/BufferedReader;

    new-instance v2, Ljava/io/FileReader;

    invoke-direct {v2, p0}, Ljava/io/FileReader;-><init>(Ljava/io/File;)V

    invoke-direct {v1, v2}, Ljava/io/BufferedReader;-><init>(Ljava/io/Reader;)V
    :try_end_1f
    .catch Ljava/lang/Exception; {:try_start_15 .. :try_end_1f} :catch_a1

    .line 112
    const/4 p0, 0x0

    .line 113
    :cond_20
    :goto_20
    :try_start_20
    invoke-virtual {v1}, Ljava/io/BufferedReader;->readLine()Ljava/lang/String;

    move-result-object v2

    if-eqz v2, :cond_92

    .line 114
    invoke-virtual {v2}, Ljava/lang/String;->trim()Ljava/lang/String;

    move-result-object v2

    .line 115
    invoke-virtual {v2}, Ljava/lang/String;->isEmpty()Z

    move-result v3

    if-nez v3, :cond_20

    const-string v3, "#"

    invoke-virtual {v2, v3}, Ljava/lang/String;->startsWith(Ljava/lang/String;)Z

    move-result v3

    if-eqz v3, :cond_39

    .line 116
    goto :goto_20

    .line 118
    :cond_39
    const/16 p0, 0x3d

    invoke-virtual {v2, p0}, Ljava/lang/String;->indexOf(I)I

    move-result p0

    .line 119
    if-lez p0, :cond_8d

    invoke-virtual {v2}, Ljava/lang/String;->length()I

    move-result v3

    const/4 v4, 0x1

    sub-int/2addr v3, v4

    if-ne p0, v3, :cond_4a

    goto :goto_8d

    .line 122
    :cond_4a
    invoke-virtual {v2, v0, p0}, Ljava/lang/String;->substring(II)Ljava/lang/String;

    move-result-object v3

    invoke-virtual {v3}, Ljava/lang/String;->trim()Ljava/lang/String;

    move-result-object v3

    .line 123
    add-int/lit8 p0, p0, 0x1

    invoke-virtual {v2, p0}, Ljava/lang/String;->substring(I)Ljava/lang/String;

    move-result-object p0

    invoke-virtual {p0}, Ljava/lang/String;->trim()Ljava/lang/String;

    move-result-object p0

    .line 124
    invoke-virtual {v3}, Ljava/lang/String;->isEmpty()Z

    move-result v2

    if-nez v2, :cond_88

    invoke-virtual {p0}, Ljava/lang/String;->isEmpty()Z

    move-result v2

    if-eqz v2, :cond_69

    goto :goto_88

    .line 127
    :cond_69
    const/4 v2, 0x0

    :goto_6a
    invoke-virtual {p0}, Ljava/lang/String;->length()I

    move-result v3

    if-ge v2, v3, :cond_85

    .line 128
    invoke-virtual {p0, v2}, Ljava/lang/String;->charAt(I)C

    move-result v3
    :try_end_74
    .catchall {:try_start_20 .. :try_end_74} :catchall_97

    .line 129
    const/16 v5, 0x20

    if-lt v3, v5, :cond_80

    const/16 v5, 0x22

    if-ne v3, v5, :cond_7d

    goto :goto_80

    .line 127
    :cond_7d
    add-int/lit8 v2, v2, 0x1

    goto :goto_6a

    .line 130
    :cond_80
    :goto_80
    nop

    .line 136
    :try_start_81
    invoke-virtual {v1}, Ljava/io/BufferedReader;->close()V

    .line 130
    return v0

    .line 133
    :cond_85
    nop

    .line 134
    const/4 p0, 0x1

    goto :goto_20

    .line 125
    :cond_88
    :goto_88
    nop

    .line 136
    invoke-virtual {v1}, Ljava/io/BufferedReader;->close()V

    .line 125
    return v0

    .line 120
    :cond_8d
    :goto_8d
    nop

    .line 136
    invoke-virtual {v1}, Ljava/io/BufferedReader;->close()V

    .line 120
    return v0

    .line 135
    :cond_92
    nop

    .line 136
    invoke-virtual {v1}, Ljava/io/BufferedReader;->close()V
    :try_end_96
    .catch Ljava/lang/Exception; {:try_start_81 .. :try_end_96} :catch_a1

    .line 135
    return p0

    .line 110
    :catchall_97
    move-exception p0

    :try_start_98
    invoke-virtual {v1}, Ljava/io/BufferedReader;->close()V
    :try_end_9b
    .catchall {:try_start_98 .. :try_end_9b} :catchall_9c

    goto :goto_a0

    :catchall_9c
    move-exception v1

    :try_start_9d
    invoke-virtual {p0, v1}, Ljava/lang/Throwable;->addSuppressed(Ljava/lang/Throwable;)V

    :goto_a0
    throw p0
    :try_end_a1
    .catch Ljava/lang/Exception; {:try_start_9d .. :try_end_a1} :catch_a1

    .line 136
    :catch_a1
    move-exception p0

    .line 137
    return v0

    .line 108
    :cond_a3
    :goto_a3
    return v0
.end method

.method public static native nativeInit()V
.end method
