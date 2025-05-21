## Setup of the server

Since we're not allowed to use sudo and therefore we cannot install any software, we need to build python3.11 from source with its dependencied.

#### ✅ **Install OpenSSL from source (user-local)**

```bash
# Install OpenSSL to $HOME/openssl
cd $HOME
wget https://www.openssl.org/source/openssl-1.1.1w.tar.gz
tar -xzf openssl-1.1.1w.tar.gz
cd openssl-1.1.1w
./config --prefix=$HOME/openssl --openssldir=$HOME/openssl
make -j$(nproc)
make install
```

---

#### ✅ **Install Python 3.11 from source with OpenSSL support**

```bash
# Download and extract Python source
cd $HOME
wget https://www.python.org/ftp/python/3.11.8/Python-3.11.8.tgz
tar -xzf Python-3.11.8.tgz
cd Python-3.11.8

# Export paths for OpenSSL
export CPPFLAGS="-I$HOME/openssl/include"
export LDFLAGS="-L$HOME/openssl/lib"
export LD_LIBRARY_PATH="$HOME/openssl/lib:$LD_LIBRARY_PATH"
export PKG_CONFIG_PATH="$HOME/openssl/lib/pkgconfig"

# Configure and build Python
./configure --prefix=$HOME/python311 \
            --with-openssl=$HOME/openssl \
            --enable-optimizations
make -j$(nproc)
make install
```

---

#### ✅ **Test it**

```bash
# Add Python to your path (~/.bash_profile)
export PATH="$HOME/python311/bin:$PATH"

# Create and activate virtual env
python3.11 -m venv ~/.myenv
source ~/.myenv/bin/activate

# Confirm SSL works
python -m ssl  # should not error
pip install requests  # should succeed
```