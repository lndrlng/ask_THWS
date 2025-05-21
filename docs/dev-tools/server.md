
# Setup Python on the Server

Since we are not allowed to use sudo, we need to provide some shared libraries and compile python with it.

### Installation

To install the custom pyenv version run first the script `install_python.sh`.

After creating the venv you need to patch it with:

```shell
echo 'export LD_LIBRARY_PATH="$HOME/local/openssl/lib:$HOME/local/libffi/lib:$HOME/local/bzip2/lib:$HOME/local/sqlite/lib:$LD_LIBRARY_PATH"' >> .venv/bin/activate
```