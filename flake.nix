{
  description = "Audio utilities for FLAC folders";

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
          xxhash
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
            exec python ${./discid/id.py} "$1"
          '';
        };

        albumWriteScript = pkgs.writeShellApplication {
          name = "album_write";
          runtimeInputs = [ pythonEnv ];
          text = ''
            if [ -z "''${1:-}" ]; then
              echo "Usage: album_write {folder/path}"
              exit 1
            fi
            exec python ${./album_write/write.py} "$1"
          '';
        };
      in
      {
        packages = {
          discid = discidScript;
          album_write = albumWriteScript;
        };
        
        devShells.default = pkgs.mkShell {
          packages = [ 
            pythonEnv 
            pkgs.libdiscid 
            discidScript
            albumWriteScript
          ];
          shellHook = ''
            export LD_LIBRARY_PATH="${pkgs.libdiscid}/lib"
          '';
        };
      }
    );
}
