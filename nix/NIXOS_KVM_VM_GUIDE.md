# NixOS VM on Fedora or Ubuntu with KVM/libvirt

Status: installation and operating guide, written 2026-09-22.

This is a companion to `FEDORA_NIX_QUADLET_PLAN.md`. Its recommended outcome is a persistent NixOS virtual machine managed by libvirt. The same VM can be created and operated either with virt-manager or entirely from the command line with `virt-install` and `virsh`.

## Recommendation

Use the host's native KVM, QEMU, and libvirt packages. Create the VM on the system libvirt connection (`qemu:///system`), install NixOS 26.05 from its minimal ISO, and put the guest's complete configuration in a pinned flake. Begin with 4 virtual CPUs, 8 GiB RAM, and a 120 GiB thin-provisioned qcow2 disk; increase that to roughly 8 CPUs, 16 GiB RAM, and 200 GiB disk if several agents will build large Nix closures concurrently.

The VM is the right boundary when the agents need any of the following:

- a real NixOS system with its own systemd and boot generations;
- NixOS service, user, networking, firewall, and container modules;
- permission to run `nixos-rebuild` without administering the Fedora or Ubuntu host;
- a persistent `/nix/store` and machine state;
- stronger isolation than a container sharing the host kernel;
- a checkpoint/clone boundary around experiments.

The VM does consume more RAM, disk, and startup time than a rootless container. A guest administrator is still not a host administrator unless the host exposes devices, host directories, or the libvirt/Podman socket to it. Do not expose those merely for convenience.

### Current Fedora host observation

This machine's CPU advertises AMD SVM virtualization and the `kvm_amd` kernel module is loaded. The KVM/QEMU, libvirt, virt-install, virt-manager, OVMF, and software-TPM packages checked during preparation are not currently installed. The managed workspace sandbox does not expose `/dev/kvm`, so confirm that device from an ordinary host terminal before installing the VM. No virtualization packages or host services were changed while preparing this guide.

## Tooling model

The layers are:

```text
Fedora or Ubuntu host
  -> KVM kernel acceleration
    -> QEMU virtual machine process
      -> libvirt lifecycle, storage, and networking
        -> NixOS guest
          -> systemd services and/or Podman agent containers
```

virt-manager, `virt-install`, and `virsh` all operate through libvirt. It is therefore safe to create a VM with the CLI and later inspect or edit it in virt-manager, or vice versa.

Prefer libvirt to a raw `qemu-system-x86_64` command for a long-lived VM. Libvirt retains the machine definition, supplies NAT/DHCP, manages UEFI variable storage, applies SELinux/AppArmor isolation, handles autostart, and provides stable lifecycle commands. Raw QEMU is excellent for short tests but makes those responsibilities manual.

This guide uses `qemu:///system`, which supplies libvirt's default NAT network and supports host-boot autostart. The alternative `qemu:///session` runs QEMU under the invoking user and avoids some file-permission issues, but it normally falls back to slower user networking and is awkward to reach from elsewhere. It is less appropriate for an always-on agent VM.

> Membership in the host `libvirt` group is highly privileged. The system libvirt socket can often be used to obtain host-equivalent access by defining a VM with sensitive host mounts or devices. Never add an agent account to the host's `libvirt` group and never pass that socket into the guest.

## 1. Check hardware and firmware support

On either host OS:

```bash
grep -E -m1 '(vmx|svm)' /proc/cpuinfo
lsmod | grep '^kvm'
ls -l /dev/kvm
```

Expected results are a CPU flag (`vmx` for Intel or `svm` for AMD), a `kvm_intel` or `kvm_amd` module, and `/dev/kvm`. If the CPU supports virtualization but `/dev/kvm` is absent, enable Intel VT-x or AMD-V/SVM in the machine firmware and reboot. If the Fedora or Ubuntu host is itself a VM, the outer hypervisor must expose nested virtualization.

Podman inside the NixOS guest does **not** require nested virtualization. Nested virtualization is needed only if the NixOS guest will itself run KVM virtual machines.

## 2A. Prepare a Fedora host

### Full workstation installation

This includes virt-manager and the graphical viewer:

```bash
sudo dnf install @virtualization edk2-ovmf swtpm swtpm-tools
```

