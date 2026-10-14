# AGENTS.md

Guidance for AI agents and contributors working in this repository.

## Environment: AWS CloudShell (disk-space constraints)

This project is often worked on inside **AWS CloudShell**, where the home
directory (`/home/cloudshell-user`) has a hard **1 GB persistent-storage
quota**. This quota is enforced independently of what `df -h` reports for the
underlying overlay filesystem (which can show many GB free). When the quota is
hit, *every* write into home fails with `ENOSPC: no space left on device`,
even a one-byte file — which breaks `cdk synth`, `cdk deploy`, and `pip`.

To stay under the quota, follow these rules when running in CloudShell:

- **Do not create a `venv` under the home directory.** The documented `.venv`
  workflow in the README creates `./.venv`, which lands in home and consumes
  quota. In CloudShell, either skip the virtualenv entirely or create it under
  `/tmp` (ephemeral, not counted against the home quota), e.g.
  `python3 -m venv /tmp/kiro-venv && source /tmp/kiro-venv/bin/activate`.

- **Disable the download cache on all installs.** Always pass `--no-cache-dir`
  to pip so wheels are not cached in `~/.cache/pip`:

  ```bash
  pip install --no-cache-dir -r requirements.txt
  ```

- **Do not install Python packages into `~/.local`.** A plain
  `pip install --user ...` (or installing into the system Python's user-site)
  writes hundreds of MB into `~/.local/lib` and can single-handedly blow the
  quota. Prefer the `/tmp` venv above.

- **Reclaim space from regenerable caches** if you do hit `ENOSPC`. Safe to
  delete (fully regenerated on next use):
  - `~/.cache/pip`
  - `~/.cache/aws`

  Check usage with `du -sh /home/cloudshell-user/.[!.]* /home/cloudshell-user/* 2>/dev/null | sort -h | tail`.

- **Detecting CloudShell:** the home dir is `/home/cloudshell-user` and the
  `AWS_EXECUTION_ENV` env var typically contains `CloudShell`. When in doubt,
  assume the tight quota applies.

Outside CloudShell (no 1 GB home quota), the standard README workflow — a local
`.venv` with a normally-cached `pip install` — is fine.

## General notes

- The CDK CLI is provided globally (`cdk --version`); you do not need a
  project-local install of it.
- Prefer `cdk synth` to validate changes before `cdk deploy`.
