{
  description = "Minimal LightRAG project dev shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = import nixpkgs {
        inherit system;
        config = {
          allowUnfree = true;
          cudaSupport = true;
        };
      };

      pythonEnv = pkgs.python311.withPackages (ps:
        with ps; [
          langchain
          sentence-transformers
          faiss
          torch
          torchvision
          torchaudio
          fastapi
          uvicorn
          requests
          pymongo
          pypdf
          (openai.overridePythonAttrs (_: {doCheck = false;}))
        ]);
    in {
      devShells.default = pkgs.mkShell {
        packages = [
          pythonEnv
          pkgs.cudatoolkit
          pkgs.git
          pkgs.ollama
        ];
        shellHook = ''
          export LD_LIBRARY_PATH="${pkgs.cudaPackages.cudatoolkit}/lib:$LD_LIBRARY_PATH"
        '';
      };
    });
}