If the group shorthand is not accepted by the installed DNF version, use:

```bash
sudo dnf group install virtualization
sudo dnf install edk2-ovmf swtpm swtpm-tools
```

### CLI-only installation

```bash
sudo dnf install \
  qemu-kvm \
  libvirt-daemon-kvm \
  libvirt-daemon-config-network \
  libvirt-client \
  virt-install \
  edk2-ovmf \
  swtpm \
  swtpm-tools
```

Fedora has used libvirt's modular daemons by default since Fedora 35. Package installation normally applies the correct systemd presets. Ensure the QEMU manager and supporting sockets are available:

```bash
sudo systemctl enable --now virtqemud.socket
sudo systemctl enable --now virtnetworkd.socket
sudo systemctl enable --now virtstoraged.socket
```

If VMs configured for autostart do not start after a host reboot, also enable the service:

```bash
sudo systemctl enable --now virtqemud.service
```

Do not simultaneously switch back and forth between `libvirtd` and the modular daemons. Fedora's new installations are intended to use `virtqemud`, `virtnetworkd`, and the other modular services.

### Host access

On a single-user workstation, add your human account—not an agent—to the management groups:

```bash
sudo usermod -aG libvirt,kvm "$(id -un)"
```

Log out of the desktop session completely and log back in. On a shared host, prefer a deliberate polkit/sudo policy over broad group membership.

## 2B. Prepare an Ubuntu host

The base system/CLI packages are:

```bash
sudo apt update
sudo apt install \
  qemu-kvm \
  libvirt-daemon-system \
  libvirt-clients \
  virtinst \
  ovmf \
  swtpm \
  swtpm-tools
```

For the GUI, also install:

```bash
sudo apt install virt-manager virt-viewer
```

Enable the distro-provided libvirt service:

```bash
sudo systemctl enable --now libvirtd
```

Add your human account to the management groups, then log out and back in:

```bash
sudo usermod -aG libvirt,kvm "$(id -un)"
```

Ubuntu's libvirt packages apply AppArmor profiles to guests. Keep VM disks and installer media in libvirt's normal storage locations unless there is a specific reason to extend those policies.

## 3. Validate libvirt and its default network

After installing the packages and refreshing group membership:

```bash
sudo virt-host-validate qemu
virsh --connect qemu:///system list --all
virsh --connect qemu:///system net-list --all
```

Warnings about optional features are not necessarily blockers, but failures for `/dev/kvm`, QEMU, or cgroups should be resolved before continuing.

The expected network is named `default`. Start it and make it persistent if it is inactive:

```bash
sudo virsh --connect qemu:///system net-start default
sudo virsh --connect qemu:///system net-autostart default
```

`net-start` will report that the network is already active when no action is required. If `default` does not exist, first look for the distribution-provided definition:

```bash
ls -l /usr/share/libvirt/networks/default.xml
```

If present, define it and then start it:

```bash
sudo virsh --connect qemu:///system net-define \
  /usr/share/libvirt/networks/default.xml
sudo virsh --connect qemu:///system net-autostart default
sudo virsh --connect qemu:///system net-start default
```

If that XML file is absent, install Fedora's `libvirt-daemon-config-network` package or verify Ubuntu's `libvirt-daemon-system` installation rather than downloading an arbitrary network definition.

The default network gives the guest outbound connectivity and an address on a private host bridge, usually `virbr0`. The host can SSH directly to that private address. Machines elsewhere on the LAN cannot initiate connections to it without a bridge, port forwarding, or a host reverse proxy. Start with NAT; changing the host's physical interface into a bridge can interrupt the host's network and should be a separate, carefully planned change.

## 4. Download and verify the NixOS installer

