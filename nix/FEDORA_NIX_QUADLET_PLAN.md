# Fedora + Nix + rootless Podman Quadlet plan

Status: proposed plan, based on this host as inspected on 2026-09-22.

## Recommendation in one paragraph

Do **not** try to turn this Fedora installation into a partial NixOS, and do not begin by giving Home Manager control of the whole home directory. Keep Fedora responsible for the kernel, systemd, SELinux, and Podman. Use rootless Quadlets managed by the Fedora user systemd instance. Add Nix first as a reproducible builder for the agent software and OCI image. After one hand-written Quadlet has survived a reboot and an update, add standalone, flake-pinned Home Manager only to deploy the already-understood Quadlet files. Treat a container as an immutable workload, not as a small mutable NixOS. If the agents truly need to run `nixos-rebuild`, control their own init system, or change their whole OS, graduate that workload to a dedicated NixOS VM instead of making a privileged Podman container.

This is a deliberately staged path. Each phase is useful by itself and has an obvious rollback.

## What is already true on this machine

The read-only inspection found:

- Host OS: Fedora 43.
- Nix: Determinate Nix 3.22.5, reporting upstream Nix 2.35.2.
- Podman: Fedora's `/usr/bin/podman`, version 5.8.4.
- Podman is running rootless, with cgroup v2 and the systemd cgroup manager.
- Storage is rootless overlay at `~/.local/share/containers/storage`; networking uses Netavark.
- The Podman user generator is installed at `/usr/lib/systemd/user-generators/podman-user-generator`.
- The account has a subordinate ID range of 65,536 UIDs/GIDs.
- SELinux is enforcing.
- User lingering is already enabled, so user units can start at boot without an interactive login.
- The user systemd manager currently reports `degraded`, but its three failed units are unrelated desktop helpers: NVIDIA settings, Snap user autostart, and DrKonqi. This is not a Podman/Quadlet failure.
- This repository currently has no project files, so there is no existing deployment layout to preserve.

These are the important prerequisites for rootless Quadlets. No bare-metal NixOS installation is required.

## Keep the layers distinct

The intended stack should be:

```text
Fedora host
  -> user systemd + Fedora's Quadlet generator
    -> rootless Fedora Podman
      -> OCI image built reproducibly with Nix
        -> agent processes and their deliberately mounted state
```

Nix being installed on Fedora does not make NixOS modules such as `containers.*` or arbitrary `services.*` applicable to the Fedora host. Those modules describe a NixOS system activation. Nixpkgs packages and build functions, however, work perfectly well on non-NixOS Linux.

Likewise, an OCI image assembled with Nix is not automatically NixOS. A normal OCI container shares the Fedora kernel and ordinarily runs one workload rather than its own full systemd instance. That distinction is useful: it keeps the initial design small and debuggable.

## Why not start with Home Manager?

Home Manager is viable here, but it should be the third step rather than the first.

The warning on the Home Manager project is not saying that it routinely destroys a home directory. It says that errors can be difficult for Nix newcomers, some modules can overwrite state they cannot fully identify, and users should begin with a small configuration. Home Manager normally detects a colliding file and aborts activation before replacing it. It also supports building without activating, backup extensions, generations, and rollback.

There are two distinct ways Home Manager could participate:

1. **Recommended at first:** use `xdg.configFile` to link reviewed raw `.container`, `.network`, `.volume`, and `.pod` files into `~/.config/containers/systemd/`. Fedora's installed Quadlet generator remains responsible for translating them.
2. **Evaluate later:** use Home Manager's `services.podman` module and its typed Quadlet options.

The second option is attractive, but the current `release-26.05` implementation also installs the Nixpkgs Podman package, writes several `containers/*.conf` files, runs the Nix-provided Podman generator during the Nix build, and links generated systemd units into the user configuration. That replaces more of the Fedora-native path and introduces a second Podman packaging/version boundary. It is not the best first diagnostic surface.

Do not initially enable Home Manager modules for the shell, desktop, Git, or unrelated dotfiles. Do not use `force = true`, automatic upgrades, automatic garbage collection, or automatic container image updates during the proving stages.

## Phase 1: prove Fedora-native Quadlet end to end

Goal: prove that a harmless rootless service can be generated, started, logged, stopped, and started after reboot before Nix or Home Manager is involved.

Suggested repository layout:

```text
quadlets/
  smoke.container
scripts/
  deploy-quadlets
  undeploy-quadlets
```

