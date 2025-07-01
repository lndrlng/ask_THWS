#!/usr/bin/env bash
set -euo pipefail

# ----------- paths & versions -----------
PYTHON_VERSION=3.11.8
TMP=/tmp/python_build_$$
PREFIX=$HOME/local
OPENSSL_DIR=$PREFIX/openssl
LIBFFI_DIR=$PREFIX/libffi
BZIP2_DIR=$PREFIX/bzip2
SQLITE_DIR=$PREFIX/sqlite
LZMA_DIR=$PREFIX/xz

mkdir -p "$TMP" "$PREFIX"

check_header() {
    local hdr=$1 dir=$2 label=$3
    if [ -f "$dir/include/$hdr" ]; then
        echo "✅  $label header ($hdr) already present"
        return 0
    fi
    return 1
}

# -------------- OpenSSL -----------------
check_header "openssl/ssl.h" "$OPENSSL_DIR" "OpenSSL" || {
    echo "⬇️  Building OpenSSL…"
    cd "$TMP"
    wget -nc https://www.openssl.org/source/openssl-1.1.1w.tar.gz
    tar -xf openssl-1.1.1w.tar.gz && cd openssl-1.1.1w
    ./config --prefix="$OPENSSL_DIR" --openssldir="$OPENSSL_DIR"
    make -j"$(nproc)" && make install
    cd "$TMP" && rm -rf openssl-1.1.1w
    check_header "openssl/ssl.h" "$OPENSSL_DIR" "OpenSSL" || {
        echo "❌ OpenSSL header missing after build"
        exit 1
    }
}

# -------------- libffi ------------------
check_header "ffi.h" "$LIBFFI_DIR" "libffi" || {
    echo "⬇️  Building libffi…"
    cd "$TMP"
    wget -nc https://github.com/libffi/libffi/releases/download/v3.4.4/libffi-3.4.4.tar.gz
    tar -xf libffi-3.4.4.tar.gz && cd libffi-3.4.4
    ./configure --prefix="$LIBFFI_DIR" --enable-shared --includedir="$LIBFFI_DIR/include"
    make -j"$(nproc)" && make install
    cd "$TMP" && rm -rf libffi-3.4.4
    check_header "ffi.h" "$LIBFFI_DIR" "libffi" || {
        echo "❌ libffi header missing after build"
        exit 1
    }
}

# -------------- bzip2 -------------------
check_header "bzlib.h" "$BZIP2_DIR" "bzip2" || {
    echo "⬇️  Building bzip2…"
    cd "$TMP"
    wget -nc https://sourceware.org/pub/bzip2/bzip2-1.0.8.tar.gz
    tar -xf bzip2-1.0.8.tar.gz && cd bzip2-1.0.8
    make -j"$(nproc)" && make install PREFIX="$BZIP2_DIR"
    make clean
    mkdir -p "$BZIP2_DIR/lib"
    make -f Makefile-libbz2_so
    cp -av libbz2.so.* "$BZIP2_DIR/lib/"
    SO_BZ2=$(ls -1 "$BZIP2_DIR/lib"/libbz2.so.* | sort | tail -n1)
    ln -sf "$SO_BZ2" "$BZIP2_DIR/lib/libbz2.so"
    mkdir -p "$BZIP2_DIR/include"
    cp bzlib.h "$BZIP2_DIR/include"
    cd "$TMP" && rm -rf bzip2-1.0.8
    check_header "bzlib.h" "$BZIP2_DIR" "bzip2" || {
        echo "❌ bzip2 header missing after build"
        exit 1
    }
}

# -------------- sqlite3 ------------------
check_header "sqlite3.h" "$SQLITE_DIR" "SQLite3" || {
    echo "⬇️  Building SQLite3…"
    cd "$TMP"
    wget -nc https://www.sqlite.org/2024/sqlite-autoconf-3450200.tar.gz
    tar -xf sqlite-autoconf-3450200.tar.gz && cd sqlite-autoconf-3450200
    ./configure --prefix="$SQLITE_DIR"
    make -j"$(nproc)" && make install
    cd "$TMP" && rm -rf sqlite-autoconf-3450200
    check_header "sqlite3.h" "$SQLITE_DIR" "SQLite3" || {
        echo "❌ SQLite3 header missing after build"
        exit 1
    }
}

# -------------- LZMA (xz) ------------------
check_header "lzma.h" "$LZMA_DIR" "LZMA (xz)" || {
    echo "⬇️  Building LZMA (xz)..."
    cd "$TMP"
    # xz is the reference implementation of the LZMA format
    wget -nc https://github.com/tukaani-project/xz/releases/download/v5.4.6/xz-5.4.6.tar.gz
    tar -xf xz-5.4.6.tar.gz && cd xz-5.4.6
    ./configure --prefix="$LZMA_DIR"
    make -j"$(nproc)" && make install
    cd "$TMP" && rm -rf xz-5.4.6
    check_header "lzma.h" "$LZMA_DIR" "LZMA (xz)" || {
        echo "❌ LZMA header missing after build"
        exit 1
    }
}


# ---------- env for pyenv ----------
export CPPFLAGS="-I$OPENSSL_DIR/include -I$LIBFFI_DIR/include -I$BZIP2_DIR/include -I$SQLITE_DIR/include -I$LZMA_DIR/include"
export LDFLAGS="-L$OPENSSL_DIR/lib -L$LIBFFI_DIR/lib -L$BZIP2_DIR/lib -L$SQLITE_DIR/lib -L$LZMA_DIR/lib"
export LD_LIBRARY_PATH="$OPENSSL_DIR/lib:$LIBFFI_DIR/lib:$BZIP2_DIR/lib:$SQLITE_DIR/lib:$LZMA_DIR/lib:$LD_LIBRARY_PATH"
export PYTHON_CONFIGURE_OPTS="--with-openssl=$OPENSSL_DIR"

# ---------- pyenv ----------
export PATH="$HOME/.pyenv/bin:$PATH"
if ! command -v pyenv &>/dev/null; then curl https://pyenv.run | bash; fi
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

pyenv uninstall -f "$PYTHON_VERSION" || true

env \
    CPPFLAGS="$CPPFLAGS" \
    LDFLAGS="$LDFLAGS" \
    LD_LIBRARY_PATH="$LD_LIBRARY_PATH" \
    PYTHON_CONFIGURE_OPTS="$PYTHON_CONFIGURE_OPTS" \
    pyenv install -f "$PYTHON_VERSION"

pyenv global "$PYTHON_VERSION"

echo "🔍 Verifying Python module support..."

PYTHON_BIN="$(pyenv which python)"

verify_module() {
    local mod="$1" test_code="$2" label="$1"

    if output=$("$PYTHON_BIN" -c "$test_code" 2>&1); then
        echo "✅ $label: OK"
    else
        echo "❌ $label: FAILED"
        echo "   → $output"
    fi
}

verify_module "ssl" "import ssl; print(ssl.OPENSSL_VERSION.split()[1])"
verify_module "bz2" "import bz2; print(bz2.BZ2Compressor)"
verify_module "ctypes" "import ctypes; print(ctypes.sizeof(ctypes.c_void_p))"
verify_module "sqlite3" "import sqlite3; print(sqlite3.sqlite_version)"
verify_module "lzma" "import lzma; print(lzma.LZMACompressor)"

echo "✅ Module check complete."