The following uses the stable NixOS 26.05 minimal x86-64 image. Check the [NixOS download page](https://nixos.org/download/) and release notes before copying this later; use a matching newer stable release when appropriate.

```bash
mkdir -p "$HOME/Downloads/nixos-vm"
cd "$HOME/Downloads/nixos-vm"

NIXOS_VM_ISO_URL="https://channels.nixos.org/nixos-26.05/latest-nixos-minimal-x86_64-linux.iso"
NIXOS_VM_ISO_FILE="nixos-minimal-26.05-x86_64-linux.iso"

curl --fail --location "$NIXOS_VM_ISO_URL" --output "$NIXOS_VM_ISO_FILE"
curl --fail --location "${NIXOS_VM_ISO_URL}.sha256" --output nixos-minimal.sha256

NIXOS_VM_EXPECTED_HASH="$(awk 'NR == 1 { print $1 }' nixos-minimal.sha256)"
printf '%s  %s\n' "$NIXOS_VM_EXPECTED_HASH" "$NIXOS_VM_ISO_FILE" | sha256sum --check -
```

Place the verified ISO in a standard system-libvirt location. This avoids home-directory traversal, SELinux, and AppArmor surprises:

```bash
sudo install -d -m 0755 /var/lib/libvirt/images/iso
sudo install -m 0644 \
  "$HOME/Downloads/nixos-vm/nixos-minimal-26.05-x86_64-linux.iso" \
  /var/lib/libvirt/images/iso/nixos-minimal-26.05-x86_64-linux.iso
```

On Fedora, restore the distribution's SELinux labels:

```bash
sudo restorecon -RFv /var/lib/libvirt/images
```

For an ARM64 host, use the NixOS AArch64 ISO and the host's AArch64 QEMU/UEFI packages. Do not use an AArch64 image for an ordinary x86-64 KVM VM; cross-architecture emulation is much slower and is a different setup.

## 5A. Create the VM with virt-manager

Start virt-manager on the system connection:

```bash
virt-manager --connect qemu:///system
```

Then:

1. Select **Create a new virtual machine**.
2. Choose **Local install media (ISO image or CDROM)**.
3. Select `/var/lib/libvirt/images/iso/nixos-minimal-26.05-x86_64-linux.iso`.
4. If NixOS is in the OS list, select the newest NixOS entry. Otherwise choose a recent generic Linux entry. The selection influences virtual-hardware defaults; it does not change the installed software.
5. Allocate 8192 MiB RAM and 4 vCPUs for the initial VM.
6. Create a 120 GiB qcow2 disk. qcow2 is thin-provisioned, but the host must still be monitored so it never runs out of real space.
7. Name the VM `nixos-hive` and select **Customize configuration before install**.
8. In Overview, select Q35 chipset and UEFI firmware. Leave Secure Boot disabled for the initial installation.
9. Set the CPU model to **host-passthrough** or **Copy host CPU configuration** when the VM will remain on this host. Use a more portable CPU model if live migration to different hardware matters.
10. Confirm that the disk and NIC use VirtIO and the NIC is attached to the `default` virtual network.
11. Add a QEMU guest-agent channel if virt-manager did not add one automatically.
12. Add a serial PTY device. It is useful for recovery even when the graphical console works.
13. SPICE graphics and a VirtIO video device are reasonable GUI defaults. 3D acceleration is unnecessary for a server/agent VM.
14. Begin installation and follow the guest installation section below.

A virtual TPM is optional. Add TPM 2.0 only when the guest will actively use it. It creates another piece of per-VM state that must be included in backups and migrations.

## 5B. Create the same VM entirely from the CLI

Check whether the installed libosinfo database knows NixOS:

```bash
virt-install --osinfo list | grep -Ei 'nixos|linux20'
```

The command below permits ISO detection to fail because NixOS is not present in every distro's libosinfo database. It explicitly selects the important modern hardware choices itself.

```bash
sudo virt-install \
  --connect qemu:///system \
  --name nixos-hive \
  --memory 8192 \
  --vcpus 4 \
  --cpu host-passthrough \
  --machine q35 \
  --boot uefi \
  --disk path=/var/lib/libvirt/images/nixos-hive.qcow2,size=120,format=qcow2,bus=virtio,discard=unmap \
  --network network=default,model=virtio \
  --controller usb,model=qemu-xhci \
  --rng /dev/urandom \
  --channel unix,target_type=virtio,name=org.qemu.guest_agent.0 \
  --cdrom /var/lib/libvirt/images/iso/nixos-minimal-26.05-x86_64-linux.iso \
  --osinfo detect=on,require=off \
  --graphics none \
  --console pty,target_type=serial
```

The NixOS ISO boot menu has a serial-console entry. Select it when installing through `virsh console`. If the current ISO/firmware combination gives a blank serial screen, do not weaken the VM or expose VNC publicly. Stop the VM, add local SPICE graphics with virt-manager or `virsh edit`, complete installation through `virt-viewer`, and retain the serial device for the installed system.

Detach from a `virsh console` session with **Ctrl+]**. This does not stop the VM.