Start with one disposable container. Use a fully qualified image name. A tag is acceptable for the first five-minute smoke test, but record and use a digest before calling the deployment reproducible.

Example shape (the exact image digest should be filled in when this phase is implemented):

```ini
[Unit]
Description=Disposable Quadlet smoke test

[Container]
Image=docker.io/library/alpine@sha256:REPLACE_WITH_VERIFIED_DIGEST
Exec=/bin/sh -c "while true; do date -Iseconds; sleep 60; done"

[Service]
Restart=on-failure
TimeoutStartSec=300

[Install]
WantedBy=default.target
```

Deployment should link each reviewed file individually into the rootless search directory. Podman explicitly supports symlinks there.

```bash
mkdir -p "$HOME/.config/containers/systemd"
ln -sfn "$PWD/quadlets/smoke.container" \
  "$HOME/.config/containers/systemd/smoke.container"
systemctl --user daemon-reload
systemd-analyze --user --generators=true verify smoke.service
systemctl --user start smoke.service
systemctl --user status smoke.service
journalctl --user -u smoke.service --no-pager -n 100
```

Important details:

- A generated Quadlet service should not be enabled with `systemctl enable`. The Quadlet's `[Install]` section tells the generator how to attach it to `default.target`.
- Keep `TimeoutStartSec` generous while an image might be pulled.
- Test a reboot only after manual start/stop and log inspection work.
- Bind host ports to `127.0.0.1` until external access is intentional and the Fedora firewall policy has been decided.
- With SELinux enforcing, label writable bind mounts intentionally: normally `:Z` for a mount private to one container and `:z` only when multiple containers really share it.

Rollback is small and explicit:

```bash
systemctl --user stop smoke.service
unlink "$HOME/.config/containers/systemd/smoke.container"
systemctl --user daemon-reload
```

Exit gate:

- The service starts, stops, and logs correctly.
- It starts after a reboot without a login.
- Removing the link and reloading removes the generated unit.
- No `sudo`, privileged container, host Podman socket, or broad home-directory mount was needed.

## Phase 2: let Nix build the workload, not operate the host

Goal: add a pinned flake that builds an OCI archive and development/test tools while Fedora Podman still owns runtime operation.

Suggested additions:

```text
flake.nix
flake.lock
nix/
  agent-image.nix
quadlets/
  agent.image
  agent.container
scripts/
  build-and-load-image
  deploy-quadlets
```

The flake should pin Nixpkgs and expose at least:

- `packages.x86_64-linux.agent-image`, initially built with `pkgs.dockerTools.buildLayeredImage`;
- `checks.x86_64-linux.*` for configuration and application tests;
- optionally a small `devShell`, but no global profile mutation.

Nixpkgs' `dockerTools` name is historical: its archive is usable by Podman. A simple deployment flow is:

1. `nix build .#agent-image`;
2. load the resulting Docker-compatible archive into rootless Podman;
3. confirm the expected image ID/tag;
4. reload/restart the associated Quadlet;
5. run a health or behavior check;
6. on failure, retag/reload the last known-good archive and restart.

Podman 5.8 can also represent a local Docker archive with a `.image` Quadlet using `Image=docker-archive:/path/to/archive` plus `ImageTag=...`. This can remove an imperative `podman load` step, but there is a subtle Nix concern: a bare `/nix/store/...` path written into a text file is not necessarily a garbage-collection root. Prefer the explicit load step first, or maintain a deliberate GC-root symlink and test garbage collection before relying on the `.image` approach.

Use immutable image identity in deployments. Avoid making `latest` the only record of what is running. The Git revision, flake lock revision, Nix output path, and Podman image digest should be inspectable together.

Exit gate:

- Two consecutive builds from the same lock file produce the expected image identity/content.
- Updating one application dependency creates a reviewable lock/config change.
- The new image can be deployed and rolled back without changing the host Podman package.
- Persistent data survives image replacement because it is in a deliberate named volume or bind mount, not in the container writable layer.

## Phase 3: introduce standalone Home Manager narrowly

Goal: use Home Manager as a reversible file deployment mechanism after raw Quadlet behavior is familiar.

Use a flake, not mutable channels. As of this plan, the matching stable pair is Nixpkgs `nixos-26.05` (or `nixpkgs-26.05`) and Home Manager `release-26.05`; set `home-manager.inputs.nixpkgs.follows = "nixpkgs"`. Pin both in `flake.lock`. If this phase is implemented after a new release, choose the then-current matching pair rather than copying these branch names blindly.

The first Home Manager configuration should contain only:

