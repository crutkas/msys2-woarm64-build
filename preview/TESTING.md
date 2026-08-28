# Portable native ARM64 Git Bash preview

This preview is a coworker test bundle. It is not an installer and it is not
the final zero-x64 Git for Windows distribution. The payload evidence lists
every remaining x64 PE/CLR file. The native shell and Git smoke is stricter:
any observed x64 process or loaded module fails validation.

## Safety

- Test on Windows ARM64 in a new, empty directory.
- Do not extract over an installed Git or `C:\msys64`.
- Do not add the preview to machine or user `PATH`.
- Do not import registry settings or change the default Git association.
- Keep production repositories outside the preview directory.
- Rollback is deletion of the extracted preview directory and diagnostics ZIP.

## Extract and test

1. Verify the preview archive against the coordinator-provided SHA-256.
2. Extract it into a short private path such as `C:\arm64-git-preview`.
3. Open native ARM64 PowerShell 7 **as Administrator** without changing
   `PATH`. Elevation is used only for the kernel Process/ImageLoad ETW session;
   the harness does not install a service, change the registry, or retain the
   ETW session.
4. Run:

   ```powershell
   pwsh -NoProfile -File C:\arm64-git-preview\preview-evidence\tools\assembler\Validate-Arm64Preview.ps1 `
     -PortableRoot C:\arm64-git-preview `
     -EvidenceDirectory C:\arm64-git-preview-diagnostics
   ```

5. If validation succeeds or fails, collect the machine-readable evidence:

   ```powershell
   pwsh -NoProfile -File C:\arm64-git-preview\preview-evidence\tools\assembler\Collect-PreviewDiagnostics.ps1 `
     -PortableRoot C:\arm64-git-preview `
     -ValidationEvidencePath C:\arm64-git-preview-diagnostics\arm64-validation-evidence.v1.json `
     -OutputArchive C:\arm64-git-preview-diagnostics.zip
   ```

Send the diagnostics ZIP with a short description of the command and observed
behavior. Review it for repository paths or other sensitive strings before
sharing. Do not publish the bundle or diagnostics outside the approved
fork-local test group.

The validation entry point runs the pinned `Collect-Arm64EtwEvidence.ps1`
collector. Sampling `Process.Modules` is diagnostic only and cannot satisfy the
authoritative runtime gate. Missing ETW events, any lost-event count, an
incomplete descendant tree/module list, or x64 process/module evidence is red.
If ETW collection fails, raw traces remain in
`runtime-evidence.v1.json.diagnostics` inside the fresh evidence directory and
are included by the diagnostics collector. Collector and Runtime-validator
stdout/stderr logs are retained there as well. Pinned validation-tool binaries
are not duplicated into the diagnostics ZIP.