The VM created by this command will immediately appear in virt-manager because both use `qemu:///system`.

## 6. Install NixOS inside the guest

The commands in this section run **inside the NixOS installer VM**, not on the Fedora or Ubuntu host.

### Confirm the target disk

```bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
```

With the settings above, the empty 120 GiB virtual disk should be `/dev/vda` and the ISO should be a separate read-only device. Confirm this carefully. The following partition commands erase their target, although in this design that target is only the new virtual disk.

### Partition and mount for UEFI

This simple layout has a 512 MiB EFI System Partition and one root filesystem. Add a separate data disk or swap later if measurements justify it.

```bash
sudo parted /dev/vda -- mklabel gpt
sudo parted /dev/vda -- mkpart ESP fat32 1MiB 513MiB
sudo parted /dev/vda -- set 1 esp on
sudo parted /dev/vda -- mkpart root ext4 513MiB 100%

sudo mkfs.fat -F 32 -n boot /dev/vda1
sudo mkfs.ext4 -L nixos /dev/vda2

sudo mount /dev/disk/by-label/nixos /mnt
sudo mkdir -p /mnt/boot
sudo mount -o umask=077 /dev/disk/by-label/boot /mnt/boot
```

### Generate the hardware configuration

```bash
sudo nixos-generate-config --root /mnt
```

Do not hand-copy `hardware-configuration.nix` from another system. It records the filesystems and detected virtual hardware for this VM.

### Create the initial NixOS configuration

Edit `/mnt/etc/nixos/configuration.nix` so it contains the following shape. Replace the example SSH key with the complete public key from the human administrator's host. Never put a private key or plaintext secret in this file.

```nix
{ config, lib, pkgs, ... }:

{
  imports = [ ./hardware-configuration.nix ];

  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;

  # Keep the VM manageable through `virsh console` as well as a graphical console.
  boot.kernelParams = [
    "console=tty0"
    "console=ttyS0,115200n8"
  ];

  networking.hostName = "nixos-hive";
  networking.useDHCP = lib.mkDefault true;
  time.timeZone = "America/New_York";

  nix.settings.experimental-features = [ "nix-command" "flakes" ];

  users.users.hiveadmin = {
    isNormalUser = true;
    description = "NixOS hive administrator";
    extraGroups = [ "wheel" ];
    openssh.authorizedKeys.keys = [
      "ssh-ed25519 REPLACE_WITH_THE_REAL_PUBLIC_KEY human-admin"
    ];
  };

  services.openssh = {
    enable = true;
    settings = {
      PermitRootLogin = "no";
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
    };
  };

  services.qemuGuest.enable = true;
  services.spice-vdagentd.enable = true;

  virtualisation.podman.enable = true;

  environment.systemPackages = with pkgs; [
    curl
    git
    jq
    tmux
    vim
  ];

  # Set this to the release used for the first installation and do not
  # routinely change it during upgrades.
  system.stateVersion = "26.05";
}
```

If this is intentionally a serial-only VM, `services.spice-vdagentd.enable` can be omitted. The QEMU guest agent remains useful because it lets libvirt query guest state and request clean shutdowns.

### Make the configuration a pinned flake

Create `/mnt/etc/nixos/flake.nix`:

```nix
{
  description = "NixOS agent hive VM";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs = { self, nixpkgs }:
    {
      nixosConfigurations.nixos-hive = nixpkgs.lib.nixosSystem {
        system = "x86_64-linux";
        modules = [ ./configuration.nix ];
      };
    };
}
```

When installing a later stable release, update the input and initial `system.stateVersion` together for the **first installation**. On subsequent upgrades, update the input deliberately but normally leave `system.stateVersion` at its original value.

### Install and set a console password

```bash
sudo nixos-install --flake /mnt/etc/nixos#nixos-hive
sudo nixos-enter --root /mnt -c 'passwd hiveadmin'
```

The password is written interactively to the guest's password database; it is not exposed in the Nix store. `nixos-install` will also offer to set a root password. Once key-based access and sudo work, consider locking direct root password access inside the installed system with `sudo passwd -l root`.

