{
  description = "Audio ID calculator for FLAC folders";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          discid
          mutagen
        ]);
        
        discidScript = pkgs.writeShellApplication {
          name = "discid";
          runtimeInputs = [ pythonEnv pkgs.libdiscid ];
          text = ''
            if [ -z "''${1:-}" ]; then
              echo "Usage: discid {folder/path}"
              exit 1
            fi
            
            export LD_LIBRARY_PATH="${pkgs.libdiscid}/lib"
            
            exec python ${./id.py} "$1"
          '';
        };
      in
      {
        packages = {
          default = discidScript;
          discid = discidScript;
        };
        
        apps = {
          default = {
            type = "app";
            program = "${discidScript}/bin/discid";
          };
          discid = {
            type = "app";
            program = "${discidScript}/bin/discid";
          };
        };

        devShells.default = pkgs.mkShell {
          nativeBuildInputs = [ discidScript ];
        };
      }
    );
}