- the correct `home.username` and `home.homeDirectory`;
- `home.stateVersion = "26.05"` for a configuration first created on 26.05 (do not routinely bump this later);
- `targets.genericLinux.enable = true`;
- one `xdg.configFile."containers/systemd/agent.container".source = ./quadlets/agent.container` entry;
- optionally `programs.home-manager.enable = true` after the initial test, solely to retain the command.

It should initially **not** contain `services.podman.enable = true`. That module can be tested in a separate branch once the Fedora-native deployment is known-good.

Safe adoption sequence:

1. Ensure the raw Phase 1 symlink is either the exact target Home Manager will adopt or has been moved aside deliberately.
2. Run `home-manager build --flake .#USER@HOST` (or invoke the pinned Home Manager app with `nix run`) and inspect `result/home-files` before activation.
3. Review every collision. Do not solve unexpected collisions with `force = true`.
4. Activate with a unique backup extension if an expected unmanaged file must be moved: `home-manager switch -b pre-hm-YYYYMMDD --flake .#USER@HOST`.
5. Explicitly run `systemctl --user daemon-reload`, inspect the generated unit, and start/restart it. Keep service lifecycle outside Home Manager activation for the first iteration.
6. Record `home-manager generations`. Home Manager 25.11 and newer supports `home-manager switch --rollback`.

Once this is stable, an idempotent `onChange` hook or a separate deploy command can perform reload and `try-restart`. Keeping build, activation, and service restart as three observable steps is preferable while learning.

Exit gate:

- `home-manager build` has no side effects.
- The activation changes only the intended Quadlet path and Home Manager's own generation/profile state.
- Rollback restores the prior file generation.
- Fedora's `/usr/bin/podman` and Fedora Quadlet generator still execute the service.

## Phase 4: build the smallest useful agent hive

Goal: demonstrate multiple agents with bounded authority, observable coordination, and reproducible replacement.

Begin with three roles, each in a separate container rather than several agents sharing one mutable container:

- a coordinator that accepts work and records desired state;
- one or two workers with separate writable workspaces;
- an optional narrow deployer that can build/check a proposed revision and request activation.

Use a dedicated `.network` Quadlet and, only where useful, named `.volume` Quadlets. A `.pod` can be added when shared network namespace/lifecycle is genuinely helpful; it is not required merely because the services form a team.

Default security boundary:

- rootless Podman only;
- run as a non-root UID inside the image where practical;
- read-only root filesystem where practical;
- drop capabilities and use `no-new-privileges`;
- memory, CPU, PID, and restart limits;
- no host Podman socket;
- no host Docker socket;
- no writable host `/nix` and no access to the host Nix daemon socket;
- no broad `$HOME` mount;
- only explicit work, state, and secret paths;
- bind ports to loopback unless there is a reviewed need for LAN access.

Do not put API keys, registry credentials, SSH keys, or tokens into Nix expressions, Home Manager `text` values, flake inputs, image layers, or Quadlet `Environment=` entries. Those are liable to become world-readable in the Nix store, image metadata, generated unit, or process inspection. Inject secrets at runtime with permissions and lifecycle appropriate to the secret (for example Podman secrets or a host file mounted read-only), and keep their paths/content out of Git.

The agents should administer **desired state**, not mutate their base image in place:

```text
agent proposes change to the flake/config repository
  -> checks build in an unprivileged context
    -> policy/review gate accepts a known Git revision
      -> trusted deployer builds and activates that revision
        -> health check passes or deployment rolls back
```

This gives agents a meaningful way to “administer their OS” while retaining history, reproducibility, and recovery. An agent running `nix profile install` or editing `/etc` inside an ephemeral container produces state that is hard to review and disappears on replacement.

Exit gate:

- Compromising one worker does not provide control of the host or other workers' private state.
- Every running image maps to a Git revision and locked Nix inputs.
- Agent-produced configuration must pass builds/checks before activation.
- A bad deployment automatically or manually rolls back to a known-good image/config.
- Logs, health checks, state backup, and secret rotation have all been exercised once.

## Phase 5 decision: OCI workload or real self-administered NixOS?

Make this decision only after the hive proof of concept.

| Need | Best fit |
| --- | --- |
| Reproducible agent binaries and filesystem; one main process per unit | Nix-built OCI images under rootless Quadlet |
| Several cooperating services with isolated writable state | Several Quadlets plus a private Podman network/volumes |
| Agents propose changes and a controller rebuilds/redeploys | OCI + Git/flake control plane (recommended) |
| Agents need a package manager interactively for experiments | Disposable dev container or `nix develop`; do not confuse it with production state |
| Agents need their own systemd, users, NixOS modules, and `nixos-rebuild` | Dedicated NixOS VM, preferably with snapshots and resource limits |
| Untrusted agents require a strong isolation boundary | VM; a container shares the Fedora kernel |