The installer should create `/mnt/etc/nixos/flake.lock`. Preserve and commit the lock file with the configuration after the first boot.

### Reboot and remove the installer media

Shut down from the installer rather than repeatedly booting the ISO:

```bash
sudo poweroff
```

Back on the host, find the CD-ROM target:

```bash
virsh --connect qemu:///system domblklist nixos-hive --details
```

Use the target name shown for the CD-ROM in place of `sda` if it differs:

```bash
sudo virsh --connect qemu:///system change-media \
  nixos-hive sda --eject --config
sudo virsh --connect qemu:///system start nixos-hive
virsh --connect qemu:///system console nixos-hive
```

In virt-manager, the equivalent action is **Remove Hardware** or **Disconnect** on the CD-ROM before starting the VM.

## 7. Find the guest and connect over SSH

Ask libvirt's DHCP lease table for the address:

```bash
virsh --connect qemu:///system domifaddr nixos-hive --source lease
```

If no address appears immediately, wait for DHCP and try again. Once the guest agent is running, this can also help:

```bash
virsh --connect qemu:///system domifaddr nixos-hive --source agent
```

Then connect from the host:

```bash
ssh hiveadmin@GUEST_IP_ADDRESS
```

Do not disable the NixOS firewall indiscriminately. The OpenSSH NixOS module opens its port when configured to do so by the current module defaults/options; verify inside the guest with `systemctl status sshd` and `ss -lntp` if connection fails.

## 8. Day-to-day libvirt commands

These commands run on the Fedora or Ubuntu host:

```bash
# List VMs.
virsh --connect qemu:///system list --all

# Start and connect to the serial console.
virsh --connect qemu:///system start nixos-hive
virsh --connect qemu:///system console nixos-hive

# Ask the guest to shut down cleanly.
virsh --connect qemu:///system shutdown nixos-hive

# Request a clean reboot.
virsh --connect qemu:///system reboot nixos-hive

# Inspect virtual disks and NICs.
virsh --connect qemu:///system domblklist nixos-hive --details
virsh --connect qemu:///system domiflist nixos-hive

# Start the VM when the host boots (optional).
sudo virsh --connect qemu:///system autostart nixos-hive
```

Use `virsh destroy nixos-hive` only as the virtual equivalent of pulling a power cable. It is not a graceful shutdown and can damage guest filesystems or state.

To resize CPU/RAM or edit devices, shut down the guest and use virt-manager or:

```bash
sudo virsh --connect qemu:///system edit nixos-hive
```

`virsh edit` validates the XML before saving, but malformed or incompatible device changes can still prevent boot. Save a copy first:

```bash
virsh --connect qemu:///system dumpxml nixos-hive > nixos-hive.xml
```

## 9. NixOS change, test, and rollback workflow

Inside the guest, keep `/etc/nixos` in Git and commit `flake.lock`. A cautious change cycle is:

```bash
cd /etc/nixos

# Evaluate and build without activation.
sudo nixos-rebuild build --flake .#nixos-hive

# Show the activation effects where supported.
sudo nixos-rebuild dry-activate --flake .#nixos-hive

# Activate until reboot, but do not make it the default boot generation.
sudo nixos-rebuild test --flake .#nixos-hive

# After validation, make it the active/default generation.
sudo nixos-rebuild switch --flake .#nixos-hive
```

If `test` breaks networking or services, rebooting returns to the previous boot generation. If a switched generation is bad, select an older generation in the boot menu or use the rollback support of `nixos-rebuild` after regaining access.

Do not give an agent passwordless permission to invoke unrestricted `nixos-rebuild` while pretending that the agent is unprivileged. An agent that controls the evaluated NixOS module and can activate it effectively has root in the guest: it can create users, replace services, read secrets available to root, or install arbitrary activation scripts. That may be the desired meaning of “administer its own OS,” but it should be an explicit trust decision.

A safer team workflow is:

```text
agents edit a Git worktree as ordinary guest users
  -> Nix evaluation/build/checks run without activation
    -> a policy or human review approves a commit
      -> a narrow controller activates that exact commit
        -> health checks pass, or the VM/generation rolls back
```

## 10. VM checkpoints, clones, and backups

