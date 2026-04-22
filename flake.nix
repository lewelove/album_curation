{
  description = "Audio utilities for FLAC folders (Python, Bash, and Rust)";

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
            exec python ${./discid/id.py} "$@"
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
          TARGET="''${1:-all}"

          build_rust() {
            echo "[>] Building rsdiscid via Cargo (Release)..."
            export LIBCLANG_PATH="${pkgs.llvmPackages.libclang.lib}/lib"
            export PKG_CONFIG_PATH="${pkgs.libdiscid}/lib/pkgconfig:${pkgs.openssl.dev}/lib/pkgconfig"
            export LD_LIBRARY_PATH="${pkgs.libdiscid}/lib:${pkgs.openssl.out}/lib"
            
            if [ -d "rsdiscid" ]; then
              cd rsdiscid
              ${pkgs.cargo}/bin/cargo build --release
              cd ..
              echo "[+] rsdiscid binary updated: rsdiscid/target/release/rsdiscid"
            else
              echo "[!] Error: rsdiscid directory not found."
              exit 1
            fi
          }

          build_nix_tool() {
            local tool=$1
            echo "[>] Building $tool via Nix..."
            nix build ".#$tool" -o "$tool/.build"
          }

          case "$TARGET" in
            "rsdiscid")
              build_rust
              ;;
            "discid" | "album_write" | "album_split" | "cover_resize")
              build_nix_tool "$TARGET"
              ;;
            "all")
              build_nix_tool "discid"
              build_nix_tool "album_write"
              build_nix_tool "album_split"
              build_nix_tool "cover_resize"
              build_rust
              ;;
            *)
              echo "Unknown target: $TARGET"
              echo "Usage: build [rsdiscid | discid | album_write | album_split | cover_resize]"
              exit 1
              ;;
          esac
          
          echo "[+] Build task '$TARGET' complete."
        '';
      in
      {
        packages = {
          discid = discidScript;
          album_write = albumWriteScript;
          album_split = albumSplitScript;
          cover_resize = coverResizeScript;
          build = buildAll;
          default = buildAll;
        };

        apps = {
          discid = flake-utils.lib.mkApp { drv = discidScript; };
          album_write = flake-utils.lib.mkApp { drv = albumWriteScript; };
          build = {
            type = "app";
            program = "${buildAll}/bin/build";
          };
        };
        
        devShells.default = pkgs.mkShell {
          packages = [ 
            pythonEnv 
            pkgs.libdiscid 
            pkgs.pkg-config
            pkgs.openssl
            pkgs.cargo
            pkgs.rustc
            pkgs.rust-analyzer
            pkgs.llvmPackages.libclang
            discidScript
            albumWriteScript
            albumSplitScript
            coverResizeScript
            buildAll
          ];
          shellHook = ''
            export LIBCLANG_PATH="${pkgs.llvmPackages.libclang.lib}/lib"
            export PKG_CONFIG_PATH="${pkgs.libdiscid}/lib/pkgconfig:${pkgs.openssl.dev}/lib/pkgconfig"
            export LD_LIBRARY_PATH="${pkgs.libdiscid}/lib:${pkgs.openssl.out}/lib"
            echo "--- Album Curation Toolset ---"
            echo "Usage: build rsdiscid  (builds ONLY rust)"
            echo "       build           (builds everything)"
          '';
        };
      }
    );
}