Running a full systemd-based NixOS userspace inside privileged Podman is technically possible in assorted forms, but it adds nested cgroups, privilege, mount, SELinux, and shutdown semantics precisely where a first deployment should stay simple. Native NixOS containers are also documented as NixOS-host functionality and are not perfectly isolated from their host. Neither is the preferred target for untrusted autonomous agents on Fedora.

## Operational rules to adopt from day one

1. Pin flake inputs and image digests; update them deliberately.
2. Build before activation, and inspect what will be linked/generated.
3. Separate immutable image content from writable state.
4. Back up named volumes/bind-mounted state; a Nix rebuild does not back up data.
5. Use health checks and bounded restart policies. Avoid infinite crash loops hidden by `Restart=always`.
6. Keep automatic image updates off until rollback is proven. A reproducible deployment should update by reviewed revision, not surprise timer.
7. Run syntax/unit verification and a smoke test in CI before deployment.
8. Never grant the hive a host container-engine socket as a shortcut to self-administration.
9. Keep the host runtime Fedora-native until there is a measured reason to replace it with Nixpkgs Podman.
10. Preserve at least one known-good Home Manager generation and image revision before garbage collection.

## Proposed implementation order

The next work should be split into small, independently reviewable changes:

1. Add a smoke Quadlet and non-destructive deploy/undeploy scripts.
2. Run it manually, verify logs, then verify one reboot.
3. Add the pinned flake and a minimal Nix-built image.
4. Add image-load/deploy and rollback scripts with checks.
5. Add a minimal standalone Home Manager output that manages only the Quadlet files.
6. Add one coordinator and one worker with no sensitive privileges.
7. Add secrets, persistence, health checks, backup, and resource limits one at a time.
8. Decide whether the long-term agent “OS” remains immutable OCI desired state or moves into a NixOS VM.

## Confidence and known unknowns

- **High confidence:** Fedora-native rootless Quadlet is supported by the installed host and is the shortest path to a working service.
- **High confidence:** Nix can reproducibly build OCI archives that Fedora Podman consumes without making the host NixOS.
- **High confidence:** a minimal, standalone, flake-pinned Home Manager configuration can safely manage only selected files if collision checks and build-before-switch are respected.
- **Moderate confidence until tested:** the exact agent application image, writable paths, SELinux labeling, health check, and UID mapping; these depend on the actual agent runtime.
- **Low confidence / not recommended:** treating a privileged Podman container as a fully autonomous NixOS machine. Use a VM if those semantics are truly required.

## Primary references

- [Podman Quadlet systemd unit documentation](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html) — unit types, rootless search paths, supported symlinks, cgroup v2, dependencies, and timeouts.
- [Podman Quadlet basic usage](https://docs.podman.io/en/latest/markdown/podman-quadlet-basic-usage.7.html) — placement, reload/start, logs, and generated-unit behavior.
- [Podman image Quadlet documentation](https://docs.podman.io/en/stable/markdown/podman-image.unit.5.html) — registry images and local Docker archives.
- [Home Manager project warning and installation choices](https://github.com/nix-community/home-manager#words-of-warning) — small configurations, non-NixOS support caveat, and standalone mode.
- [Home Manager flake standalone setup](https://nix-community.github.io/home-manager/nix-flakes/standalone.html) — pinned standalone structure.
- [Home Manager file collision and backup behavior](https://nix-community.github.io/home-manager/usage/dotfiles.html) — collision aborts, backup extensions, `force`, and symlink behavior.
- [Home Manager Podman options](https://nix-community.github.io/home-manager/options/home-manager/services/podman.html) — the available typed Podman/Quadlet module.
- [Home Manager 26.05 Podman implementation](https://github.com/nix-community/home-manager/tree/release-26.05/modules/services/podman) — important for understanding what that module generates and installs.
- [Nixpkgs `dockerTools` documentation](https://github.com/NixOS/nixpkgs/blob/master/doc/build-helpers/images/dockertools.section.md) — reproducible layered OCI/Docker-compatible archives.
- [NixOS manual: container management](https://nixos.org/manual/nixos/stable/#ch-containers) — why native NixOS containers are a NixOS-host feature and why container root is not a strong isolation boundary.