NixOS generations and VM backups solve different problems:

- A NixOS generation rolls back declarative system software/configuration.
- A qcow2 snapshot/clone rolls back mutable data too.
- Neither is a substitute for an independent backup stored away from the host disk.

Before a high-risk experiment, cleanly shut down the VM:

```bash
virsh --connect qemu:///system shutdown nixos-hive
virsh --connect qemu:///system domstate nixos-hive
```

A simple full clone can serve as a local known-good checkpoint:

```bash
sudo virt-clone \
  --connect qemu:///system \
  --original nixos-hive \
  --name nixos-hive-known-good \
  --auto-clone
```

Do not run the original and full clone on the same network without changing the clone's hostname, machine ID, and SSH host keys. A full clone copies those identities and any secrets on disk.

Libvirt internal/external snapshots have storage-format, UEFI NVRAM, TPM-state, and guest-quiescing details that vary with the VM definition. Use them only after testing restoration. For a durable cold backup, shut the guest down and preserve:

- `virsh dumpxml` output;
- every disk shown by `virsh domblklist`;
- UEFI NVRAM shown in the domain XML;
- virtual TPM state if a TPM was added;
- any external persistent volumes or network definitions.

Keep backups outside `/var/lib/libvirt/images` and, ideally, off the host.

## 11. Running the agent hive in NixOS

Once the base VM and rollback path are proven, choose one of two guest layouts.

### Agents as native NixOS services

Use NixOS modules/systemd services when each agent is already a Nix package and does not need its own container boundary. This is the simplest way to let one NixOS configuration describe users, services, resource controls, directories, and networking.

### Agents as Podman containers inside NixOS

Keep `virtualisation.podman.enable = true` and choose one declarative interface:

- NixOS `virtualisation.oci-containers` with `backend = "podman"` for system-level containers;
- raw Podman Quadlets under the appropriate rootful or rootless Quadlet path;
- later, a reviewed third-party Quadlet Nix module if its behavior is preferable.

Start with the built-in NixOS `virtualisation.oci-containers` module or raw Quadlets rather than combining several container abstractions at once. Rootful system containers and per-agent rootless containers have different security and lifecycle tradeoffs; do not migrate between them accidentally.

Even inside the VM:

- keep agent data in explicit guest volumes/directories;
- keep secrets out of the Nix store and image layers;
- avoid mounting the host filesystem into the guest;
- do not pass the host Podman or libvirt socket through;
- use private virtual networks and loopback bindings until exposure is intentional;
- set CPU, memory, PID, and restart limits;
- back up mutable hive state independently of `/nix/store`.

## 12. Optional: Nix's fast `build-vm` test loop

The persistent libvirt VM should be the operational machine. Separately, Nix can build an ephemeral QEMU VM directly from a NixOS configuration. This is useful on either Fedora or Ubuntu for testing the configuration before applying it to the persistent guest.

From a flake containing `nixosConfigurations.nixos-hive`:

```bash
nix build \
  .#nixosConfigurations.nixos-hive.config.system.build.vm
./result/bin/run-nixos-hive-vm
```

For a headless run with host port 2222 forwarded to guest SSH:

```bash
QEMU_NET_OPTS="hostfwd=tcp:127.0.0.1:2222-:22" \
QEMU_KERNEL_PARAMS="console=ttyS0" \
  ./result/bin/run-nixos-hive-vm -nographic
```

The NixOS module can give the test VM more resources without changing the real-machine configuration:

```nix
virtualisation.vmVariant = {
  virtualisation = {
    memorySize = 8192;
    cores = 4;
  };
};
```

This `build-vm` runner is not managed by libvirt, and its local qcow2 state can retain old users/data between runs. It is a test harness, not a replacement for the persistent VM, lifecycle management, backups, or the libvirt network.

## 13. Troubleshooting checklist

### `virt-host-validate` says KVM is unavailable

- Check BIOS/UEFI VT-x or AMD-V/SVM.
- Check `/dev/kvm` and `kvm_intel`/`kvm_amd`.
- If the host is a VM, enable nested virtualization in the outer hypervisor.
- Verify the account's `kvm` group membership after a full logout/login.

### `virsh` cannot connect

