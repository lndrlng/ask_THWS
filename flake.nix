{
  description = "devShell for the rag tool";

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
  in {
    devShells.${system}.default = pkgs.mkShell {
      buildInputs = [
        pkgs.python313
        # Scraper
        pkgs.python313Packages.scrapy
        pkgs.python313Packages.beautifulsoup4
        pkgs.python313Packages.pymupdf
        # Preprocess
        pkgs.python313Packages.langdetect
        pkgs.python313Packages.langchain
        pkgs.python313Packages.pandas
        # Embedding
        pkgs.python313Packages.qdrant-client
        pkgs.python313Packages.sentence-transformers
        pkgs.python313Packages.tqdm
        pkgs.python313Packages.torch
        # Ollama with CUDA support
        # pkgs.ollama-cuda
        pkgs.ollama
      ];
    };
  };
}
