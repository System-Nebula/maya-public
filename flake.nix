{
  description = "maya-public — reproducible development environment";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      # Systems we support developing on.
      systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      pkgsFor = system: import nixpkgs { inherit system; };
    in
    {
      # `nix develop` — reproduces the full dev toolchain (pinned by flake.lock).
      devShells = forAllSystems (system:
        let
          pkgs = pkgsFor system;

          # Postgres 16 + pgvector, matching the gateway/maya-db dev DB.
          postgres = pkgs.postgresql_16.withPackages (ps: [ ps.pgvector ]);

          # Playwright browsers (e2e) — Linux only; replaces the Makefile's
          # ad-hoc `nix-shell -p playwright-driver.browsers`.
          playwright = pkgs.lib.optionals pkgs.stdenv.isLinux [ pkgs.playwright-driver.browsers ];
        in
        {
          default = pkgs.mkShell {
            packages = [
              pkgs.python311      # interpreter (uv manages venv on top)
              pkgs.uv             # Python package/workspace manager (uv.lock)
              postgres            # psql + server + pgvector
              pkgs.bun            # JS/TS toolchain (homepage + e2e)
              pkgs.nodejs_22
              pkgs.gnumake        # Makefile targets
              pkgs.git
            ] ++ playwright;

            # Keep uv reproducible: use the Nix-provided interpreter, never let
            # uv silently fetch a different Python build.
            env = {
              UV_PYTHON = "${pkgs.python311}/bin/python3.11";
              UV_PYTHON_DOWNLOADS = "never";
            };

            shellHook = ''
              ${pkgs.lib.optionalString pkgs.stdenv.isLinux ''
                export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
                export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
              ''}
              echo "maya-public dev shell"
              echo "  python : $(python3 --version 2>&1)"
              echo "  uv     : $(uv --version 2>&1)"
              echo "  psql   : $(psql --version 2>&1)"
              echo "  bun    : $(bun --version 2>&1)"
              echo "  node   : $(node --version 2>&1)"
              echo "Next: uv sync --all-packages && ENV=development PORT=8090 uv run maya-gateway"
            '';
          };
        });

      formatter = forAllSystems (system: (pkgsFor system).nixpkgs-fmt);
    };
}