- Always specify `--connect qemu:///system` while diagnosing; desktop tools may otherwise choose a session connection.
- On Fedora inspect `virtqemud.socket` and `journalctl -u virtqemud`.
- On Ubuntu inspect `libvirtd` and `journalctl -u libvirtd`.
- Do not solve socket errors by making libvirt sockets world-writable.

### The default network is missing or inactive

- Check `virsh --connect qemu:///system net-list --all`.
- Install/repair the distro's libvirt network configuration package.
- Check `virtnetworkd` on Fedora or `libvirtd` on Ubuntu.
- Check host firewall logs rather than disabling the firewall.

### QEMU cannot read the ISO or disk

- Use `/var/lib/libvirt/images` for system-libvirt media.
- On Fedora run `restorecon` instead of disabling SELinux.
- On Ubuntu keep AppArmor enabled and use its libvirt-supported paths.
- Confirm file and directory traversal permissions.

### The serial console is blank

- Use the ISO's serial-console boot entry.
- Confirm the VM has a serial PTY.
- Retain the `console=ttyS0,115200n8` guest kernel parameter.
- Use local SPICE/virt-viewer for installation if the ISO/UEFI menu is not visible on serial; do not expose unauthenticated VNC on `0.0.0.0`.

### The VM boots the installer again

- Power it off and eject/remove the virtual CD-ROM.
- Confirm the qcow2 disk is first in the persistent boot order.

### The guest has no network

- Confirm its NIC is attached to libvirt network `default` with model VirtIO.
- Confirm the network is active and DHCP has leases.
- Inspect `ip address`, `ip route`, and `systemctl status dhcpcd` inside NixOS.
- Do not immediately replace NAT with a host bridge; isolate the simpler failure first.

### Builds consume too much disk

- Inspect `df -h / /nix` and `nix path-info -Sh /run/current-system`.
- Preserve working generations before collecting garbage.
- Increase the qcow2 virtual size and then grow the guest partition/filesystem in a planned maintenance step.
- For a serious hive, consider a separate virtual disk for agent data so OS rollback and data backup have clearer boundaries.

## 14. Proposed adoption sequence

1. Install KVM/libvirt tools on the host and validate `/dev/kvm`.
2. Start the default NAT network.
3. Download and verify the NixOS ISO.
4. Create the VM with either virt-manager or `virt-install`.
5. Install the minimal flake-pinned NixOS configuration.
6. Verify serial console, SSH, clean shutdown, and guest-agent reporting.
7. Commit the guest's `/etc/nixos` configuration and lock file to a private/reviewed repository.
8. Make a powered-off known-good clone or cold backup.
9. Add one native service or one Podman workload—not the entire agent hive.
10. Exercise NixOS `build`, `test`, `switch`, boot-generation rollback, and VM restoration.
11. Add the coordinator and workers with explicit resource and authority boundaries.
12. Enable host autostart only after shutdown and recovery behavior is understood.

## Primary references

- [NixOS 26.05 manual: installation and administration](https://nixos.org/manual/nixos/stable/) — UEFI partitioning, `nixos-generate-config`, flake installation, user passwords, `nixos-rebuild`, rollback, and `build-vm`.
- [NixOS downloads](https://nixos.org/download/) — current stable installer images and checksums.
- [Ubuntu libvirt documentation](https://ubuntu.com/server/docs/how-to/virtualisation/libvirt/) — KVM checks, packages, system/session connections, NAT, AppArmor, and `virsh`.
- [Ubuntu virt-manager and virt-install documentation](https://ubuntu.com/server/docs/how-to/virtualisation/virtual-machine-manager/) — GUI and CLI lifecycle tooling.
- [Fedora virtualization package guidance](https://fedoraproject.org/wiki/Getting_started_with_virtualization) — Fedora virtualization group and KVM/libvirt setup.
- [Fedora modular libvirt daemon change](https://fedoraproject.org/wiki/Changes/LibvirtModularDaemons) — why current Fedora uses `virtqemud` and related daemons instead of monolithic `libvirtd`.
- [Upstream libvirt daemon documentation](https://libvirt.org/daemons.html) — modular sockets, services, and privilege implications.
- [Upstream `virt-install` manual](https://github.com/virt-manager/virt-manager/blob/main/man/virt-install.rst) — current CLI options and libosinfo behavior.
