{
  description = "devShell for the rag tool";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = {
    self,
    nixpkgs,
    ...
  }: let
    system = "x86_64-linux";
    pkgs = import nixpkgs {inherit system;};
  in {
    devShells.${system}.default = pkgs.mkShell {
      buildInputs = [
        pkgs.python313
        # Scraper
        pkgs.python313Packages.scrapy
        pkgs.python313Packages.beautifulsoup4
        pkgs.python313Packages.pymupdf
        # Preprocess
      ];
    };
  };
}
