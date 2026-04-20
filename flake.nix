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
          musicbrainzngs
          requests
          python-dotenv
        ]);
        
        discidScript = pkgs.writeShellApplication {
          name = "discid";
          runtimeInputs = [ pythonEnv pkgs.libdiscid ];
          text = ''
            export LD_LIBRARY_PATH="${pkgs.libdiscid}/lib"
            exec python ${./discid/id.py} "''${1:-.}"
          '';
        };

        mbidScript = pkgs.writeShellApplication {
          name = "mbid";
          runtimeInputs = [ pythonEnv ];
          text = ''
            if [ -z "''${1:-}" ]; then
              echo "Usage: mbid {musicbrainz_url}"
              exit 1
            fi
            exec python ${./mbid/mbid.py} "$1"
          '';
        };

        albumWriteScript = pkgs.writeShellApplication {
          name = "album_write";
          runtimeInputs = [ pythonEnv ];
          text = ''
            exec python ${./album_write/write.py} "''${1:-.}"
          '';
        };

        albumSplitScript = pkgs.writeShellApplication {
          name = "album_split";
          runtimeInputs = [ pkgs.shntool pkgs.cuetools pkgs.flac ];
          text = ''
            exec bash ${./album_split/split.sh} "''${1:-.}"
          '';
        };

        coverResizeScript = pkgs.writeShellApplication {
          name = "cover_resize";
          runtimeInputs = [ pkgs.imagemagick ];
          text = ''
            exec bash ${./cover_resize/resize.sh} "$@"
          '';
        };

        buildAll = pkgs.writeShellScriptBin "build" ''
          nix build .#discid -o discid/.build
          nix build .#mbid -o mbid/.build
          nix build .#album_write -o album_write/.build
          nix build .#album_split -o album_split/.build
          nix build .#cover_resize -o cover_resize/.build
          echo "[+] Done. Binaries are in {util_name}/.build/"
        '';
      in
      {
        packages = {
          discid = discidScript;
          mbid = mbidScript;
          album_write = albumWriteScript;
          album_split = albumSplitScript;
          cover_resize = coverResizeScript;
          build = buildAll;
        };

        apps = {
          build = {
            type = "app";
            program = "${buildAll}/bin/build";
          };
        };
        
        devShells.default = pkgs.mkShell {
          packages = [ 
            pythonEnv 
            pkgs.libdiscid 
            discidScript
            mbidScript
            albumWriteScript
            albumSplitScript
            coverResizeScript
            buildAll
          ];
          shellHook = ''
            export LD_LIBRARY_PATH="${pkgs.libdiscid}/lib"
          '';
        };
      }
    );
}
