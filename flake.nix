{
  description = "devShell for the RAG tool";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = {
    self,
    nixpkgs,
    ...
  }: let
    system = "x86_64-linux";
    pkgs = import nixpkgs {
      inherit system;
      config.allowUnfree = true;
    };

    python = pkgs.python311.override {
      packageOverrides = pyFinal: pyPrev: {
        torch = pyPrev.torch.override { cudaSupport = true; };
      };
    };

    pythonEnv = python.withPackages (ps:
      with ps; [
        # Scraper
        scrapy
        beautifulsoup4
        pymupdf
        # Preprocess
        langdetect
        langchain
        pandas
        # Embedding
        sentence-transformers
        tqdm
        qdrant-client
        # Mkdocs
        mkdocs
        mkdocs-material
      ]);
  in {
    devShells.${system}.default = pkgs.mkShell {
      buildInputs = [
        pythonEnv
        pkgs.ollama-cuda
        pkgs.commitizen
        pkgs.black
      ];
    };
  };
}
