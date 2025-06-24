{
  description = "Minimal LightRAG project dev shell with venvShellHook";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
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
    in {
      devShells.default = pkgs.mkShell {
        packages = [
          pkgs.python311
          pkgs.poetry
          pkgs.poetryPlugins.poetry-plugin-shell
          pkgs.stdenv.cc.cc.lib
          pkgs.pre-commit
          pkgs.git-lfs
        ];
        shellHook = ''
          export LD_LIBRARY_PATH="${pkgs.cudatoolkit}/lib:${pkgs.stdenv.cc.cc.lib}/lib:/run/opengl-driver/lib:$LD_LIBRARY_PATH"
        '';
      };
    });
}
