from llama_cpp import Llama

#//pip install llama-cpp-python==0.2.23+cu121 --upgrade --force-reinstall --no-cache-dir --extra-index-url https://jllllll.github.io/llama-cpp-python-cuBLAS-wheels/AVX2/cu121


llm = Llama(
    model_path="D:/LLMS/mistral-7b-instruct-v0.2.Q6_K.gguf",
    n_gpu_layers=-1,
    verbose=True
)

try:
    layers_gpu = getattr(llm.model, "layers_offloaded", None)
    if layers_gpu and layers_gpu > 0:
        print(f"✅ CUDA is active! Layers offloaded: {layers_gpu}")
    else:
        print("❌ Still on CPU or GPU layers couldn't be assigned.")
except Exception as e:
    print(f"⚠️ Unable to detect CUDA usage: {e}")
